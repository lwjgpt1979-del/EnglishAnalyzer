"""发音评测 service（腾讯云智聆口语评测 SOE，基础版）。

dev-mock：tencent_soe_secret_key 以 'placeholder' 开头 → 走本地 mock（复用 speech_score_service），
无需密钥即可跑通整条跟读评分链路与前端。
生产：填 TENCENT_SOE_SECRET_ID/KEY/REGION（独立子账号，与 COS 隔离），调 SOE
TransmitOralProcessWithInit 一次性传录音，返回 准确度/流利度/完整度 + 逐词逐音素分。
文档：https://cloud.tencent.com/document/product/884/19319
"""
from __future__ import annotations

import asyncio
import base64
import logging
import uuid

from app.core.config import settings
from app.services import speech_score_service

logger = logging.getLogger(__name__)

# SOE 枚举（基础版）：题型 / 语种 / 容器格式
_EVAL_MODE = {"word": 0, "sentence": 1}
_SERVER_EN = 0
_WORKMODE_ONCE = 1            # 非流式：整段一次性
_FILE_TYPE = {"pcm": 1, "wav": 2, "mp3": 3}


def _is_dev() -> bool:
    return settings.tencent_soe_secret_key.startswith("placeholder")


def _level(score: int) -> str:
    if score >= 90:
        return "excellent"
    if score >= 80:
        return "good"
    if score >= 60:
        return "fair"
    return "poor"


def _call_soe(ref_text: str, audio_bytes: bytes, *, mode: str, audio_format: str):
    """同步调用 SOE（在 to_thread 中执行）。"""
    from tencentcloud.common import credential
    from tencentcloud.soe.v20180724 import models, soe_client

    cred = credential.Credential(
        settings.tencent_soe_secret_id, settings.tencent_soe_secret_key)
    client = soe_client.SoeClient(cred, settings.tencent_soe_region)

    req = models.TransmitOralProcessWithInitRequest()
    req.SeqId = 1
    req.IsEnd = 1
    req.WorkMode = _WORKMODE_ONCE
    req.EvalMode = _EVAL_MODE.get(mode, 1)
    req.ServerType = _SERVER_EN
    req.ScoreCoeff = 1.0
    req.SessionId = uuid.uuid4().hex
    req.RefText = ref_text
    req.VoiceFileType = _FILE_TYPE.get((audio_format or "mp3").lower(), 3)
    req.VoiceEncodeType = 1
    req.UserVoiceData = base64.b64encode(audio_bytes).decode()
    return client.TransmitOralProcessWithInit(req)


def _build_tip(words: list[dict], weak_phones: list[str]) -> str:
    weak_words = [w["word"] for w in words if w["score"] < 80]
    if weak_phones:
        return f"重点纠音：{ '、'.join(weak_phones[:3]) }（音读得不够准），多跟读几遍"
    if weak_words:
        return f"再练一练：{ '、'.join(weak_words[:4]) }"
    return "发音很标准，继续保持！"


async def assess(
    *, reference_text: str, audio_bytes: bytes | None,
    mode: str = "word", audio_format: str = "mp3",
) -> dict:
    """对一段跟读录音做发音评测。返回 {overall, level, words, tip, accuracy, fluency, completion}。"""
    ref = (reference_text or "").strip()
    if _is_dev() or not audio_bytes:
        # dev-mock：无密钥或无音频 → 本地确定性评分，链路照常跑通
        return {**speech_score_service.score_pronunciation(reference_text=ref),
                "accuracy": None, "fluency": None, "completion": None}

    try:
        resp = await asyncio.to_thread(
            _call_soe, ref, audio_bytes, mode=mode, audio_format=audio_format)
    except Exception as e:  # noqa: BLE001
        logger.error("[SOE] 发音评测失败，回退 mock: %s", e)
        return {**speech_score_service.score_pronunciation(reference_text=ref),
                "accuracy": None, "fluency": None, "completion": None}

    words: list[dict] = []
    weak_phones: list[str] = []
    for w in (resp.Words or []):
        score = int(round(getattr(w, "PronAccuracy", 0) or 0))
        words.append({"word": getattr(w, "Word", "") or getattr(w, "ReferenceWord", "") or "", "score": score})
        for ph in (getattr(w, "PhoneInfos", None) or []):
            pa = getattr(ph, "PronAccuracy", 100) or 100
            if pa < 60:
                rl = getattr(ph, "ReferenceLetter", "") or getattr(ph, "ReferencePhone", "") or getattr(ph, "Phone", "")
                if rl:
                    weak_phones.append(str(rl))

    accuracy = int(round(getattr(resp, "PronAccuracy", 0) or 0))
    fluency = int(round(getattr(resp, "PronFluency", 0) or 0))
    completion = int(round(getattr(resp, "PronCompletion", 0) or 0))
    overall = int(round(getattr(resp, "SuggestedScore", 0) or accuracy or 0))

    return {
        "overall": overall,
        "level": _level(overall),
        "words": words or [{"word": ref, "score": overall}],
        "tip": _build_tip(words, weak_phones),
        "accuracy": accuracy,
        "fluency": fluency,
        "completion": completion,
    }
