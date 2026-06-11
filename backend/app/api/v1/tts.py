"""语音合成流式接口（火山 TTS）。

公开（音频播放器无法携带鉴权头）；以文本长度上限 + 进程内缓存控制成本。
dev-mock 下返回 204（无音频）。
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.services import tts_service

router = APIRouter(prefix="/tts", tags=["tts"])

UserDep = Annotated[User, Depends(get_current_user)]

_MAX_TEXT = 1000  # 支持整段听力素材
_CACHE_MAX = 200
_cache: "OrderedDict[str, bytes]" = OrderedDict()


@router.get("/url", response_model=BaseResponse[dict])
async def speak_url(
    current_user: UserDep,
    text: str = Query("", max_length=1200),
    stage: str = Query("junior", description="学段语速: primary/junior/senior，默认初中"),
):
    """返回文本对应的可播放音频 URL：优先 COS 直链（持久化）；COS 未配置则返回空，
    前端回退到 /tts/speak 流式接口。stage 控制语速（小学慢/初中标准/高中略快）。"""
    t = (text or "").strip()[:_MAX_TEXT]
    speed = tts_service.speed_for_stage(stage)
    url = await tts_service.get_or_create_audio_url(t, speed=speed) if t else None
    return make_ok({"url": url or ""})


@router.get("/speak")
async def speak(text: str = Query("", max_length=1200), stage: str = Query("junior")):
    """合成并返回 mp3 音频。命中缓存直接复用，dev-mock 返回 204。"""
    text = (text or "").strip()[:_MAX_TEXT]
    if not text:
        return Response(status_code=204)
    speed = tts_service.speed_for_stage(stage)
    ckey = f"{text}@{speed}"

    if ckey in _cache:
        _cache.move_to_end(ckey)
        audio = _cache[ckey]
    else:
        audio = await tts_service.synthesize(text, speed_ratio=speed)
        if audio:
            _cache[ckey] = audio
            if len(_cache) > _CACHE_MAX:
                _cache.popitem(last=False)

    if not audio:
        return Response(status_code=204)
    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )
