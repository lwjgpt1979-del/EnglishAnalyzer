"""语法精讲(作业精讲/课程精讲 的「语法精讲」模块)取数。

- 作业:学生「加入待学习」的语法点(student_kp_target,带 source_paper_id)→ 按【卷=批次】归组;
- 课程:学生当前教材单元里的语法点(unit_node→knowledge_nodes cf/jf)→ 按【年级→册→单元】归组;
- 每个语法点的「详解」= 讲解页 kp-content(kp_lecture),前端点进即到。
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d1_users import User
from app.models.d4_knowledge import CurriculumUnit
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d17_curriculum_kg import UnitNode
from app.models.d26_kp_target import StudentKpTarget
from app.models.d13_v2_user_papers import UserUploadedPaper

_GRAMMAR = (KnowledgeNode.code.ilike("cf%")) | (KnowledgeNode.code.ilike("jf%"))


def _pt(nid, name, code) -> dict:
    return {"node_id": str(nid), "name": name, "code": code}


# ── 作业精讲 · 语法:按卷(批次)──────────────────────────────────────────────
async def homework_batches(db: AsyncSession, *, student_id: uuid.UUID) -> list[dict]:
    """学生加入待学习的语法点,按来源卷(批次)归组。年月日倒序。"""
    rows = (await db.execute(
        select(StudentKpTarget.source_paper_id, func.count(StudentKpTarget.id),
               UserUploadedPaper.title, UserUploadedPaper.created_at)
        .join(KnowledgeNode, KnowledgeNode.id == StudentKpTarget.node_id)
        .join(UserUploadedPaper, UserUploadedPaper.id == StudentKpTarget.source_paper_id)
        .where(StudentKpTarget.student_id == student_id,
               StudentKpTarget.source_paper_id.isnot(None), _GRAMMAR)
        .group_by(StudentKpTarget.source_paper_id, UserUploadedPaper.title, UserUploadedPaper.created_at)
        .order_by(UserUploadedPaper.created_at.desc()))).all()
    return [{"paper_id": str(pid), "title": title or "未命名试卷",
             "date": created_at.strftime("%Y-%m-%d") if created_at else "",
             "count": int(cnt)} for pid, cnt, title, created_at in rows]


async def homework_points(db: AsyncSession, *, student_id: uuid.UUID,
                          paper_id: uuid.UUID) -> list[dict]:
    """某批次(卷)里加入待学习的语法点。"""
    rows = (await db.execute(
        select(KnowledgeNode.id, KnowledgeNode.name, KnowledgeNode.code)
        .join(StudentKpTarget, StudentKpTarget.node_id == KnowledgeNode.id)
        .where(StudentKpTarget.student_id == student_id,
               StudentKpTarget.source_paper_id == paper_id, _GRAMMAR)
        .order_by(KnowledgeNode.code))).all()
    return [_pt(nid, name, code) for nid, name, code in rows]


# ── 课程精讲 · 语法:按教材单元 ────────────────────────────────────────────────
async def course_units(db: AsyncSession, *, student_id: uuid.UUID) -> dict:
    """学生当前教材单元 + 每单元语法点数,供【年级→册→单元】下钻。"""
    student = await db.get(User, student_id)
    tv = student.preferred_textbook_version if student else None
    if not tv:
        return {"version": None, "units": []}
    rows = (await db.execute(
        select(CurriculumUnit.id, CurriculumUnit.grade, CurriculumUnit.semester,
               CurriculumUnit.unit_no, CurriculumUnit.unit_title,
               func.count(func.distinct(UnitNode.node_id)))
        .join(UnitNode, UnitNode.unit_id == CurriculumUnit.id)
        .join(KnowledgeNode, KnowledgeNode.id == UnitNode.node_id)
        .where(CurriculumUnit.textbook_version == tv, _GRAMMAR)
        .group_by(CurriculumUnit.id, CurriculumUnit.grade, CurriculumUnit.semester,
                  CurriculumUnit.unit_no, CurriculumUnit.unit_title)
        .order_by(CurriculumUnit.grade, CurriculumUnit.semester, CurriculumUnit.unit_no))).all()
    units = [{"unit_id": str(uid), "grade": grade, "semester": sem, "unit_no": uno,
              "unit_title": title or f"Unit {uno}", "count": int(cnt)}
             for uid, grade, sem, uno, title, cnt in rows]
    return {"version": tv, "units": units}


async def course_points(db: AsyncSession, *, unit_id: uuid.UUID) -> list[dict]:
    """某教材单元的语法点。"""
    rows = (await db.execute(
        select(KnowledgeNode.id, KnowledgeNode.name, KnowledgeNode.code)
        .join(UnitNode, UnitNode.node_id == KnowledgeNode.id)
        .where(UnitNode.unit_id == unit_id, _GRAMMAR)
        .order_by(KnowledgeNode.code).distinct())).all()
    return [_pt(nid, name, code) for nid, name, code in rows]
