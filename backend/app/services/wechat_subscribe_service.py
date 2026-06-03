"""微信订阅消息服务（D-108）。MVP dev-mock：占位 provider 仅记日志，不真发。"""
from __future__ import annotations

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


def _is_dev() -> bool:
    return settings.wechat_subscribe_provider.startswith("placeholder")


async def send_checkin_reminder(*, openid: str, streak_days: int) -> bool:
    """发送打卡提醒订阅消息。dev-mock 记日志返回 True；prod 走真实微信 API（未接入）。"""
    if _is_dev():
        logger.info(
            "[WX SUBSCRIBE DEV MOCK] checkin reminder openid=%s streak=%s template=%s",
            openid, streak_days, settings.wechat_subscribe_template_checkin,
        )
        return True
    raise NotImplementedError("生产微信订阅消息 provider 未接入")
