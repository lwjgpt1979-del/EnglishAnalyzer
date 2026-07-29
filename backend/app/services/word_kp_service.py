"""单词考点(深挖):固定搭配 / 近义 / 反义 / 派生·同族 / 易混辨析 / 考法。
全关系型落库(vocab_word_kp 词根 + vocab_word_relation 关系图);近义/反义/派生/易混命中词库
时链 related_word_id(可点去学)。LLM 一次生成全局缓存,查看即生成 + prewarm。合并原词族。"""
from __future__ import annotations

import random
import re
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d5_learning import StudentVocabCandidate, VocabularyLearning, VocabularyWord
from datetime import datetime, timezone

from app.models.d18_vocab_kg import (
    VocabKpMcq, VocabKpMcqRevision, VocabWordKp, VocabWordKpReview, VocabWordRelation, VocabWordSense,
    VocabKpRelationReport,
)

# 受控可扩维度清单(动态考点):dim_key → (中文名, relational=项是否可链词, 适用词性提示)
# LLM 按词/词组的词性与特点,从中挑适用维度填充;新维度往这里加即可。
_DIM_REGISTRY: dict[str, tuple[str, bool, str]] = {
    # —— 可链词维(relational:项是英文词/词形,命中词库→可点去学)——
    "synonym": ("近义", True, "通用"),
    "antonym": ("反义", True, "通用"),
    "confusion": ("易混", True, "通用"),
    "ambiguity": ("歧义", True, "通用"),
    "derivation": ("派生·词族", True, "通用"),
    "tense": ("时态变化", True, "动词"),
    "plural": ("单复数", True, "名词"),
    "comparative": ("比较级·最高级", True, "形容词/副词"),
    # —— 文本维(text:项是用法/说明内容,不链词)——
    "collocation": ("固定搭配", False, "通用"),
    "transitivity": ("及物性", False, "动词"),
    "voice": ("语态", False, "动词"),
    "sentence_pattern": ("常见句型", False, "动词"),
    "countability": ("可数性", False, "名词"),
    "possessive": ("所有格", False, "名词"),
    "ed_ing": ("-ed/-ing 辨析", False, "形容词"),
    "prep_discrimination": ("介词辨析", False, "介词"),
    "usage": ("用法·位置", False, "词组/副词"),
    "semantic_focus": ("语义侧重", False, "词组/近义组"),
    "exam_tip": ("常见考法", False, "通用"),
}
_DIM_ORDER = list(_DIM_REGISTRY.keys())            # 展示顺序
_DIM_INDEX = {k: i for i, k in enumerate(_DIM_ORDER)}
_RELATIONAL_DIMS = {k for k, v in _DIM_REGISTRY.items() if v[1]}
_MORPH_DIMS = {"tense", "plural", "comparative"}   # 形态维:确定性生成,不进 LLM 菜单、禁止 LLM 覆盖
_MAX_TEST_DIMS = 8   # 考点扩展测试最多覆盖的维度数(控 LLM 输出/测试长度)


def _dim_label(key: str) -> str:
    return _DIM_REGISTRY.get(key, (key, False, ""))[0]


def _meaning_of(w: VocabularyWord) -> str:
    defs = w.definitions if isinstance(w.definitions, list) else []
    return " / ".join(str(d.get("meaning")) for d in defs
                      if isinstance(d, dict) and d.get("meaning"))[:120]


async def _gen_kp(word: str, meaning: str, examples, is_phrase: bool = False) -> dict:
    """LLM 先枚举该词/词组的主要义项,再为每个义项按词性/特点从受控清单动态挑维度出考点(fast 档)。
    形态维(tense/plural/comparative)不进菜单——由 morph/exchange 确定性覆盖。dev-mock 返回空。
    返回 {root, senses:[{gloss, pos, dims:[{key, items:[{text, zh, note}]}]}]}。"""
    from app.services.llm_provider import complete_json, fast_model, is_llm_dev_mode
    if is_llm_dev_mode():
        return {"root": "", "senses": []}
    tgt = "词组" if is_phrase else "单词"
    menu = "\n".join(f"- {k}({lbl},{'可链词' if rel else '文本'},适用:{pos})"
                     for k, (lbl, rel, pos) in _DIM_REGISTRY.items()
                     if k not in _MORPH_DIMS)
    system = (
        f"你是英语词汇考点专家。给定{tgt}+释义+例句:\n"
        f"1) 先枚举该{tgt}的**主要义项**(每个义项:中文义 gloss + 该义项词性 pos)。"
        "**给定释义仅供参考、可能不全**——请基于该词真实的常用义项列全,尤其功能词的**高频义项**"
        "(如 but 必须含『但是·转折·conj』,还有『除…外·prep』『只有·adv』;as / since / that 等同理);单义词就一个义项。\n"
        f"2) **为每个义项**,从下面【维度清单】里挑出真正适用于该义项词性与特点的维度(只挑适用的,数量不限),每维给 1-4 个考点项。\n"
        "【维度清单】dim_key(维度名,类型,适用词性)——**不含时态/单复数/比较级**(系统用词典词形表生成,勿输出):\n"
        + menu + "\n"
        "可链词维:项 text 填英文词(近义→近义词等);文本维:项 text 填该用法/考点的简明说明。\n"
        '严格输出 JSON:{"root":"词根/词干或空","senses":[{"gloss":"该义项中文义","pos":"verb|noun|adj|adv|prep|conj|phrase|其他",'
        '"dims":[{"key":"清单里的dim_key","items":[{"text":"词 或 说明","zh":"中文(可空)","note":"备注(可空)"}]}]}]}\n'
        "【质量硬规则·必须遵守】\n"
        f"① **可链词维的项必须是真实存在的英文词、且确与该义项相关**(近义/反义/派生/易混);"
        "不确定、生僻、或不常见的词**宁可不出**,绝不臆造英文词;\n"
        "② **维度必须匹配该义项词性**:名词别出及物性/语态,动词别出可数性,介词别出不适用维;\n"
        "③ **宁缺毋滥**:某维想不出可靠的项,就不出该维、也不硬凑到 4 项;\n"
        f"④ 考点按义项归属正确(转折义项不要混入除外义项的搭配);中文义准确;用词简单、不高于目标{tgt}难度。")
    d = await complete_json(
        system_prompt=system, user_prompt=f"{tgt}:{word}\n释义:{meaning}\n参考例句:{examples}\n返回 JSON:",
        max_tokens=3600, model=fast_model(), feature="vocab_word_kp",
        validate=lambda x: isinstance(x.get("senses"), list))
    return d or {"root": "", "senses": []}


def _clean_items(arr) -> list[dict]:
    """规整一个维度下的项:{text, zh, note}。text 必填。"""
    out = []
    for it in (arr or [])[:5]:
        if not isinstance(it, dict):
            continue
        text = str(it.get("text") or it.get("word") or it.get("en") or "").strip()
        if text:
            out.append({"text": text, "zh": str(it.get("zh") or "").strip(),
                        "note": str(it.get("note") or "").strip()})
    return out


# P3 语料印证:固定搭配以该词的 examples + phrases(源自教材/真题词频的真实内容)为准
_COLLOC_STOP = {"a", "an", "the", "to", "of", "in", "on", "at", "with", "for", "and", "or", "by",
                "sb", "sth", "one", "ones", "oneself", "do", "be", "is", "are", "have", "has",
                "that", "this", "your", "his", "her", "its", "not", "no"}


def _corpus_text(w) -> str:
    parts: list[str] = []
    for arr in (w.examples, w.phrases):
        if isinstance(arr, list):
            parts += [str(x.get("en") or "") for x in arr if isinstance(x, dict)]
    return " ".join(parts).lower()


