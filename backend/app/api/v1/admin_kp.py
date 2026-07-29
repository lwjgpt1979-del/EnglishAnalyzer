"""考点(vocab_word_relation)后台复核 API:有凭证举报列表 / 下架·恢复 / AI 修正 / 编辑删除。
方案1:生成即对学生可见;运营核实举报后下架(hidden_at),行保留防 LLM 回写同 text。"""
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
from app.models.d18_vocab_kg import VocabKpRelationReport, VocabWordKpReview, VocabWordRelation, VocabWordSense
from app.schemas.base import BaseResponse, make_ok
from app.services import word_kp_service

router = APIRouter(prefix="/admin/kp-relations", tags=["admin-kp-relation"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
AdminDep = Annotated[User, Depends(require_role("platform_admin"))]


def _row(r: VocabWordRelation, word: str, gloss: str, *, evidence: dict | None = None) -> dict:
    note = r.hide_note or ""
    return {"id": str(r.id), "word_id": str(r.word_id), "word": word,
            "sense_id": str(r.sense_id) if r.sense_id else None, "gloss": gloss,
            "dim": r.relation, "dim_label": r.dim_label or word_kp_service._dim_label(r.relation),
            "text": r.related_text, "zh": r.related_zh or "", "note": r.note or "",
            "source": getattr(r, "source", "llm") or "llm",
            "report_count": r.report_count,
            "hidden": r.hidden_at is not None,
            "hidden_at": r.hidden_at.isoformat() if r.hidden_at else None,
            "hide_note": note,
            "hide_origin": "ai_prehide" if note == word_kp_service._HIDE_NOTE_AI else ("manual" if r.hidden_at else ""),
            "evidence": evidence or {},
            "created_at": r.created_at.isoformat() if r.created_at else None}


async def _evidence_map(db: AsyncSession, relation_ids: list) -> dict:
    """每条关系取最新一条凭证摘要 + 举报条数。"""
    if not relation_ids:
        return {}
    rows = (await db.execute(
        sa.select(VocabKpRelationReport)
        .where(VocabKpRelationReport.relation_id.in_(relation_ids))
        .order_by(VocabKpRelationReport.created_at.desc()))).scalars().all()
    out: dict = {}
    for x in rows:
        rid = x.relation_id
        if rid not in out:
            out[rid] = {"count": 0, "latest_reason": "", "latest_reason_label": "",
                        "latest_detail": "", "latest_suggested": ""}
        out[rid]["count"] += 1
        if not out[rid]["latest_reason"]:
            out[rid]["latest_reason"] = x.reason
            out[rid]["latest_reason_label"] = word_kp_service._REPORT_REASONS.get(x.reason, x.reason)
            out[rid]["latest_detail"] = x.detail or ""
            out[rid]["latest_suggested"] = x.suggested or ""
    return out


@router.get("", response_model=BaseResponse[dict])
async def list_reported(db: DbDep, admin: AdminDep, min_report: int = 1, skip: int = 0, limit: int = 20,
                        hidden: str | None = None, hide_origin: str | None = None):
    """复核列表(分页)。hidden=only|exclude|all(默认 exclude)。
    hide_origin=ai_prehide|manual:在已下架中按来源筛;ai_prehide 时不要求报错数(预隐可能 0 报错)。"""
    if hide_origin == "ai_prehide":
        base = sa.select(VocabWordRelation).where(
            VocabWordRelation.hide_note == word_kp_service._HIDE_NOTE_AI,
            VocabWordRelation.hidden_at.isnot(None))
    else:
        base = sa.select(VocabWordRelation).where(VocabWordRelation.report_count >= min_report)
        if hidden == "only":
            base = base.where(VocabWordRelation.hidden_at.isnot(None))
        elif hidden != "all":
            base = base.where(VocabWordRelation.hidden_at.is_(None))
        if hide_origin == "manual":
            base = base.where(VocabWordRelation.hidden_at.isnot(None),
                              sa.or_(VocabWordRelation.hide_note.is_(None),
                                     VocabWordRelation.hide_note != word_kp_service._HIDE_NOTE_AI))
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
    evid = await _evidence_map(db, [r.id for r in rows])
    threshold = await word_kp_service.get_kp_report_threshold(db)
    return make_ok({"items": [_row(r, wmap.get(r.word_id, ""), gmap.get(r.sense_id, ""),
                                   evidence=evid.get(r.id)) for r in rows],
                    "total": total, "threshold": threshold,
                    "reason_options": [{"value": k, "label": v}
                                       for k, v in word_kp_service._REPORT_REASONS.items()]})


@router.get("/{relation_id}/reports", response_model=BaseResponse[list])
async def relation_reports(relation_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """某条考点的全部有凭证举报明细。"""
    return make_ok(await word_kp_service.list_relation_reports(db, relation_id=relation_id))


@router.post("/{relation_id}/hide", response_model=BaseResponse[dict])
async def hide_relation(relation_id: uuid.UUID, body: dict, db: DbDep, admin: AdminDep):
    """核实后下架(对学生隐藏)。body: {note?}。"""
    r = await word_kp_service.hide_relation(
        db, relation_id=relation_id, admin_id=admin.id, note=str(body.get("note") or "") or None)
    if r is None:
        return make_ok({})
    ws = await db.get(VocabularyWord, r.word_id)
    return make_ok(_row(r, ws.word if ws else "", ""))


@router.post("/{relation_id}/unhide", response_model=BaseResponse[dict])
async def unhide_relation(relation_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """恢复上架。"""
    r = await word_kp_service.unhide_relation(db, relation_id=relation_id)
    if r is None:
        return make_ok({})
    ws = await db.get(VocabularyWord, r.word_id)
    return make_ok(_row(r, ws.word if ws else "", ""))


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


@router.post("/batch-hide", response_model=BaseResponse[dict])
async def batch_hide(body: dict, db: DbDep, admin: AdminDep):
    """批量下架。body: {ids, note?}。"""
    ids = [uuid.UUID(str(i)) for i in (body.get("ids") or [])]
    note = str(body.get("note") or "") or None
    n = 0
    for rid in ids:
        r = await word_kp_service.hide_relation(db, relation_id=rid, admin_id=admin.id, note=note)
        if r:
            n += 1
    return make_ok({"hidden": n})


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
