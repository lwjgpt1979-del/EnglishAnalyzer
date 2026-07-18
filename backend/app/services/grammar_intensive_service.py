"""语法精讲(作业精讲/课程精讲 的「语法精讲」模块)取数。

- 作业:学生「加入待学习」的语法点(student_kp_target,带 source_paper_id)→ 按【卷=批次】归组;
- 课程:学生当前教材单元里的语法点(unit_node→knowledge_nodes cf/jf)→ 按【年级→册→单元】归组;
- 每个语法点的「详解」= 讲解页 kp-content(kp_lecture),前端点进即到。
"""
from __future__ import annotations

import uuid

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d1_users import User
from app.models.d4_knowledge import CurriculumUnit
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d17_curriculum_kg import UnitNode
from app.models.d26_kp_target import StudentKpTarget
from app.models.d13_v2_user_papers import UserUploadedPaper

_GRAMMAR = (KnowledgeNode.code.ilike("cf%")) | (KnowledgeNode.code.ilike("jf%"))


def _pt(nid, name, code) -> dict:
    return {"node_id": str(nid), "name": name, "code": code, "personal": False}


def _mastery(has_row, recog, det, prod, transfer) -> dict | None:
    """四维掌握度(识别/纠错/产出 各 0–1 + 迁移布尔);无 student_grammar_mastery 行(未学)返回 None。"""
    if not has_row:
        return None
    return {"recognize": float(recog or 0), "detect": float(det or 0),
            "produce": float(prod or 0), "transfer": bool(transfer)}


# ── 作业精讲 · 语法:按卷(批次)──────────────────────────────────────────────
async def homework_batches(db: AsyncSession, *, student_id: uuid.UUID) -> list[dict]:
    """学生作业里的语法点,按来源卷(批次)归组。年月日倒序。
    含两类:①匹配上图谱的语法(student_kp_target,cf/jf);②没匹配上的个人语法(挂个人树)。"""
    from app.models.d27_student_grammar import StudentGrammarNode
    from app.models.d4_knowledge import StudentGrammarMastery
    kp = (await db.execute(
        select(StudentKpTarget.source_paper_id, func.count(func.distinct(StudentKpTarget.node_id)),
               # 已学过的点数(该生该点有 student_grammar_mastery 行)= studied
               func.count(func.distinct(case(
                   (StudentGrammarMastery.id.isnot(None), StudentKpTarget.node_id)))),
               UserUploadedPaper.title, UserUploadedPaper.created_at)
        .join(KnowledgeNode, KnowledgeNode.id == StudentKpTarget.node_id)
        .join(UserUploadedPaper, UserUploadedPaper.id == StudentKpTarget.source_paper_id)
        .outerjoin(StudentGrammarMastery,
                   (StudentGrammarMastery.kp_id == StudentKpTarget.node_id)
                   & (StudentGrammarMastery.student_id == student_id))
        .where(StudentKpTarget.student_id == student_id,
               StudentKpTarget.source_paper_id.isnot(None), _GRAMMAR)
        .group_by(StudentKpTarget.source_paper_id, UserUploadedPaper.title, UserUploadedPaper.created_at))).all()
    pers = (await db.execute(
        select(StudentGrammarNode.source_paper_id, func.count(StudentGrammarNode.id),
               UserUploadedPaper.title, UserUploadedPaper.created_at)
        .join(UserUploadedPaper, UserUploadedPaper.id == StudentGrammarNode.source_paper_id)
        .where(StudentGrammarNode.student_id == student_id,
               StudentGrammarNode.source_paper_id.isnot(None),
               StudentGrammarNode.ref_node_id.is_(None))   # 未匹配图谱的个人语法
        .group_by(StudentGrammarNode.source_paper_id, UserUploadedPaper.title, UserUploadedPaper.created_at))).all()
    merged: dict = {}
    for pid, cnt, studied, title, ca in kp:
        m = merged.setdefault(pid, {"title": title, "ca": ca, "count": 0, "studied": 0})
        m["count"] += int(cnt); m["studied"] += int(studied)
    for pid, cnt, title, ca in pers:   # 个人语法只计入总数,不计已学
        m = merged.setdefault(pid, {"title": title, "ca": ca, "count": 0, "studied": 0})
        m["count"] += int(cnt)
    out = [{"paper_id": str(pid), "title": m["title"] or "未命名作业",
            "date": m["ca"].strftime("%Y-%m-%d") if m["ca"] else "",
            "count": m["count"], "studied": m["studied"]}
           for pid, m in merged.items()]
    out.sort(key=lambda x: x["date"], reverse=True)
    return out