def _collocate_words(colloc_en: str, word: str) -> list[str]:
    toks = re.findall(r"[a-z']+", (colloc_en or "").lower())
    return [t for t in toks if t != word.lower() and t not in _COLLOC_STOP and len(t) > 2]


def _corpus_grounding(w, senses: list) -> None:
    """① 词条 phrases 直接作高置信固定搭配(加到主义项);② LLM 搭配在 examples/phrases 语料里印证的升 source=corpus;
    ③ 同维内 corpus 项排前(P1 搭配 corpus 优先)。"""
    corpus = _corpus_text(w)
    for _g, _p, _s, sdims in senses:
        for key, items in sdims:
            if key != "collocation":
                continue
            for it in items:
                if it.get("source"):
                    continue
                cw = _collocate_words(it["text"], w.word)
                if cw and any(t in corpus for t in cw):
                    it["source"] = "corpus"
    phrases = [x for x in (w.phrases or []) if isinstance(x, dict) and str(x.get("en") or "").strip()]
    if phrases and senses:
        sdims = senses[0][3]
        col = next((its for k, its in sdims if k == "collocation"), None)
        if col is None:
            col = []
            sdims.append(("collocation", col))
        have = {str(it["text"]).lower() for it in col}
        for ph in phrases[:4]:
            en = str(ph["en"]).strip()
            if en.lower() not in have:
                col.append({"text": en, "zh": str(ph.get("zh") or "").strip(), "note": "", "source": "corpus"})
                have.add(en.lower())
    for _g, _p, _s, sdims in senses:
        for key, items in sdims:
            if key == "collocation" and items:
                items.sort(key=lambda it: 0 if it.get("source") == "corpus" else 1)


async def _exam_syllabus_words(db: AsyncSession) -> set[str]:
    """中考∪高考已上架考纲词库词面集合(小写)。无上架词库时返回空集(=不做过滤,避免误删)。"""
    from app.models.d18_vocab_kg import VocabListItem
    from app.services import vocab_list_service
    lids: list = []
    for lvl in ("junior", "senior"):
        lid = await vocab_list_service.resolve_word_list(db, exam_level=lvl)
        if lid:
            lids.append(lid)
    if not lids:
        return set()
    rows = (await db.execute(
        sa.select(sa.func.lower(VocabularyWord.word))
        .join(VocabListItem, VocabListItem.word_id == VocabularyWord.id)
        .where(VocabListItem.list_id.in_(lids)))).all()
    return {r[0] for r in rows if r[0]}


def _filter_syn_ant_by_syllabus(senses: list, syllabus: set[str]) -> None:
    """近义/反义考纲内过滤(P1):超纲叶子丢弃;syllabus 空则不滤。WordNet 确认的也须在考纲内(中高考优先)。"""
    if not syllabus:
        return
    for i, (gloss, pos, sort, sdims) in enumerate(senses):
        rebuilt = []
        for key, items in sdims:
            if key in ("synonym", "antonym"):
                items = [it for it in items if str(it.get("text") or "").strip().lower() in syllabus]
            if items:
                rebuilt.append((key, items))
        senses[i] = (gloss, pos, sort, rebuilt)


def _apply_morph_overlay(word: str, senses: list, exchange: str | None = None) -> list:
    """形态学打底:去掉 LLM 形态维,用 exchange/lemminflect 确定性覆盖(source=morph)。"""
    from app.services import morphology
    rebuilt = []
    for gloss, pos, sort, sdims in senses:
        sdims = [(k, its) for (k, its) in sdims if k not in _MORPH_DIMS]
        mp = morphology.forms_for_pos(word, pos or "", exchange=exchange)
        if mp and mp[1]:
            dim_key, forms = mp
            sdims.append((dim_key, [{"text": f, "zh": z, "note": "", "source": "morph"} for f, z in forms]))
        rebuilt.append((gloss, pos, sort, sdims))
    return rebuilt


async def _refresh_morph_relations(db: AsyncSession, *, word_id: uuid.UUID) -> None:
    """存量修补(P0):删掉形态维的 LLM 行,按义项 pos + ECDICT exchange 重写 morph 行。幂等。"""
    w = await db.get(VocabularyWord, word_id)
    if w is None or w.type == "phrase":
        return
    from app.services import morphology
    from app.services.vocab_definition_service import dict_lookup
    hit = await dict_lookup(db, w.word)
    exchange = (hit or {}).get("exchange") or None
    senses = (await db.execute(
        sa.select(VocabWordSense).where(VocabWordSense.word_id == word_id)
        .order_by(VocabWordSense.sort))).scalars().all()
    if not senses:
        return
    await db.execute(sa.delete(VocabWordRelation).where(
        VocabWordRelation.word_id == word_id,
        VocabWordRelation.relation.in_(list(_MORPH_DIMS)),
        VocabWordRelation.source == "llm"))
    vals: list[dict] = []
    for s in senses:
        mp = morphology.forms_for_pos(w.word, s.pos or "", exchange=exchange)
        if not mp or not mp[1]:
            continue
        dim_key, forms = mp
        # 清掉该义项旧 morph(再写入,便于 exchange 升级后刷新词形)
        await db.execute(sa.delete(VocabWordRelation).where(
            VocabWordRelation.word_id == word_id,
            VocabWordRelation.sense_id == s.id,
            VocabWordRelation.relation == dim_key,
            VocabWordRelation.source == "morph"))
        for f, z in forms:
            if f.lower() == w.word.lower():
                continue
            vals.append({"id": uuid.uuid4(), "word_id": word_id, "sense_id": s.id, "relation": dim_key,
                         "dim_label": _dim_label(dim_key), "sort": _DIM_INDEX.get(dim_key, 99),
                         "related_word_id": None, "related_text": f, "related_zh": z,
                         "note": None, "source": "morph"})
    if vals:
        await db.execute(pg_insert(VocabWordRelation).values(vals)
                         .on_conflict_do_nothing(index_elements=["word_id", "relation", "related_text"]))
    await db.commit()


