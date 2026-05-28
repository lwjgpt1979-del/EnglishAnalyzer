"""SMS 验证码服务。MVP 阶段 dev mock：不真发短信，验证码记日志并固定为 '123456'。
生产接入：替换 _send_real_sms 内实现（阿里云/腾讯云短信 SDK）。
"""
from __future__ import annotations

import logging
import random
import string
from datetime import datetime, timedelta, timezone

from app.core.config import settings

logger = logging.getLogger(__name__)

CODE_TTL_MINUTES = 10
DEV_FIXED_CODE = "123456"


def _is_dev_mode() -> bool:
    return settings.sms_provider.startswith("placeholder")


def generate_code() -> str:
    if _is_dev_mode():
        return DEV_FIXED_CODE
    return "".join(random.choices(string.digits, k=6))


def expires_at_from_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=CODE_TTL_MINUTES)


async def send_sms_code(*, phone: str, code: str, purpose: str) -> None:
    if _is_dev_mode():
        logger.warning(
            "[SMS DEV MOCK] phone=%s purpose=%s code=%s (dev固定%s)",
            phone, purpose, code, DEV_FIXED_CODE,
        )
        return
    await _send_real_sms(phone=phone, code=code, purpose=purpose)


async def _send_real_sms(*, phone: str, code: str, purpose: str) -> None:
    raise NotImplementedError("生产 SMS provider 未接入")
