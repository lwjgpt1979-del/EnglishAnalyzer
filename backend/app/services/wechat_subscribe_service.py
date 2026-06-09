"""微信订阅消息服务（D-108）。
dev-mock：`wechat_subscribe_provider` 以 `placeholder` 开头时仅记日志。
生产：设 `WECHAT_SUBSCRIBE_PROVIDER=wechat` + 真实 appid/appsecret/template_id。
"""
from __future__ import annotations

import logging
import time

import httpx

from app.core.config import settings
from app.core.exceptions import AppError

logger = logging.getLogger(__name__)

# 模块级 access_token 缓存（避免频繁调用微信接口超限）
_token_cache: dict = {"token": "", "expires_at": 0.0}


def _is_dev() -> bool:
    return settings.wechat_subscribe_provider.startswith("placeholder")


async def _get_access_token() -> str:
    """获取微信 access_token，带 60s 余量的内存缓存。"""
    now = time.time()
    if _token_cache["expires_at"] > now + 60:
        return _token_cache["token"]

    url = "https://api.weixin.qq.com/cgi-bin/token"
    params = {
        "grant_type": "client_credential",
        "appid": settings.wechat_appid,
        "secret": settings.wechat_appsecret,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params)
    data = resp.json()

    if "access_token" not in data:
        raise AppError(502, f"微信 access_token 获取失败：{data.get('errmsg', data)}")

    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = now + data.get("expires_in", 7200)
    logger.info("[WX SUBSCRIBE] access_token 已刷新，有效至 %.0f", _token_cache["expires_at"])
    return _token_cache["token"]


async def _send_real_subscribe_message(*, openid: str, streak_days: int) -> bool:
    """调用微信 subscribeMessage.send 接口，失败时返回 False（非关键路径，不抛错）。"""
    try:
        token = await _get_access_token()
    except AppError as e:
        logger.warning("[WX SUBSCRIBE] access_token 获取失败，跳过推送：%s", e.message)
        return False

    url = f"https://api.weixin.qq.com/cgi-bin/message/subscribe/send?access_token={token}"
    payload = {
        "touser": openid,
        "template_id": settings.wechat_subscribe_template_checkin,
        "data": {
            "thing1": {"value": f"已连续打卡 {streak_days} 天，继续加油！"},
            "time2": {"value": _today_str()},
        },
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json=payload)
    result = resp.json()

    errcode = result.get("errcode", 0)
    if errcode == 0:
        logger.info("[WX SUBSCRIBE] 推送成功 openid=%s", openid)
        return True

    # 43101: 用户未订阅该消息，属正常情况
    if errcode == 43101:
        logger.debug("[WX SUBSCRIBE] 用户未订阅 openid=%s", openid)
    else:
        logger.warning(
            "[WX SUBSCRIBE] 推送失败 openid=%s errcode=%s errmsg=%s",
            openid, errcode, result.get("errmsg"),
        )
    return False


def _today_str() -> str:
    from datetime import date, timezone
    return date.today().isoformat()


async def send_checkin_reminder(*, openid: str, streak_days: int) -> bool:
    """发送打卡提醒订阅消息。
    dev-mock 记日志返回 True；prod 调微信 subscribeMessage.send。
    """
    if _is_dev():
        logger.info(
            "[WX SUBSCRIBE DEV MOCK] checkin reminder openid=%s streak=%s template=%s",
            openid, streak_days, settings.wechat_subscribe_template_checkin,
        )
        return True
    return await _send_real_subscribe_message(openid=openid, streak_days=streak_days)