async def ensure_word_kp(db: AsyncSession, *, word_id: uuid.UUID) -> None:
    """确保该词/词组考点已生成:有 kp 标记**且有考点**才跳过(仍刷新 morph 防 LLM 污染);
    有标记但零考点(旧版/生成失败残留)则重新生成。
    否则 LLM 动态挖义项+维度 → 落 vocab_word_sense + relation(每维每项一行)+ kp(词根)。"""
    if await db.get(VocabWordKp, word_id) is not None:
        has_content = (await db.execute(
            sa.select(VocabWordRelation.id).where(VocabWordRelation.word_id == word_id).limit(1))).first()
        if has_content:
            # P0:存量若形态维仍有 LLM 行 → 清掉并用 morph/exchange 重写;干净则跳过
            polluted = (await db.execute(
                sa.select(VocabWordRelation.id).where(
                    VocabWordRelation.word_id == word_id,
                    VocabWordRelation.relation.in_(list(_MORPH_DIMS)),
                    VocabWordRelation.source == "llm").limit(1))).first()
            if polluted:
                await _refresh_morph_relations(db, word_id=word_id)
            return
        # 有 kp 行但零考点 → 空壳,继续往下重新生成(kp 行 on_conflict 保留,补 sense/relation)
    w = await db.get(VocabularyWord, word_id)
    if w is None:
        return
    d = await _gen_kp(w.word, _meaning_of(w), w.examples or [], is_phrase=(w.type == "phrase"))
    # 规整义项 → 每义项的维度(只留清单内 dim_key;形态维即便 LLM 误出也丢弃)
    senses = []   # [(gloss, pos, sort, [(dim_key, items)])]
    for si, sense in enumerate(d.get("senses") or []):
        if not isinstance(sense, dict):
            continue
        gloss = str(sense.get("gloss") or "").strip()[:120]
        sdims = []
        for dim in (sense.get("dims") or []):
            if not isinstance(dim, dict):
                continue
            key = str(dim.get("key") or "").strip()
            items = _clean_items(dim.get("items"))
            if key in _DIM_REGISTRY and key not in _MORPH_DIMS and items:
                sdims.append((key, items))
        if gloss and sdims:
            senses.append((gloss, str(sense.get("pos") or "").strip()[:16] or None, si, sdims))
    # P0/P1 形态学打底:ECDICT exchange 优先 → lemminflect;覆盖 LLM 形态维
    exchange = None
    if w.type != "phrase":
        from app.services.vocab_definition_service import dict_lookup
        hit = await dict_lookup(db, w.word)
        exchange = (hit or {}).get("exchange") or None
        senses = _apply_morph_overlay(w.word, senses, exchange=exchange)
    # P2 WordNet 校验:LLM 出的近义/反义被 WordNet 确认的升为高置信(source=wordnet;不覆盖 morph)
    from app.services import lexical
    for _g, pos, _s, sdims in senses:
        for key, items in sdims:
            if key not in ("synonym", "antonym"):
                continue
            for it in items:
                if not it.get("source") and lexical.confirm(w.word, pos or "", key, it["text"]):
                    it["source"] = "wordnet"
    # P1 近义/反义考纲内过滤(中考∪高考上架词库)
    _filter_syn_ant_by_syllabus(senses, await _exam_syllabus_words(db))
    # P3 语料印证固定搭配:词条 phrases 直接作高置信搭配;LLM 搭配能在 examples/phrases 语料里印证的升高
    _corpus_grounding(w, senses)
    senses = [s for s in senses if s[3]]  # 过滤后无维度的义项丢弃
    # 可链词维:批量查 related_text 是否在词库,填 related_word_id
    link_texts = [it["text"] for _g, _p, _s, sdims in senses
                  for key, items in sdims if key in _RELATIONAL_DIMS for it in items]
    id_by_text: dict = {}
    lows = list({t.lower() for t in link_texts if t})
    if lows:
        rows = (await db.execute(
            sa.select(VocabularyWord.id, VocabularyWord.word)
            .where(sa.func.lower(VocabularyWord.word).in_(lows)))).all()
        id_by_text = {ww.lower(): wid for wid, ww in rows}
    vals: list[dict] = []
    for gloss, pos, sort, sdims in senses:
        sense_id = uuid.uuid4()
        db.add(VocabWordSense(id=sense_id, word_id=word_id, gloss_zh=gloss, pos=pos, sort=sort))
        for key, items in sdims:
            relational = key in _RELATIONAL_DIMS
            for it in items:
                t = it["text"]
                if relational and t.lower() == w.word.lower():
                    continue   # 不自指
                vals.append({"id": uuid.uuid4(), "word_id": word_id, "sense_id": sense_id, "relation": key,
                             "dim_label": _dim_label(key), "sort": _DIM_INDEX.get(key, 99),
                             "related_word_id": id_by_text.get(t.lower()) if relational else None,
                             "related_text": t, "related_zh": it.get("zh") or None,
                             "note": it.get("note") or None, "source": it.get("source") or "llm"})
    await db.flush()   # 落 sense 行(供 relation FK)
    if vals:
        await db.execute(pg_insert(VocabWordRelation).values(vals)
                         .on_conflict_do_nothing(index_elements=["word_id", "relation", "related_text"]))
    await db.execute(pg_insert(VocabWordKp)
                     .values(word_id=word_id, root=(str(d.get("root") or "")[:64] or None))
                     .on_conflict_do_nothing(index_elements=["word_id"]))
    await db.commit()


def _dims_from_rows(rows: list, seed_ids: list) -> list[dict]:
    """一组 relation 行 → 动态维度 dims_out(按 registry 顺序);收集可链词 seed_ids。
    形态维若已有 morph 则隐藏同维 LLM 行(P0 展示层加固)。"""
    by_dim: dict = {}
    for r in rows:
        by_dim.setdefault(r.relation, []).append(r)
    dims_out = []
    for key in sorted(by_dim.keys(), key=lambda k: _DIM_INDEX.get(k, 99)):
        relational = key in _RELATIONAL_DIMS
        dim_rows = by_dim[key]
        if key in _MORPH_DIMS and any(getattr(r, "source", "llm") == "morph" for r in dim_rows):
            dim_rows = [r for r in dim_rows if getattr(r, "source", "llm") == "morph"]
        # 搭配:corpus 排前(与落库序一致,展示层再保一次)
        if key == "collocation":
            dim_rows = sorted(dim_rows, key=lambda r: 0 if getattr(r, "source", "") == "corpus" else 1)
        items = []
        for r in dim_rows:
            wid = str(r.related_word_id) if r.related_word_id else None
            src = getattr(r, "source", "llm") or "llm"
            # 置信度(P0 收紧):
            # · 形态/WordNet/策展/语料 = 高;可链词命中词库 = 高;纯 LLM = 低
            # · 固定搭配:corpus = 高;纯 LLM = 低
            # · 其它文本维 = 高
            if relational:
                confidence = "high" if (src in ("morph", "wordnet", "curated") or wid) else "low"
            elif key == "collocation":
                confidence = "high" if src == "corpus" else "low"
            else:
                confidence = "high"
            items.append({"id": str(r.id), "text": r.related_text, "zh": r.related_zh or "", "note": r.note or "",
                          "word_id": wid, "confidence": confidence, "source": src})
            if relational and r.related_word_id:
                seed_ids.append(r.related_word_id)
        dims_out.append({"key": key, "label": (by_dim[key][0].dim_label or _dim_label(key)),
                         "relational": relational, "items": items})
    return dims_out


async def word_kp_out(db: AsyncSession, *, word_id: uuid.UUID, sense_id: uuid.UUID | None = None,
                      student_id: uuid.UUID | None = None) -> dict:
    """考点全套(按义项分组):`senses:[{sense_id,gloss,pos,dims:[...]}]`;可链词维的项命中词库带 word_id(可点去学)。
    传 sense_id 只返回该义项;兼容字段 `dims` = 选定义项(或主义项)的维度(供未升级前端/考点测试)。
    传 student_id 则把在库未学的相关词加入候选池。"""
    await ensure_word_kp(db, word_id=word_id)
    kp = await db.get(VocabWordKp, word_id)
    senses = (await db.execute(
        sa.select(VocabWordSense).where(VocabWordSense.word_id == word_id)
        .order_by(VocabWordSense.sort))).scalars().all()
    rows = (await db.execute(
        sa.select(VocabWordRelation).where(
            VocabWordRelation.word_id == word_id,
            VocabWordRelation.hidden_at.is_(None)))).scalars().all()
    by_sense: dict = {}
    for r in rows:
        by_sense.setdefault(r.sense_id, []).append(r)
    seed_ids: list = []
    senses_out = []
    for s in senses:
        senses_out.append({"sense_id": str(s.id), "gloss": s.gloss_zh, "pos": s.pos or "",
                           "dims": _dims_from_rows(by_sense.get(s.id, []), seed_ids)})
    # 存量/无义项 relation(sense_id=None)→ 归到"综合"义项兜底
    if by_sense.get(None):
        senses_out.append({"sense_id": None, "gloss": "综合", "pos": "",
                           "dims": _dims_from_rows(by_sense[None], seed_ids)})
    if student_id is not None and seed_ids:
        await _seed_queue(db, student_id=student_id, word_ids=list(set(seed_ids)))

    # 选定义项(sense_id 命中,否则主义项)→ 兼容 dims
    chosen = None
    if sense_id is not None:
        chosen = next((s for s in senses_out if s["sense_id"] == str(sense_id)), None)
    chosen = chosen or (senses_out[0] if senses_out else None)
    out_senses = [chosen] if sense_id is not None and chosen else senses_out
    return {"root": (kp.root if kp else "") or "", "senses": out_senses,
            "gloss": chosen["gloss"] if chosen else "", "pos": chosen["pos"] if chosen else "",
            "dims": chosen["dims"] if chosen else []}


