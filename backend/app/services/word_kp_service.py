"""单词考点(深挖):固定搭配 / 近义 / 反义 / 派生·同族 / 易混辨析 / 考法。
全关系型落库(vocab_word_kp 词根 + vocab_word_relation 关系图);近义/反义/派生/易混命中词库
时链 related_word_id(可点去学)。LLM 一次生成全局缓存,查看即生成 + prewarm。合并原词族。"""
from __future__ import annotations

import random
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d5_learning import StudentVocabCandidate, VocabularyLearning, VocabularyWord
from app.models.d18_vocab_kg import VocabKpMcq, VocabWordKp, VocabWordRelation

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


def _dim_label(key: str) -> str:
    return _DIM_REGISTRY.get(key, (key, False, ""))[0]


def _meaning_of(w: VocabularyWord) -> str:
    defs = w.definitions if isinstance(w.definitions, list) else []
    return " / ".join(str(d.get("meaning")) for d in defs
                      if isinstance(d, dict) and d.get("meaning"))[:120]


async def _gen_kp(word: str, meaning: str, examples, is_phrase: bool = False) -> dict:
    """LLM 按词性/特点从受控维度清单动态挑维度出考点(fast 档)。dev-mock 返回空。
    返回 {pos, root, dims:[{key, items:[{text, zh, note}]}]}。"""
    from app.services.llm_provider import complete_json, fast_model, is_llm_dev_mode
    if is_llm_dev_mode():
        return {"pos": "", "root": "", "dims": []}
    tgt = "词组" if is_phrase else "单词"
    menu = "\n".join(f"- {k}({lbl},{'可链词' if rel else '文本'},适用:{pos})"
                     for k, (lbl, rel, pos) in _DIM_REGISTRY.items())
    system = (
        f"你是英语词汇考点专家。给定{tgt}+释义+例句:先判断其词性(pos),再从下面【维度清单】里挑出"
        f"**真正适用于该{tgt}词性与特点**的维度(只挑适用的,不适用不出;数量不限),每个维度给 1-4 个考点项。\n"
        "【维度清单】dim_key(维度名,类型,适用词性):\n" + menu + "\n"
        "可链词维:项 text 填英文词/词形(时态→went/gone、单复数→复数形、比较级→更级形、近义→近义词等);\n"
        "文本维:项 text 填该用法/考点的简明说明(中文为主,可含英文例)。\n"
        '严格输出 JSON:{"pos":"verb|noun|adj|adv|prep|phrase|其他","root":"词根/词干或空",'
        '"dims":[{"key":"清单里的dim_key","items":[{"text":"词/词形 或 说明","zh":"中文(可空)","note":"备注(可空)"}]}]}\n'
        f"只用清单里的 dim_key;项要真实、确与该{tgt}相关,不臆造;例句/说明用词简单、不高于目标{tgt}难度。")
    d = await complete_json(
        system_prompt=system, user_prompt=f"{tgt}:{word}\n释义:{meaning}\n参考例句:{examples}\n返回 JSON:",
        max_tokens=1800, model=fast_model(), feature="vocab_word_kp",
        validate=lambda x: isinstance(x.get("dims"), list))
    return d or {"pos": "", "root": "", "dims": []}


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


async def ensure_word_kp(db: AsyncSession, *, word_id: uuid.UUID) -> None:
    """确保该词/词组考点已生成:vocab_word_kp 有行=已生成直接返回;否则 LLM 动态挖维度 → 落 relation(每维每项一行)+ kp(词根)。"""
    if await db.get(VocabWordKp, word_id) is not None:
        return
    w = await db.get(VocabularyWord, word_id)
    if w is None:
        return
    d = await _gen_kp(w.word, _meaning_of(w), w.examples or [], is_phrase=(w.type == "phrase"))
    # 规整维度:只留清单内 dim_key
    dims = []
    for dim in (d.get("dims") or []):
        if not isinstance(dim, dict):
            continue
        key = str(dim.get("key") or "").strip()
        items = _clean_items(dim.get("items"))
        if key in _DIM_REGISTRY and items:
            dims.append((key, items))
    # 可链词维:批量查 related_text 是否在词库,填 related_word_id
    link_texts = [it["text"] for key, items in dims if key in _RELATIONAL_DIMS for it in items]
    id_by_text: dict = {}
    lows = list({t.lower() for t in link_texts if t})
    if lows:
        rows = (await db.execute(
            sa.select(VocabularyWord.id, VocabularyWord.word)
            .where(sa.func.lower(VocabularyWord.word).in_(lows)))).all()
        id_by_text = {ww.lower(): wid for wid, ww in rows}
    vals: list[dict] = []
    for key, items in dims:
        relational = key in _RELATIONAL_DIMS
        for it in items:
            t = it["text"]
            if relational and t.lower() == w.word.lower():
                continue   # 不自指
            vals.append({"id": uuid.uuid4(), "word_id": word_id, "relation": key,
                         "dim_label": _dim_label(key), "sort": _DIM_INDEX.get(key, 99),
                         "related_word_id": id_by_text.get(t.lower()) if relational else None,
                         "related_text": t, "related_zh": it.get("zh") or None, "note": it.get("note") or None})
    if vals:
        await db.execute(pg_insert(VocabWordRelation).values(vals)
                         .on_conflict_do_nothing(index_elements=["word_id", "relation", "related_text"]))
    await db.execute(pg_insert(VocabWordKp)
                     .values(word_id=word_id, root=(str(d.get("root") or "")[:64] or None))
                     .on_conflict_do_nothing(index_elements=["word_id"]))
    await db.commit()