async def homework_points(db: AsyncSession, *, student_id: uuid.UUID,
                          paper_id: uuid.UUID) -> list[dict]:
    """某批次(卷)里的语法点:匹配上图谱的(可跳讲解)+ 未匹配的个人语法(personal,按名练习)。
    带 studied(该点是否已学=有 student_grammar_mastery 行;个人语法暂计未学)。"""
    from app.models.d27_student_grammar import StudentGrammarNode
    from app.models.d4_knowledge import StudentGrammarMastery
    rows = (await db.execute(
        select(KnowledgeNode.id, KnowledgeNode.name, KnowledgeNode.code,
               StudentGrammarMastery.id.isnot(None),
               StudentGrammarMastery.mastery_recognize, StudentGrammarMastery.mastery_detect,
               StudentGrammarMastery.mastery_produce, StudentGrammarMastery.transfer_ok)
        .join(StudentKpTarget, StudentKpTarget.node_id == KnowledgeNode.id)
        .outerjoin(StudentGrammarMastery,
                   (StudentGrammarMastery.kp_id == KnowledgeNode.id)
                   & (StudentGrammarMastery.student_id == student_id))
        .where(StudentKpTarget.student_id == student_id,
               StudentKpTarget.source_paper_id == paper_id, _GRAMMAR)
        .order_by(KnowledgeNode.code))).all()
    out = [{**_pt(nid, name, code), "studied": bool(st),
            "mastery": _mastery(st, recog, det, prod, tr)}
           for nid, name, code, st, recog, det, prod, tr in rows]
    pers = (await db.execute(
        select(StudentGrammarNode.id, StudentGrammarNode.name)
        .where(StudentGrammarNode.student_id == student_id,
               StudentGrammarNode.source_paper_id == paper_id,
               StudentGrammarNode.ref_node_id.is_(None))
        .order_by(StudentGrammarNode.name))).all()
    for sgn_id, pname in pers:
        out.append({"node_id": None, "name": pname, "code": None, "personal": True,
                    "sgn_id": str(sgn_id), "studied": False, "mastery": None})
    return out


# ── 课程精讲 · 语法:按教材单元 ────────────────────────────────────────────────
async def course_units(db: AsyncSession, *, student_id: uuid.UUID,
                       grade: str | None = None, semester: str | None = None) -> dict:
    """学生当前教材某学期的单元(默认聚焦 preferred 当前学期)+ 每单元语法点数/已学数,
    含闯关顺序解锁 + 本学期通关 + 下学期。"""
    from app.models.d4_knowledge import StudentGrammarMastery
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
               func.count(func.distinct(UnitNode.node_id)),
               # 已学点数 = 该生该点有 student_grammar_mastery 行
               func.count(func.distinct(case(
                   (StudentGrammarMastery.id.isnot(None), UnitNode.node_id)))))
        .join(UnitNode, UnitNode.unit_id == CurriculumUnit.id)
        .join(KnowledgeNode, KnowledgeNode.id == UnitNode.node_id)
        .outerjoin(StudentGrammarMastery,
                   (StudentGrammarMastery.kp_id == UnitNode.node_id)
                   & (StudentGrammarMastery.student_id == student_id))
        .where(CurriculumUnit.textbook_version == tv, _GRAMMAR,
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


async def course_points(db: AsyncSession, *, unit_id: uuid.UUID,
                        student_id: uuid.UUID | None = None) -> list[dict]:
    """某教材单元的语法点;传 student_id 则每点带 studied(有无 student_grammar_mastery)。"""
    rows = (await db.execute(
        select(KnowledgeNode.id, KnowledgeNode.name, KnowledgeNode.code)
        .join(UnitNode, UnitNode.node_id == KnowledgeNode.id)
        .where(UnitNode.unit_id == unit_id, _GRAMMAR)
        .order_by(KnowledgeNode.code).distinct())).all()
    mastery_map: dict = {}   # kp_id → (recognize, detect, produce, transfer)
    if student_id is not None and rows:
        from app.models.d4_knowledge import StudentGrammarMastery
        mrows = (await db.execute(
            select(StudentGrammarMastery.kp_id, StudentGrammarMastery.mastery_recognize,
                   StudentGrammarMastery.mastery_detect, StudentGrammarMastery.mastery_produce,
                   StudentGrammarMastery.transfer_ok).where(
                StudentGrammarMastery.student_id == student_id,
                StudentGrammarMastery.kp_id.in_([nid for nid, _, _ in rows])))).all()
        mastery_map = {str(k): (r, d, p, t) for k, r, d, p, t in mrows}
    return [{**_pt(nid, name, code), "studied": str(nid) in mastery_map,
             "mastery": _mastery(str(nid) in mastery_map, *mastery_map.get(str(nid), (None, None, None, None)))}
            for nid, name, code in rows]