async def _seed_queue(db: AsyncSession, *, student_id: uuid.UUID, word_ids: list) -> None:
    """在库、未学的相关词加入候选池 → 提前进新词队列(先验)。幂等。"""
    learned = set((await db.execute(
        sa.select(VocabularyLearning.word_id)
        .where(VocabularyLearning.student_id == student_id))).scalars().all())
    todo = [wid for wid in word_ids if wid not in learned]
    if not todo:
        return
    await db.execute(
        pg_insert(StudentVocabCandidate)
        .values([{"id": uuid.uuid4(), "student_id": student_id, "word_id": wid, "source": "kp"}
                 for wid in todo])
        .on_conflict_do_nothing(index_elements=["student_id", "word_id"]))
    await db.commit()


# ---------------- 考点扩展测试(每维 3 题,随机取 1 组合) ----------------

def _kp_content_lines(kp: dict) -> list[tuple[str, str, str]]:
    """从动态维度 kp['dims'] 整理成 (dim_key, dim_label, 供出题的内容文本) —— 只保留有项的维度。"""
    lines: list[tuple[str, str, str]] = []
    for dim in (kp.get("dims") or []):
        # P4:只用高置信项出题(过滤掉 LLM 造的、没命中词库的可疑关系词)→ 学生做的题都基于真实内容
        items = [it for it in (dim.get("items") or []) if it.get("confidence") != "low"]
        if not items:
            continue   # 该维过滤后无高置信项 → 不为该维出题
        txt = "; ".join(
            it["text"] + (f"({it['zh']})" if it.get("zh") else "") + (f"[{it['note']}]" if it.get("note") else "")
            for it in items)
        lines.append((dim["key"], dim.get("label") or _dim_label(dim["key"]), txt))
    return lines


async def _gen_kp_mcqs(word: str, meaning: str, kp: dict, is_phrase: bool = False) -> list[dict]:
    """LLM 一次为每个「有内容的动态考点维度」各出 3 道单选(fast 档);目标可为单词或词组。dev-mock 返回空。"""
    from app.services.llm_provider import complete_json, fast_model, is_llm_dev_mode
    if is_llm_dev_mode():
        return []
    lines = _kp_content_lines(kp)[:_MAX_TEST_DIMS]   # 上限维度数:控输出/测试长度(按 registry 序取核心维)
    if not lines:
        return []
    tgt = "词组" if is_phrase else "单词"
    dims_desc = "\n".join(f"- {key}({label}): {txt}" for key, label, txt in lines)
    system = (
        f"你是英语词汇考点命题专家。给定目标{tgt}及其**各动态考点维度**的内容,**为下面列出的每个维度各出 3 道单选题**。\n"
        "每道题要**真正考该维度指向的知识点**(维度名点明考什么),例如:\n"
        "- 时态变化/单复数/比较级/派生 → 挖空句选正确的词形/时态/单复数/级/派生形式;\n"
        "- 可数性/所有格 → 考冠词、单复数、of/'s 所有格的正确用法;\n"
        "- 及物性/语态/常见句型 → 给句子选是否接宾语/主被动/句型正确的一项;\n"
        "- 固定搭配 → 挖空选正确搭配词/介词;近义/易混/歧义 → 语境中选最贴切/区分易混项;\n"
        "- 介词辨析/用法·位置/语义侧重/常见考法 → 结合语境考该维度的具体用法。\n"
        "严格输出 JSON:{\"items\":[{\"dimension\":\"上面给的维度 key(英文)\",\"stem\":\"题干\",\n"
        "\"options\":[\"4个选项\"],\"answer\":\"正确项(必须与 options 之一完全一致)\",\"explanation\":\"中文解析\"}]}\n"
        "每维恰好 3 题、每题 4 个选项单选;dimension 只用上面给的 key,不臆造。\n"
        "**【解析语言·强制】explanation 一律用中文**——即使题干/选项/单词是英文,解析也必须是中文,讲清正确项为什么对、其它选项为什么错。\n"
        "【质量硬规则·必须遵守】① **答案唯一**:题干在语境下只有一个正确项;② **每个干扰项都要明确是错的**——"
        "不能也讲得通、不能与正确答案同义或都成立(如考『过去能够』时,别把『was unable to』这种相反却也合语法的项当干扰);"
        "③ 题干无歧义、信息足以锁定唯一答案;④ 维度名要真考该维关系(反义题就考反义区分,不要退化成普通填空);"
        "⑤ explanation 说清为什么这个对、其它为什么错。\n"
        f"【用词要简单】题干句里除目标{tgt}与考点词(选项中的词)外,其余单词一律用简单常见词、"
        f"难度不高于目标{tgt},不要用更生僻的词做句子载体——避免学生被句中难词绊住、学不到考点。")
    d = await complete_json(
        system_prompt=system,
        user_prompt=f"目标{tgt}:{word}\n释义:{meaning}\n各维度内容:\n{dims_desc}\n返回 JSON:",
        max_tokens=3000, model=fast_model(), feature="vocab_kp_mcq",
        validate=lambda x: isinstance(x.get("items"), list) and len(x.get("items")) >= 1)
    return (d or {}).get("items") or []


def _eff_sense(kp: dict) -> uuid.UUID | None:
    """word_kp_out 结果里的选定义项 id(sense_id 或主义项);None=无义项(综合)。"""
    ss = kp.get("senses") or []
    sid = ss[0]["sense_id"] if ss else None
    return uuid.UUID(sid) if sid else None


async def ensure_kp_mcqs(db: AsyncSession, *, word_id: uuid.UUID, sense_id: uuid.UUID | None = None) -> None:
    """确保某义项的考点测试题已生成:该义项已有题直接返回;否则按该义项维度 LLM 出题落库(带 sense_id)。"""
    await ensure_word_kp(db, word_id=word_id)          # FK 依赖 vocab_word_kp 行 + 需考点内容出题
    if await db.get(VocabWordKp, word_id) is None:
        return
    kp = await word_kp_out(db, word_id=word_id, sense_id=sense_id)   # 选定义项的维度
    eff = _eff_sense(kp)
    q = sa.select(VocabKpMcq.id).where(VocabKpMcq.word_id == word_id)
    q = q.where(VocabKpMcq.sense_id == eff) if eff else q.where(VocabKpMcq.sense_id.is_(None))
    if (await db.execute(q.limit(1))).first():
        return
    w = await db.get(VocabularyWord, word_id)
    if w is None:
        return
    gen = await _gen_kp_mcqs(w.word, _meaning_of(w), kp, is_phrase=(w.type == "phrase"))
    objs = []
    for g in gen:
        if not isinstance(g, dict):
            continue
        opts = [str(o).strip() for o in (g.get("options") or []) if str(o).strip()]
        ans = str(g.get("answer") or "").strip()
        dim = str(g.get("dimension") or "").strip()
        stem = str(g.get("stem") or "").strip()
        if dim not in _DIM_REGISTRY or len(opts) < 2 or ans not in opts or not stem:
            continue                                    # 缺项/维度非法即丢弃,不硬塞
        objs.append(VocabKpMcq(id=uuid.uuid4(), word_id=word_id, sense_id=eff, dimension=dim, stem=stem,
                               options=opts, answer=ans, explanation=g.get("explanation") or None))
    if objs:
        db.add_all(objs)
        await db.commit()


