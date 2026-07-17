"""长难句精讲(作业精讲/课程精讲 的「长难句」模块)取数。

- 作业:学生「加入待学习」的长难句(student_long_sentence,带 source_paper_id)→ 按【卷=批次】归组;
- 课程:教材长难句(long_sentence source_kind=textbook,按学生教材版本 + 单元)→ 按【年级→册→单元】归组;
- 每句「详解」= 长难句解析页(前端点进传 text)。
"""
from __future__ import annotations

import uuid

from sqlalchemy import case, func, select
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
               # 已看过解析(analysis_json 非空)的句数 = studied
               func.count(func.distinct(case(
                   (StudentLongSentence.analysis_json.isnot(None), StudentLongSentence.text)))),
               UserUploadedPaper.title, UserUploadedPaper.created_at)
        .join(UserUploadedPaper, UserUploadedPaper.id == StudentLongSentence.source_paper_id)
        .where(StudentLongSentence.owner_id == student_id,
               StudentLongSentence.source_paper_id.isnot(None),
               StudentLongSentence.status == "published")
        .group_by(StudentLongSentence.source_paper_id, UserUploadedPaper.title, UserUploadedPaper.created_at)
        .order_by(UserUploadedPaper.created_at.desc()))).all()
    return [{"paper_id": str(pid), "title": title or "未命名试卷",
             "date": created_at.strftime("%Y-%m-%d") if created_at else "",
             "count": int(cnt), "studied": int(st)}
            for pid, cnt, st, title, created_at in rows]


async def homework_sentences(db: AsyncSession, *, student_id: uuid.UUID,
                             paper_id: uuid.UUID) -> list[dict]:
    """某批次(卷)里加入待学习的长难句(按文本去重,存量可能有重复行);
    带 studied(该句是否已学=有过解析 analysis_json)。"""
    rows = (await db.execute(
        select(StudentLongSentence.text, func.min(StudentLongSentence.created_at).label("ca"),
               func.bool_or(StudentLongSentence.analysis_json.isnot(None)))
        .where(StudentLongSentence.owner_id == student_id,
               StudentLongSentence.source_paper_id == paper_id,
               StudentLongSentence.status == "published")
        .group_by(StudentLongSentence.text)
        .order_by(func.min(StudentLongSentence.created_at).desc()))).all()
    return [{"text": t, "studied": bool(st)} for t, _, st in rows]


# ── 课程精讲 · 长难句:按教材单元 ──────────────────────────────────────────────
async def course_units(db: AsyncSession, *, student_id: uuid.UUID,
                       grade: str | None = None, semester: str | None = None) -> dict:
    """学生当前教材某学期的长难句单元(默认聚焦 preferred 当前学期)+ 每单元句数/已学数,
    含闯关顺序解锁 + 本学期通关 + 下学期。教材长难句 = long_sentence(source_kind=textbook,有 unit_id)。"""
    from app.services.course_intensive_util import decorate_units, next_semester, resolve_semester
    student = await db.get(User, student_id)
    tv = student.preferred_textbook_version if student else None
    if not tv:
        return {"version": None, "grade": None, "semester": None, "units": [],
                "semester_done": False, "next_semester": None}
    g, s = await resolve_semester(db, tv, student, grade, semester)
    rows = (await db.execute(
        select(CurriculumUnit.id, CurriculumUnit.grade, CurriculumUnit.semester,
               CurriculumUnit.unit_no, CurriculumUnit.unit_title,
               func.count(func.distinct(LongSentence.id)),
               # 已学句数 = 该生对该句文本有过解析(student_long_sentence.analysis_json 非空)
               func.count(func.distinct(case(
                   (StudentLongSentence.analysis_json.isnot(None), LongSentence.id)))))
        .join(LongSentence, LongSentence.unit_id == CurriculumUnit.id)
        .outerjoin(StudentLongSentence,
                   (StudentLongSentence.text == LongSentence.text)
                   & (StudentLongSentence.owner_id == student_id))
        .where(CurriculumUnit.textbook_version == tv,
               LongSentence.source_kind == "textbook",
               LongSentence.status == "published",
               CurriculumUnit.grade == g, CurriculumUnit.semester == s)
        .group_by(CurriculumUnit.id, CurriculumUnit.grade, CurriculumUnit.semester,
                  CurriculumUnit.unit_no, CurriculumUnit.unit_title)
        .order_by(CurriculumUnit.unit_no))).all()
    units = [{"unit_id": str(uid), "grade": gr, "semester": sem, "unit_no": uno,
              "unit_title": title or f"Unit {uno}", "count": int(cnt),
              "total": int(cnt), "studied": int(st)}
             for uid, gr, sem, uno, title, cnt, st in rows]
    done = decorate_units(units)
    return {"version": tv, "grade": g, "semester": s, "units": units,
            "semester_done": done,
            "next_semester": await next_semester(db, tv, g, s) if done else None}


async def course_sentences(db: AsyncSession, *, unit_id: uuid.UUID,
                          student_id: uuid.UUID | None = None) -> list[dict]:
    """某教材单元的长难句;传 student_id 则每句带 studied(该生对该句文本有过解析)。"""
    rows = (await db.execute(
        select(LongSentence.text).where(
            LongSentence.unit_id == unit_id, LongSentence.source_kind == "textbook",
            LongSentence.status == "published").order_by(LongSentence.difficulty.desc()))).scalars().all()
    studied_texts: set = set()
    if student_id is not None and rows:
        studied_texts = set((await db.execute(
            select(StudentLongSentence.text).where(
                StudentLongSentence.owner_id == student_id,
                StudentLongSentence.analysis_json.isnot(None),
                StudentLongSentence.text.in_(list(rows))))).scalars().all())
    return [{"text": t, "studied": t in studied_texts} for t in rows]
