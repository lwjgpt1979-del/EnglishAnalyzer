"""词族(G 构词法)服务:词根 + 同族词。LLM 生成一次全局缓存(查看即生成),
在库同族词可「先验进队列」(加入学生候选池)。词力通科学学习策略 P2。"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d5_learning import StudentVocabCandidate, VocabularyLearning, VocabularyWord
from app.models.d18_vocab_kg import VocabWordFamily


def _meaning_of(w: VocabularyWord) -> str:
    defs = w.definitions if isinstance(w.definitions, list) else []
    for d in defs:
        if isinstance(d, dict) and d.get("meaning"):
            return str(d["meaning"])
    return ""


async def _gen_family(word: str, meaning: str) -> dict:
    """LLM 生成词根 + 同族词(chat 快档;规格明确的抽取,不臆造)。dev-mock 离线返回空。"""
    from app.services.llm_provider import complete_json, fast_model, is_llm_dev_mode
    if is_llm_dev_mode():
        return {"root": "", "members": []}
    system = (
        "你是英语构词法助手。给定一个英文单词及其中文义,输出它的词根/词干与同族词"
        "(同词根的常见派生/屈折词),严格输出 JSON:\n"
        '{"root":"词根或词干(如 poe- / act;无明显词根则空串)",'
        '"members":[{"word":"同族词(英文)","pos":"词性缩写 n./v./adj. 等","meaning":"简洁中文释义"}]'
        "(2-5 个初高中常见同族词,不含原词本身;无则空数组)}\n"
        "只返回纯 JSON。同族词必须真实存在、与原词同词根,不臆造。")
    d = await complete_json(
        system_prompt=system, user_prompt=f"单词:{word}\n中文义:{meaning}\n返回 JSON:",
        max_tokens=500, model=fast_model(), feature="vocab_word_family",
        validate=lambda x: isinstance(x.get("members"), list))
    if not d:
        return {"root": "", "members": []}
    members = [
        {"word": str(m.get("word") or "").strip(), "pos": str(m.get("pos") or ""),
         "meaning": str(m.get("meaning") or "")}
        for m in (d.get("members") or [])
        if isinstance(m, dict) and str(m.get("word") or "").strip()
        and str(m.get("word") or "").strip().lower() != word.lower()
    ]
    return {"root": str(d.get("root") or "")[:64], "members": members[:5]}


async def ensure_word_family(db: AsyncSession, *, word_id: uuid.UUID) -> dict:
    """取该词词族:命中缓存直接返回;未命中调 LLM 生成并写缓存(全局共享,同词不二次付费)。"""
    fam = await db.get(VocabWordFamily, word_id)
    if fam is not None:
        return {"root": fam.root or "", "members": fam.members or []}
    w = await db.get(VocabularyWord, word_id)
    if w is None:
        return {"root": "", "members": []}
    gen = await _gen_family(w.word, _meaning_of(w))
    await db.execute(
        pg_insert(VocabWordFamily)
        .values(word_id=word_id, root=(gen["root"] or None), members=gen["members"])
        .on_conflict_do_nothing(index_elements=["word_id"]))
    await db.commit()
    return gen


async def word_family_out(
    db: AsyncSession, *, word_id: uuid.UUID, student_id: uuid.UUID | None = None,
) -> dict:
    """词族 + 标注同族词是否在词库(in_dict);传 student_id 则把在库且未学的同族词
    加入该生候选池(source='family',先验进新词队列)。"""
    fam = await ensure_word_family(db, word_id=word_id)
    members = fam["members"]
    dict_map: dict = {}
    if members:
        lowers = [m["word"].lower() for m in members]
        rows = (await db.execute(
            sa.select(VocabularyWord.id, VocabularyWord.word)
            .where(sa.func.lower(VocabularyWord.word).in_(lowers)))).all()
        dict_map = {w.lower(): wid for wid, w in rows}
    out_members = [{**m, "in_dict": m["word"].lower() in dict_map} for m in members]
    if student_id is not None and dict_map:
        await _seed_queue(db, student_id=student_id, member_ids=list(dict_map.values()))
    return {"root": fam["root"], "members": out_members}


async def _seed_queue(db: AsyncSession, *, student_id: uuid.UUID, member_ids: list) -> None:
    """在库、未学的同族词加入候选池 → 提前进新词队列(先验)。幂等。"""
    learned = set((await db.execute(
        sa.select(VocabularyLearning.word_id)
        .where(VocabularyLearning.student_id == student_id))).scalars().all())
    todo = [wid for wid in member_ids if wid not in learned]
    if not todo:
        return
    await db.execute(
        pg_insert(StudentVocabCandidate)
        .values([{"id": uuid.uuid4(), "student_id": student_id, "word_id": wid, "source": "family"}
                 for wid in todo])
        .on_conflict_do_nothing(index_elements=["student_id", "word_id"]))
    await db.commit()
