"""单词考点(深挖):固定搭配 / 近义 / 反义 / 派生·同族 / 易混辨析 / 考法。
全关系型落库(vocab_word_kp 词根 + vocab_word_relation 关系图);近义/反义/派生/易混命中词库
时链 related_word_id(可点去学)。LLM 一次生成全局缓存,查看即生成 + prewarm。合并原词族。"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d5_learning import StudentVocabCandidate, VocabularyLearning, VocabularyWord
from app.models.d18_vocab_kg import VocabWordKp, VocabWordRelation

# 词-词类关系(可链 related_word_id、可点去学);collocation/exam_tip 为文本类
_WORD_RELATIONS = ("synonym", "antonym", "derivation", "confusion")


def _meaning_of(w: VocabularyWord) -> str:
    defs = w.definitions if isinstance(w.definitions, list) else []
    return " / ".join(str(d.get("meaning")) for d in defs
                      if isinstance(d, dict) and d.get("meaning"))[:120]


async def _gen_kp(word: str, meaning: str, examples) -> dict:
    """LLM 一次挖全六维(fast 档)。dev-mock 返回空。"""
    from app.services.llm_provider import complete_json, fast_model, is_llm_dev_mode
    if is_llm_dev_mode():
        return {"root": "", "synonyms": [], "antonyms": [], "derivations": [],
                "collocations": [], "confusions": [], "exam_tips": ""}
    system = (
        "你是英语词汇考点专家。给定单词+释义+例句,挖掘它的考点,严格输出 JSON:\n"
        '{"root":"词根/词干(如 poe-;无明显则空)",'
        '"synonyms":[{"word":"近义英文词","zh":"中文"}],'
        '"antonyms":[{"word":"反义英文词","zh":"中文"}],'
        '"derivations":[{"word":"同族/派生词(英文)","zh":"中文(含词性,如 n. 庆典)"}],'
        '"collocations":[{"en":"固定搭配(含该词)","zh":"中文"}],'
        '"confusions":[{"word":"易混英文词","zh":"中文","note":"一句辨析要点"}],'
        '"exam_tips":"一句常见考法/考点提示(中文)"}\n'
        "各数组 0-4 条,无则空;近义/反义/派生/易混必须是真实存在、确与该词相关的英文词,不臆造。")
    d = await complete_json(
        system_prompt=system, user_prompt=f"单词:{word}\n释义:{meaning}\n参考例句:{examples}\n返回 JSON:",
        max_tokens=1000, model=fast_model(), feature="vocab_word_kp",
        validate=lambda x: isinstance(x, dict))
    return d or {}


def _clean_word_items(arr, keys=("word", "zh")) -> list[dict]:
    out = []
    for it in (arr or [])[:4]:
        if isinstance(it, dict) and str(it.get(keys[0]) or "").strip():
            out.append({k: str(it.get(k) or "").strip() for k in ("word", "zh", "note", "en")})
    return out


async def ensure_word_kp(db: AsyncSession, *, word_id: uuid.UUID) -> None:
    """确保该词考点已生成:vocab_word_kp 有行=已生成直接返回;否则 LLM 生成 → 落 kp(词根)+ relation(六维)。"""
    if await db.get(VocabWordKp, word_id) is not None:
        return
    w = await db.get(VocabularyWord, word_id)
    if w is None:
        return
    d = await _gen_kp(w.word, _meaning_of(w), w.examples or [])
    # 词-词类:批量查 related_text 是否在词库,填 related_word_id
    word_texts = []
    for rel in _WORD_RELATIONS:
        src = "derivations" if rel == "derivation" else (rel + "s")
        word_texts += [str(x.get("word") or "").strip() for x in (d.get(src) or []) if isinstance(x, dict)]
    id_by_text: dict = {}
    lows = list({t.lower() for t in word_texts if t})
    if lows:
        rows = (await db.execute(
            sa.select(VocabularyWord.id, VocabularyWord.word)
            .where(sa.func.lower(VocabularyWord.word).in_(lows)))).all()
        id_by_text = {ww.lower(): wid for wid, ww in rows}
    vals: list[dict] = []
    for rel in _WORD_RELATIONS:
        src = "derivations" if rel == "derivation" else (rel + "s")
        for it in _clean_word_items(d.get(src)):
            t = it["word"]
            if t.lower() == w.word.lower():
                continue
            vals.append({"id": uuid.uuid4(), "word_id": word_id, "relation": rel,
                         "related_word_id": id_by_text.get(t.lower()), "related_text": t,
                         "related_zh": it.get("zh") or None, "note": it.get("note") or None})
    for c in _clean_word_items(d.get("collocations")):
        en = c.get("en") or c.get("word")
        if en:
            vals.append({"id": uuid.uuid4(), "word_id": word_id, "relation": "collocation",
                         "related_word_id": None, "related_text": en, "related_zh": c.get("zh") or None, "note": None})
    tip = str(d.get("exam_tips") or "").strip()
    if tip:
        vals.append({"id": uuid.uuid4(), "word_id": word_id, "relation": "exam_tip",
                     "related_word_id": None, "related_text": tip, "related_zh": None, "note": None})
    if vals:
        await db.execute(pg_insert(VocabWordRelation).values(vals)
                         .on_conflict_do_nothing(index_elements=["word_id", "relation", "related_text"]))
    await db.execute(pg_insert(VocabWordKp)
                     .values(word_id=word_id, root=(str(d.get("root") or "")[:64] or None))
                     .on_conflict_do_nothing(index_elements=["word_id"]))
    await db.commit()


async def word_kp_out(db: AsyncSession, *, word_id: uuid.UUID, student_id: uuid.UUID | None = None) -> dict:
    """考点全套(六维 + 词根);近义/反义/派生/易混带 word_id(命中词库→可点去学)。
    传 student_id 则把在库未学的派生/近义词加入候选池(先验进队列,合并原词族行为)。"""
    await ensure_word_kp(db, word_id=word_id)
    kp = await db.get(VocabWordKp, word_id)
    rows = (await db.execute(
        sa.select(VocabWordRelation).where(VocabWordRelation.word_id == word_id))).scalars().all()
    out: dict = {"root": (kp.root if kp else "") or "", "collocations": [], "synonyms": [],
                 "antonyms": [], "derivations": [], "confusions": [], "exam_tips": ""}
    seed_ids: list = []
    for r in rows:
        if r.relation == "exam_tip":
            out["exam_tips"] = r.related_text
        elif r.relation == "collocation":
            out["collocations"].append({"en": r.related_text, "zh": r.related_zh or ""})
        elif r.relation in _WORD_RELATIONS:
            key = "derivations" if r.relation == "derivation" else (r.relation + "s")
            item = {"word": r.related_text, "zh": r.related_zh or "",
                    "word_id": str(r.related_word_id) if r.related_word_id else None}
            if r.relation == "confusion":
                item["note"] = r.note or ""
            out[key].append(item)
            if r.related_word_id and r.relation in ("derivation", "synonym"):
                seed_ids.append(r.related_word_id)
    if student_id is not None and seed_ids:
        await _seed_queue(db, student_id=student_id, word_ids=list(set(seed_ids)))
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
