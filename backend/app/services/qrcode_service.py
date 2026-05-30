"""微信小程序码生成（D-078 / Plan M）。"""
from __future__ import annotations

import base64

import httpx

from app.core.config import settings
from app.core.exceptions import AppError
from app.services.wechat_service import _is_dev_mode, get_access_token

_PICSUM_DEV_FALLBACK_URL = "https://picsum.photos/seed/qrcode/280/280.jpg"


async def get_miniprogram_qrcode_base64(
    *,
    scene: str,
    page: str,
    env_version: str = "trial",
) -> str:
    if len(scene) > 32:
        raise AppError(code=400, message=f"scene 长度超过 32：{scene}")

    if _is_dev_mode():
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(_PICSUM_DEV_FALLBACK_URL)
            return base64.b64encode(r.content).decode("ascii")
        except Exception:
            # 无外网时返回一个最小 1x1 PNG 占位（base64）
            return (
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
            )

    token = await get_access_token()
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"https://api.weixin.qq.com/wxa/getwxacodeunlimit?access_token={token}",
            json={
                "scene": scene,
                "page": page,
                "check_path": False,
                "env_version": env_version,
            },
        )

    if resp.headers.get("content-type", "").startswith("image"):
        return base64.b64encode(resp.content).decode("ascii")

    err = resp.json()
    raise AppError(code=502, message=f"微信小程序码生成失败：{err}")
