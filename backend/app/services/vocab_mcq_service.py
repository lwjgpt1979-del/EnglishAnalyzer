"""词汇测试题库:每词 3-5 道混合单选题,LLM 生成一次全局缓存,测试时随机取 1。
词义丰富=5 道、简单单义=3 道(LLM 定);类型 w2m/m2w/cloze 混合。查看即生成 + 秒回后台异步。"""
from __future__ import annotations

import random
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d5_learning import VocabularyWord
from app.models.d18_vocab_kg import VocabMcq

_MCQ_INFLIGHT: set = set()   # 后台生成中的 word_id,防并发重复调 LLM


def _meaning_of(w: VocabularyWord) -> str:
    defs = w.definitions if isinstance(w.definitions, list) else []
    return " / ".join(str(d.get("meaning")) for d in defs
                      if isinstance(d, dict) and d.get("meaning"))[:120]


async def _gen_mcqs(word: str, meaning: str, examples) -> list[dict]:
    """LLM 生成 3-5 道混合单选题(fast 档)。dev-mock 返回 1-2 道占位。"""
    from app.services.llm_provider import complete_json, fast_model, is_llm_dev_mode
    if is_llm_dev_mode():
        return [{"mcq_type": "w2m", "stem": f"(dev) {word} 的意思是?", "options": [meaning or "A", "B", "C", "D"],
                 "answer": meaning or "A", "explanation": "(dev)"}]
    system = (
        "你是英语词汇命题专家。给定单词+释义+例句,为「词汇掌握测试」生成 3-5 道单选题,题型混合覆盖:\n"
        "- w2m 词→义:题干给英文词,选正确中文义;\n"
        "- m2w 义→词:题干给中文义或语境,选正确英文词;\n"
        "- cloze 语境填空:题干给一句挖空(用 ____)的英文句,选正确英文词。\n"
        "词义丰富/多义/搭配多的词出到 5 道,简单单义词只出 3 道。严格输出 JSON:\n"
        '{"items":[{"type":"w2m|m2w|cloze","stem":"题干","options":["4个选项"],'
        '"answer":"正确项(必须与 options 之一完全一致)","explanation":"一句中文解析"}]}\n'
        "每题 4 个选项、单选;干扰项像「读半懂的人会选的」(形近/近义/他义),不得等于正确项;不臆造。")
    d = await complete_json(
        system_prompt=system, user_prompt=f"单词:{word}\n释义:{meaning}\n参考例句:{examples}\n返回 JSON:",
        max_tokens=1200, model=fast_model(), feature="vocab_mcq",
        validate=lambda x: isinstance(x.get("items"), list) and len(x.get("items")) >= 1)
    if not d:
        return []
    out = []
    for it in (d.get("items") or [])[:5]:
        if not isinstance(it, dict):
            continue
        opts = [str(o).strip() for o in (it.get("options") or []) if str(o).strip()]
        ans = str(it.get("answer") or "").strip()
        t = str(it.get("type") or "").strip()
        if len(opts) < 2 or ans not in opts or t not in ("w2m", "m2w", "cloze") or not str(it.get("stem") or "").strip():
            continue   # 缺项即丢弃,不硬塞
        out.append({"mcq_type": t, "stem": str(it["stem"]).strip(), "options": opts,
                    "answer": ans, "explanation": str(it.get("explanation") or "")})
    return out


async def ensure_word_mcqs(db: AsyncSession, *, word_id: uuid.UUID) -> list[VocabMcq]:
    """取该词题库:已有(≥1 道)直接返回;为空则 LLM 生成 3-5 道落库(全局共享,不二次付费)。"""
    rows = list((await db.execute(
        sa.select(VocabMcq).where(VocabMcq.word_id == word_id))).scalars().all())
    if rows:
        return rows
    w = await db.get(VocabularyWord, word_id)
    if w is None:
        return []
    gen = await _gen_mcqs(w.word, _meaning_of(w), w.examples or [])
    if not gen:
        return []
    objs = [VocabMcq(id=uuid.uuid4(), word_id=word_id, mcq_type=g["mcq_type"], stem=g["stem"],
                     options=g["options"], answer=g["answer"], explanation=g["explanation"] or None)
            for g in gen]
    db.add_all(objs)
    await db.commit()
    return objs


def _to_dict(m: VocabMcq) -> dict:
    return {"word_id": str(m.word_id), "mcq_type": m.mcq_type, "stem": m.stem,
            "options": m.options, "answer": m.answer, "explanation": m.explanation or ""}


async def random_mcq(db: AsyncSession, *, word_id: uuid.UUID) -> dict | None:
    """随机取该词一道题(缺则先生成)。"""
    rows = await ensure_word_mcqs(db, word_id=word_id)
    return _to_dict(random.choice(rows)) if rows else None


async def _bg_gen_mcqs(word_id: uuid.UUID) -> None:
    """后台异步生成该词题库(独立 session;秒回场景用)。inflight 防并发重复。"""
    import logging
    from app.core.database import _async_session_factory
    if word_id in _MCQ_INFLIGHT:
        return
    _MCQ_INFLIGHT.add(word_id)
    try:
        async with _async_session_factory() as db:
            try:
                await ensure_word_mcqs(db, word_id=word_id)
            except Exception:  # noqa: BLE001
                await db.rollback()
                logging.getLogger(__name__).exception("bg mcq gen failed wid=%s", word_id)
    finally:
        _MCQ_INFLIGHT.discard(word_id)


async def random_mcqs_batch(db: AsyncSession, *, word_ids: list) -> list[dict]:
    """测试出题:每词随机取一道已缓存题;未缓存的**后台异步生成**并返回 mcq=null
    (前端当场回退客户端模板题,下次即有 LLM 题)。不阻塞测试开始。"""
    import asyncio
    wids = [uuid.UUID(str(w)) for w in word_ids]
    cached = {}
    if wids:
        rows = (await db.execute(sa.select(VocabMcq).where(VocabMcq.word_id.in_(wids)))).scalars().all()
        for m in rows:
            cached.setdefault(m.word_id, []).append(m)
    out = []
    for wid in wids:
        rs = cached.get(wid)
        if rs:
            out.append({"word_id": str(wid), "mcq": _to_dict(random.choice(rs))})
        else:
            asyncio.create_task(_bg_gen_mcqs(wid))   # 秒回:后台生成
            out.append({"word_id": str(wid), "mcq": None})
    return out
