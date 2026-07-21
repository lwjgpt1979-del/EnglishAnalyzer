"""考点(vocab_word_relation)后台复核 API:按 report_count 筛被学生报错的考点,
按词 AI 修正(复用 P5 推理档审校)/ 人工编辑 / 删除 / 看审校记录(vocab_word_kp_review)+ 报错阈值配置。
独立模块,避免与 admin.py / admin_kp_mcq.py 冲突。"""
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
from app.models.d18_vocab_kg import VocabWordKpReview, VocabWordRelation, VocabWordSense
from app.schemas.base import BaseResponse, make_ok
from app.services import word_kp_service

router = APIRouter(prefix="/admin/kp-relations", tags=["admin-kp-relation"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
AdminDep = Annotated[User, Depends(require_role("platform_admin"))]


def _row(r: VocabWordRelation, word: str, gloss: str) -> dict:
    return {"id": str(r.id), "word_id": str(r.word_id), "word": word,
            "sense_id": str(r.sense_id) if r.sense_id else None, "gloss": gloss,
            "dim": r.relation, "dim_label": r.dim_label or word_kp_service._dim_label(r.relation),
            "text": r.related_text, "zh": r.related_zh or "", "note": r.note or "",
            "report_count": r.report_count,
            "created_at": r.created_at.isoformat() if r.created_at else None}


@router.get("", response_model=BaseResponse[dict])
async def list_reported(db: DbDep, admin: AdminDep, min_report: int = 1, skip: int = 0, limit: int = 20):
    """复核列表(分页):默认只列被报错过(report_count≥min_report)的考点,按报错次数降序。"""
    base = sa.select(VocabWordRelation).where(VocabWordRelation.report_count >= min_report)
    total = (await db.execute(sa.select(sa.func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(
        base.order_by(VocabWordRelation.report_count.desc(), VocabWordRelation.created_at.desc())
        .offset(skip).limit(limit))).scalars().all()
    wmap, gmap = {}, {}
    if rows:
        ws = (await db.execute(sa.select(VocabularyWord.id, VocabularyWord.word)
                               .where(VocabularyWord.id.in_([r.word_id for r in rows])))).all()
        wmap = {wid: w for wid, w in ws}
        sids = [r.sense_id for r in rows if r.sense_id]
        if sids:
            ss = (await db.execute(sa.select(VocabWordSense.id, VocabWordSense.gloss_zh)
                                   .where(VocabWordSense.id.in_(sids)))).all()
            gmap = {sid: g for sid, g in ss}
    threshold = await word_kp_service.get_kp_report_threshold(db)
    return make_ok({"items": [_row(r, wmap.get(r.word_id, ""), gmap.get(r.sense_id, "")) for r in rows],
                    "total": total, "threshold": threshold})


@router.post("/{word_id}/fix", response_model=BaseResponse[dict])
async def fix_word(word_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """对该词被报错达阈值的考点手动触发 AI 审校修正(推理档,记 vocab_word_kp_review)。"""
    r = await word_kp_service.fix_reported_kp(db, word_id=word_id)
    return make_ok(r or {})


@router.put("/{relation_id}", response_model=BaseResponse[dict])
async def edit_relation(relation_id: uuid.UUID, body: dict, db: DbDep, admin: AdminDep):
    """人工编辑一条考点(text/zh/note),report_count 归 0。body: {text, zh, note}。"""
    r = await db.get(VocabWordRelation, relation_id)
    if r is None:
        return make_ok({})
    text = str(body.get("text") or "").strip()
    if not text:
        from app.core.exceptions import AppError
        raise AppError(code=400, message="考点内容不能为空")
    r.related_text = text
    r.related_zh = str(body.get("zh") or "").strip() or None
    r.note = str(body.get("note") or "").strip() or None
    r.report_count = 0
    await db.commit()
    ws = await db.get(VocabularyWord, r.word_id)
    return make_ok(_row(r, ws.word if ws else "", ""))


@router.delete("/{relation_id}", response_model=BaseResponse[dict])
async def delete_relation(relation_id: uuid.UUID, db: DbDep, admin: AdminDep):
    await db.execute(sa.delete(VocabWordRelation).where(VocabWordRelation.id == relation_id))
    await db.commit()
    return make_ok({"ok": True})


@router.post("/batch-delete", response_model=BaseResponse[dict])
async def batch_delete(body: dict, db: DbDep, admin: AdminDep):
    ids = [uuid.UUID(str(i)) for i in (body.get("ids") or [])]
    if ids:
        await db.execute(sa.delete(VocabWordRelation).where(VocabWordRelation.id.in_(ids)))
        await db.commit()
    return make_ok({"deleted": len(ids)})


@router.get("/{word_id}/reviews", response_model=BaseResponse[list])
async def reviews(word_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """该词考点审校记录(before/after,时间倒序;含 P5 自审 + P6 报错修正)。"""
    rows = (await db.execute(
        sa.select(VocabWordKpReview).where(VocabWordKpReview.word_id == word_id)
        .order_by(VocabWordKpReview.created_at.desc()))).scalars().all()
    return make_ok([{"id": str(r.id), "before": r.before, "after": r.after,
                     "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows])


@router.get("/threshold/value", response_model=BaseResponse[dict])
async def get_threshold(db: DbDep, admin: AdminDep):
    return make_ok({"threshold": await word_kp_service.get_kp_report_threshold(db)})


@router.put("/threshold/value", response_model=BaseResponse[dict])
async def set_threshold(body: dict, db: DbDep, admin: AdminDep):
    """考点报错阈值(≥该值进复核/AI 修正)。body: {threshold}。"""
    t = await word_kp_service.set_kp_report_threshold(db, threshold=int(body.get("threshold", 3)), updated_by=admin.id)
    return make_ok({"threshold": t})
