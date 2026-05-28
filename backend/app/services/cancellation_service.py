"""账号注销流程（需求文档 §4.2）。

3 步：申请（发 SMS） → 确认（提交码） → 30天冷静期 → 懒执行匿名化。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d1_users import User
from app.schemas.compliance import CancellationStatusOut
from app.services.sms_service import (
    generate_code,
    expires_at_from_now,
    send_sms_code,
)

COOLING_PERIOD_DAYS = 30


async def request_cancellation(db: AsyncSession, *, user: User) -> None:
    """Step 1：发 SMS 验证码到用户本人手机。"""
    if not user.phone:
        raise AppError(code=400, message="请先在账号设置补填本人手机号")
    if user.deactivation_requested_at is not None:
        raise AppError(code=409, message="账号已在注销冷静期内")

    code = generate_code()
    user.phone_verify_code = code
    user.phone_verify_purpose = "cancel_account"
    user.phone_verify_target = user.phone
    user.phone_verify_expires_at = expires_at_from_now()
    await send_sms_code(phone=user.phone, code=code, purpose="cancel_account")
    await db.flush()


async def confirm_cancellation(db: AsyncSession, *, user: User, code: str) -> None:
    """Step 2：核码 → 进入 30 天冷静期，is_active=false。"""
    if user.phone_verify_purpose != "cancel_account":
        raise AppError(code=400, message="无待确认的注销申请")
    if (
        user.phone_verify_code != code
        or user.phone_verify_expires_at is None
        or user.phone_verify_expires_at < datetime.now(timezone.utc)
    ):
        raise AppError(code=400, message="验证码错误或已过期")

    now = datetime.now(timezone.utc)
    user.deactivation_requested_at = now
    user.deactivation_scheduled_at = now + timedelta(days=COOLING_PERIOD_DAYS)
    user.is_active = False
    user.phone_verify_code = None
    user.phone_verify_purpose = None
    user.phone_verify_target = None
    user.phone_verify_expires_at = None
    await db.flush()


async def revoke_cancellation(db: AsyncSession, *, user: User) -> None:
    """冷静期内撤销注销。"""
    if user.deactivation_requested_at is None:
        raise AppError(code=400, message="账号不在注销冷静期内")
    if user.deactivation_scheduled_at and user.deactivation_scheduled_at < datetime.now(timezone.utc):
        raise AppError(code=410, message="冷静期已结束，无法撤销")
    user.deactivation_requested_at = None
    user.deactivation_scheduled_at = None
    user.is_active = True
    await db.flush()


async def execute_cancellation_if_due(db: AsyncSession, *, user: User) -> bool:
    """懒执行：若 scheduled_at 已过则脱敏匿名化，返回是否执行。"""
    if user.is_anonymized:
        return False
    if user.deactivation_scheduled_at is None:
        return False
    if user.deactivation_scheduled_at > datetime.now(timezone.utc):
        return False

    user.openid = f"deleted_{uuid.uuid4().hex}"
    user.nickname = None
    user.avatar_url = None
    user.phone = None
    user.guardian_phone = None
    user.is_anonymized = True
    user.is_active = False
    await db.flush()
    return True


def status_for(user: User) -> CancellationStatusOut:
    days_remaining = None
    if user.deactivation_scheduled_at is not None:
        delta = user.deactivation_scheduled_at - datetime.now(timezone.utc)
        days_remaining = max(0, delta.days)
    return CancellationStatusOut(
        requested_at=user.deactivation_requested_at,
        scheduled_at=user.deactivation_scheduled_at,
        days_remaining=days_remaining,
    )
