"""R5 通用词库(平台域,超管维护):导入权威考纲表 + 真题/教材频率增强。

词条共享 d5.VocabularyWord(import 来的词 source='import');词库元数据 vocab_list,
库内属性(rank/frequency/star)在 vocab_list_item。
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d5_learning import VocabularyWord
from app.models.d18_vocab_kg import VocabList, VocabListItem, VocabQuestion


async def create_list(
    db: AsyncSession, *, name: str, exam_level: str | None = None,
    source_type: str | None = None, maintained_by: uuid.UUID | None = None,
    status: str = "draft",
) -> VocabList:
    exists = (await db.execute(sa.select(VocabList).where(VocabList.name == name))).scalar_one_or_none()
    if exists is not None:
        raise AppError(code=409, message="同名词库已存在")
    vl = VocabList(id=uuid.uuid4(), name=name, exam_level=exam_level,
                   source_type=source_type, maintained_by=maintained_by, status=status)
    db.add(vl)
    await db.flush()
    return vl


async def list_lists(db: AsyncSession, *, status: str | None = None) -> list[VocabList]:
    stmt = sa.select(VocabList)
    if status is not None:
        stmt = stmt.where(VocabList.status == status)
    return list((await db.execute(stmt.order_by(VocabList.created_at.desc()))).scalars().all())


async def _get_or_create_word(db: AsyncSession, word: str) -> uuid.UUID:
    """按词形找词条(忽略大小写);无则建 import 占位词条(媒体/释义后续补)。"""
    wid = (await db.execute(
        sa.select(VocabularyWord.id).where(sa.func.lower(VocabularyWord.word) == word.lower())
    )).scalar_one_or_none()
    if wid is not None:
        return wid
    new_id = uuid.uuid4()
    db.add(VocabularyWord(id=new_id, word=word, definitions=[], difficulty=3,
                          type="word", source="import"))
    await db.flush()
    return new_id


async def add_items(db: AsyncSession, *, list_id: uuid.UUID, items: list[dict]) -> int:
    """批量加入词库条目。items: [{word|word_id, rank?, frequency?, star?, verified?}]。幂等。返回处理数。"""
    n = 0
    for it in items:
        wid = it.get("word_id") or await _get_or_create_word(db, it["word"])
        await db.execute(
            pg_insert(VocabListItem)
            .values(list_id=list_id, word_id=wid, rank=it.get("rank"),
                    frequency=it.get("frequency"), star=it.get("star", 0),
                    verified=it.get("verified", False))
            .on_conflict_do_update(
                index_elements=["list_id", "word_id"],
                set_={"rank": it.get("rank"), "frequency": it.get("frequency"),
                      "star": it.get("star", 0)},
            )
        )
        n += 1
    await db.flush()
    return n


async def list_items(
    db: AsyncSession, *, list_id: uuid.UUID, skip: int = 0, limit: int = 100
) -> list[dict]:
    rows = (await db.execute(
        sa.select(VocabListItem.word_id, VocabularyWord.word, VocabListItem.rank,
                  VocabListItem.frequency, VocabListItem.star, VocabListItem.verified)
        .join(VocabularyWord, VocabularyWord.id == VocabListItem.word_id)
        .where(VocabListItem.list_id == list_id)
        .order_by(VocabListItem.rank.asc().nullslast())
        .offset(skip).limit(limit)
    )).all()
    return [
        {"word_id": wid, "word": w, "rank": rank, "frequency": freq, "star": star, "verified": v}
        for wid, w, rank, freq, star, v in rows
    ]


async def recompute_star_from_questions(db: AsyncSession, *, list_id: uuid.UUID) -> int:
    """真题频率增强:按词在 vocab_question 的出现次数给库内 star 打分(0–5)。返回更新条目数。"""
    counts = dict((await db.execute(
        sa.select(VocabQuestion.word_id, sa.func.count())
        .join(VocabListItem, VocabListItem.word_id == VocabQuestion.word_id)
        .where(VocabListItem.list_id == list_id)
        .group_by(VocabQuestion.word_id)
    )).all())
    updated = 0
    for wid, cnt in counts.items():
        star = min(5, int(cnt))
        await db.execute(
            sa.update(VocabListItem)
            .where(VocabListItem.list_id == list_id, VocabListItem.word_id == wid)
            .values(star=star)
        )
        updated += 1
    await db.flush()
    return updated
