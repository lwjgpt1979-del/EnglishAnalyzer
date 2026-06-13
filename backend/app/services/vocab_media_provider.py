"""词力通图/音频 provider（P1 / D-101）。

图片：image_provider='ark' + 真实 ARK_API_KEY → 火山方舟 Seedream 文生图，
生成的临时图 URL 下载后上传 COS 持久化，返回 COS 直链；否则 dev-mock 占位图。
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
    return settings.image_provider != "ark" or settings.ark_api_key.startswith("placeholder")


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


async def _ark_t2i(prompt: str) -> str | None:
    """火山方舟 Seedream 文生图：返回一张图的临时 URL。"""
    url = f"{settings.ark_base_url}/images/generations"
    headers = {"Authorization": f"Bearer {settings.ark_api_key}",
               "Content-Type": "application/json"}
    payload = {
        "model": settings.ark_image_model, "prompt": prompt,
        "size": settings.ark_image_size, "response_format": "url", "watermark": False,
    }
    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
    items = data.get("data") or []
    return items[0].get("url") if items else None


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


async def generate_images(prompt: str, n: int = 3) -> list[str]:
    """为单词(prompt=单词)生成 n 张配图 URL。dev-mock 占位；真实走 Ark→COS。"""
    word = (prompt or "word").strip()
    if is_image_dev_mode():
        safe = urllib.parse.quote(word[:20])
        return [f"https://placehold.co/600x400?text={safe}-{i + 1}" for i in range(n)]

    img_prompt = (
        f"A clear, simple, friendly illustration representing the English word \"{word}\", "
        f"for children learning English vocabulary. Flat illustration style, bright colors, "
        f"clean plain background, single obvious subject, NO text or letters in the image."
    )
    out: list[str] = []
    for _ in range(max(1, min(n, 2))):   # 控成本：每词最多 2 张
        try:
            tmp = await _ark_t2i(img_prompt)
            if tmp:
                out.append(await _persist_to_cos(tmp))
        except Exception as e:  # noqa: BLE001
            logger.error("[Ark文生图] %s 失败: %s", word, e)
            break
    if not out:   # 全失败 → 占位兜底，不阻塞流程
        safe = urllib.parse.quote(word[:20])
        return [f"https://placehold.co/600x400?text={safe}-1"]
    return out


def generate_tts(text: str) -> str:
    """返回音频 URL。dev-mock 占位（卡片实际发音走 tts_service / 火山 TTS）。"""
    if is_tts_dev_mode():
        h = hashlib.md5((text or "").encode("utf-8")).hexdigest()[:12]
        return f"https://mock-tts.local/audio/{h}.mp3"
    raise NotImplementedError("真 TTS provider 未接入（卡片发音已走 tts_service）")
