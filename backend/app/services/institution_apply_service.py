"""机构自助入驻申请 service（M47，公开免登录）。

流程：申请人填手机号 → 发验证码 → 提交申请（验码通过）→ 写入 status='pending'
机构记录 → 进入超管现有审核队列（admin_institution_service）。
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d1_users import Institution
from app.models.d9_system import SmsVerification
from app.services import captcha_service
from app.services.sms_service import (
    expires_at_from_now,
    generate_code,
    send_sms_code,
)

PURPOSE = "institution_apply"
RESEND_COOLDOWN_SECONDS = 60
_PHONE_RE = re.compile(r"^1[3-9]\d{9}$")


def _validate_phone(phone: str) -> str:
    phone = (phone or "").strip()
    if not _PHONE_RE.match(phone):
        raise AppError(code=400, message="请输入正确的 11 位手机号")
    return phone


async def send_apply_code(
    db: AsyncSession, *, phone: str, captcha_id: str, captcha_code: str,
) -> None:
    """发送机构入驻申请验证码。先过图形验证码，再 60s 冷却。"""
    phone = _validate_phone(phone)

    # 图形验证码挡在前面，防短信盗刷
    await captcha_service.verify(db, captcha_id=captcha_id, answer=captcha_code)

    latest = (await db.execute(
        select(SmsVerification)
        .where(SmsVerification.phone == phone, SmsVerification.purpose == PURPOSE)
        .order_by(SmsVerification.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if latest is not None:
        elapsed = (datetime.now(timezone.utc) - latest.created_at).total_seconds()
        if elapsed < RESEND_COOLDOWN_SECONDS:
            raise AppError(
                code=429,
                message=f"验证码发送过于频繁，请 {int(RESEND_COOLDOWN_SECONDS - elapsed)} 秒后再试",
            )

    code = generate_code()
    db.add(SmsVerification(
        id=uuid.uuid4(), phone=phone, purpose=PURPOSE,
        code=code, expires_at=expires_at_from_now(),
    ))
    await db.flush()
    await send_sms_code(phone=phone, code=code, purpose=PURPOSE)


async def _consume_code(db: AsyncSession, *, phone: str, code: str) -> None:
    """校验并核销验证码；失败抛 AppError。"""
    row = (await db.execute(
        select(SmsVerification)
        .where(
            SmsVerification.phone == phone,
            SmsVerification.purpose == PURPOSE,
            SmsVerification.consumed.is_(False),
        )
        .order_by(SmsVerification.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if row is None:
        raise AppError(code=400, message="请先获取验证码")
    if row.expires_at < datetime.now(timezone.utc):
        raise AppError(code=400, message="验证码已过期，请重新获取")
    if row.code != (code or "").strip():
        raise AppError(code=400, message="验证码错误")
    row.consumed = True  # type: ignore[assignment]
    await db.flush()


async def apply_institution(
    db: AsyncSession, *,
    name: str, contact_phone: str,
    province_code: str, city_code: str, address: str, code: str,
) -> Institution:
    name = (name or "").strip()
    address = (address or "").strip()
    contact_phone = _validate_phone(contact_phone)
    if len(name) < 2:
        raise AppError(code=400, message="请填写机构名称")
    if not province_code or not city_code:
        raise AppError(code=400, message="请选择所在省市")
    if len(address) < 4:
        raise AppError(code=400, message="请填写详细地址")

    await _consume_code(db, phone=contact_phone, code=code)

    # 去重：同手机号已有待审核申请 → 拒绝重复提交
    dup = (await db.execute(
        select(Institution).where(
            Institution.contact_phone == contact_phone,
            Institution.status == "pending",
        ).limit(1)
    )).scalar_one_or_none()
    if dup is not None:
        raise AppError(code=409, message="您已提交过入驻申请，正在审核中，请耐心等待")

    inst = Institution(
        id=uuid.uuid4(), name=name, contact_phone=contact_phone,
        province_code=province_code, city_code=city_code, address=address,
        status="pending", source="self_apply",
    )
    db.add(inst)
    await db.flush()
    return inst
