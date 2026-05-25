"""AI 分析服务：调用 Anthropic Claude API 生成英语错题诊断报告。

- 使用 AsyncAnthropic（异步 client）。
- LLM 返回 JSON 字符串，解析后写入 ai_analyses 表。
- 调用方需 await db.commit() 才真正落库。
"""
from __future__ import annotations

import json
import uuid

import anthropic
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.d3_wrong_questions import AiAnalysis, WrongQuestion

_SYSTEM_PROMPT = (
    "你是一个专业的英语教学诊断助手，擅长分析英语错题并给出结构化诊断报告。"
    "请严格按照 JSON 格式输出，不要有任何其他文字。"
)

_USER_PROMPT_TEMPLATE = """请分析以下英语错题，给出诊断报告。

题目内容: {question_text}
学生答案: {student_answer}
正确答案: {correct_answer}
题型: {question_type}

请以纯 JSON 格式返回（不要任何 markdown 代码块或额外文字）:
{{
  "error_types": ["错误类型1", "错误类型2"],
  "knowledge_points": ["涉及知识点1", "涉及知识点2"],
  "diagnosis": "详细诊断说明（2-3句话，指出错误原因）",
  "suggestions": "学习建议（2-3句话，给出提升方向）",
  "confidence_score": 0.85
}}"""


async def analyze_wrong_question(
    db: AsyncSession,
    *,
    wq: WrongQuestion,
    student_id: uuid.UUID,
) -> AiAnalysis:
    """调用 Claude API 分析错题，写入 ai_analyses 表，返回 ORM 对象（未 commit）。

    异常处理：
    - Anthropic API 错误 → AppError(502, "AI服务暂时不可用，请稍后重试")
    - JSON 解析失败   → AppError(500, "AI分析返回格式异常")
    """
    prompt = _USER_PROMPT_TEMPLATE.format(
        question_text=wq.question_text or "(暂无文字内容)",
        student_answer=wq.student_answer or "(未提供)",
        correct_answer=wq.correct_answer or "(未提供)",
        question_type=wq.question_type or "未知",
    )

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        raise AppError(code=502, message=f"AI服务暂时不可用，请稍后重试（{exc}）") from exc

    raw_text = response.content[0].text.strip()

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise AppError(code=500, message="AI分析返回格式异常") from exc

    analysis = AiAnalysis(
        id=uuid.uuid4(),
        wrong_question_id=wq.id,
        student_id=student_id,
        llm_provider="claude",
        error_types=data.get("error_types", []),
        knowledge_points=data.get("knowledge_points", []),
        diagnosis=data["diagnosis"],
        suggestions=data["suggestions"],
        confidence_score=data.get("confidence_score"),
        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
    )
    db.add(analysis)
    await db.flush()
    return analysis
