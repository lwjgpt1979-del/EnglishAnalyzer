"""SMS 验证码服务。MVP 阶段 dev mock：不真发短信，验证码记日志并固定为 '123456'。
生产接入：设置环境变量 SMS_PROVIDER=aliyun 及阿里云 AccessKey 即可。
"""
from __future__ import annotations

import asyncio
import logging
import random
import string
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.exceptions import AppError

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
    """调用阿里云短信 SDK 发送短信。仅当 sms_provider=aliyun 时被调用。"""
    from alibabacloud_dysmsapi20170525.client import Client
    from alibabacloud_dysmsapi20170525.models import SendSmsRequest
    from alibabacloud_tea_openapi.models import Config

    cfg = Config(
        access_key_id=settings.sms_access_key_id,
        access_key_secret=settings.sms_access_key_secret,
        endpoint="dysmsapi.aliyuncs.com",
    )
    client = Client(cfg)
    template_code = (
        settings.sms_template_code_verify
        if purpose in ("guardian_verify", "cancel_account", "institution_apply")
        else settings.sms_template_code_invite
    )
    req = SendSmsRequest(
        phone_numbers=phone,
        sign_name=settings.sms_sign_name,
        template_code=template_code,
        template_param=f'{{"code":"{code}"}}',
    )
    resp = await asyncio.to_thread(client.send_sms, req)
    if resp.body.code != "OK":
        raise AppError(code=503, message=f"短信发送失败：{resp.body.message}")


async def send_invite_sms(
    *,
    phone: str,
    code: str,
    inviter_name: str,
    role: str,
) -> None:
    """发送邀请短信。dev mode 仅记日志；prod 走 _send_real_sms。"""
    role_text = "老师" if role == "teacher" else "家人"
    page_text = "教师中心" if role == "teacher" else "家人中心"
    content = (
        f"【engGramer】{inviter_name}邀请您加入"
        f"，邀请码 {code}（24h有效）。"
        f"请在小程序-我的-{page_text} 输入此码完成绑定。"
    )
    if _is_dev_mode():
        logger.warning("[SMS DEV MOCK invite] phone=%s role=%s content=%s", phone, role, content)
        return
    await _send_real_sms(phone=phone, code=code, purpose=f"invite_{role}")
