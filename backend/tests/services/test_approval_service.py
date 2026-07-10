"""敏感操作二次审批(maker-checker)service 测试。

覆盖:阈值闸门(未达→直接放行/达标→落 pending)、复核人须≠发起人、驳回关单、
批准回放执行(批量发券真的发出去)。自包含 seed + finally 清理。
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text

from app.core.database import _async_session_factory
from app.core.exceptions import AppError
from app.models.d1_users import User
from app.models.d2_payments import Coupon, CouponGrant
from app.models.d26_sensitive_approval import SensitiveApproval
from app.services import approval_service as svc

_TAG = "apprtest"


async def _mk_admin(db) -> User:
    u = User(id=uuid.uuid4(), openid=f"{_TAG}_{uuid.uuid4().hex[:8]}", role="platform_admin")
    db.add(u)
    await db.flush()
    return u


async def _mk_coupon(db) -> uuid.UUID:
    cid = uuid.uuid4()
    db.add(Coupon(id=cid, name=f"{_TAG}券", discount_type="amount", discount_value=100))
    await db.flush()
    return cid


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


@pytest.mark.asyncio
async def test_maker_checker_flow(db_session):
    db = db_session
    maker = await _mk_admin(db)
    checker = await _mk_admin(db)
    cid = await _mk_coupon(db)
    targets = [uuid.uuid4() for _ in range(2)]
    # 建目标用户(发券对象)
    for t in targets:
        db.add(User(id=t, openid=f"{_TAG}_{t.hex[:8]}", role="student"))
    await db.flush()

    # 阈值:发券人数 ≥ 2 需审批
    await svc.update_config(db, patch={"coupon_grant_count": 2}, updated_by=maker.id)

    # 1) 未达阈值(1 人)→ 直接放行(gate 返回 None)
    assert await svc.gate_coupon_grant(db, admin=maker, coupon_id=cid, user_ids=targets[:1]) is None

    # 2) 达阈值(2 人)→ 落 pending
    ap = await svc.gate_coupon_grant(db, admin=maker, coupon_id=cid, user_ids=targets)
    assert ap is not None and ap.status == "pending" and ap.action_type == "coupon_grant"

    # 3) 复核人 == 发起人 → 403
    with pytest.raises(AppError) as ei:
        await svc.decide(db, approval_id=ap.id, checker=maker, approve=True)
    assert ei.value.code == 403

    # 4) 另一位管理员批准 → 回放执行,券真的发出去
    await svc.decide(db, approval_id=ap.id, checker=checker, approve=True)
    granted = int(await db.scalar(
        select(func.count()).select_from(CouponGrant).where(CouponGrant.coupon_id == cid)) or 0)
    assert granted == 2
    ap2 = await db.get(SensitiveApproval, ap.id)
    assert ap2.status == "executed" and ap2.checker_id == checker.id

    # 5) 已处理的单再复核 → 400
    with pytest.raises(AppError) as ei2:
        await svc.decide(db, approval_id=ap.id, checker=checker, approve=False)
    assert ei2.value.code == 400


@pytest.mark.asyncio
async def test_reject_closes_without_executing(db_session):
    db = db_session
    maker = await _mk_admin(db)
    checker = await _mk_admin(db)
    cid = await _mk_coupon(db)
    targets = [uuid.uuid4() for _ in range(2)]
    for t in targets:
        db.add(User(id=t, openid=f"{_TAG}_{t.hex[:8]}", role="student"))
    await db.flush()
    await svc.update_config(db, patch={"coupon_grant_count": 2}, updated_by=maker.id)

    ap = await svc.gate_coupon_grant(db, admin=maker, coupon_id=cid, user_ids=targets)
    await svc.decide(db, approval_id=ap.id, checker=checker, approve=False, note="不合规")
    ap2 = await db.get(SensitiveApproval, ap.id)
    assert ap2.status == "rejected" and ap2.checker_note == "不合规"
    # 驳回不发券
    granted = int(await db.scalar(
        select(func.count()).select_from(CouponGrant).where(CouponGrant.coupon_id == cid)) or 0)
    assert granted == 0
