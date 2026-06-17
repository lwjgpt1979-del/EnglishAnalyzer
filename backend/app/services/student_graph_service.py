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

import datetime as _dt

from app.models.d4_knowledge import CurriculumUnit
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import (
    StudentKp, AnswerLog, PlatformQuestionKp,
)
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


def _status(mastery, practice_count: int, wrong_count: int) -> str:
    """掌握=mastery≥1;薄弱=有错未掌握;已练=练过未错未掌握;未学=在全集未练。"""
    if mastery is not None and float(mastery) >= 1.0:
        return "mastered"
    if wrong_count > 0:
        return "weak"
    if practice_count > 0:
        return "practiced"
    return "unlearned"


async def get_graph(
    db: AsyncSession, *, student_id: uuid.UUID, include_all: bool = False,
) -> list[dict]:
    """个人知识地图:默认只亮已练/已错(practice_count>0 或 wrong_count>0);
    include_all=True 加上 in_scope 的未学节点(教材全集展开)。"""
    stmt = (
        sa.select(StudentKp.node_id, KnowledgeNode.name, KnowledgeNode.axis,
                  KnowledgeNode.node_kind, StudentKp.mastery, StudentKp.practice_count,
                  StudentKp.wrong_count, StudentKp.source_tags, StudentKp.in_scope)
        .join(KnowledgeNode, KnowledgeNode.id == StudentKp.node_id)
        .where(StudentKp.student_id == student_id)
    )
    if not include_all:
        stmt = stmt.where(sa.or_(StudentKp.practice_count > 0, StudentKp.wrong_count > 0))
    stmt = stmt.order_by(StudentKp.wrong_count.desc(), StudentKp.last_practice_at.desc().nullslast())
    rows = (await db.execute(stmt)).all()
    return [
        {
            "node_id": nid, "name": name, "axis": axis, "node_kind": nk,
            "mastery": float(mastery) if mastery is not None else None,
            "practice_count": pc, "wrong_count": wc, "source_tags": list(tags or []),
            "in_scope": in_scope, "status": _status(mastery, pc, wc),
        }
        for nid, name, axis, nk, mastery, pc, wc, tags, in_scope in rows
    ]


async def graph_summary(db: AsyncSession, *, student_id: uuid.UUID) -> dict:
    """图谱总览:全集 / 已练 / 薄弱 / 已掌握。"""
    base = sa.select(StudentKp).where(StudentKp.student_id == student_id).subquery()
    total_scope = (await db.execute(
        sa.select(sa.func.count()).where(base.c.in_scope.is_(True))
    )).scalar_one()
    practiced = (await db.execute(
        sa.select(sa.func.count()).where(sa.or_(base.c.practice_count > 0, base.c.wrong_count > 0))
    )).scalar_one()
    weak = (await db.execute(
        sa.select(sa.func.count()).where(
            base.c.wrong_count > 0,
            sa.or_(base.c.mastery.is_(None), base.c.mastery < 1.0))
    )).scalar_one()
    mastered = (await db.execute(
        sa.select(sa.func.count()).where(base.c.mastery >= 1.0)
    )).scalar_one()
    return {"in_scope": total_scope, "practiced": practiced, "weak": weak, "mastered": mastered}


async def node_trend(
    db: AsyncSession, *, student_id: uuid.UUID, node_id: uuid.UUID,
    days: int = 30, today: _dt.date | None = None,
) -> list[dict]:
    """某 node 掌握趋势:answer_log 按日聚合 accuracy(只算该 node 的平台题作答)。"""
    today = today or _dt.date.today()
    since = today - _dt.timedelta(days=days)
    day = sa.cast(AnswerLog.answered_at, sa.Date).label("d")
    rows = (await db.execute(
        sa.select(
            day,
            sa.func.count().label("total"),
            sa.func.sum(sa.case((AnswerLog.is_correct.is_(True), 1), else_=0)).label("correct"),
        )
        .join(PlatformQuestionKp, PlatformQuestionKp.question_id == AnswerLog.question_id)
        .where(AnswerLog.student_id == student_id,
               PlatformQuestionKp.node_id == node_id,
               sa.cast(AnswerLog.answered_at, sa.Date) >= since)
        .group_by(day).order_by(day)
    )).all()
    out = []
    for d, total, correct in rows:
        c = int(correct or 0)
        out.append({"date": d, "accuracy": round(c / total, 4) if total else 0.0,
                    "correct": c, "wrong": int(total) - c})
    return out