# 过渡期:动态维度键 → 现有前端读的固定 legacy 键(R3 前端动态化后可删)
_LEGACY_KEY = {"synonym": "synonyms", "antonym": "antonyms", "derivation": "derivations",
               "confusion": "confusions", "ambiguity": "ambiguities", "related": "relateds"}


async def word_kp_out(db: AsyncSession, *, word_id: uuid.UUID, student_id: uuid.UUID | None = None) -> dict:
    """考点全套:动态维度 `dims:[{key,label,relational,items:[{text,zh,note,word_id}]}]`(按 registry 顺序);
    可链词维的项命中词库带 word_id(可点去学)。传 student_id 则把在库未学的相关词加入候选池(先验进队列)。
    过渡期同时返回旧固定键(synonyms/collocations/exam_tips…)供未升级的前端读。"""
    await ensure_word_kp(db, word_id=word_id)
    kp = await db.get(VocabWordKp, word_id)
    rows = (await db.execute(
        sa.select(VocabWordRelation).where(VocabWordRelation.word_id == word_id))).scalars().all()
    by_dim: dict = {}
    for r in rows:
        by_dim.setdefault(r.relation, []).append(r)
    seed_ids: list = []
    dims_out = []
    for key in sorted(by_dim.keys(), key=lambda k: _DIM_INDEX.get(k, 99)):
        relational = key in _RELATIONAL_DIMS
        items = []
        for r in by_dim[key]:
            wid = str(r.related_word_id) if r.related_word_id else None
            items.append({"text": r.related_text, "zh": r.related_zh or "", "note": r.note or "", "word_id": wid})
            if relational and r.related_word_id:
                seed_ids.append(r.related_word_id)
        dims_out.append({"key": key, "label": (by_dim[key][0].dim_label or _dim_label(key)),
                         "relational": relational, "items": items})
    if student_id is not None and seed_ids:
        await _seed_queue(db, student_id=student_id, word_ids=list(set(seed_ids)))

    out: dict = {"pos": "", "root": (kp.root if kp else "") or "", "dims": dims_out}
    # —— 过渡期 legacy 键(现前端读)——
    out.update({"collocations": [], "synonyms": [], "antonyms": [], "derivations": [],
                "confusions": [], "ambiguities": [], "relateds": [], "exam_tips": ""})
    for dim in dims_out:
        k = dim["key"]
        if k == "exam_tip":
            out["exam_tips"] = dim["items"][0]["text"] if dim["items"] else ""
        elif k == "collocation":
            out["collocations"] = [{"en": it["text"], "zh": it["zh"]} for it in dim["items"]]
        elif k in _LEGACY_KEY:
            out[_LEGACY_KEY[k]] = [{"word": it["text"], "zh": it["zh"], "word_id": it["word_id"],
                                    "note": it["note"]} for it in dim["items"]]
    return out


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

def _kp_content_lines(kp: dict) -> list[tuple[str, str]]:
    """把六维考点内容整理成 (dimension, 供出题的文本) —— 只保留有内容的维度。"""
    lines: list[tuple[str, str]] = []
    if kp.get("collocations"):
        lines.append(("collocation", "; ".join(f"{c['en']}({c.get('zh', '')})" for c in kp["collocations"])))
    if kp.get("synonyms"):
        lines.append(("synonym", "; ".join(f"{w['word']}({w.get('zh', '')})" for w in kp["synonyms"])))
    if kp.get("antonyms"):
        lines.append(("antonym", "; ".join(f"{w['word']}({w.get('zh', '')})" for w in kp["antonyms"])))
    if kp.get("derivations"):
        lines.append(("derivation", "; ".join(f"{w['word']}({w.get('zh', '')})" for w in kp["derivations"])))
    if kp.get("confusions"):
        lines.append(("confusion", "; ".join(
            f"{w['word']}({w.get('zh', '')};{w.get('note', '')})" for w in kp["confusions"])))
    if kp.get("ambiguities"):
        lines.append(("ambiguity", "; ".join(
            f"{w['word']}({w.get('zh', '')};{w.get('note', '')})" for w in kp["ambiguities"])))
    if kp.get("relateds"):
        lines.append(("related", "; ".join(
            f"{w['word']}({w.get('zh', '')};{w.get('note', '')})" for w in kp["relateds"])))
    if kp.get("exam_tips"):
        lines.append(("exam_tip", kp["exam_tips"]))
    return lines


