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
import re
import uuid

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# 对话行：以「英文名:」开头，如 "Anna: Hi Tom"
_DIALOGUE_LINE = re.compile(r"([A-Z][A-Za-z]{1,15})\s*[:：]\s*")


def _split_dialogue(text: str) -> list[tuple[str, str]] | None:
    """把对话体拆成 [(说话人, 台词)]；说话人少于 2 个则返回 None（非对话）。"""
    parts = _DIALOGUE_LINE.split(text or "")
    # split 结果：[前缀, 名1, 台词1, 名2, 台词2, ...]
    if len(parts) < 5:
        return None
    segs: list[tuple[str, str]] = []
    for i in range(1, len(parts) - 1, 2):
        speaker = parts[i].strip()
        line = parts[i + 1].strip()
        if line:
            segs.append((speaker, line))
    speakers = {s for s, _ in segs}
    return segs if len(speakers) >= 2 else None


def _male_voices() -> list[str]:
    return [v.strip() for v in (settings.volc_tts_voice_male or "").split(",") if v.strip()]


def _female_voices() -> list[str]:
    return [v.strip() for v in (settings.volc_tts_voice_female or "").split(",") if v.strip()]


def _all_voices() -> list[str]:
    return (_male_voices() + _female_voices()) or [settings.volc_tts_voice]


# 常见英文名性别（用于对话听力按角色选男/女声；未知名按出现顺序男女交替）
_FEMALE_NAMES = {
    "anna", "lily", "lucy", "mary", "kate", "amy", "jenny", "susan", "helen",
    "grace", "emma", "alice", "lisa", "nancy", "cindy", "sandy", "linda", "betty",
    "rose", "ann", "sally", "kitty", "eve", "may", "joy", "lulu", "mona", "miss",
}
_MALE_NAMES = {
    "tom", "jack", "mike", "tim", "bob", "peter", "david", "john", "sam", "ben",
    "mark", "tony", "jim", "eric", "frank", "jerry", "harry", "andy", "mr", "dad",
    "daniel", "kevin", "leo", "max", "nick", "paul", "tony", "bill", "george",
}


def _gender_of(name: str) -> str | None:
    n = (name or "").strip().lower()
    if n in _FEMALE_NAMES:
        return "f"
    if n in _MALE_NAMES:
        return "m"
    return None


def _voices_for_gender(g: str) -> list[str]:
    vs = _female_voices() if g == "f" else _male_voices()
    return vs or _all_voices()


def _pick_voice_for_text(text: str) -> str:
    """单词/句子：按文本哈希稳定选一个音色（同文本固定、跨文本有男有女）。"""
    voices = _all_voices()
    h = int(hashlib.md5((text or "").encode("utf-8")).hexdigest(), 16)
    return voices[h % len(voices)]


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


def _assign_dialogue_voices(segs: list[tuple[str, str]]) -> dict[str, str]:
    """按说话人分配音色：已知名按性别选；未知名男女交替；同性别多角色在池内轮换。"""
    speaker_voice: dict[str, str] = {}
    gidx = {"m": 0, "f": 0}
    alt = 0
    for speaker, _ in segs:
        if speaker in speaker_voice:
            continue
        g = _gender_of(speaker)
        if g is None:
            g = "m" if alt % 2 == 0 else "f"
            alt += 1
        vlist = _voices_for_gender(g)
        speaker_voice[speaker] = vlist[gidx[g] % len(vlist)]
        gidx[g] += 1
    return speaker_voice


async def _synthesize_smart(text: str, *, voice: str | None) -> bytes:
    """对话体→按说话人性别多音色逐句合成拼接；否则用指定音色单合成。"""
    segs = _split_dialogue(text) if voice is None else None
    if not segs:
        v = voice or _pick_voice_for_text(text)
        audio = await synthesize(text, voice=v)
        if not audio and v != settings.volc_tts_voice:
            audio = await synthesize(text, voice=settings.volc_tts_voice)
        return audio

    speaker_voice = _assign_dialogue_voices(segs)
    chunks: list[bytes] = []
    for speaker, line in segs:
        v = speaker_voice[speaker]
        audio = await synthesize(line, voice=v)
        if not audio and v != settings.volc_tts_voice:  # 音色不可用→退默认
            audio = await synthesize(line, voice=settings.volc_tts_voice)
        if audio:
            chunks.append(audio)
    return b"".join(chunks)


async def get_or_create_audio_url(text: str, *, voice: str | None = None) -> str | None:
    """返回该文本对应的 COS 音频直链（不存在则现合成并上传）。

    对话体自动多说话人不同音色；COS 为 dev 占位时返回 None，调用方回退流式。
    """
    text = (text or "").strip()
    if not text or _is_cos_dev():
        return None
    # 缓存 key：对话按音色池标记；单文本按所选(哈希稳定)音色，保证幂等
    is_dlg = voice is None and _split_dialogue(text) is not None
    if is_dlg:
        v = f"dialogue:{settings.volc_tts_voice_male}|{settings.volc_tts_voice_female}"
    elif voice:
        v = voice
    else:
        v = _pick_voice_for_text(text)
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

    audio = await _synthesize_smart(text, voice=voice)
    if not audio:
        return None

    def _put() -> None:
        _get_cos_client().put_object(
            Bucket=settings.cos_bucket, Key=key, Body=audio,
            ContentType="audio/mpeg",
            ACL="public-read",  # 对象级公开读，音频直链可匿名播放（不依赖桶ACL）
        )

    try:
        await asyncio.to_thread(_put)
    except Exception as e:  # noqa: BLE001
        logger.error("[TTS] COS 上传失败: %s", e)
        return None
    return url
