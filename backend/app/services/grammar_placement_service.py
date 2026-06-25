"""R10.6 语法分级测验(CAT 冷启动定级)。

设计见 docs/R10-...§4。用最少题给「目标教材×年级(±前置)语法点」设起始掌握先验,定起点。
- 题库圈定:curriculum(textbook×grade)→ applicable_grades/textbooks 兜底 →(显式 kp_ids 覆盖)。
- 自适应路由:在难度阶梯上二分定位「会/不会」的分界。
- 知识空间推断:过下游→上游推定会;败基础→下游推定不会(免逐点考)。
- BKT 暖启动:每点写 student_grammar_mastery.mastery_recognize 先验(prior_source=placement,低置信)。
- 产出:掌握热力图 + 学习起点线。仅设先验、不判真会(真会交日常四维 + 间隔环)。
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d4_knowledge import (
    KnowledgePoint, CurriculumUnit, UnitKnowledgePoint,
    StudentGrammarMastery, GrammarPlacementSession,
)
from app.services import grammar_probe_service as gp

_log = logging.getLogger(__name__)

MAX_ITEMS = 25                          # 单次测验最多题数(控时)
# 暖启动先验:测对/测错/推定会/推定不会
_PRIOR_ASKED_OK = 0.70
_PRIOR_ASKED_NO = 0.10
_PRIOR_INFER_OK = 0.55
_PRIOR_INFER_NO = 0.15
# 年级难度阶梯(由浅到深;target 及之前的都纳入前置)
_GRADE_LADDER = ["小学3年级", "小学4年级", "小学5年级", "小学6年级",
                 "七年级", "八年级", "九年级", "初一", "初二", "初三"]


def _grade_scope(grade: str | None) -> list[str]:
    """目标年级 + 其之前的年级(找地基洞)。未知年级→仅该年级。"""
    if not grade or grade not in _GRADE_LADDER:
        return [grade] if grade else []
    return _GRADE_LADDER[: _GRADE_LADDER.index(grade) + 1]


# ── 题库圈定(级联兜底)──────────────────────────────────────────────────
async def build_pool(db: AsyncSession, *, textbook: str | None, grade: str | None,
                     kp_ids: list | None = None) -> list[dict]:
    """返回按难度排序的题库 [{kp_id, name}]。显式 kp_ids > curriculum > applicable 兜底 > 全量。"""
    if kp_ids:
        ids = []
        for k in kp_ids:
            try:
                ids.append(uuid.UUID(str(k)))
            except (ValueError, TypeError):
                continue
        rows = (await db.execute(
            sa.select(KnowledgePoint.id, KnowledgePoint.name)
            .where(KnowledgePoint.id.in_(ids)))).all()
        order = {x: i for i, x in enumerate(ids)}
        out = [{"kp_id": str(r[0]), "name": r[1]} for r in rows]
        out.sort(key=lambda d: order.get(uuid.UUID(d["kp_id"]), 1e9))
        return out

    grades = _grade_scope(grade)
    # 1) curriculum 映射(textbook × 前置年级),按 年级→单元 排序
    if textbook and grades:
        rows = (await db.execute(
            sa.select(KnowledgePoint.id, KnowledgePoint.name, CurriculumUnit.grade, CurriculumUnit.unit_no)
            .select_from(UnitKnowledgePoint)
            .join(CurriculumUnit, CurriculumUnit.id == UnitKnowledgePoint.unit_id)
            .join(KnowledgePoint, KnowledgePoint.id == UnitKnowledgePoint.knowledge_point_id)
            .where(CurriculumUnit.textbook_version == textbook,
                   CurriculumUnit.grade.in_(grades),
                   KnowledgePoint.category == "grammar"))).all()
        if rows:
            def _grank(g):
                return _GRADE_LADDER.index(g) if g in _GRADE_LADDER else 99
            rows = sorted(rows, key=lambda r: (_grank(r[2]), r[3] or 0))
            seen, out = set(), []
            for r in rows:
                if r[0] not in seen:
                    seen.add(r[0])
                    out.append({"kp_id": str(r[0]), "name": r[1]})
            return out

    # 2) applicable_grades / applicable_textbooks 兜底
    cond = [KnowledgePoint.category == "grammar"]
    if grades:
        cond.append(sa.or_(KnowledgePoint.applicable_grades.op("&&")(sa.cast(grades, sa.ARRAY(sa.String))),
                           KnowledgePoint.applicable_grades == sa.cast([], sa.ARRAY(sa.String))))
    rows = (await db.execute(
        sa.select(KnowledgePoint.id, KnowledgePoint.name)
        .where(*cond).order_by(KnowledgePoint.sort_order, KnowledgePoint.name).limit(60))).all()
    return [{"kp_id": str(r[0]), "name": r[1]} for r in rows]


# ── 取题(在 [lo,hi] 内靠中位、可出题的点)────────────────────────────────
async def _servable_item(db: AsyncSession, pool: list, lo: int, hi: int, asked_idx: set) -> dict | None:
    """在 [lo,hi] 内、优先中位、未问过且能出识别题的点,返回 {idx, kp_id, item}。"""
    if lo > hi:
        return None
    mid = (lo + hi) // 2
    order = sorted(range(lo, hi + 1), key=lambda i: abs(i - mid))   # 由近及远找可出题点
    for i in order:
        if i in asked_idx:
            continue
        kid = uuid.UUID(pool[i]["kp_id"])
        kp = (await db.execute(sa.select(KnowledgePoint).where(KnowledgePoint.id == kid))).scalar_one_or_none()
        if kp is None:
            continue
        p = await gp.ensure_probes(db, kp)
        recog = p.get("recognize") or []
        if not recog:
            continue
        opts = list(recog[0]["options"])
        return {"idx": i, "kp_id": pool[i]["kp_id"], "kp_name": kp.name,
                "item": {"key": "recognize:0", "stem": recog[0]["stem"], "options": opts}}
    return None


def _progress(session: GrammarPlacementSession) -> dict:
    return {"asked": len(session.asked or []), "max": MAX_ITEMS,
            "pool": len(session.pool_kp_ids or [])}


# ── 开始 ────────────────────────────────────────────────────────────────
async def start(db: AsyncSession, *, student_id: uuid.UUID, textbook: str | None = None,
                grade: str | None = None, kp_ids: list | None = None) -> dict:
    pool = await build_pool(db, textbook=textbook, grade=grade, kp_ids=kp_ids)
    if len(pool) < 2:
        raise AppError(code=400, message="题库不足,无法分级测验(请检查教材/年级或传入 kp_ids)")
    session = GrammarPlacementSession(
        id=uuid.uuid4(), student_id=student_id, textbook=textbook, grade=grade,
        pool_kp_ids=pool, asked=[], lo=0, hi=len(pool) - 1, status="active")
    db.add(session)
    await db.flush()
    served = await _servable_item(db, pool, session.lo, session.hi, set())
    if served is None:
        return await _finish(db, session)
    return {"session_id": str(session.id), "item": served, "progress": _progress(session), "done": False}


# ── 作答 + 路由 ──────────────────────────────────────────────────────────
async def answer(db: AsyncSession, *, student_id: uuid.UUID, session_id: uuid.UUID,
                 kp_id: str, chosen: str) -> dict:
    session = (await db.execute(
        sa.select(GrammarPlacementSession).where(
            GrammarPlacementSession.id == session_id,
            GrammarPlacementSession.student_id == student_id))).scalar_one_or_none()
    if session is None:
        raise AppError(code=404, message="测验会话不存在")
    if session.status != "active":
        return await _finish(db, session)

    pool = session.pool_kp_ids or []
    idx = next((i for i, d in enumerate(pool) if d["kp_id"] == kp_id), None)
    if idx is None:
        raise AppError(code=400, message="该题不在本次题库")
    kp = (await db.execute(sa.select(KnowledgePoint).where(KnowledgePoint.id == uuid.UUID(kp_id)))).scalar_one_or_none()
    recog = (kp.grammar_probes_json or {}).get("recognize") if kp else None
    if not recog:
        raise AppError(code=400, message="题目缺失")
    correct = (chosen or "").strip() == str(recog[0]["answer"]).strip()

    asked = list(session.asked or [])
    asked.append({"idx": idx, "kp_id": kp_id, "correct": correct})
    session.asked = asked
    # 二分:对→该点及更易推定会(lo=idx+1);错→该点及更难推定不会(hi=idx-1)
    if correct:
        session.lo = max(session.lo, idx + 1)
    else:
        session.hi = min(session.hi, idx - 1)
    session.updated_at = datetime.now(timezone.utc)
    await db.flush()

    if len(asked) >= MAX_ITEMS or session.lo > session.hi:
        return await _finish(db, session)
    asked_idx = {a["idx"] for a in asked}
    served = await _servable_item(db, pool, session.lo, session.hi, asked_idx)
    if served is None:
        return await _finish(db, session)
    return {"session_id": str(session.id), "item": served, "progress": _progress(session), "done": False}


# ── 收尾:暖启动先验 + 热力图 ────────────────────────────────────────────
def _bucket(prior: float) -> str:
    if prior >= 0.6:
        return "已会"
    if prior >= 0.4:
        return "临界"
    if prior >= 0.2:
        return "薄弱"
    return "未学"


async def _finish(db: AsyncSession, session: GrammarPlacementSession) -> dict:
    pool = session.pool_kp_ids or []
    asked = {a["idx"]: a["correct"] for a in (session.asked or [])}
    lo = session.lo   # lo 之前推定会、lo 及之后推定不会
    heatmap, priors = [], {}
    start_line = None
    now = datetime.now(timezone.utc)
    for i, d in enumerate(pool):
        if i in asked:
            prior = _PRIOR_ASKED_OK if asked[i] else _PRIOR_ASKED_NO
        elif i < lo:
            prior = _PRIOR_INFER_OK
        else:
            prior = _PRIOR_INFER_NO
        priors[d["kp_id"]] = prior
        bucket = _bucket(prior)
        heatmap.append({"kp_id": d["kp_id"], "name": d["name"], "prior": prior, "bucket": bucket})
        if start_line is None and prior < 0.5:
            start_line = {"kp_id": d["kp_id"], "name": d["name"], "index": i}
        # 暖启动:写入 mastery_recognize 先验(低置信)
        kid = uuid.UUID(d["kp_id"])
        m = (await db.execute(sa.select(StudentGrammarMastery).where(
            StudentGrammarMastery.student_id == session.student_id,
            StudentGrammarMastery.kp_id == kid))).scalar_one_or_none()
        if m is None:
            m = StudentGrammarMastery(id=uuid.uuid4(), student_id=session.student_id, kp_id=kid)
            db.add(m)
        if m.prior_source in (None, "default", "placement"):   # 不覆盖学生已实练出的掌握
            m.mastery_recognize = prior
            m.prior_source = "placement"
            m.last_seen_at = now
    session.status = "done"
    session.result_priors = priors
    session.updated_at = now
    await db.flush()
    return {"session_id": str(session.id), "done": True,
            "heatmap": heatmap, "start_line": start_line, "asked": len(session.asked or [])}


async def result(db: AsyncSession, *, student_id: uuid.UUID, session_id: uuid.UUID) -> dict:
    session = (await db.execute(
        sa.select(GrammarPlacementSession).where(
            GrammarPlacementSession.id == session_id,
            GrammarPlacementSession.student_id == student_id))).scalar_one_or_none()
    if session is None:
        raise AppError(code=404, message="测验会话不存在")
    if session.status != "done":
        return {"session_id": str(session_id), "done": False, "heatmap": [], "start_line": None}
    priors = session.result_priors or {}
    pool = session.pool_kp_ids or []
    heatmap = [{"kp_id": d["kp_id"], "name": d["name"],
                "prior": priors.get(d["kp_id"], _PRIOR_INFER_NO),
                "bucket": _bucket(priors.get(d["kp_id"], _PRIOR_INFER_NO))} for d in pool]
    sl = next((h for h in heatmap if h["prior"] < 0.5), None)
    return {"session_id": str(session_id), "done": True, "heatmap": heatmap,
            "start_line": sl, "asked": len(session.asked or [])}