async def kp_mcq_test(db: AsyncSession, *, word_id: uuid.UUID, sense_id: uuid.UUID | None = None,
                      dim: str | None = None) -> list[dict]:
    """考点扩展测试(限定义项):确保该义项题库 → 每个有题的维度随机取 1 道 → 按维度顺序组合返回。
    传 dim 则「重练该维」:只出该维的一套题(最多 4 道,优先未被报错)。"""
    await ensure_kp_mcqs(db, word_id=word_id, sense_id=sense_id)
    eff = _eff_sense(await word_kp_out(db, word_id=word_id, sense_id=sense_id))
    q = sa.select(VocabKpMcq).where(VocabKpMcq.word_id == word_id)
    q = q.where(VocabKpMcq.sense_id == eff) if eff else q.where(VocabKpMcq.sense_id.is_(None))
    if dim:
        q = q.where(VocabKpMcq.dimension == dim)
    rows = (await db.execute(q)).scalars().all()
    by_dim: dict = {}
    for r in rows:
        by_dim.setdefault(r.dimension, []).append(r)
    out = []
    if dim:   # 重练该维:出该维一套(优先未报错)
        rs = sorted(by_dim.get(dim, []), key=lambda r: r.report_count)[:4]
        return [{"id": str(m.id), "dimension": dim, "dimension_label": _dim_label(dim),
                 "stem": m.stem, "options": m.options, "answer": m.answer,
                 "explanation": m.explanation or ""} for m in rs]
    for d in sorted(by_dim.keys(), key=lambda k: _DIM_INDEX.get(k, 99)):
        rs = by_dim.get(d)
        if rs:
            m = random.choice([r for r in rs if r.report_count == 0] or rs)   # 优先未被报错的题
            out.append({"id": str(m.id), "dimension": d, "dimension_label": _dim_label(d),
                        "stem": m.stem, "options": m.options, "answer": m.answer,
                        "explanation": m.explanation or ""})
    return out


def _mcq_out(m: VocabKpMcq) -> dict:
    return {"id": str(m.id), "dimension": m.dimension, "dimension_label": _dim_label(m.dimension),
            "stem": m.stem, "options": m.options, "answer": m.answer, "explanation": m.explanation or ""}


async def swap_kp_mcq(db: AsyncSession, *, mcq_id: uuid.UUID) -> dict | None:
    """学生「换一题」= 报错该题(report_count++,供后台复核)+ 返回同 词/义项/维度 的另一道
    (优先未报错;该维仅此一道则重生成该词该义项题库)。"""
    m = await db.get(VocabKpMcq, mcq_id)
    if m is None:
        return None
    m.report_count = (m.report_count or 0) + 1   # ≥阈值即"待修";AI 审校修正由低峰 cron 批量做(fix_kp_mcqs 任务)
    await db.commit()

    async def _others():
        cond = [VocabKpMcq.word_id == m.word_id, VocabKpMcq.dimension == m.dimension, VocabKpMcq.id != m.id]
        cond.append(VocabKpMcq.sense_id == m.sense_id if m.sense_id else VocabKpMcq.sense_id.is_(None))
        return (await db.execute(sa.select(VocabKpMcq).where(*cond))).scalars().all()

    others = await _others()
    pool = [o for o in others if o.report_count == 0] or others
    if not pool:
        # 该维仅此一道(且已报错)→ 重生成该词该义项题库(先删,绕过 ensure 幂等)
        cond = [VocabKpMcq.word_id == m.word_id]
        cond.append(VocabKpMcq.sense_id == m.sense_id if m.sense_id else VocabKpMcq.sense_id.is_(None))
        await db.execute(sa.delete(VocabKpMcq).where(*cond))
        await db.commit()
        await ensure_kp_mcqs(db, word_id=m.word_id, sense_id=m.sense_id)
        pool = await _others()
    return _mcq_out(random.choice(pool)) if pool else None


# ---------------- 考点题·AI 修正 + 复核(阈值可配 + 修改记录) ----------------

_REPORT_THRESHOLD_KEY = "kp_mcq_report_threshold"
_REPORT_THRESHOLD_DEFAULT = 3


async def get_report_threshold(db: AsyncSession) -> int:
    """报错阈值(≥该值触发 AI 自动修正)。运营可配 system_configs.kp_mcq_report_threshold,缺省 3。"""
    from app.models.d9_system import SystemConfig
    cfg = (await db.execute(
        sa.select(SystemConfig).where(SystemConfig.key == _REPORT_THRESHOLD_KEY))).scalar_one_or_none()
    if cfg is not None and isinstance(cfg.value, dict):
        try:
            return max(1, int(cfg.value.get("threshold", _REPORT_THRESHOLD_DEFAULT)))
        except (ValueError, TypeError):
            pass
    return _REPORT_THRESHOLD_DEFAULT


async def set_report_threshold(db: AsyncSession, *, threshold: int, updated_by: uuid.UUID | None = None) -> int:
    from app.models.d9_system import SystemConfig
    t = max(1, int(threshold))
    cfg = (await db.execute(
        sa.select(SystemConfig).where(SystemConfig.key == _REPORT_THRESHOLD_KEY))).scalar_one_or_none()
    if cfg is None:
        db.add(SystemConfig(id=uuid.uuid4(), key=_REPORT_THRESHOLD_KEY, value={"threshold": t},
                            description="考点题报错阈值(≥该值 AI 自动修正)", updated_by=updated_by))
    else:
        cfg.value = {"threshold": t}
        cfg.updated_by = updated_by
    await db.commit()
    return t


def _mcq_snapshot(m: VocabKpMcq) -> dict:
    return {"stem": m.stem, "options": m.options, "answer": m.answer,
            "explanation": m.explanation, "report_count": m.report_count}


async def _gen_fix_mcq(word: str, meaning: str, dim_key: str, mcq: dict) -> dict | None:
    """LLM 审校并修正一道被学生反馈有问题的考点题(改正答案/解析/必要干扰项;维度不变)。
    用**推理档**(审校要多步判断答案唯一性/干扰项是否也成立);由低峰 cron 批量调用省钱。"""
    from app.services.llm_provider import complete_json, is_llm_dev_mode
    if is_llm_dev_mode():
        return None
    system = (
        f"你是英语考点命题审校专家。下面这道单选题(维度:{_dim_label(dim_key)},目标词:{word})被学生反馈**有问题**"
        "(可能:答案不唯一/题干有歧义/某个干扰项也讲得通/答案或解析本身错)。请**审校并修正**:\n"
        "① 确保答案唯一正确;② 每个干扰项都明确是错的(不能也成立/同义);③ 题干无歧义、信息足以锁定唯一答案;"
        "④ 维度不变、仍真考该维;⑤ 解析说清为什么对、其它为什么错。若原题基本可用只需微调,大问题可重写题干/选项。\n"
        "**explanation 一律用中文**(即使题干/选项是英文)。\n"
        '严格输出 JSON:{"stem":"题干","options":["4个选项"],"answer":"正确项(必须与 options 之一完全一致)","explanation":"中文解析"}')
    import json as _json
    d = await complete_json(
        system_prompt=system,
        user_prompt=f"目标词:{word}({meaning})\n原题:{_json.dumps(mcq, ensure_ascii=False)}\n返回修正后 JSON:",
        max_tokens=3000, feature="vocab_kp_mcq_fix",   # 不传 model → 主推理模型(深度思考);推理需更大 token
        validate=lambda x: isinstance(x.get("options"), list) and str(x.get("answer") or "").strip())
    if not d:
        return None
    opts = [str(o).strip() for o in (d.get("options") or []) if str(o).strip()]
    ans = str(d.get("answer") or "").strip()
    stem = str(d.get("stem") or "").strip()
    if len(opts) < 2 or ans not in opts or not stem:
        return None
    return {"stem": stem, "options": opts, "answer": ans, "explanation": str(d.get("explanation") or "").strip() or None}


