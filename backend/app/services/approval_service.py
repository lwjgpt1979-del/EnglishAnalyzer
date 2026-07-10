"""敏感操作二次审批(maker-checker)service。

高风险操作(退款批准、批量发券)超阈值 → 落 pending,由**另一位** platform_admin 复核后
才由本 service 回放执行(事前双人复核)。阈值走 system_configs.sensitive_approval,后台可配。
独立模块,避免与 admin.py 并发改动冲突。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d1_users import User
from app.models.d9_system import SystemConfig
from app.models.d26_sensitive_approval import SensitiveApproval

_CFG_KEY = "sensitive_approval"
# 默认阈值(缺省兜底;实际值以 system_configs.sensitive_approval 为准,后台可改)
_DEFAULTS = {
    "enabled": True,
    "refund_amount_fen": 20000,   # 退款批准金额 ≥ ¥200 → 需二次审批
    "coupon_grant_count": 20,     # 批量发券人数 ≥ 20 → 需二次审批
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def get_config(db: AsyncSession) -> dict:
    """读阈值配置(缺失走默认)。"""
    cfg = (await db.execute(
        select(SystemConfig).where(SystemConfig.key == _CFG_KEY))).scalar_one_or_none()
    if cfg is None:
        return dict(_DEFAULTS)
    v = cfg.value if isinstance(cfg.value, dict) else json.loads(cfg.value)
    return {**_DEFAULTS, **(v or {})}


async def update_config(db: AsyncSession, *, patch: dict, updated_by: uuid.UUID) -> dict:
    """运营改阈值:upsert system_configs.sensitive_approval。"""
    cur = await get_config(db)
    merged = {**cur, **{k: v for k, v in patch.items() if k in _DEFAULTS}}
    row = (await db.execute(
        select(SystemConfig).where(SystemConfig.key == _CFG_KEY))).scalar_one_or_none()
    if row is None:
        db.add(SystemConfig(key=_CFG_KEY, value=merged,
                            description="敏感操作二次审批阈值", updated_by=updated_by))
    else:
        row.value = merged
        row.updated_by = updated_by
    await db.flush()
    return merged


async def create_pending(
    db: AsyncSession, *, action_type: str, summary: str, payload: dict,
    amount_fen: int | None, maker: User, maker_note: str | None = None,
) -> SensitiveApproval:
    ap = SensitiveApproval(
        id=uuid.uuid4(), action_type=action_type, summary=summary, payload=payload,
        amount_fen=amount_fen, maker_id=maker.id, maker_note=maker_note, status="pending")
    db.add(ap)
    await db.flush()
    return ap


async def list_approvals(
    db: AsyncSession, *, status: str = "pending", skip: int = 0, limit: int = 50,
) -> tuple[list[dict], int]:
    """审批单列表(默认 pending)。带发起/复核人昵称。"""
    base = select(SensitiveApproval)
    if status and status != "all":
        base = base.where(SensitiveApproval.status == status)
    total = (await db.execute(
        select(sa.func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(
        base.order_by(SensitiveApproval.created_at.desc()).offset(skip).limit(limit))).scalars().all()
    uids = {r.maker_id for r in rows} | {r.checker_id for r in rows if r.checker_id}
    names = {uid: nk for uid, nk in (await db.execute(
        select(User.id, User.nickname).where(User.id.in_(uids)))).all()} if uids else {}
    items = [{
        "id": str(r.id), "action_type": r.action_type, "summary": r.summary,
        "amount_fen": r.amount_fen, "status": r.status,
        "maker_id": str(r.maker_id), "maker_name": names.get(r.maker_id),
        "maker_note": r.maker_note,
        "checker_id": str(r.checker_id) if r.checker_id else None,
        "checker_name": names.get(r.checker_id) if r.checker_id else None,
        "checker_note": r.checker_note, "exec_error": r.exec_error,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "decided_at": r.decided_at.isoformat() if r.decided_at else None,
    } for r in rows]
    return items, total


async def decide(
    db: AsyncSession, *, approval_id: uuid.UUID, checker: User,
    approve: bool, note: str | None = None,
) -> SensitiveApproval:
    """复核:批准 → 回放执行;驳回 → 关单。复核人必须 ≠ 发起人。调用方 commit。"""
    ap = await db.get(SensitiveApproval, approval_id)
    if ap is None:
        raise AppError(code=404, message="审批单不存在")
    if ap.status != "pending":
        raise AppError(code=400, message="该审批单已处理")
    if ap.maker_id == checker.id:
        raise AppError(code=403, message="不能复核自己发起的操作,需另一位管理员")
    ap.checker_id = checker.id
    ap.checker_note = note
    ap.decided_at = _now()
    if not approve:
        ap.status = "rejected"
        await db.flush()
        return ap
    try:
        await _dispatch(db, ap, checker)
    except AppError:
        raise
    except Exception as e:  # noqa: BLE001
        ap.status = "failed"
        ap.exec_error = str(e)[:500]
        await db.flush()
        raise AppError(code=500, message=f"批准后执行失败:{e}")
    ap.status = "executed"
    await db.flush()
    return ap


async def _dispatch(db: AsyncSession, ap: SensitiveApproval, checker: User) -> None:
    """按 action_type 回放到真实 service 执行。"""
    p = ap.payload or {}
    if ap.action_type == "refund_approve":
        from app.services import refund_service
        await refund_service.review(
            db, checker, uuid.UUID(p["refund_id"]),
            approve=True, amount_fen=p.get("amount_fen"), reason=p.get("reason"))
    elif ap.action_type == "coupon_grant":
        from app.services import coupon_service
        await coupon_service.admin_grant(
            db, coupon_id=uuid.UUID(p["coupon_id"]),
            user_ids=[uuid.UUID(u) for u in p["user_ids"]])
    else:
        raise AppError(code=400, message=f"未知审批动作:{ap.action_type}")


# ── 端点闸门:超阈值返回 pending(调用方据此返回「已提交审批」),否则 None(直接执行)──

async def gate_refund_approve(
    db: AsyncSession, *, admin: User, refund_id: uuid.UUID,
    amount_fen: int | None, reason: str | None,
) -> SensitiveApproval | None:
    """退款批准闸门。命中阈值 → 落 pending 并返回;否则 None。"""
    cfg = await get_config(db)
    if not cfg.get("enabled", True):
        return None
    from app.models.d2_payments import RefundRecord
    rec = await db.get(RefundRecord, refund_id)
    if rec is None:
        return None   # 让下游 review 抛 404
    amt = amount_fen if amount_fen is not None else rec.amount_fen
    if amt is None or amt < cfg["refund_amount_fen"]:
        return None
    return await create_pending(
        db, action_type="refund_approve",
        summary=f"退款批准 ¥{amt / 100:.2f}(退款单 {str(refund_id)[:8]})",
        payload={"refund_id": str(refund_id), "amount_fen": amount_fen, "reason": reason},
        amount_fen=amt, maker=admin)


async def gate_coupon_grant(
    db: AsyncSession, *, admin: User, coupon_id: uuid.UUID, user_ids: list[uuid.UUID],
) -> SensitiveApproval | None:
    """批量发券闸门。人数达阈值 → 落 pending 并返回;否则 None。"""
    cfg = await get_config(db)
    if not cfg.get("enabled", True):
        return None
    if len(user_ids) < cfg["coupon_grant_count"]:
        return None
    return await create_pending(
        db, action_type="coupon_grant",
        summary=f"批量发券 {len(user_ids)} 人(券 {str(coupon_id)[:8]})",
        payload={"coupon_id": str(coupon_id), "user_ids": [str(u) for u in user_ids]},
        amount_fen=None, maker=admin)
