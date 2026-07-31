"""平台题选项词 × 主考/干扰 · 统计与反查。

池见 POOL_KINDS;仅 option_vocab_ready=true 的题计入(校验通过+挂边成功)。
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d5_learning import VocabularyWord
from app.models.d16_question_domain import PlatformQuestion
from app.models.d18_vocab_kg import VocabQuestion
from app.services import region_service

POOL_STANDALONE_WORD_MCQ = "standalone_word_mcq"
POOL_OPTION_VOCAB_SLOT = "option_vocab_slot"
POOL_OPTION_MCQ = "option_mcq"
POOL_OPTION_FILL = "option_fill"

POOL_KINDS: dict[str, frozenset[str]] = {
    POOL_STANDALONE_WORD_MCQ: frozenset({"grammar_mc"}),
    POOL_OPTION_MCQ: frozenset({"grammar_mc", "cloze"}),
    POOL_OPTION_FILL: frozenset({"word_fill", "passage_fill"}),
    POOL_OPTION_VOCAB_SLOT: frozenset({"grammar_mc", "cloze", "word_fill", "passage_fill"}),
}


def pool_analysis_kinds(pool: str) -> frozenset[str] | None:
    return POOL_KINDS.get(pool)


_SORT_WORD = {
    "correct_count_desc": lambda c: c.c.correct_count.desc(),
    "distractor_count_desc": lambda c: c.c.distractor_count.desc(),
    "word": lambda c: c.c.word.asc(),
}
_SORT_REGION = {
    "question_count_desc": lambda c: c.c.question_count.desc(),
    "word_count_desc": lambda c: c.c.word_count.desc(),
}


def _ready_cond(pq: type[PlatformQuestion]):
    """校验通过且挂边成功的题才进统计。"""
    return pq.meta["analysis"]["option_vocab_ready"].as_boolean().is_(True)


def _pool_conds(pq: type[PlatformQuestion], pool: str) -> list | None:
    """按池过滤:仅含已确认解析且 kind 在池内的真题。"""
    kinds = pool_analysis_kinds(pool)
    if not kinds:
        return None
    return [
        pq.type == "real",
        pq.meta["analysis"]["kind"].astext.in_(list(kinds)),
        _ready_cond(pq),
    ]


def _vq_conds(vq: type[VocabQuestion]) -> list:
    return [
        vq.q_scope == "platform",
        vq.link_kind.in_(("correct", "distractor")),
    ]


def _region_bucket(pq: type[PlatformQuestion], level: str):
    if level == "province":
        return sa.func.left(pq.region_code, 2)
    if level == "city":
        return sa.func.left(pq.region_code, 4)
    raise ValueError(f"unknown region_level: {level}")


def _min_region_len(level: str) -> int:
    return 2 if level == "province" else 4


def _apply_filters(
    pq: type[PlatformQuestion],
    *,
    exam_type: str | None,
    region_code: str | None,
) -> list:
    conds: list = []
    if exam_type:
        conds.append(pq.exam_type == exam_type)
    if region_code:
        conds.append(pq.region_code.like(f"{region_code}%"))
    return conds


async def word_role_stats(
    db: AsyncSession,
    *,
    pool: str = POOL_OPTION_VOCAB_SLOT,
    exam_type: str | None = None,
    group_by: str = "word",
    region_level: str | None = None,
    region_code: str | None = None,
    q: str | None = None,
    min_correct: int = 0,
    min_distractor: int = 0,
    sort: str = "correct_count_desc",
    skip: int = 0,
    limit: int = 50,
) -> dict:
    """词表 / 地区汇总。group_by=word|region;region_level=province|city。"""
    pq_conds = _pool_conds(PlatformQuestion, pool)
    if pq_conds is None:
        return {"total": 0, "items": [], "pool": pool, "unknown_question_count": 0}

    vq, pq, w = VocabQuestion, PlatformQuestion, VocabularyWord
    conds = _vq_conds(vq) + pq_conds + _apply_filters(
        pq, exam_type=exam_type, region_code=region_code)

    unknown = await _unknown_region_count(db, exam_type=exam_type, pool=pool)

    if group_by == "region":
        if region_level not in ("province", "city"):
            return {
                "total": 0, "items": [], "pool": pool, "exam_type": exam_type,
                "region_level": region_level, "unknown_question_count": unknown,
            }
        items, total = await _region_stats(
            db, conds=conds, region_level=region_level, sort=sort, skip=skip, limit=limit)
        await _attach_region_names(db, items, region_level)
        return {
            "total": total, "items": items, "pool": pool, "exam_type": exam_type,
            "group_by": "region", "region_level": region_level,
            "region_code": region_code, "unknown_question_count": unknown,
        }

    # group_by=word
    items, total = await _word_stats(
        db, conds=conds, region_level=region_level, q=q,
        min_correct=min_correct, min_distractor=min_distractor,
        sort=sort, skip=skip, limit=limit)
    if region_level:
        await _attach_region_names(db, items, region_level)
    return {
        "total": total, "items": items, "pool": pool, "exam_type": exam_type,
        "group_by": "word", "region_level": region_level,
        "region_code": region_code, "unknown_question_count": unknown,
    }


async def _unknown_region_count(db: AsyncSession, *, exam_type: str | None, pool: str) -> int:
    pq = PlatformQuestion
    pq_conds = _pool_conds(pq, pool)
    if pq_conds is None:
        return 0
    conds = pq_conds + [
        sa.or_(pq.region_code.is_(None), pq.region_code == ""),
    ]
    if exam_type:
        conds.append(pq.exam_type == exam_type)
    return int((await db.execute(
        sa.select(sa.func.count(sa.distinct(pq.id)))
        .select_from(pq)
        .join(VocabQuestion, sa.and_(
            VocabQuestion.question_id == pq.id,
            VocabQuestion.q_scope == "platform",
            VocabQuestion.link_kind.in_(("correct", "distractor")),
        ))
        .where(*conds)
    )).scalar_one())


async def _word_stats(
    db: AsyncSession, *, conds: list, region_level: str | None, q: str | None,
    min_correct: int, min_distractor: int, sort: str, skip: int, limit: int,
) -> tuple[list[dict], int]:
    vq, pq, w = VocabQuestion, PlatformQuestion, VocabularyWord
    region_col = None
    group_cols = [w.id, w.word]
    if region_level:
        min_len = _min_region_len(region_level)
        conds = list(conds) + [
            pq.region_code.isnot(None),
            sa.func.length(pq.region_code) >= min_len,
        ]
        region_col = _region_bucket(pq, region_level).label("region_code")
        group_cols.append(region_col)

    sel = [
        w.id.label("word_id"),
        w.word,
        sa.func.count(sa.distinct(vq.question_id))
        .filter(vq.link_kind == "correct").label("correct_count"),
        sa.func.count(sa.distinct(vq.question_id))
        .filter(vq.link_kind == "distractor").label("distractor_count"),
        sa.func.count(sa.distinct(vq.question_id)).label("question_count"),
    ]
    if region_col is not None:
        sel.append(region_col)

    if q and q.strip():
        conds = list(conds) + [w.word.ilike(f"%{q.strip()}%")]

    base = (
        sa.select(*sel)
        .select_from(vq)
        .join(w, w.id == vq.word_id)
        .join(pq, pq.id == vq.question_id)
        .where(*conds)
        .group_by(*group_cols)
    )
    if min_correct:
        base = base.having(
            sa.func.count(sa.distinct(vq.question_id)).filter(vq.link_kind == "correct") >= min_correct)
    if min_distractor:
        base = base.having(
            sa.func.count(sa.distinct(vq.question_id)).filter(vq.link_kind == "distractor") >= min_distractor)

    sub = base.subquery()
    total = int((await db.execute(sa.select(sa.func.count()).select_from(sub))).scalar_one())

    order_fn = _SORT_WORD.get(sort, _SORT_WORD["correct_count_desc"])(sub)
    rows = (await db.execute(
        sa.select(sub).order_by(order_fn, sub.c.word).offset(skip).limit(limit)
    )).all()

    items = [{
        "word_id": str(r.word_id),
        "word": r.word,
        "correct_count": int(r.correct_count or 0),
        "distractor_count": int(r.distractor_count or 0),
        "question_count": int(r.question_count or 0),
        **({"region_code": r.region_code} if region_level else {}),
    } for r in rows]
    return items, total


async def _region_stats(
    db: AsyncSession, *, conds: list, region_level: str, sort: str, skip: int, limit: int,
) -> tuple[list[dict], int]:
    vq, pq = VocabQuestion, PlatformQuestion
    min_len = _min_region_len(region_level)
    conds = list(conds) + [
        pq.region_code.isnot(None),
        sa.func.length(pq.region_code) >= min_len,
    ]
    bucket = _region_bucket(pq, region_level).label("region_code")

    base = (
        sa.select(
            bucket,
            sa.func.count(sa.distinct(pq.id)).label("question_count"),
            sa.func.count(sa.distinct(vq.word_id)).label("word_count"),
            sa.func.count(sa.distinct(sa.tuple_(vq.word_id, vq.question_id)))
            .filter(vq.link_kind == "correct").label("correct_link_count"),
            sa.func.count(sa.distinct(sa.tuple_(vq.word_id, vq.question_id)))
            .filter(vq.link_kind == "distractor").label("distractor_link_count"),
        )
        .select_from(pq)
        .join(vq, sa.and_(vq.question_id == pq.id, *_vq_conds(vq)))
        .where(*conds)
        .group_by(bucket)
    ).subquery()

    total = int((await db.execute(sa.select(sa.func.count()).select_from(base))).scalar_one())
    order_fn = _SORT_REGION.get(sort, _SORT_REGION["question_count_desc"])(base)
    rows = (await db.execute(
        sa.select(base).order_by(order_fn, base.c.region_code).offset(skip).limit(limit)
    )).all()

    items = [{
        "region_code": r.region_code,
        "question_count": int(r.question_count or 0),
        "word_count": int(r.word_count or 0),
        "correct_link_count": int(r.correct_link_count or 0),
        "distractor_link_count": int(r.distractor_link_count or 0),
    } for r in rows]
    return items, total


async def _attach_region_names(
    db: AsyncSession, items: list[dict], region_level: str,
) -> None:
    codes = [str(it.get("region_code") or "") for it in items if it.get("region_code")]
    if not codes:
        return
    # region_breakdowns 需要完整码;桶码补零到标准长度查名
    padded = []
    for c in codes:
        if region_level == "province" and len(c) == 2:
            padded.append(c)
        elif region_level == "city" and len(c) == 4:
            padded.append(c)
        else:
            padded.append(c)
    bd = await region_service.region_breakdowns(db, padded)
    key = "province" if region_level == "province" else "city"
    for it in items:
        rc = str(it.get("region_code") or "")
        info = bd.get(rc, {})
        it["region_name"] = info.get(key) or rc


async def stats_for_word(
    db: AsyncSession, word_id: uuid.UUID, *, pool: str = POOL_STANDALONE_WORD_MCQ,
    exam_type: str | None = None, region_code: str | None = None,
) -> dict:
    """单词在池内的 correct/distractor 计数。"""
    data = await word_role_stats(
        db, pool=pool, exam_type=exam_type, group_by="word",
        region_code=region_code, skip=0, limit=1, q=None)
    for it in data.get("items") or []:
        if it.get("word_id") == str(word_id):
            return it
    vq, pq, w = VocabQuestion, PlatformQuestion, VocabularyWord
    pq_conds = _pool_conds(pq, pool)
    if pq_conds is None:
        return {"word_id": str(word_id), "correct_count": 0, "distractor_count": 0, "question_count": 0}
    conds = _vq_conds(vq) + pq_conds + _apply_filters(
        pq, exam_type=exam_type, region_code=region_code) + [w.id == word_id]
    row = (await db.execute(
        sa.select(
            sa.func.count(sa.distinct(vq.question_id))
            .filter(vq.link_kind == "correct").label("correct_count"),
            sa.func.count(sa.distinct(vq.question_id))
            .filter(vq.link_kind == "distractor").label("distractor_count"),
        )
        .select_from(vq)
        .join(pq, pq.id == vq.question_id)
        .where(*conds)
    )).one()
    return {
        "word_id": str(word_id),
        "correct_count": int(row.correct_count or 0),
        "distractor_count": int(row.distractor_count or 0),
        "question_count": int((row.correct_count or 0) + (row.distractor_count or 0)),
    }