async def _gen_kp_mcqs(word: str, meaning: str, kp: dict, is_phrase: bool = False) -> list[dict]:
    """LLM 一次为每个「有内容的考点维度」出 3 道单选(fast 档);目标可为单词或词组。dev-mock 返回空。"""
    from app.services.llm_provider import complete_json, fast_model, is_llm_dev_mode
    if is_llm_dev_mode():
        return []
    lines = _kp_content_lines(kp)
    if not lines:
        return []
    tgt = "词组" if is_phrase else "单词"
    dims_desc = "\n".join(f"- {d}({_dim_label(d)}): {txt}" for d, txt in lines)
    system = (
        f"你是英语词汇考点命题专家。给定目标{tgt}及其各考点维度的内容,**为下面列出的每个维度各出 3 道单选题**,\n"
        f"题要真正考该维度的知识点(不是重复问{tgt}义):\n"
        f"- collocation 固定搭配:挖空句选正确搭配词/介词,或选出与该{tgt}正确搭配的项;\n"
        f"- synonym 近义:语境中选与该{tgt}意思最接近的词/词组;\n"
        f"- antonym 反义:选该{tgt}的反义词/词组;\n"
        "- derivation 派生:挖空句按词性选正确词形(如名词/形容词形式);\n"
        f"- confusion 易混辨析:给语境,在该{tgt}与易混项之间选正确的;\n"
        f"- ambiguity 歧义:给语境,考该{tgt}与易混淆多义项的区分;\n"
        f"- related 其他关联:考该{tgt}与相关词/词组的关系或用法。\n"
        "- exam_tip 常见考法:结合高频考法出一道综合运用题。\n"
        "严格输出 JSON:{\"items\":[{\"dimension\":\"上面的英文维度名\",\"stem\":\"题干\",\n"
        "\"options\":[\"4个选项\"],\"answer\":\"正确项(必须与 options 之一完全一致)\",\"explanation\":\"一句中文解析\"}]}\n"
        "每维恰好 3 题、每题 4 个选项单选;干扰项合理不等于正确项;只出所列维度,不臆造内容。\n"
        f"【用词要简单】题干句里除目标{tgt}与考点词(选项中的词)外,其余单词一律用简单常见词、"
        f"难度不高于目标{tgt},不要用更生僻的词做句子载体——避免学生被句中难词绊住、学不到考点。")
    d = await complete_json(
        system_prompt=system,
        user_prompt=f"目标{tgt}:{word}\n释义:{meaning}\n各维度内容:\n{dims_desc}\n返回 JSON:",
        max_tokens=2400, model=fast_model(), feature="vocab_kp_mcq",
        validate=lambda x: isinstance(x.get("items"), list) and len(x.get("items")) >= 1)
    return (d or {}).get("items") or []


async def ensure_kp_mcqs(db: AsyncSession, *, word_id: uuid.UUID) -> None:
    """确保考点测试题已生成:已有(≥1 题)直接返回;否则先保证考点存在,再按维度 LLM 出题落库。"""
    exists = (await db.execute(
        sa.select(VocabKpMcq.id).where(VocabKpMcq.word_id == word_id).limit(1))).first()
    if exists:
        return
    await ensure_word_kp(db, word_id=word_id)          # FK 依赖 vocab_word_kp 行 + 需考点内容出题
    if await db.get(VocabWordKp, word_id) is None:
        return                                          # 无考点(生成失败)→ 不出题
    kp = await word_kp_out(db, word_id=word_id)         # 六维内容(不传 student_id 不入队)
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
        objs.append(VocabKpMcq(id=uuid.uuid4(), word_id=word_id, dimension=dim, stem=stem,
                               options=opts, answer=ans, explanation=g.get("explanation") or None))
    if objs:
        db.add_all(objs)
        await db.commit()


async def kp_mcq_test(db: AsyncSession, *, word_id: uuid.UUID) -> list[dict]:
    """考点扩展测试:确保题库 → 每个有题的维度随机取 1 道 → 按固定维度顺序组合返回。"""
    await ensure_kp_mcqs(db, word_id=word_id)
    rows = (await db.execute(
        sa.select(VocabKpMcq).where(VocabKpMcq.word_id == word_id))).scalars().all()
    by_dim: dict = {}
    for r in rows:
        by_dim.setdefault(r.dimension, []).append(r)
    out = []
    for dim in sorted(by_dim.keys(), key=lambda k: _DIM_INDEX.get(k, 99)):
        rs = by_dim.get(dim)
        if rs:
            m = random.choice(rs)
            out.append({"id": str(m.id), "dimension": dim, "dimension_label": _dim_label(dim),
                        "stem": m.stem, "options": m.options, "answer": m.answer,
                        "explanation": m.explanation or ""})
    return out