async def fix_kp_mcq(db: AsyncSession, *, mcq_id: uuid.UUID, trigger: str = "manual",
                     by_admin_id: uuid.UUID | None = None) -> dict | None:
    """AI 修正一道考点题:审校改正 → 更新题 + report_count 归 0 + 记 revision(before/after)。返回修正后题或 None。"""
    m = await db.get(VocabKpMcq, mcq_id)
    if m is None:
        return None
    w = await db.get(VocabularyWord, m.word_id)
    before = _mcq_snapshot(m)
    fixed = await _gen_fix_mcq(w.word if w else "", _meaning_of(w) if w else "", m.dimension,
                               {k: before[k] for k in ("stem", "options", "answer", "explanation")})
    if not fixed:
        return None
    m.stem, m.options, m.answer, m.explanation = fixed["stem"], fixed["options"], fixed["answer"], fixed["explanation"]
    m.report_count = 0   # 已修正,清报错计数
    db.add(VocabKpMcqRevision(id=uuid.uuid4(), mcq_id=m.id, before=before, after=_mcq_snapshot(m),
                              trigger=trigger, by_admin_id=by_admin_id, reason="AI 审校修正"))
    await db.commit()
    return _mcq_out(m)


async def fix_pending_kp_mcqs(db: AsyncSession, *, limit: int = 100) -> dict:
    """低峰批量:扫报错数 ≥ 阈值的考点题,逐题 AI 审校修正(推理档)。供 crontab 低峰调用。
    修好即 report_count 归 0(下轮不再扫);逐题独立 try,失败不阻断其余。"""
    import logging
    threshold = await get_report_threshold(db)
    ids = (await db.execute(
        sa.select(VocabKpMcq.id).where(VocabKpMcq.report_count >= threshold)
        .order_by(VocabKpMcq.report_count.desc()).limit(limit))).scalars().all()
    stat = {"pending": len(ids), "fixed": 0, "failed": 0}
    for mid in ids:
        try:
            r = await fix_kp_mcq(db, mcq_id=mid, trigger="auto")
            stat["fixed" if r else "failed"] += 1
        except Exception:  # noqa: BLE001
            await db.rollback()
            stat["failed"] += 1
            logging.getLogger(__name__).exception("auto fix kp_mcq failed id=%s", mid)
    return stat


# ---------------- 考点 AI 自审校(P5·推理档·低峰批量) ----------------

# 只审"LLM 写的用法/考法类文本维"(可链维已 morph/wordnet/词库背书、搭配已 P3 语料印证,不重审)
_REVIEW_DIMS = ("transitivity", "voice", "sentence_pattern", "countability", "possessive",
                "ed_ing", "prep_discrimination", "usage", "semantic_focus", "exam_tip")


async def _review_kp_rows(word: str, rows: list, sense_gloss: dict) -> dict | None:
    """推理档审校:逐条判断考点是否正确/准确/归属义项无误 → {delete:[id], fix:[{id,text,zh,note}]}。dev-mock 返回 None。"""
    from app.services.llm_provider import complete_json, is_llm_dev_mode
    if is_llm_dev_mode():
        return None
    listing = "\n".join(
        f"[{r.id}] 义项:{sense_gloss.get(r.sense_id, '')} 【{_dim_label(r.relation)}】{r.related_text}"
        + (f"({r.related_zh})" if r.related_zh else "") + (f" 备注:{r.note}" if r.note else "")
        for r in rows)
    system = (
        f"你是英语词汇考点审校专家(请用推理仔细判断)。下面是单词『{word}』各义项下的『用法/考法类』考点(带 id)。"
        "**逐条**审校每条是否正确、准确、归属义项无误:\n"
        "① 明显错误 / 张冠李戴 / 与该义项不符 → 放入 delete;\n"
        "② 基本对但表述不准 / 中文有误 → 放入 fix,给出修正后的 text/zh/note;\n"
        "③ 正确无误的不用列。\n"
        '严格输出 JSON:{"delete":["id",...],"fix":[{"id":"要改的id","text":"修正题面","zh":"修正中文","note":"备注(可空)"}]}')
    d = await complete_json(
        system_prompt=system, user_prompt=f"考点条目:\n{listing}\n返回 JSON:",
        max_tokens=4000, feature="vocab_kp_review",   # 不传 model → 主推理模型(留足推理+JSON)
        validate=lambda x: isinstance(x, dict))
    return d


async def review_kp(db: AsyncSession, *, word_id: uuid.UUID) -> dict:
    """AI 审校一个词的用法/考法类考点:删错项 / 改正 → 置 reviewed_at + 记 review(before/after)。"""
    kprow = await db.get(VocabWordKp, word_id)
    if kprow is None:
        return {"reviewed": False}
    rows = (await db.execute(
        sa.select(VocabWordRelation).where(
            VocabWordRelation.word_id == word_id,
            VocabWordRelation.relation.in_(_REVIEW_DIMS)))).scalars().all()
    if not rows:
        kprow.reviewed_at = datetime.now(timezone.utc)
        await db.commit()
        return {"reviewed": True, "no_content": True}
    w = await db.get(VocabularyWord, word_id)
    sense_gloss = {s.id: s.gloss_zh for s in (await db.execute(
        sa.select(VocabWordSense).where(VocabWordSense.word_id == word_id))).scalars().all()}
    result = await _review_kp_rows(w.word if w else "", rows, sense_gloss)
    if result is None:
        return {"reviewed": False}   # LLM 失败/dev-mock:不标记,下轮再审
    before = [{"id": str(r.id), "dim": _dim_label(r.relation), "text": r.related_text,
               "zh": r.related_zh, "note": r.note} for r in rows]
    del_ids = {str(x) for x in (result.get("delete") or [])}
    fixes = {str(f.get("id")): f for f in (result.get("fix") or []) if isinstance(f, dict) and f.get("id")}
    deleted, fixed = [], []
    for r in rows:
        rid = str(r.id)
        if rid in del_ids:
            await db.delete(r)
            deleted.append(rid)
        elif rid in fixes:
            f = fixes[rid]
            r.related_text = (str(f.get("text") or "").strip() or r.related_text)
            r.related_zh = str(f.get("zh") or "").strip() or None
            r.note = str(f.get("note") or "").strip() or None
            fixed.append(rid)
    kprow.reviewed_at = datetime.now(timezone.utc)
    db.add(VocabWordKpReview(id=uuid.uuid4(), word_id=word_id, before=before,
                             after={"deleted": deleted, "fixed": fixed}))
    await db.commit()
    return {"reviewed": True, "deleted": len(deleted), "fixed": len(fixed)}


async def review_pending_kp(db: AsyncSession, *, limit: int = 100) -> dict:
    """低峰批量:扫未审校(reviewed_at 为空)的词考点,逐词 AI 审校。供 crontab 低峰调用。"""
    import logging
    ids = (await db.execute(
        sa.select(VocabWordKp.word_id).where(VocabWordKp.reviewed_at.is_(None)).limit(limit))).scalars().all()
    stat = {"pending": len(ids), "reviewed": 0, "failed": 0}
    for wid in ids:
        try:
            r = await review_kp(db, word_id=wid)
            stat["reviewed" if r.get("reviewed") else "failed"] += 1
        except Exception:  # noqa: BLE001
            await db.rollback()
            stat["failed"] += 1
            logging.getLogger(__name__).exception("review kp failed wid=%s", wid)
    return stat


# ---------------- 二期 AI 预隐(中考高频·近义/易混·只隐纯 LLM 行) ----------------

_PREHIDE_DIMS = ("synonym", "confusion")
_HIDE_NOTE_AI = "ai_prehide"


