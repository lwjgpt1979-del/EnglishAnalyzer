"""词力通图/音频 provider 抽象（P1 / D-101）。

dev-mock：图与音频返回确定性占位 URL，一分钱不花、可测。
真·文生图 / 真 TTS 留 config 接缝（image_provider/tts_provider != "mock"），
等确认预算 + 安全渠道给 key 后实现 _real_* 分支。
"""
from __future__ import annotations

import hashlib
import urllib.parse

from app.core.config import settings


def is_image_dev_mode() -> bool:
    return settings.image_provider == "mock" or settings.image_api_key.startswith("img-placeholder")


def is_tts_dev_mode() -> bool:
    return settings.tts_provider == "mock" or settings.tts_api_key.startswith("tts-placeholder")


def generate_images(prompt: str, n: int = 3) -> list[str]:
    """返回 n 张图 URL。dev-mock 用 placehold.co 占位（按 prompt+序号确定性）。"""
    if is_image_dev_mode():
        safe = urllib.parse.quote((prompt or "word")[:20])
        return [f"https://placehold.co/600x400?text={safe}-{i + 1}" for i in range(n)]
    raise NotImplementedError("真·文生图 provider 未接入（需预算 + key）")


def generate_tts(text: str) -> str:
    """返回音频 URL。dev-mock 用确定性占位 URL（按文本 hash）。"""
    if is_tts_dev_mode():
        h = hashlib.md5((text or "").encode("utf-8")).hexdigest()[:12]
        return f"https://mock-tts.local/audio/{h}.mp3"
    raise NotImplementedError("真 TTS provider 未接入（需预算 + key）")
