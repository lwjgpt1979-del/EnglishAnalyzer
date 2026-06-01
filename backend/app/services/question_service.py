"""V2 仿真题 service（D-079 / M3a）。

职责：
1. persist_questions() — AI 生成 → SimulatedQuestion 行（按 (kp_id, stem) 去重）
2. list_questions_by_kp() — 给 API 用的读取（不带 answer，前端拿不到答案）
3. submit_attempt() — 判分 + 错题落库（含 KP 链接）+ 返回结果

WrongQuestion 映射规则：
- 单选 → enum "单选"；填空/判断 → enum "其他"（d3_wrong_questions.question_type_enum 没有这两个值）
- source_image_url 是 NOT NULL，练习场景没有图片，写占位字符串 "v2-practice"
- 没有 source_type 字段，所以来源标识体现在 source_image_url 的值上
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d3_wrong_questions import WrongQuestion
from app.models.d4_knowledge import WrongQuestionKnowledgePoint
from app.models.d12_v2_exams import SimulatedQuestion
from app.schemas.questions import (
    AIGeneratedQuestion, PracticeResultOut, SimQuestionOut,
)


# 映射 SimQuestion.question_type → WrongQuestion.question_type（合法 enum）
_WQ_QTYPE_MAP = {
    "单选": "单选",
    "填空": "其他",
    "判断": "其他",
    "完型": "完型",
    "阅读": "阅读",
    "写作": "作文",
}


# ─── Persist ────────────────────────────────────────────────────────────────

async def persist_questions(
    db: AsyncSession,
    *,
    kp_id: uuid.UUID,
    questions: list[AIGeneratedQuestion],
) -> list[SimulatedQuestion]:
    """按 (kp_id, stem) 幂等 upsert。返回本次确保入库的所有行。"""
    out: list[SimulatedQuestion] = []
    for q in questions:
        existing = (await db.execute(
            select(SimulatedQuestion).where(
                SimulatedQuestion.knowledge_point_id == kp_id,
                SimulatedQuestion.stem == q.stem,
            )
        )).scalar_one_or_none()
        if existing is not None:
            out.append(existing)
            continue
        sq = SimulatedQuestion(
            id=uuid.uuid4(),
            knowledge_point_id=kp_id,
            question_type=q.question_type,
            stem=q.stem,
            options=q.options,
            answer=q.answer,
            explanation=q.explanation,
            difficulty=q.difficulty,
            status="published",
        )
        db.add(sq)
        await db.flush()
        out.append(sq)
    return out


# ─── Read ───────────────────────────────────────────────────────────────────

async def list_questions_by_kp(
    db: AsyncSession,
    *,
    kp_id: uuid.UUID,
    limit: int = 5,
) -> list[SimQuestionOut]:
    rows = (await db.execute(
        select(SimulatedQuestion)
        .where(
            SimulatedQuestion.knowledge_point_id == kp_id,
            SimulatedQuestion.status == "published",
        )
        .order_by(SimulatedQuestion.created_at)
        .limit(limit)
    )).scalars().all()
    return [SimQuestionOut(
        id=r.id,
        question_type=str(r.question_type),
        stem=r.stem,
        options=r.options,
        difficulty=r.difficulty,
    ) for r in rows]


# ─── Grading ────────────────────────────────────────────────────────────────

def _grade(question_type: str, correct_answer: str, user_answer: str) -> bool:
    ua = user_answer.strip()
    ca = correct_answer.strip()
    if question_type == "单选":
        return ua.upper() == ca.upper()
    if question_type == "判断":
        return ua == ca
    if question_type == "填空":
        candidates = [c.strip().lower() for c in ca.split("|") if c.strip()]
        return ua.lower() in candidates
    return ua == ca


async def submit_attempt(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    question_id: uuid.UUID,
    user_answer: str,
) -> PracticeResultOut:
    q = (await db.execute(
        select(SimulatedQuestion).where(SimulatedQuestion.id == question_id)
    )).scalar_one_or_none()
    if q is None:
        raise AppError(code=404, message="题目不存在")

    correct = _grade(str(q.question_type), q.answer, user_answer)

    wq_id: uuid.UUID | None = None
    if not correct:
        # 映射到合法的 question_type enum
        wq_qtype = _WQ_QTYPE_MAP.get(str(q.question_type), "其他")
        wq = WrongQuestion(
            id=uuid.uuid4(),
            student_id=user_id,
            source_image_url="v2-practice",  # NOT NULL placeholder
            question_text=q.stem,
            student_answer=user_answer,
            correct_answer=q.answer,
            question_type=wq_qtype,  # type: ignore[arg-type]
        )
        db.add(wq)
        await db.flush()
        db.add(WrongQuestionKnowledgePoint(
            wrong_question_id=wq.id,
            knowledge_point_id=q.knowledge_point_id,
        ))
        await db.flush()
        wq_id = wq.id

    return PracticeResultOut(
        correct=correct,
        correct_answer=q.answer,
        explanation=q.explanation or "",
        wrong_question_id=wq_id,
    )
