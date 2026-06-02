"""AI 分析服务：调用 DeepSeek API（OpenAI 兼容协议）生成英语错题诊断报告。

- 通过 llm_provider.chat_completion 统一调用 LLM（厂商配置集中在 llm_provider）。
- LLM 返回 JSON 字符串，解析后写入 ai_analyses 表。
- 调用方需 await db.commit() 才真正落库。
"""
from __future__ import annotations

import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d3_wrong_questions import AiAnalysis, WrongQuestion
from app.services.llm_provider import chat_completion, is_llm_dev_mode

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
    """调用 DeepSeek API 分析错题，写入 ai_analyses 表，返回 ORM 对象（未 commit）。

    Dev 模式（DEEPSEEK_API_KEY 以 'sk-placeholder' 开头）：跳过真实 API，
    返回固定 mock 诊断结果，让整条链路可在无账号时完整测试。

    异常处理：
    - DeepSeek API 错误 → AppError(502, "AI服务暂时不可用，请稍后重试")
    - JSON 解析失败   → AppError(500, "AI分析返回格式异常")
    """
    if is_llm_dev_mode():
        # Dev mock：返回固定诊断结果
        analysis = AiAnalysis(
            id=uuid.uuid4(),
            wrong_question_id=wq.id,
            student_id=student_id,
            llm_provider="deepseek",
            error_types=["词义辨析错误", "动词短语混淆"],
            knowledge_points=["动词短语 hand in/out/over/up", "语境理解"],
            diagnosis="学生将 hand in（上交）误选为 hand out（分发）。两者意思相反，是常见的动词短语混淆错误。",
            suggestions="建议重点记忆 hand 系列短语：hand in=上交，hand out=分发，hand over=移交，hand up=举手。多做语境题加深记忆。",
            confidence_score=0.92,
            tokens_used=0,
        )
        db.add(analysis)
        await db.flush()
        # —— 发"AI分析完成"通知（D-074 Module 7B）——
        from app.services.notification_service import emit_analysis_done
        try:
            await emit_analysis_done(db, user_id=student_id, wq_id=wq.id)
        except Exception:
            pass  # 通知失败不影响主链路
        return analysis

    prompt = _USER_PROMPT_TEMPLATE.format(
        question_text=wq.question_text or "(暂无文字内容)",
        student_answer=wq.student_answer or "(未提供)",
        correct_answer=wq.correct_answer or "(未提供)",
        question_type=wq.question_type or "未知",
    )

    try:
        response = await chat_completion(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=prompt,
            max_tokens=1024,
        )
    except Exception as exc:
        raise AppError(code=502, message=f"AI服务暂时不可用，请稍后重试（{exc}）") from exc

    raw_text = response.choices[0].message.content or ""
    raw_text = raw_text.strip()

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise AppError(code=500, message="AI分析返回格式异常") from exc

    analysis = AiAnalysis(
        id=uuid.uuid4(),
        wrong_question_id=wq.id,
        student_id=student_id,
        llm_provider="deepseek",
        error_types=data.get("error_types", []),
        knowledge_points=data.get("knowledge_points", []),
        diagnosis=data["diagnosis"],
        suggestions=data["suggestions"],
        confidence_score=data.get("confidence_score"),
        tokens_used=(
            response.usage.prompt_tokens + response.usage.completion_tokens
            if response.usage
            else None
        ),
    )
    db.add(analysis)
    await db.flush()
    # —— 发"AI分析完成"通知（D-074 Module 7B）——
    from app.services.notification_service import emit_analysis_done
    try:
        await emit_analysis_done(db, user_id=student_id, wq_id=wq.id)
    except Exception:
        pass  # 通知失败不影响主链路
    return analysis
