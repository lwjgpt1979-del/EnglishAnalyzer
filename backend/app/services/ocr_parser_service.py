"""OCR 结果解析：将两路 OCR 原始文字送入 DeepSeek，提取结构化字段。

输入：印刷体文字 + 手写体文字
输出：question_text / student_answer / correct_answer / question_type
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.exceptions import AppError
from app.services.ocr_service import OcrResult


@dataclass
class ParsedQuestion:
    """DeepSeek 从 OCR 文字中提取的结构化字段。"""
    question_text: str | None
    student_answer: str | None
    correct_answer: str | None
    question_type: str | None  # 单选|完型|阅读|作文|其他


_SYSTEM_PROMPT = (
    "你是一个专业的英语教育 OCR 后处理助手。"
    "你会收到从英语试卷图片中识别到的原始文字（印刷体 + 手写体），"
    "请提取结构化信息并严格按 JSON 格式输出，不要有任何其他文字。"
)

_USER_PROMPT_TEMPLATE = """以下是从英语试卷图片中识别到的文字：

【印刷体识别（题目印刷文字）】
{printed_text}

【手写体识别（学生作答内容）】
{handwritten_text}

请从以上文字中提取结构化信息，返回纯 JSON 格式（不要任何 markdown 代码块或额外文字）：
{{
  "question_text": "题目内容（印刷体部分，包含题干和选项，不含学生作答）",
  "student_answer": "学生手写的答案（从手写体识别中提取，若无法识别则 null）",
  "correct_answer": "正确答案（若题目中有标注或可推断则填写，否则 null）",
  "question_type": "单选|完型|阅读|作文|其他"
}}

若无法判断某字段，设为 null。"""


async def parse_ocr_result(ocr_result: OcrResult) -> ParsedQuestion:
    """将 OCR 原始文字送入 DeepSeek，返回结构化 ParsedQuestion。

    异常处理：
    - API 错误 → AppError(502, "OCR解析服务暂时不可用")
    - JSON 解析失败 → AppError(500, "OCR解析返回格式异常")
    """
    prompt = _USER_PROMPT_TEMPLATE.format(
        printed_text=ocr_result.printed_text or "(无印刷体识别结果)",
        handwritten_text=ocr_result.handwritten_text or "(无手写体识别结果)",
    )

    try:
        client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url="https://api.deepseek.com",
        )
        response = await client.chat.completions.create(
            model="deepseek-chat",
            max_tokens=1024,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
    except Exception as exc:
        raise AppError(code=502, message=f"OCR解析服务暂时不可用（{exc}）") from exc

    raw_text = (response.choices[0].message.content or "").strip()
    # Strip markdown code fences if the model returns them despite instructions
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[-2] if raw_text.count("```") >= 2 else raw_text
        raw_text = raw_text.lstrip("json").strip()

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise AppError(code=500, message="OCR解析返回格式异常") from exc

    if not isinstance(data, dict):
        raise AppError(code=500, message="OCR解析返回格式异常")

    valid_types = {"单选", "完型", "阅读", "作文", "其他"}
    question_type = data.get("question_type")
    if question_type not in valid_types:
        question_type = "其他"

    return ParsedQuestion(
        question_text=data.get("question_text"),
        student_answer=data.get("student_answer"),
        correct_answer=data.get("correct_answer"),
        question_type=question_type,
    )
