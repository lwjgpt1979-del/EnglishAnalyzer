"""V2 仿真题 service（D-079 / M3a）。

职责：
1. persist_questions() — AI 生成 → SimulatedQuestion 行（按 (kp_id, stem) 去重）
2. list_questions_by_kp() — 给 API 用的读取（不带 answer，前端拿不到答案）
3. submit_attempt() — 判分 + 错题落库（含 KP 链接）+ 返回结果

WrongQuestion 映射规则：
- 单选/填空/判断/完型/阅读 → 同名 enum；写作 → "作文"；连线 → "其他"
  （填空/判断 已于迁移 0012 加入 question_type enum，不再降级 "其他"）
- source_image_url 是 NOT NULL，练习场景没有图片，写占位字符串 "v2-practice"
- 没有 source_type 字段，所以来源标识体现在 source_image_url 的值上
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d3_wrong_questions import WrongQuestion
from app.models.d4_knowledge import KnowledgePoint, WrongQuestionKnowledgePoint
from app.models.d12_v2_exams import SimPracticeRecord, SimulatedQuestion
from app.schemas.questions import (
    AIGeneratedQuestion, KPAccuracyItem, KPAccuracyOut,
    PracticeResultOut, SimQuestionOut,
)


# 映射 SimQuestion.question_type → WrongQuestion.question_type（合法 enum）
_WQ_QTYPE_MAP = {
    "单选": "单选",
    "填空": "填空",
    "判断": "判断",
    "完型": "完型",
    "阅读": "阅读",
    "写作": "作文",
    "连线": "其他",
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
    if question_type in ("单选", "完型", "阅读"):
        return ua.upper() == ca.upper()
    if question_type == "判断":
        return ua == ca
    if question_type == "填空":
        candidates = [c.strip().lower() for c in ca.split("|") if c.strip()]
        return ua.lower() in candidates
    if question_type == "写作":
        return True  # 写作不判分，永远视为完成（前端展示范文供对照）
    if question_type == "连线":
        # 答案格式 "1-A|2-B|3-C"，set 比较忽略顺序
        ua_pairs = {p.strip() for p in ua.split("|") if p.strip()}
        ca_pairs = {p.strip() for p in ca.split("|") if p.strip()}
        return ua_pairs == ca_pairs
    return ua == ca


# ─── 错题闭环（去重 + 掌握标记）──────────────────────────────────────────────

async def _record_wrong(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    question: SimulatedQuestion,
    user_answer: str,
) -> uuid.UUID:
    """落库一条错题，按 (student_id, question_text, "v2-practice") 去重。

    - 已存在：更新作答/正确答案，重置 is_mastered=False、mastered_at=None（重新错了重新进错题本），复用原 id。
    - 不存在：新建 WrongQuestion + KP 链接。
    """
    existing = (await db.execute(
        select(WrongQuestion).where(
            WrongQuestion.student_id == user_id,
            WrongQuestion.question_text == question.stem,
            WrongQuestion.source_image_url == "v2-practice",
        )
    )).scalars().first()

    if existing is not None:
        existing.student_answer = user_answer
        existing.correct_answer = question.answer
        existing.is_mastered = False
        existing.mastered_at = None
        await db.flush()
        return existing.id

    wq_qtype = _WQ_QTYPE_MAP.get(str(question.question_type), "其他")
    wq = WrongQuestion(
        id=uuid.uuid4(),
        student_id=user_id,
        source_image_url="v2-practice",  # NOT NULL placeholder
        question_text=question.stem,
        student_answer=user_answer,
        correct_answer=question.answer,
        question_type=wq_qtype,  # type: ignore[arg-type]
    )
    db.add(wq)
    await db.flush()
    db.add(WrongQuestionKnowledgePoint(
        wrong_question_id=wq.id,
        knowledge_point_id=question.knowledge_point_id,
    ))
    await db.flush()
    return wq.id


async def _mark_mastered(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    question_stem: str,
) -> None:
    """答对时，把之前未掌握的同题错题标记为已掌握。无记录则静默跳过。"""
    existing = (await db.execute(
        select(WrongQuestion).where(
            WrongQuestion.student_id == user_id,
            WrongQuestion.question_text == question_stem,
            WrongQuestion.source_image_url == "v2-practice",
            WrongQuestion.is_mastered.is_(False),
        )
    )).scalars().first()
    if existing is not None:
        existing.is_mastered = True
        existing.mastered_at = datetime.now(timezone.utc)
        await db.flush()


async def _log_attempt(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    question: SimulatedQuestion,
    user_answer: str,
    correct: bool,
) -> None:
    """逐题作答日志（对错都写）—— 学情按 KP 聚合正确率的数据源。"""
    db.add(SimPracticeRecord(
        id=uuid.uuid4(),
        student_id=user_id,
        simulated_question_id=question.id,
        knowledge_point_id=question.knowledge_point_id,
        is_correct=correct,
        user_answer=user_answer,
    ))
    await db.flush()


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

    await _log_attempt(db, user_id=user_id, question=q, user_answer=user_answer, correct=correct)

    wq_id: uuid.UUID | None = None
    if not correct:
        wq_id = await _record_wrong(db, user_id=user_id, question=q, user_answer=user_answer)
    else:
        await _mark_mastered(db, user_id=user_id, question_stem=q.stem)

    return PracticeResultOut(
        correct=correct,
        correct_answer=q.answer,
        explanation=q.explanation or "",
        wrong_question_id=wq_id,
    )


# ─── 模拟考批量提交（M3b）─────────────────────────────────────────────────

async def submit_exam_attempts(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    answers: list,  # list[PracticeAttemptIn]
):
    """批量判分 N 道题，错题统一落 wrong_questions。

    与 submit_attempt 的区别：
    - 一次性处理多题
    - 中间不 commit（调用方在所有判分完后一次性 commit）
    - 返回 ExamResultOut 含总分 + 每题结果
    """
    from app.schemas.questions import ExamItemResult, ExamResultOut

    items: list = []
    correct_count = 0
    for atin in answers:
        q = (await db.execute(
            select(SimulatedQuestion).where(SimulatedQuestion.id == atin.question_id)
        )).scalar_one_or_none()
        if q is None:
            raise AppError(code=404, message=f"题目 {atin.question_id} 不存在")

        correct = _grade(str(q.question_type), q.answer, atin.user_answer)
        if correct:
            correct_count += 1

        await _log_attempt(
            db, user_id=user_id, question=q, user_answer=atin.user_answer, correct=correct)

        wq_id = None
        if not correct:
            wq_id = await _record_wrong(
                db, user_id=user_id, question=q, user_answer=atin.user_answer)
        else:
            await _mark_mastered(db, user_id=user_id, question_stem=q.stem)

        items.append(ExamItemResult(
            question_id=q.id,
            correct=correct,
            correct_answer=q.answer,
            user_answer=atin.user_answer,
            explanation=q.explanation or "",
            wrong_question_id=wq_id,
        ))

    return ExamResultOut(
        total=len(items),
        correct_count=correct_count,
        items=items,
    )


# ─── 学情：知识点正确率聚合（D-085）─────────────────────────────────────────

async def get_kp_accuracy(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
) -> KPAccuracyOut:
    """按知识点聚合该学生的练习正确率，弱项（正确率低）在前。

    数据源：sim_practice_records（练习 + 模拟考逐题作答日志）。
    内存聚合（MVP 单用户作答量小，够用）。
    """
    rows = (await db.execute(
        select(
            SimPracticeRecord.knowledge_point_id,
            SimPracticeRecord.is_correct,
        ).where(SimPracticeRecord.student_id == user_id)
    )).all()

    # KP id → [attempts, correct]
    agg: dict[uuid.UUID, list[int]] = {}
    total_attempts = 0
    total_correct = 0
    for kp_id, is_correct in rows:
        total_attempts += 1
        if is_correct:
            total_correct += 1
        slot = agg.setdefault(kp_id, [0, 0])
        slot[0] += 1
        if is_correct:
            slot[1] += 1

    # 取 KP 名
    kp_ids = list(agg.keys())
    name_map: dict[uuid.UUID, str] = {}
    if kp_ids:
        kp_rows = (await db.execute(
            select(KnowledgePoint.id, KnowledgePoint.name).where(KnowledgePoint.id.in_(kp_ids))
        )).all()
        name_map = {kid: kname for kid, kname in kp_rows}

    items = [
        KPAccuracyItem(
            knowledge_point_id=kp_id,
            knowledge_point_name=name_map.get(kp_id, "未知知识点"),
            attempts=attempts,
            correct=correct,
            accuracy=round(correct / attempts, 4) if attempts > 0 else 0.0,
        )
        for kp_id, (attempts, correct) in agg.items()
    ]
    # 弱项优先：正确率升序，正确率相同则作答数多的在前
    items.sort(key=lambda it: (it.accuracy, -it.attempts))

    return KPAccuracyOut(
        total_attempts=total_attempts,
        overall_accuracy=round(total_correct / total_attempts, 4) if total_attempts > 0 else 0.0,
        items=items,
    )