def _is_prehide_hideable(r: VocabWordRelation) -> bool:
    """可预隐:近义/易混 + source=llm + 未命中词库 + 未下架。"""
    return (r.relation in _PREHIDE_DIMS
            and (r.source or "llm") == "llm"
            and r.related_word_id is None
            and r.hidden_at is None)


async def _junior_high_freq_word_ids(db: AsyncSession, *, limit: int) -> list[uuid.UUID]:
    """中考已上架词库 star=3(高频)词 id,按 frequency/rank 优先,且 kp 未预隐、存在可隐 llm 近义/易混。"""
    from app.models.d18_vocab_kg import VocabListItem
    from app.services import vocab_list_service
    lid = await vocab_list_service.resolve_word_list(db, exam_level="junior")
    if lid is None:
        return []
    hideable = sa.exists(
        sa.select(VocabWordRelation.id).where(
            VocabWordRelation.word_id == VocabWordKp.word_id,
            VocabWordRelation.relation.in_(_PREHIDE_DIMS),
            VocabWordRelation.source == "llm",
            VocabWordRelation.related_word_id.is_(None),
            VocabWordRelation.hidden_at.is_(None)))
    rows = (await db.execute(
        sa.select(VocabWordKp.word_id)
        .join(VocabListItem, VocabListItem.word_id == VocabWordKp.word_id)
        .where(VocabListItem.list_id == lid,
               VocabListItem.star == 3,
               VocabWordKp.prehide_at.is_(None),
               hideable)
        .order_by(VocabListItem.frequency.desc().nullslast(),
                  VocabListItem.rank.asc().nullslast())
        .limit(limit))).scalars().all()
    return list(rows)


async def _gen_prehide_ids(word: str, rows: list, sense_gloss: dict,
                           hideable_ids: set[str]) -> list[str] | None:
    """推理档:返回应预隐的 id 列表(只应来自 hideable)。dev-mock/失败 → None。"""
    from app.services.llm_provider import complete_json, is_llm_dev_mode
    if is_llm_dev_mode():
        return None
    if not hideable_ids:
        return []
    listing = "\n".join(
        f"[{r.id}]{'[可隐]' if str(r.id) in hideable_ids else '[上下文]'}"
        f" 义项:{sense_gloss.get(r.sense_id, '')} 【{_dim_label(r.relation)}】"
        f"{r.related_text}" + (f"({r.related_zh})" if r.related_zh else "")
        + (f" source={r.source}" if r.source else "")
        for r in rows)
    system = (
        f"你是中考英语词汇审校专家。目标词『{word}』的近义/易混条目如下。"
        "标【可隐】的是纯 LLM 且未命中词库的项,可以建议预隐;"
        "标【上下文】的是词库命中/WordNet 等,只供对照,**禁止**放入 hide。\n"
        "只把**明显错误**的【可隐】项 id 放入 hide(不是近义、张冠李戴、易混配对荒谬);"
        "不确定就不要隐。\n"
        '严格输出 JSON:{"hide":["uuid",...]}')
    d = await complete_json(
        system_prompt=system, user_prompt=f"条目:\n{listing}\n返回 JSON:",
        max_tokens=2000, feature="vocab_kp_prehide",
        validate=lambda x: isinstance(x, dict) and isinstance(x.get("hide"), list))
    if not d:
        return None
    out = []
    for x in d.get("hide") or []:
        sid = str(x)
        if sid in hideable_ids:
            out.append(sid)
    return out


async def prehide_kp(db: AsyncSession, *, word_id: uuid.UUID) -> dict:
    """对一词跑近义/易混 AI 预隐:只 hidden 可隐 llm 行;成功则置 prehide_at(含无可隐/无需隐)。"""
    kprow = await db.get(VocabWordKp, word_id)
    if kprow is None:
        return {"prehidden": False}
    if kprow.prehide_at is not None:
        return {"prehidden": True, "already": True}
    rows = (await db.execute(
        sa.select(VocabWordRelation).where(
            VocabWordRelation.word_id == word_id,
            VocabWordRelation.relation.in_(_PREHIDE_DIMS),
            VocabWordRelation.hidden_at.is_(None)))).scalars().all()
    hideable = [r for r in rows if _is_prehide_hideable(r)]
    if not hideable:
        kprow.prehide_at = datetime.now(timezone.utc)
        await db.commit()
        return {"prehidden": True, "no_hideable": True, "hidden": 0}
    w = await db.get(VocabularyWord, word_id)
    sense_gloss = {s.id: s.gloss_zh for s in (await db.execute(
        sa.select(VocabWordSense).where(VocabWordSense.word_id == word_id))).scalars().all()}
    hideable_ids = {str(r.id) for r in hideable}
    result = await _gen_prehide_ids(w.word if w else "", rows, sense_gloss, hideable_ids)
    if result is None:
        return {"prehidden": False}   # LLM 失败:不置 prehide_at,下轮重试
    now = datetime.now(timezone.utc)
    hidden_ids = []
    by_id = {str(r.id): r for r in hideable}
    for rid in result:
        r = by_id.get(rid)
        if r is None or not _is_prehide_hideable(r):
            continue
        r.hidden_at = now
        r.hidden_by = None
        r.hide_note = _HIDE_NOTE_AI
        hidden_ids.append(rid)
    before = [{"id": str(r.id), "dim": _dim_label(r.relation), "text": r.related_text,
               "zh": r.related_zh, "source": r.source, "hideable": str(r.id) in hideable_ids}
              for r in rows]
    kprow.prehide_at = now
    db.add(VocabWordKpReview(id=uuid.uuid4(), word_id=word_id, before=before,
                             after={"hidden": hidden_ids, "trigger": "ai_prehide"}))
    await db.commit()
    return {"prehidden": True, "hidden": len(hidden_ids)}


async def prehide_pending_kp(db: AsyncSession, *, limit: int = 50) -> dict:
    """低峰批量:中考高频(star=3)未预隐词 → 逐词 AI 预隐。"""
    import logging
    ids = await _junior_high_freq_word_ids(db, limit=limit)
    stat = {"pending": len(ids), "prehidden": 0, "failed": 0, "hidden_rows": 0}
    for wid in ids:
        try:
            r = await prehide_kp(db, word_id=wid)
            if r.get("prehidden"):
                stat["prehidden"] += 1
                stat["hidden_rows"] += int(r.get("hidden") or 0)
            else:
                stat["failed"] += 1
        except Exception:  # noqa: BLE001
            await db.rollback()
            stat["failed"] += 1
            logging.getLogger(__name__).exception("prehide kp failed wid=%s", wid)
    return stat


# ---------------- 考点报错闭环(P6·学生报错 + 后台复核,复用 P5 审校管线) ----------------

_KP_REPORT_THRESHOLD_KEY = "kp_report_threshold"
_KP_REPORT_THRESHOLD_DEFAULT = 3
# 有凭证举报原因(前端标签 ↔ 存库码);加权进 report_count
_REPORT_REASONS = {
    "meaning_mismatch": "词义不符",
    "out_of_syllabus": "超纲",
    "confuse_wrong": "形近误导",
    "collocation_fake": "搭配不真实",
    "other": "其它",
}
_REPORT_WEIGHT = 2


async def get_kp_report_threshold(db: AsyncSession) -> int:
    """考点报错阈值(≥该值进复核/AI 修正)。运营可配 system_configs.kp_report_threshold,缺省 3。"""
    from app.models.d9_system import SystemConfig
    cfg = (await db.execute(
        sa.select(SystemConfig).where(SystemConfig.key == _KP_REPORT_THRESHOLD_KEY))).scalar_one_or_none()
    if cfg is not None and isinstance(cfg.value, dict):
        try:
            return max(1, int(cfg.value.get("threshold", _KP_REPORT_THRESHOLD_DEFAULT)))
        except (ValueError, TypeError):
            pass
    return _KP_REPORT_THRESHOLD_DEFAULT


