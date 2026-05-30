"""微信 access_token 缓存（D-078 / Plan M）。

access_token 2h 有效，内存缓存。dev 模式（wechat_appid 以 'wx_dev' 开头）返回 mock。
"""
from __future__ import annotations

import time

import httpx

from app.core.config import settings
from app.core.exceptions import AppError

_TOKEN_REFRESH_BEFORE_SECONDS = 600
_DEV_MOCK_TOKEN = "dev_mock_access_token_AAAAA"

_cache: dict[str, float | str] = {"token": "", "expires_at": 0.0}


def _is_dev_mode() -> bool:
    return settings.wechat_appid.startswith("wx_dev")


async def get_access_token() -> str:
    if _is_dev_mode():
        return _DEV_MOCK_TOKEN

    now = time.time()
    expires_at = float(_cache.get("expires_at", 0))
    if _cache.get("token") and now + _TOKEN_REFRESH_BEFORE_SECONDS < expires_at:
        return str(_cache["token"])

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            "https://api.weixin.qq.com/cgi-bin/token",
            params={
                "grant_type": "client_credential",
                "appid": settings.wechat_appid,
                "secret": settings.wechat_appsecret,
            },
        )
    data = resp.json()
    if "access_token" not in data:
        raise AppError(code=502, message=f"微信 access_token 获取失败：{data}")

    _cache["token"] = data["access_token"]
    _cache["expires_at"] = now + int(data["expires_in"])
    return str(_cache["token"])
