"""R5 词汇接入(KP-First):词条挂 KP/真题/错题 + 教材词派生 + 个人体系命中词。

- attach_node/attach_question/attach_wrong:三种边原子 upsert(幂等)。
- derive_unit_vocab_nodes:单元核心词 × 单元 node(unit_node)共现 → vocab_node(教材批量派生)。
- personal_kp_words:student_kp(in_scope)→ vocab_node → 词(背词来源收敛核心)。
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d4_knowledge import CurriculumWord
from app.models.d5_learning import VocabularyWord, VocabularyLearning
from app.models.d16_question_domain import StudentKp
from app.models.d17_curriculum_kg import UnitNode
from app.models.d18_vocab_kg import VocabNode, VocabQuestion, VocabWrong


async def attach_node(db: AsyncSession, *, word_id: uuid.UUID, node_id: uuid.UUID, source: str = "textbook") -> bool:
    stmt = (pg_insert(VocabNode).values(word_id=word_id, node_id=node_id, source=source)
            .on_conflict_do_nothing(index_elements=["word_id", "node_id"])
            .returning(VocabNode.word_id))
    return (await db.execute(stmt)).scalar_one_or_none() is not None


async def attach_question(
    db: AsyncSession, *, word_id: uuid.UUID, q_scope: str, question_id: uuid.UUID, source: str | None = None
) -> bool:
    stmt = (pg_insert(VocabQuestion)
            .values(word_id=word_id, q_scope=q_scope, question_id=question_id, source=source,
                    link_kind="occur")
            .on_conflict_do_nothing(index_elements=["word_id", "q_scope", "question_id"])
            .returning(VocabQuestion.word_id))
    return (await db.execute(stmt)).scalar_one_or_none() is not None


async def attach_wrong(db: AsyncSession, *, word_id: uuid.UUID, wrong_record_id: uuid.UUID) -> bool:
    stmt = (pg_insert(VocabWrong).values(word_id=word_id, wrong_record_id=wrong_record_id)
            .on_conflict_do_nothing(index_elements=["word_id", "wrong_record_id"])
            .returning(VocabWrong.word_id))
    return (await db.execute(stmt)).scalar_one_or_none() is not None


async def derive_unit_vocab_nodes(db: AsyncSession, *, unit_id: uuid.UUID, core_only: bool = True) -> int:
    """单元核心词 × 单元 node 共现 → vocab_node 边(教材派生,幂等)。返回新建边数。"""
    wq = sa.select(CurriculumWord.word_id).where(CurriculumWord.unit_id == unit_id)
    if core_only:
        wq = wq.where(CurriculumWord.is_core.is_(True))
    word_ids = list((await db.execute(wq)).scalars().all())
    node_ids = list((await db.execute(
        sa.select(UnitNode.node_id).where(UnitNode.unit_id == unit_id))).scalars().all())
    created = 0
    for w in word_ids:
        for n in node_ids:
            if await attach_node(db, word_id=w, node_id=n, source="textbook"):
                created += 1
    await db.flush()
    return created


async def personal_kp_words(
    db: AsyncSession, *, student_id: uuid.UUID, limit: int = 20, exclude_mastered: bool = True
) -> list[VocabularyWord]:
    """个人体系命中词:student_kp(in_scope)→ vocab_node → 词;可排除已掌握。背词来源收敛核心。"""
    stmt = (
        sa.select(VocabularyWord)
        .join(VocabNode, VocabNode.word_id == VocabularyWord.id)
        .join(StudentKp, StudentKp.node_id == VocabNode.node_id)
        .where(StudentKp.student_id == student_id, StudentKp.in_scope.is_(True))
    )
    if exclude_mastered:
        mastered = (
            sa.select(VocabularyLearning.word_id)
            .where(VocabularyLearning.student_id == student_id,
                   VocabularyLearning.level == "mastered")
        )
        stmt = stmt.where(VocabularyWord.id.notin_(mastered))
    stmt = stmt.distinct().limit(limit)
    return list((await db.execute(stmt)).scalars().all())
