"""豆包 Vision 服务（M40）。

实现 OcrProvider 协议，用豆包 Seed-2.0 多模态模型直接看图拆题，
替代原有「阿里云OCR + 腾讯云OCR」双引擎方案。

Dev 模式（doubao_api_key 以 'placeholder' 开头）返回与原 OCR mock 一致的
OcrResult，保证现有 344 个测试全部继续通过。
"""
from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from app.core.config import settings
from app.services.ocr_service import OcrResult

_log = logging.getLogger(__name__)

# ── mock 数据（豆包直出 JSON 格式，含正确答案供 is_wrong 判断）─────────────────
# 题27 学生答 A 正确答案 A → is_wrong=False（写 correct_count）
# 题28 学生答 B 正确答案 A → is_wrong=True（写 wrong_count）
import json as _json

_MOCK_DOUBAO_JSON = _json.dumps([
    {
        "question_no": "27",
        "question_type": "单选",
        "stem": (
            "The teacher asked the students to _____ their homework on time.\n"
            "A. hand in  B. hand out  C. hand over  D. hand up"
        ),
        "student_answer": "A",
        "correct_answer": "A",
        "explanation": "hand in 意为上交",
    },
    {
        "question_no": "28",
        "question_type": "单选",
        "stem": (
            "She _____ in Beijing for three years before she moved to Shanghai.\n"
            "A. lived  B. had lived  C. has lived  D. lives"
        ),
        "student_answer": "B",
        "correct_answer": "A",
        "explanation": "过去完成时表示过去某时之前已发生的动作",
    },
], ensure_ascii=False)

# ── dev 模式检测 ──────────────────────────────────────────────────────────────


def _is_doubao_dev_mode() -> bool:
    return settings.doubao_api_key.startswith("placeholder")


# ── Prompt ────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "你是一个专业的英语试卷结构化助手。"
    "你会收到一整张英语试卷图片（含印刷体题目和学生手写答案），"
    "请把整卷拆分为一道道独立题目，严格按 JSON 数组输出，不要任何额外文字。"
)

_USER_PROMPT = """请分析这张英语试卷图片，把所有题目拆分为结构化 JSON 数组。

每一项格式：
{
  "question_no": "题号（如 27），无法识别则 null",
  "question_type": "单选|填空|完型|阅读|写作|判断|连线",
  "stem": "该题完整题干（含选项，不含学生作答）",
  "student_answer": "该题学生手写答案，无法识别则 null",
  "correct_answer": "正确答案（可推断则填，否则 null）",
  "explanation": "简要解析（可推断则填，否则 null）"
}

要求：按题号顺序输出；识别不到任何题目时返回空数组 []。
只返回纯 JSON 数组，不要任何 markdown 代码块或额外文字。"""


# ── Provider 实现 ─────────────────────────────────────────────────────────────


class DoubaoVisionProvider:
    """豆包 Vision 实现的 OcrProvider。

    接口与 DualEngineOcrProvider 完全一致（recognize(image_url) → OcrResult），
    ocr_service.get_ocr_provider() 切换到本类后其余链路零改动。

    返回的 OcrResult：
      printed_text   — 豆包解析出的原始 JSON 字符串（供 paper_split_service 兼容处理）
      handwritten_text — 空字符串（豆包已在 printed_text JSON 里含学生答案，无需分离）
    """

    async def recognize(self, image_url: str) -> OcrResult:
        if _is_doubao_dev_mode():
            # 直出 JSON 格式（handwritten_text="" 触发 paper_split_service 的豆包直解析路径）
            return OcrResult(
                printed_text=_MOCK_DOUBAO_JSON,
                handwritten_text="",
            )

        client = AsyncOpenAI(
            api_key=settings.doubao_api_key,
            base_url=settings.doubao_base_url,
        )

        try:
            response = await client.chat.completions.create(
                model=settings.doubao_vision_model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": _USER_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {"url": image_url},
                            },
                        ],
                    },
                ],
                max_tokens=8192,
            )
        except Exception as exc:
            _log.error("DoubaoVision API failed: %s", exc)
            raise

        raw = (response.choices[0].message.content or "").strip()

        # 豆包直接返回 JSON 数组字符串，存入 printed_text 供下游 paper_split_service
        # 的 _doubao_parse_direct() 方法直接解析，跳过传统 OCR 文字拼接步骤。
        return OcrResult(
            printed_text=raw,
            handwritten_text="",  # 豆包已在 JSON 里包含 student_answer，无需分离
        )
