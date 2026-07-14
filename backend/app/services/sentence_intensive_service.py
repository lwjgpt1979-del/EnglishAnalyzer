"""长难句精讲(作业精讲/课程精讲 的「长难句」模块)取数。

- 作业:学生「加入待学习」的长难句(student_long_sentence,带 source_paper_id)→ 按【卷=批次】归组;
- 课程:教材长难句(long_sentence source_kind=textbook,按学生教材版本 + 单元)→ 按【年级→册→单元】归组;
- 每句「详解」= 长难句解析页(前端点进传 text)。
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d1_users import User
from app.models.d4_knowledge import CurriculumUnit
from app.models.d13_v2_user_papers import UserUploadedPaper
from app.models.d20_long_sentence import LongSentence, StudentLongSentence


# ── 作业精讲 · 长难句:按卷(批次)──────────────────────────────────────────────
async def homework_batches(db: AsyncSession, *, student_id: uuid.UUID) -> list[dict]:
    """学生加入待学习的长难句,按来源卷(批次)归组。年月日倒序。"""
    rows = (await db.execute(
        select(StudentLongSentence.source_paper_id,
               func.count(func.distinct(StudentLongSentence.text)),   # 同句只算一条(存量可能有重复行)
               UserUploadedPaper.title, UserUploadedPaper.created_at)
        .join(UserUploadedPaper, UserUploadedPaper.id == StudentLongSentence.source_paper_id)
        .where(StudentLongSentence.owner_id == student_id,
               StudentLongSentence.source_paper_id.isnot(None),
               StudentLongSentence.status == "published")
        .group_by(StudentLongSentence.source_paper_id, UserUploadedPaper.title, UserUploadedPaper.created_at)
        .order_by(UserUploadedPaper.created_at.desc()))).all()
    return [{"paper_id": str(pid), "title": title or "未命名试卷",
             "date": created_at.strftime("%Y-%m-%d") if created_at else "",
             "count": int(cnt)} for pid, cnt, title, created_at in rows]


async def homework_sentences(db: AsyncSession, *, student_id: uuid.UUID,
                             paper_id: uuid.UUID) -> list[dict]:
    """某批次(卷)里加入待学习的长难句(按文本去重,存量可能有重复行)。"""
    rows = (await db.execute(
        select(StudentLongSentence.text, func.min(StudentLongSentence.created_at).label("ca"))
        .where(StudentLongSentence.owner_id == student_id,
               StudentLongSentence.source_paper_id == paper_id,
               StudentLongSentence.status == "published")
        .group_by(StudentLongSentence.text)
        .order_by(func.min(StudentLongSentence.created_at).desc()))).all()
    return [{"text": t} for t, _ in rows]


# ── 课程精讲 · 长难句:按教材单元 ──────────────────────────────────────────────
async def course_units(db: AsyncSession, *, student_id: uuid.UUID) -> dict:
    """学生当前教材的长难句单元 + 每单元句数,供【年级→册→单元】下钻。
    教材长难句 = long_sentence(source_kind=textbook,有 unit_id)。"""
    student = await db.get(User, student_id)
    tv = student.preferred_textbook_version if student else None
    if not tv:
        return {"version": None, "units": []}
    rows = (await db.execute(
        select(CurriculumUnit.id, CurriculumUnit.grade, CurriculumUnit.semester,
               CurriculumUnit.unit_no, CurriculumUnit.unit_title, func.count(LongSentence.id))
        .join(LongSentence, LongSentence.unit_id == CurriculumUnit.id)
        .where(CurriculumUnit.textbook_version == tv,
               LongSentence.source_kind == "textbook",
               LongSentence.status == "published")
        .group_by(CurriculumUnit.id, CurriculumUnit.grade, CurriculumUnit.semester,
                  CurriculumUnit.unit_no, CurriculumUnit.unit_title)
        .order_by(CurriculumUnit.grade, CurriculumUnit.semester, CurriculumUnit.unit_no))).all()
    units = [{"unit_id": str(uid), "grade": grade, "semester": sem, "unit_no": uno,
              "unit_title": title or f"Unit {uno}", "count": int(cnt)}
             for uid, grade, sem, uno, title, cnt in rows]
    return {"version": tv, "units": units}


async def course_sentences(db: AsyncSession, *, unit_id: uuid.UUID) -> list[dict]:
    """某教材单元的长难句。"""
    rows = (await db.execute(
        select(LongSentence.text).where(
            LongSentence.unit_id == unit_id, LongSentence.source_kind == "textbook",
            LongSentence.status == "published").order_by(LongSentence.difficulty.desc()))).scalars().all()
    return [{"text": t} for t in rows]
