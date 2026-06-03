"""作文 AI 精修 service（D-109）。复用 LLM dev-mock；会员闸门 Pro月3次/ProMax不限。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, time, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d5_learning import Essay
from app.services import membership_service
from app.services.llm_provider import chat_completion, is_llm_dev_mode

_DIMENSIONS = [("内容", 25), ("语言", 25), ("结构", 25), ("词汇", 25)]
_PRO_MONTHLY_LIMIT = 3

_SYSTEM_PROMPT = (
    "你是专业英语作文批改老师。请对学生作文从内容/语言/结构/词汇四个维度各 25 分打分，"
    "逐处指出问题（原文片段、修改建议、类型[语法/表达/词汇]、说明），并给出整体优化版本。"
    "只返回 JSON，键：scores(list of {dimension,score,full})、total(int)、"
    "issues(list of {original,suggestion,type,color,explanation})、polished_text(str)。"
    "颜色规则：语法=red，表达=yellow，词汇=blue。"
)


async def _monthly_count(db: AsyncSession, student_id: uuid.UUID) -> int:
    now = datetime.now(timezone.utc)
    month_start = datetime.combine(now.date().replace(day=1), time.min, tzinfo=timezone.utc)
    return (await db.execute(
        select(func.count()).select_from(Essay).where(
            Essay.student_id == student_id,
            Essay.created_at >= month_start,
        )
    )).scalar_one()


async def _grade(*, original_text: str, essay_type: str | None) -> dict:
    if is_llm_dev_mode():
        return {
            "scores": [{"dimension": d, "score": s - 3, "full": s} for d, s in _DIMENSIONS],
            "total": sum(s - 3 for _, s in _DIMENSIONS),
            "issues": [{
                "original": "very good", "suggestion": "excellent", "type": "词汇",
                "color": "blue", "explanation": "将 'very good' 替换为 'excellent' 更符合书面表达。",
            }],
            "polished_text": original_text + "\n\n[AI 优化版 - dev mock]",
        }
    prompt = f"作文题型：{essay_type or '未指定'}\n作文原文：\n{original_text}"
    try:
        resp = await chat_completion(
            system_prompt=_SYSTEM_PROMPT, user_prompt=prompt, max_tokens=2048)
    except Exception as exc:
        raise AppError(code=502, message=f"AI服务暂时不可用，请稍后重试（{exc}）") from exc
    try:
        return json.loads((resp.choices[0].message.content or "").strip())
    except json.JSONDecodeError as exc:
        raise AppError(code=500, message="AI作文批改返回格式异常") from exc


async def polish_essay(
    db: AsyncSession, *, student_id: uuid.UUID, original_text: str,
    title: str | None = None, essay_type: str | None = None,
    wrong_question_id: uuid.UUID | None = None,
) -> Essay:
    m = await membership_service.get_active_membership(db, user_id=student_id)
    tier = str(m.tier) if m else "free"
    if tier in ("free", "basic"):
        raise AppError(code=403, message="作文精修为 Pro/ProMax 专属功能，请升级会员")
    if tier == "pro" and await _monthly_count(db, student_id) >= _PRO_MONTHLY_LIMIT:
        raise AppError(code=403, message="本月作文精修次数已用完（Pro 每月3次）")
    result = await _grade(original_text=original_text, essay_type=essay_type)
    essay = Essay(
        id=uuid.uuid4(), student_id=student_id, wrong_question_id=wrong_question_id,
        original_text=original_text, polished_text=result["polished_text"],
        dimensions={
            "scores": result["scores"], "total": result["total"],
            "issues": result["issues"], "title": title, "essay_type": essay_type,
        },
        round_count=1, status="completed",
    )
    db.add(essay)
    await db.flush()
    return essay


async def get_essay(db: AsyncSession, *, student_id: uuid.UUID, essay_id: uuid.UUID) -> Essay | None:
    return (await db.execute(
        select(Essay).where(Essay.id == essay_id, Essay.student_id == student_id)
    )).scalar_one_or_none()


async def list_essays(db: AsyncSession, *, student_id: uuid.UUID) -> list[Essay]:
    return list((await db.execute(
        select(Essay).where(Essay.student_id == student_id).order_by(Essay.created_at.desc())
    )).scalars().all())
