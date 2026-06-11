"""发音评分 service（听力跟读模块·跟读评分）。

MVP：dev mock 评分——按参照文本生成可信的逐词得分，跑通整套跟读 UX。
生产接入：设 SPEECH_EVAL_PROVIDER=iflytek（或 aliyun）后改 _score_real，
调用语音评测 API（讯飞/阿里），对比录音与标准音素返回真实评分。
"""
from __future__ import annotations

import random
import re

from app.core.config import settings

# 低于此分判为「待加强」并标红
WEAK_THRESHOLD = 80

# 常见易错音提示（dev mock 用，命中即给针对性建议）
_TIPS = [
    ("th", "注意 th 的齿间音，舌尖轻触上齿"),
    ("r", "卷舌音 r 不要发成中文的「儿」"),
    ("v", "v 是上齿咬下唇的浊辅音，别发成 w"),
    ("ed", "过去式 -ed 结尾的清浊读音要区分"),
    ("s", "复数/三单 -s 结尾别吞音"),
]


def _is_dev() -> bool:
    return settings.speech_eval_provider.startswith("placeholder")


def _tokenize(text: str) -> list[str]:
    return [w for w in re.findall(r"[A-Za-z']+", text or "")]


def _level(score: int) -> str:
    if score >= 90:
        return "excellent"
    if score >= 80:
        return "good"
    if score >= 60:
        return "fair"
    return "poor"


def _pick_tip(words: list[dict]) -> str:
    weak = [w["word"].lower() for w in words if w["score"] < WEAK_THRESHOLD]
    for frag, tip in _TIPS:
        if any(frag in w for w in weak):
            return tip
    if weak:
        return f"重点再练：{'、'.join(w['word'] for w in words if w['score'] < WEAK_THRESHOLD)[:40]}"
    return "发音很标准，继续保持！"


def score_pronunciation(*, reference_text: str) -> dict:
    """对一句话的跟读录音评分。MVP 返回 mock 评分。"""
    tokens = _tokenize(reference_text)
    if not tokens:
        return {"overall": 0, "level": "poor", "words": [], "tip": "没有可跟读的内容"}

    if not _is_dev():
        return _score_real(reference_text=reference_text)

    # dev mock：长词/含难音的词更容易低分，整体偏正向（70~98）
    words: list[dict] = []
    for w in tokens:
        base = random.randint(72, 98)
        if len(w) >= 8:
            base -= random.randint(4, 12)
        if any(frag in w.lower() for frag, _ in _TIPS):
            base -= random.randint(3, 10)
        words.append({"word": w, "score": max(45, min(100, base))})

    overall = round(sum(x["score"] for x in words) / len(words))
    return {
        "overall": overall,
        "level": _level(overall),
        "words": words,
        "tip": _pick_tip(words),
    }


def _score_real(*, reference_text: str) -> dict:  # pragma: no cover - 生产接入占位
    raise NotImplementedError(
        "真实语音评测未接入：请实现讯飞/阿里语音评测 API 调用"
    )