async def set_kp_report_threshold(db: AsyncSession, *, threshold: int, updated_by: uuid.UUID | None = None) -> int:
    from app.models.d9_system import SystemConfig
    t = max(1, int(threshold))
    cfg = (await db.execute(
        sa.select(SystemConfig).where(SystemConfig.key == _KP_REPORT_THRESHOLD_KEY))).scalar_one_or_none()
    if cfg is None:
        db.add(SystemConfig(id=uuid.uuid4(), key=_KP_REPORT_THRESHOLD_KEY, value={"threshold": t},
                            description="考点报错阈值(≥该值进复核/AI 修正)", updated_by=updated_by))
    else:
        cfg.value = {"threshold": t}
        cfg.updated_by = updated_by
    await db.commit()
    return t


async def report_relation(db: AsyncSession, *, relation_id: uuid.UUID, student_id: uuid.UUID,
                          reason: str, detail: str | None = None, suggested: str | None = None) -> dict:
    """有凭证举报一条考点:校验原因+凭证 → 落 vocab_kp_relation_report → report_count 加权(+2)。
    同生同条不可重复。已下架的仍可记举报但不加重。"""
    from app.core.exceptions import AppError
    r = await db.get(VocabWordRelation, relation_id)
    if r is None:
        raise AppError(code=404, message="考点不存在")
    reason = (reason or "").strip()
    if reason not in _REPORT_REASONS:
        raise AppError(code=400, message="请选择举报原因")
    detail_s = (detail or "").strip()
    suggested_s = (suggested or "").strip()
    if len(detail_s) < 4 and not suggested_s:
        raise AppError(code=400, message="请填写说明(≥4字)或「我认为正确的词/用法」作为凭证")
    existed = (await db.execute(
        sa.select(VocabKpRelationReport.id).where(
            VocabKpRelationReport.relation_id == relation_id,
            VocabKpRelationReport.student_id == student_id).limit(1))).first()
    if existed:
        th = await get_kp_report_threshold(db)
        return {"reported": False, "already": True, "count": r.report_count, "threshold": th,
                "pending": r.report_count >= th, "hidden": r.hidden_at is not None}
    db.add(VocabKpRelationReport(
        id=uuid.uuid4(), relation_id=relation_id, student_id=student_id,
        reason=reason, detail=detail_s or None, suggested=suggested_s or None))
    if r.hidden_at is None:
        r.report_count = int(r.report_count or 0) + _REPORT_WEIGHT
    await db.commit()
    th = await get_kp_report_threshold(db)
    return {"reported": True, "count": r.report_count, "threshold": th,
            "pending": r.report_count >= th, "hidden": False,
            "reason_label": _REPORT_REASONS[reason]}


async def hide_relation(db: AsyncSession, *, relation_id: uuid.UUID, admin_id: uuid.UUID | None = None,
                        note: str | None = None) -> VocabWordRelation | None:
    """运营核实后下架:对学生隐藏;行保留(unique 占位,ensure 不会用 LLM 再插入同 text)。"""
    r = await db.get(VocabWordRelation, relation_id)
    if r is None:
        return None
    r.hidden_at = datetime.now(timezone.utc)
    r.hidden_by = admin_id
    r.hide_note = (note or "").strip() or None
    await db.commit()
    return r


async def unhide_relation(db: AsyncSession, *, relation_id: uuid.UUID) -> VocabWordRelation | None:
    """恢复上架(对学生重新可见)。"""
    r = await db.get(VocabWordRelation, relation_id)
    if r is None:
        return None
    r.hidden_at = None
    r.hidden_by = None
    r.hide_note = None
    await db.commit()
    return r


async def list_relation_reports(db: AsyncSession, *, relation_id: uuid.UUID, limit: int = 20) -> list[dict]:
    """某条考点的凭证举报明细(时间倒序)。"""
    rows = (await db.execute(
        sa.select(VocabKpRelationReport)
        .where(VocabKpRelationReport.relation_id == relation_id)
        .order_by(VocabKpRelationReport.created_at.desc()).limit(limit))).scalars().all()
    return [{"id": str(x.id), "reason": x.reason, "reason_label": _REPORT_REASONS.get(x.reason, x.reason),
             "detail": x.detail or "", "suggested": x.suggested or "",
             "student_id": str(x.student_id),
             "created_at": x.created_at.isoformat() if x.created_at else None} for x in rows]


async def fix_reported_kp(db: AsyncSession, *, word_id: uuid.UUID) -> dict:
    """针对某词被报错达阈值的考点行,推理档审校(复用 _review_kp_rows,带义项上下文)→ 删/改。
    审后被报错行 report_count 一律归 0(已复核),删除的即移除;记 VocabWordKpReview。LLM 失败则保留报错数、下轮再修。"""
    th = await get_kp_report_threshold(db)
    rows = (await db.execute(
        sa.select(VocabWordRelation).where(
            VocabWordRelation.word_id == word_id,
            VocabWordRelation.report_count >= th,
            VocabWordRelation.hidden_at.is_(None)))).scalars().all()
    if not rows:
        return {"fixed": False, "no_reported": True}
    w = await db.get(VocabularyWord, word_id)
    sense_gloss = {s.id: s.gloss_zh for s in (await db.execute(
        sa.select(VocabWordSense).where(VocabWordSense.word_id == word_id))).scalars().all()}
    result = await _review_kp_rows(w.word if w else "", rows, sense_gloss)
    if result is None:
        return {"fixed": False}   # LLM 失败/dev-mock:保留报错数,下轮再修
    before = [{"id": str(r.id), "dim": _dim_label(r.relation), "text": r.related_text,
               "zh": r.related_zh, "note": r.note, "report_count": r.report_count} for r in rows]
    del_ids = {str(x) for x in (result.get("delete") or [])}
    fixes = {str(f.get("id")): f for f in (result.get("fix") or []) if isinstance(f, dict) and f.get("id")}
    deleted, fixed = [], []
    for r in rows:
        rid = str(r.id)
        if rid in del_ids:
            await db.delete(r)
            deleted.append(rid)
            continue
        if rid in fixes:
            f = fixes[rid]
            r.related_text = (str(f.get("text") or "").strip() or r.related_text)
            r.related_zh = str(f.get("zh") or "").strip() or None
            r.note = str(f.get("note") or "").strip() or None
            fixed.append(rid)
        r.report_count = 0   # 已复核(改过 or 判定正确)→ 清报错数
    db.add(VocabWordKpReview(id=uuid.uuid4(), word_id=word_id, before=before,
                             after={"deleted": deleted, "fixed": fixed, "trigger": "reported"}))
    await db.commit()
    return {"fixed": True, "deleted": len(deleted), "fixed_n": len(fixed)}


async def fix_pending_reported_kp(db: AsyncSession, *, limit: int = 100) -> dict:
    """低峰批量:扫有考点被报错达阈值的词,逐词 fix_reported_kp(报错优先于 P5 巡检自审)。"""
    import logging
    th = await get_kp_report_threshold(db)
    word_ids = (await db.execute(
        sa.select(VocabWordRelation.word_id).where(VocabWordRelation.report_count >= th)
        .group_by(VocabWordRelation.word_id).limit(limit))).scalars().all()
    stat = {"pending_words": len(word_ids), "fixed": 0, "failed": 0}
    for wid in word_ids:
        try:
            r = await fix_reported_kp(db, word_id=wid)
            stat["fixed" if r.get("fixed") else "failed"] += 1
        except Exception:  # noqa: BLE001
            await db.rollback()
            stat["failed"] += 1
            logging.getLogger(__name__).exception("fix reported kp failed wid=%s", wid)
    return stat
