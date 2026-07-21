"""考点扩展测试题(vocab_kp_mcq)后台复核 API:按 report_count 筛被学生「换一题」报错的 AI 题,
AI 修正 / 人工编辑 / 删除 / 看修改记录 + 报错阈值配置。独立模块避免与 admin.py 冲突。"""
from __future__ import annotations

import uuid
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_role
from app.models.d1_users import User
from app.models.d5_learning import VocabularyWord
from app.models.d18_vocab_kg import VocabKpMcq, VocabKpMcqRevision
from app.schemas.base import BaseResponse, make_ok
from app.services import word_kp_service

router = APIRouter(prefix="/admin/kp-mcqs", tags=["admin-kp-mcq"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
AdminDep = Annotated[User, Depends(require_role("platform_admin"))]


def _row(m: VocabKpMcq, word: str) -> dict:
    return {"id": str(m.id), "word_id": str(m.word_id), "word": word, "dimension": m.dimension,
            "dimension_label": word_kp_service._dim_label(m.dimension), "stem": m.stem, "options": m.options,
            "answer": m.answer, "explanation": m.explanation or "", "report_count": m.report_count,
            "created_at": m.created_at.isoformat() if m.created_at else None}


@router.get("", response_model=BaseResponse[dict])
async def list_kp_mcqs(db: DbDep, admin: AdminDep, min_report: int = 1, skip: int = 0, limit: int = 20):
    """复核列表(分页):默认只列被报错过(report_count≥min_report)的题,按报错次数降序。"""
    base = sa.select(VocabKpMcq).where(VocabKpMcq.report_count >= min_report)
    total = (await db.execute(
        sa.select(sa.func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(
        base.order_by(VocabKpMcq.report_count.desc(), VocabKpMcq.created_at.desc())
        .offset(skip).limit(limit))).scalars().all()
    wmap = {}
    if rows:
        ws = (await db.execute(sa.select(VocabularyWord.id, VocabularyWord.word)
                               .where(VocabularyWord.id.in_([m.word_id for m in rows])))).all()
        wmap = {wid: w for wid, w in ws}
    threshold = await word_kp_service.get_report_threshold(db)
    return make_ok({"items": [_row(m, wmap.get(m.word_id, "")) for m in rows],
                    "total": total, "threshold": threshold})


@router.post("/{mcq_id}/fix", response_model=BaseResponse[dict])
async def fix_kp_mcq(mcq_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """手动触发 AI 审校修正(记修改记录 by=该管理员)。"""
    r = await word_kp_service.fix_kp_mcq(db, mcq_id=mcq_id, trigger="manual", by_admin_id=admin.id)
    return make_ok(r or {})


@router.put("/{mcq_id}", response_model=BaseResponse[dict])
async def edit_kp_mcq(mcq_id: uuid.UUID, body: dict, db: DbDep, admin: AdminDep):
    """人工编辑(记 before/after 修改记录)。body: {stem, options[], answer, explanation}。"""
    m = await db.get(VocabKpMcq, mcq_id)
    if m is None:
        return make_ok({})
    before = word_kp_service._mcq_snapshot(m)
    opts = [str(o).strip() for o in (body.get("options") or []) if str(o).strip()]
    ans = str(body.get("answer") or "").strip()
    stem = str(body.get("stem") or "").strip()
    if len(opts) < 2 or ans not in opts or not stem:
        from app.core.exceptions import AppError
        raise AppError(code=400, message="选项≥2、答案须为选项之一、题干不能空")
    m.stem, m.options, m.answer, m.explanation = stem, opts, ans, (str(body.get("explanation") or "").strip() or None)
    m.report_count = 0
    db.add(VocabKpMcqRevision(id=uuid.uuid4(), mcq_id=m.id, before=before, after=word_kp_service._mcq_snapshot(m),
                              trigger="manual", by_admin_id=admin.id, reason="人工编辑"))
    await db.commit()
    return make_ok(word_kp_service._mcq_out(m))


@router.delete("/{mcq_id}", response_model=BaseResponse[dict])
async def delete_kp_mcq(mcq_id: uuid.UUID, db: DbDep, admin: AdminDep):
    await db.execute(sa.delete(VocabKpMcq).where(VocabKpMcq.id == mcq_id))
    await db.commit()
    return make_ok({"ok": True})


@router.post("/batch-delete", response_model=BaseResponse[dict])
async def batch_delete(body: dict, db: DbDep, admin: AdminDep):
    ids = [uuid.UUID(str(i)) for i in (body.get("ids") or [])]
    if ids:
        await db.execute(sa.delete(VocabKpMcq).where(VocabKpMcq.id.in_(ids)))
        await db.commit()
    return make_ok({"deleted": len(ids)})


@router.get("/{mcq_id}/revisions", response_model=BaseResponse[list])
async def revisions(mcq_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """该题修改记录(before/after,时间倒序)。"""
    rows = (await db.execute(
        sa.select(VocabKpMcqRevision).where(VocabKpMcqRevision.mcq_id == mcq_id)
        .order_by(VocabKpMcqRevision.created_at.desc()))).scalars().all()
    return make_ok([{"id": str(r.id), "before": r.before, "after": r.after, "trigger": r.trigger,
                     "by_admin_id": str(r.by_admin_id) if r.by_admin_id else None, "reason": r.reason or "",
                     "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows])


@router.get("/threshold/value", response_model=BaseResponse[dict])
async def get_threshold(db: DbDep, admin: AdminDep):
    return make_ok({"threshold": await word_kp_service.get_report_threshold(db)})


@router.put("/threshold/value", response_model=BaseResponse[dict])
async def set_threshold(body: dict, db: DbDep, admin: AdminDep):
    """报错阈值(≥该值 AI 自动修正)。body: {threshold}。"""
    t = await word_kp_service.set_report_threshold(db, threshold=int(body.get("threshold", 3)), updated_by=admin.id)
    return make_ok({"threshold": t})
