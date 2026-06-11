"""语音合成流式接口（火山 TTS）。

公开（音频播放器无法携带鉴权头）；以文本长度上限 + 进程内缓存控制成本。
dev-mock 下返回 204（无音频）。
"""
from __future__ import annotations

from collections import OrderedDict

from fastapi import APIRouter, Query, Response

from app.services import tts_service

router = APIRouter(prefix="/tts", tags=["tts"])

_MAX_TEXT = 300
_CACHE_MAX = 200
_cache: "OrderedDict[str, bytes]" = OrderedDict()


@router.get("/speak")
async def speak(text: str = Query("", max_length=600)):
    """合成并返回 mp3 音频。命中缓存直接复用，dev-mock 返回 204。"""
    text = (text or "").strip()[:_MAX_TEXT]
    if not text:
        return Response(status_code=204)

    if text in _cache:
        _cache.move_to_end(text)
        audio = _cache[text]
    else:
        audio = await tts_service.synthesize(text)
        if audio:
            _cache[text] = audio
            if len(_cache) > _CACHE_MAX:
                _cache.popitem(last=False)

    if not audio:
        return Response(status_code=204)
    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )
