"""发音评测 service（腾讯云智聆口语评测·新版 WebSocket）。

dev-mock：tencent_soe_secret_key 以 'placeholder' 开头 → 走本地 mock（复用 speech_score_service），
无需密钥即可跑通整条跟读评分链路与前端。
生产：填 TENCENT_SOE_APPID / SECRET_ID / SECRET_KEY（独立子账号，与 COS 隔离），
经 wss://soe.cloud.tencent.com/soe/api/<appid> 握手（HmacSha1 签名）→ 推音频 → 拿
准确度/流利度/完整度 + 逐词逐音素分。
文档：https://cloud.tencent.com/document/product/1774/107497
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
import uuid
from urllib.parse import quote

from app.core.config import settings
from app.services import speech_score_service

logger = logging.getLogger(__name__)

_WS_HOST = "soe.cloud.tencent.com"
_VOICE_FORMAT = {"pcm": 0, "wav": 1, "mp3": 2, "speex": 4}
_EVAL_MODE = {"word": 0, "sentence": 1}   # 新版：0 单词 / 1 句子
_CHUNK = 8000                              # 每帧字节（录音模式，非实时无需严格 1:1）


def _is_dev() -> bool:
    return (settings.tencent_soe_secret_key.startswith("placeholder")
            or settings.tencent_soe_appid.startswith("placeholder"))


def _level(score: int) -> str:
    if score >= 90:
        return "excellent"
    if score >= 80:
        return "good"
    if score >= 60:
        return "fair"
    return "poor"


def _build_ws_url(ref_text: str, *, mode: str, audio_format: str) -> str:
    """构造带签名的握手 URL。签名串=path?字典序原始参数；HmacSha1+Base64；再整体URL编码。"""
    now = int(time.time())
    params = {
        "secretid": settings.tencent_soe_secret_id,
        "timestamp": now,
        "expired": now + 3600,
        "nonce": now % 1_000_000_000,
        "server_engine_type": "16k_en",
        "voice_id": uuid.uuid4().hex,
        "voice_format": _VOICE_FORMAT.get((audio_format or "mp3").lower(), 2),
        "eval_mode": _EVAL_MODE.get(mode, 1),
        "score_coeff": 1.0,
        "rec_mode": 1,            # 录音模式（整段评测，非实时）
        "ref_text": ref_text,
    }
    path = f"/soe/api/{settings.tencent_soe_appid}"
    # 1) 字典序拼原始参数串
    raw = "&".join(f"{k}={params[k]}" for k in sorted(params))
    sign_str = f"{_WS_HOST}{path}?{raw}"
    # 2) HmacSha1 + Base64
    sig = base64.b64encode(
        hmac.new(settings.tencent_soe_secret_key.encode(), sign_str.encode(), hashlib.sha1).digest()
    ).decode()
    # 3) 连接 URL：参数值 URL 编码 + 追加编码后的 signature
    query = "&".join(f"{k}={quote(str(params[k]), safe='')}" for k in sorted(params))
    return f"wss://{_WS_HOST}{path}?{query}&signature={quote(sig, safe='')}"


async def _call_soe_ws(ref_text: str, audio_bytes: bytes, *, mode: str, audio_format: str) -> dict:
    """新版 WebSocket：握手→分帧推音频→发 end→收最终结果(final=1)。"""
    import websockets  # 延迟导入，dev-mock 无需该依赖

    url = _build_ws_url(ref_text, mode=mode, audio_format=audio_format)
    result: dict | None = None
    async with websockets.connect(url, max_size=8 * 1024 * 1024) as ws:
        # 录音模式(rec_mode=1)：整段音频一次性发送一个数据包
        await ws.send(audio_bytes)
        await ws.send(json.dumps({"type": "end"}))
        # 收结果直到 final=1
        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=20)
            if isinstance(msg, bytes):
                continue
            data = json.loads(msg)
            if data.get("code", 0) not in (0, None):
                raise RuntimeError(f"SOE {data.get('code')}: {data.get('message')}")
            if data.get("result"):
                result = data["result"]
            if data.get("final") == 1:
                break
    if not result:
        raise RuntimeError("SOE 无评测结果返回")
    return result


def _build_tip(words: list[dict], weak_phones: list[str]) -> str:
    weak_words = [w["word"] for w in words if w["score"] < 80]
    if weak_phones:
        return f"重点纠音：{'、'.join(weak_phones[:3])}（音读得不够准），多跟读几遍"
    if weak_words:
        return f"再练一练：{'、'.join(weak_words[:4])}"
    return "发音很标准，继续保持！"


def _map_result(res: dict) -> dict:
    words: list[dict] = []
    weak_phones: list[str] = []
    for w in (res.get("Words") or []):
        score = int(round(w.get("PronAccuracy", 0) or 0))
        words.append({"word": w.get("Word") or w.get("ReferenceWord") or "", "score": score})
        for ph in (w.get("PhoneInfos") or []):
            if (ph.get("PronAccuracy", 100) or 100) < 60:
                rl = ph.get("ReferenceLetter") or ph.get("ReferencePhone") or ph.get("Phone")
                if rl:
                    weak_phones.append(str(rl))
    # 准确度/总分为 0-100；流利度/完整度为 0-1 小数 → ×100 统一成百分制
    accuracy = int(round(res.get("PronAccuracy", 0) or 0))
    fluency = int(round((res.get("PronFluency", 0) or 0) * 100))
    completion = int(round((res.get("PronCompletion", 0) or 0) * 100))
    overall = int(round(res.get("SuggestedScore", 0) or accuracy or 0))
    return {
        "overall": overall, "level": _level(overall),
        "words": words or [{"word": "", "score": overall}],
        "tip": _build_tip(words, weak_phones),
        "accuracy": accuracy, "fluency": fluency, "completion": completion,
    }


async def assess(
    *, reference_text: str, audio_bytes: bytes | None,
    mode: str = "word", audio_format: str = "mp3",
) -> dict:
    """对一段跟读录音做发音评测。返回 {overall, level, words, tip, accuracy, fluency, completion}。"""
    ref = (reference_text or "").strip()
    if _is_dev() or not audio_bytes:
        return {**speech_score_service.score_pronunciation(reference_text=ref),
                "accuracy": None, "fluency": None, "completion": None}
    try:
        res = await _call_soe_ws(ref, audio_bytes, mode=mode, audio_format=audio_format)
        out = _map_result(res)
        if not out["words"] or not out["words"][0]["word"]:
            out["words"] = [{"word": ref, "score": out["overall"]}]
        logger.info("[SOE] 评测 ref=%r mode=%s 音频=%dB → 总分%d 准%d 流%d 整%d",
                    ref, mode, len(audio_bytes), out["overall"],
                    out["accuracy"], out["fluency"], out["completion"])
        return out
    except Exception as e:  # noqa: BLE001
        logger.error("[SOE] 发音评测失败，回退 mock: %s", e)
        return {**speech_score_service.score_pronunciation(reference_text=ref),
                "accuracy": None, "fluency": None, "completion": None}
