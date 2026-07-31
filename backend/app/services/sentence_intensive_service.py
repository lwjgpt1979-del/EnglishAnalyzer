"""长难句精讲(作业精讲/课程精讲 的「长难句」模块)取数。

- 作业:学生「加入待学习」的长难句(student_long_sentence,带 source_paper_id)→ 按【卷=批次】归组;
- 课程:单元理解向长难句(unit_understand_ls,后台 L1 抽尽/合成)→ 按【年级→册→单元】归组;
- 每句「详解」= 长难句解析页(前端点进传 text)。
"""
from __future__ import annotations

import uuid

from sqlalchemy import case, func, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d1_users import User
from app.models.d4_knowledge import CurriculumUnit
from app.models.d13_v2_user_papers import UserUploadedPaper
from app.models.d20_long_sentence import StudentLongSentence
from app.models.d29_unit_ls_understand import UnitUnderstandLs


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
               func.bool_or(StudentLongSentence.analysis_json.isnot(None)),
               func.bool_or(StudentLongSentence.did_comp),
               func.bool_or(StudentLongSentence.did_gram),
               func.bool_or(StudentLongSentence.did_word))
        .where(StudentLongSentence.owner_id == student_id,
               StudentLongSentence.source_paper_id == paper_id,
               StudentLongSentence.status == "published")
        .group_by(StudentLongSentence.text)
        .order_by(func.min(StudentLongSentence.created_at).desc()))).all()
    # ring 0-3 = 认成分 + 认语法 + 重点词 三态之和(蓝-4 徽章环)
    return [{"text": t, "studied": bool(st), "ring": int(bool(c)) + int(bool(g)) + int(bool(w))}
            for t, _, st, c, g, w in rows]


# ── 课程精讲 · 长难句:按教材单元(真源 unit_understand_ls)─────────────────────
async def course_units(db: AsyncSession, *, student_id: uuid.UUID,
                       grade: str | None = None, semester: str | None = None) -> dict:
    """学生当前教材某学期的长难句单元(默认聚焦 preferred 当前学期)+ 每单元句数/已学数,
    含闯关顺序解锁 + 本学期通关 + 下学期。
    数据真源:unit_understand_ls(后台「找出/合成长难句」);已学=该生对该句文本有过解析。"""
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
               func.count(func.distinct(UnitUnderstandLs.id)),
               func.count(func.distinct(case(
                   (StudentLongSentence.analysis_json.isnot(None), UnitUnderstandLs.id)))))
        .join(UnitUnderstandLs, UnitUnderstandLs.unit_id == CurriculumUnit.id)
        .outerjoin(StudentLongSentence,
                   (StudentLongSentence.text == UnitUnderstandLs.text)
                   & (StudentLongSentence.owner_id == student_id))
        .where(CurriculumUnit.textbook_version == tv,
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
    """某教材单元的理解向长难句;传 student_id 则每句带 studied(该生对该句文本有过解析)。"""
    rows = (await db.execute(
        select(UnitUnderstandLs.text)
        .where(UnitUnderstandLs.unit_id == unit_id)
        .order_by(UnitUnderstandLs.sort_order, UnitUnderstandLs.created_at)
    )).scalars().all()
    studied_texts: set = set()
    ring_map: dict = {}
    if student_id is not None and rows:
        srows = (await db.execute(
            select(StudentLongSentence.text,
                   func.bool_or(StudentLongSentence.analysis_json.isnot(None)),
                   func.bool_or(StudentLongSentence.did_comp),
                   func.bool_or(StudentLongSentence.did_gram),
                   func.bool_or(StudentLongSentence.did_word))
            .where(StudentLongSentence.owner_id == student_id,
                   StudentLongSentence.text.in_(list(rows)))
            .group_by(StudentLongSentence.text))).all()
        for t, st, c, g, w in srows:
            if st:
                studied_texts.add(t)
            ring_map[t] = int(bool(c)) + int(bool(g)) + int(bool(w))
    return [{"text": t, "studied": t in studied_texts, "ring": ring_map.get(t, 0)} for t in rows]


async def touch_sentence_studied(
    db: AsyncSession, *, student_id: uuid.UUID, text: str,
    analysis: dict | None = None, paper_id: uuid.UUID | None = None,
) -> None:
    """打开解析时:确保有 student_long_sentence 行并写入 analysis_json(看过即 studied)。

    无行时新建(可带 source_paper_id)。已有行只补空 analysis_json。best-effort,调用方 commit。
    """
    text = (text or "").strip()
    if not text:
        return
    rows = list((await db.execute(
        select(StudentLongSentence).where(
            StudentLongSentence.owner_id == student_id,
            StudentLongSentence.text == text,
        )
    )).scalars().all())
    payload = analysis if isinstance(analysis, dict) and analysis else {"viewed": True}
    if rows:
        for r in rows:
            if r.analysis_json is None:
                r.analysis_json = payload
        return
    db.add(StudentLongSentence(
        id=uuid.uuid4(),
        owner_id=student_id,
        text=text,
        analysis_json=payload,
        status="published",
        source_paper_id=paper_id,
    ))


async def mark_sentence_progress(db: AsyncSession, *, student_id: uuid.UUID,
                                 text: str, kind: str) -> dict:
    """标记某句三态之一(蓝-4 徽章环):kind ∈ {comp, gram, word}——学生在解析页答成分/语法题、
    看重点词时置位。按 (owner, text) 更新学生个人长难句行;未加入待学习(无行)则忽略。返回新 ring。"""
    col = {"comp": StudentLongSentence.did_comp,
           "gram": StudentLongSentence.did_gram,
           "word": StudentLongSentence.did_word}.get(kind)
    text = (text or "").strip()
    if col is None or not text:
        return {"ring": 0}
    await db.execute(
        sa_update(StudentLongSentence)
        .where(StudentLongSentence.owner_id == student_id, StudentLongSentence.text == text)
        .values({col: True}))
    await db.commit()
    row = (await db.execute(
        select(func.bool_or(StudentLongSentence.did_comp),
               func.bool_or(StudentLongSentence.did_gram),
               func.bool_or(StudentLongSentence.did_word))
        .where(StudentLongSentence.owner_id == student_id,
               StudentLongSentence.text == text))).first()
    ring = (int(bool(row[0])) + int(bool(row[1])) + int(bool(row[2]))) if row else 0
    return {"ring": ring}
