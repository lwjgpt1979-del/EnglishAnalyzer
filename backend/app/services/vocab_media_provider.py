"""词力通图/音频 provider（P1 / D-101）。

图片：image_provider='tencent' + 真实 TENCENT_AIART_SECRET_* → 腾讯混元生图极速版
(TextToImageLite)，生成的临时图 URL 下载后上传 COS 持久化，返回 COS 直链；否则 dev-mock。
音频：mock 占位（卡片实际发音走 TTS / tts_service，不依赖这里）。
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import urllib.parse
import uuid

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_cos_client = None


def is_image_dev_mode() -> bool:
    return (settings.image_provider != "tencent"
            or settings.tencent_aiart_secret_key.startswith("placeholder"))


def is_tts_dev_mode() -> bool:
    return settings.tts_provider == "mock" or settings.tts_api_key.startswith("tts-placeholder")


def _cos_dev() -> bool:
    return settings.cos_secret_key.startswith("placeholder")


def _get_cos_client():
    global _cos_client
    if _cos_client is None:
        from qcloud_cos import CosConfig, CosS3Client  # type: ignore[import]
        _cos_client = CosS3Client(CosConfig(
            Region=settings.cos_region, SecretId=settings.cos_secret_id,
            SecretKey=settings.cos_secret_key))
    return _cos_client


def _tencent_t2i(prompt: str) -> str | None:
    """腾讯混元生图极速版 TextToImageLite（同步，在 to_thread 中执行）：返回临时图 URL。"""
    from tencentcloud.common import credential
    from tencentcloud.aiart.v20221229 import aiart_client, models
    cred = credential.Credential(
        settings.tencent_aiart_secret_id, settings.tencent_aiart_secret_key)
    client = aiart_client.AiartClient(cred, settings.tencent_aiart_region)
    req = models.TextToImageLiteRequest()
    req.Prompt = prompt[:1024]
    req.Resolution = settings.tencent_aiart_resolution
    req.RspImgType = "url"
    req.LogoAdd = 0   # 不加水印
    resp = client.TextToImageLite(req)
    return getattr(resp, "ResultImage", None) or None


async def _persist_to_cos(img_url: str) -> str:
    """下载临时图 → 上传 COS（public-read）→ 返回直链；COS 未配则原样返回临时 URL。"""
    if _cos_dev():
        return img_url
    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.get(img_url)
        r.raise_for_status()
        body = r.content
    key = f"vocab/img/{uuid.uuid4().hex}.png"

    def _put() -> None:
        _get_cos_client().put_object(
            Bucket=settings.cos_bucket, Key=key, Body=body,
            ContentType="image/png", ACL="public-read")

    await asyncio.to_thread(_put)
    return f"{settings.cos_base_url}/{key}"


async def t2i_to_cos(prompt: str, *, label: str = "") -> str | None:
    """单条完整提示词 → 混元生图极速版 → 下载转存 COS → 返回直链。

    dev-mock 返回 placehold 占位（按 label/prompt 哈希）；失败返回 None（调用方决定兜底）。
    """
    if is_image_dev_mode():
        safe = urllib.parse.quote((label or prompt or "word")[:20])
        h = hashlib.md5((prompt or "").encode()).hexdigest()[:4]
        return f"https://placehold.co/600x400?text={safe}-{h}"
    try:
        tmp = await asyncio.to_thread(_tencent_t2i, prompt)
        if not tmp:
            return None
        return await _persist_to_cos(tmp)
    except Exception as e:  # noqa: BLE001
        logger.error("[混元生图] %s 失败: %s", label or prompt[:20], e)
        return None


def generate_tts(text: str) -> str:
    """返回音频 URL。mock 时返回空串（不写假URL；卡片发音走 tts_service / 火山 TTS 兜底）。"""
    if is_tts_dev_mode():
        return ""
    raise NotImplementedError("真 TTS provider 未接入（卡片发音已走 tts_service）")
