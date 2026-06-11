"""语音合成 service（火山引擎/豆包 TTS）。

dev-mock：tts_provider != 'volcano' 或缺凭据时返回空字节（无音频，不报错）。
生产：设 TTS_PROVIDER=volcano + VOLC_TTS_APPID/ACCESS_TOKEN/CLUSTER，调用
火山引擎语音合成 HTTP API，返回 mp3 音频字节。
文档: https://www.volcengine.com/docs/6561/79817
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import uuid

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def is_dev_mode() -> bool:
    return (
        settings.tts_provider != "volcano"
        or not settings.volc_tts_appid
        or not settings.volc_tts_access_token
    )


async def synthesize(text: str, *, voice: str | None = None) -> bytes:
    """把文本合成为 mp3 音频字节。dev-mock 返回空字节。"""
    text = (text or "").strip()
    if not text:
        return b""
    if is_dev_mode():
        logger.warning("[TTS DEV MOCK] 无真实语音合成，text=%r", text[:40])
        return b""

    payload = {
        "app": {
            "appid": settings.volc_tts_appid,
            "token": settings.volc_tts_access_token,
            "cluster": settings.volc_tts_cluster,
        },
        "user": {"uid": "enggramer"},
        "audio": {
            "voice_type": voice or settings.volc_tts_voice,
            "encoding": "mp3",
            "speed_ratio": 1.0,
        },
        "request": {
            "reqid": str(uuid.uuid4()),
            "text": text,
            "operation": "query",
        },
    }
    # 火山鉴权头格式特殊：Bearer 后跟分号
    headers = {"Authorization": f"Bearer;{settings.volc_tts_access_token}"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(settings.volc_tts_url, json=payload, headers=headers)
    data = resp.json()
    # 火山成功码为 3000
    if data.get("code") != 3000 or not data.get("data"):
        logger.error("[TTS] 火山合成失败: %s", data.get("message") or data)
        return b""
    return base64.b64decode(data["data"])


# ── 持久化到腾讯 COS ─────────────────────────────────────────────────────────
_cos_client = None


def _is_cos_dev() -> bool:
    return settings.cos_secret_key.startswith("placeholder")


def _get_cos_client():
    global _cos_client
    if _cos_client is None:
        from qcloud_cos import CosConfig, CosS3Client  # type: ignore[import]
        _cos_client = CosS3Client(CosConfig(
            Region=settings.cos_region,
            SecretId=settings.cos_secret_id,
            SecretKey=settings.cos_secret_key,
        ))
    return _cos_client


def _cos_key(text: str, voice: str) -> str:
    digest = hashlib.md5(f"{voice}|{text}".encode("utf-8")).hexdigest()
    return f"tts/{digest}.mp3"


async def get_or_create_audio_url(text: str, *, voice: str | None = None) -> str | None:
    """返回该文本对应的 COS 音频直链（不存在则现合成并上传）。

    COS 为 dev 占位时返回 None，由调用方回退到 /tts/speak 流式播放。
    """
    text = (text or "").strip()
    if not text or _is_cos_dev():
        return None
    v = voice or settings.volc_tts_voice
    key = _cos_key(text, v)
    url = f"{settings.cos_base_url}/{key}"

    def _exists() -> bool:
        try:
            return bool(_get_cos_client().object_exists(Bucket=settings.cos_bucket, Key=key))
        except Exception as e:  # noqa: BLE001
            logger.warning("[TTS] COS object_exists 失败: %s", e)
            return False

    if await asyncio.to_thread(_exists):
        return url

    audio = await synthesize(text, voice=voice)
    if not audio:
        return None

    def _put() -> None:
        _get_cos_client().put_object(
            Bucket=settings.cos_bucket, Key=key, Body=audio,
            ContentType="audio/mpeg",
        )

    try:
        await asyncio.to_thread(_put)
    except Exception as e:  # noqa: BLE001
        logger.error("[TTS] COS 上传失败: %s", e)
        return None
    return url
