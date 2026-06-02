"""整卷拆题：将整卷 OCR 原始文字（印刷体 + 手写体）送入 DeepSeek，拆分为多道结构化题目。

输入：OcrResult（印刷体 = 题目，手写体 = 学生作答）
输出：list[ParsedPaperQuestion]，每题含 question_no / question_type / stem /
      student_answer / correct_answer / explanation。

Dev 模式（deepseek_api_key 以 'sk-placeholder' 开头）跳过真实 API，确定性返回 2 题，
让整条链路在无账号时可完整测试。
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from app.core.exceptions import AppError
from app.services.llm_provider import chat_completion, is_llm_dev_mode
from app.services.ocr_service import OcrResult

# 与 ai_question_type_enum 对齐
_VALID_TYPES = {"单选", "填空", "完型", "阅读", "写作", "判断", "连线"}


@dataclass
class ParsedPaperQuestion:
    """DeepSeek 从整卷 OCR 文字拆出的单题结构化字段。"""
    question_no: str | None
    question_type: str | None
    stem: str | None
    student_answer: str | None
    correct_answer: str | None
    explanation: str | None


_SYSTEM_PROMPT = (
    "你是一个专业的英语试卷结构化助手。"
    "你会收到一整张英语试卷的 OCR 识别文字（印刷体为题目，手写体为学生作答），"
    "请把整卷拆分为一道道独立的题目，严格按 JSON 数组输出，不要任何额外文字。"
)

_USER_PROMPT_TEMPLATE = """以下是从一整张英语试卷图片中识别到的文字：

【印刷体识别（题目印刷文字，含题号/题干/选项）】
{printed_text}

【手写体识别（学生作答内容，通常是题号 + 答案）】
{handwritten_text}

请把整卷拆分为多道题目，返回纯 JSON 数组（不要任何 markdown 代码块或额外文字）。
数组每一项格式：
{{
  "question_no": "题号（如 27），无法识别则 null",
  "question_type": "单选|填空|完型|阅读|写作|判断|连线",
  "stem": "该题完整题干（含选项，不含学生作答）",
  "student_answer": "该题学生手写答案（按题号从手写体匹配，无法识别则 null）",
  "correct_answer": "正确答案（可推断则填，否则 null）",
  "explanation": "简要解析（可推断则填，否则 null）"
}}

要求：按题号顺序输出；识别不到任何题目时返回空数组 []。"""


def _normalize_type(raw: object) -> str:
    """归一化题型到 ai_question_type_enum 合法值，非法值兜底为 单选。"""
    return raw if raw in _VALID_TYPES else "单选"


def _dev_mock_split(ocr: OcrResult) -> list[ParsedPaperQuestion]:
    """dev 模式确定性拆题：识别 _MOCK_PRINTED 里的两道题。

    OCR mock 文字结构固定（题号 27/28，每题题干一行 + 选项一行），
    手写体为 '27. B\\n28. B'。这里做轻量行解析，保证测试确定性，
    无需真实 DeepSeek。OCR 全空时返回 []。
    """
    if not (ocr.printed_text or "").strip():
        return []

    # 解析手写体答案：'27. B' -> {'27': 'B'}
    answers: dict[str, str] = {}
    for line in (ocr.handwritten_text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        # 形如 '27. B' 或 '27 B'
        parts = line.replace(".", " ").split()
        if len(parts) >= 2 and parts[0].isdigit():
            answers[parts[0]] = parts[1]

    # 解析印刷体题目：题号行开启一题，后续非题号行并入题干
    questions: list[ParsedPaperQuestion] = []
    cur_no: str | None = None
    cur_lines: list[str] = []

    def _flush() -> None:
        if cur_no is None:
            return
        stem = "\n".join(cur_lines).strip() or None
        questions.append(
            ParsedPaperQuestion(
                question_no=cur_no,
                question_type="单选",
                stem=stem,
                student_answer=answers.get(cur_no),
                correct_answer=None,
                explanation=None,
            )
        )

    for line in ocr.printed_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        head = stripped.split(".", 1)[0]
        if head.isdigit():
            _flush()
            cur_no = head
            rest = stripped.split(".", 1)[1].strip() if "." in stripped else ""
            cur_lines = [rest] if rest else []
        else:
            cur_lines.append(stripped)
    _flush()
    return questions


async def split_paper_questions(ocr: OcrResult) -> list[ParsedPaperQuestion]:
    """将整卷 OCR 文字拆分为多道结构化题目。

    Dev 模式：确定性本地拆题，无需 API。
    Prod 模式：DeepSeek 拆题，返回 JSON 数组。

    异常处理：
    - API 错误 → AppError(502, "整卷拆题服务暂时不可用")
    - JSON 解析失败 / 非数组 → AppError(500, "整卷拆题返回格式异常")
    """
    if is_llm_dev_mode():
        return _dev_mock_split(ocr)

    if not (ocr.printed_text or "").strip():
        return []

    prompt = _USER_PROMPT_TEMPLATE.format(
        printed_text=ocr.printed_text or "(无印刷体识别结果)",
        handwritten_text=ocr.handwritten_text or "(无手写体识别结果)",
    )

    try:
        # 整卷可能含多道题，需较大输出预算（与课程/生题 service 对齐为 8192）
        response = await chat_completion(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=prompt,
            max_tokens=8192,
        )
    except Exception as exc:
        raise AppError(code=502, message=f"整卷拆题服务暂时不可用（{exc}）") from exc

    raw_text = (response.choices[0].message.content or "").strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[-2] if raw_text.count("```") >= 2 else raw_text
        raw_text = raw_text.lstrip("json").strip()

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise AppError(code=500, message="整卷拆题返回格式异常") from exc

    if not isinstance(data, list):
        raise AppError(code=500, message="整卷拆题返回格式异常")

    result: list[ParsedPaperQuestion] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        result.append(
            ParsedPaperQuestion(
                question_no=item.get("question_no"),
                question_type=_normalize_type(item.get("question_type")),
                stem=item.get("stem"),
                student_answer=item.get("student_answer"),
                correct_answer=item.get("correct_answer"),
                explanation=item.get("explanation"),
            )
        )
    return result
