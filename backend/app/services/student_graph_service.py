"""R4 学生个人知识图谱(KP-First):物化 student_kp(node 维度)。

- enroll_textbook:选/换教材 → 该教材单元 node 全集批量纳入 student_kp(in_scope + source 'textbook')。
- add_source:KP 进入个人体系的来源原子追加 source_tags(去重),供命中并入复用。
- get_graph / graph_summary:知识地图(默认只亮已练已错,全集折叠可展开)。
旧 student_kp_mastery 台账保留供现有诊断;本服务写新 node 维度 student_kp。
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d4_knowledge import CurriculumUnit
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import StudentKp
from app.models.d17_curriculum_kg import UnitNode


def _append_tag_expr(tag: str):
    """source_tags 去重追加(PG):ARRAY(SELECT DISTINCT unnest(source_tags || ARRAY[:tag]))。"""
    return sa.text(
        "ARRAY(SELECT DISTINCT unnest(student_kp.source_tags || ARRAY[:tag]))"
    ).bindparams(tag=tag)


async def _textbook_node_ids(
    db: AsyncSession, *, textbook_version: str, grade: str, semester: str
) -> list[uuid.UUID]:
    """教材 → curriculum_units → unit_node → 去重 node_ids(教材应学全集)。"""
    return list((await db.execute(
        sa.select(sa.distinct(UnitNode.node_id))
        .join(CurriculumUnit, CurriculumUnit.id == UnitNode.unit_id)
        .where(CurriculumUnit.textbook_version == textbook_version,
               CurriculumUnit.grade == grade, CurriculumUnit.semester == semester)
    )).scalars().all())


async def enroll_textbook(
    db: AsyncSession, *, student_id: uuid.UUID, textbook_version: str, grade: str, semester: str,
) -> int:
    """把该教材单元的 node 全集纳入个人体系(in_scope=true,source += textbook)。

    幂等:已存在的节点只置 in_scope=true + 追加 'textbook',**不覆盖练习计数/掌握度**。
    返回纳入(涉及)的 node 数。
    """
    node_ids = await _textbook_node_ids(
        db, textbook_version=textbook_version, grade=grade, semester=semester)
    for nid in node_ids:
        await db.execute(
            pg_insert(StudentKp)
            .values(student_id=student_id, node_id=nid, in_scope=True, source_tags=["textbook"])
            .on_conflict_do_update(
                index_elements=["student_id", "node_id"],
                set_={"in_scope": True, "source_tags": _append_tag_expr("textbook")},
            )
        )
    await db.flush()
    return len(node_ids)


async def add_source(
    db: AsyncSession, *, student_id: uuid.UUID, node_id: uuid.UUID, tag: str,
    in_scope: bool = True,
) -> None:
    """KP 进入个人体系的来源追加(去重)。新行带该来源;已存在追加并置 in_scope。"""
    await db.execute(
        pg_insert(StudentKp)
        .values(student_id=student_id, node_id=node_id, in_scope=in_scope, source_tags=[tag])
        .on_conflict_do_update(
            index_elements=["student_id", "node_id"],
            set_={"in_scope": in_scope, "source_tags": _append_tag_expr(tag)},
        )
    )
    await db.flush()
