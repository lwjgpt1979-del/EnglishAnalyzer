"""R3.4 错题复习(KP-First):基于 wrong_record 的 SM-2 复习队列/提交。

复用 review_service.sm2_update 纯算法;数据载体从旧 wrong_questions 切到 wrong_record。
今日队列:status=open AND next_review_at <= today。复习提交按 SM-2 调度;
quality≥4 且 review_count≥3 且 interval≥21 → 判掌握(mastery_source=review)。
"""
from __future__ import annotations

import datetime as _dt
import uuid
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d16_question_domain import WrongRecord
from app.services.review_service import sm2_update

_MAX_DAILY_QUEUE = 20
_MASTER_MIN_INTERVAL = 21       # 连续高质量且间隔≥21天 → 判长期掌握


async def get_due_queue(
    db: AsyncSession, *, student_id: uuid.UUID, today: _dt.date | None = None,
    limit: int = _MAX_DAILY_QUEUE,
) -> list[WrongRecord]:
    """今日待复习错题:open 且 next_review_at <= today,近期优先。"""
    today = today or _dt.date.today()
    return list((await db.execute(
        sa.select(WrongRecord).where(
            WrongRecord.student_id == student_id,
            WrongRecord.status == "open",
            WrongRecord.next_review_at.isnot(None),
            WrongRecord.next_review_at <= today,
        ).order_by(WrongRecord.next_review_at).limit(limit)
    )).scalars().all())


async def review_queue_items(
    db: AsyncSession, *, student_id: uuid.UUID, today: _dt.date | None = None,
    limit: int = _MAX_DAILY_QUEUE,
) -> list[dict]:
    """今日复习队列(wrong_record)→ WrongQuestionOut 形状。复用 to_wq_out_fields(平台/上传题面 +
    选项/解析),客观重做需要选项与正确答案;tags 补 node 名。队列上限 20,逐行解析成本可忽略。"""
    from app.models.d15_knowledge_graph import KnowledgeNode
    today = today or _dt.date.today()
    wrs = list((await db.execute(
        sa.select(WrongRecord)
        .where(WrongRecord.student_id == student_id, WrongRecord.status == "open",
               WrongRecord.next_review_at.isnot(None), WrongRecord.next_review_at <= today)
        .order_by(WrongRecord.next_review_at).limit(limit)
    )).scalars().all())
    out = []
    for wr in wrs:
        fields = await to_wq_out_fields(db, wr)
        if wr.node_id:
            name = (await db.execute(
                sa.select(KnowledgeNode.name).where(KnowledgeNode.id == wr.node_id)
            )).scalar_one_or_none()
            if name:
                fields["tags"] = [name]
        out.append(fields)
    return out


async def review_stats(db: AsyncSession, *, student_id: uuid.UUID, today: _dt.date | None = None) -> dict:
    """复习统计:未掌握 / 今日到期 / 新错题(未排期)。"""
    today = today or _dt.date.today()
    base = sa.select(sa.func.count()).select_from(WrongRecord).where(
        WrongRecord.student_id == student_id, WrongRecord.status == "open")
    total = (await db.execute(base)).scalar_one()
    due = (await db.execute(base.where(WrongRecord.next_review_at.isnot(None),
                                       WrongRecord.next_review_at <= today))).scalar_one()
    new = (await db.execute(base.where(WrongRecord.next_review_at.is_(None)))).scalar_one()
    return {"total_unmastered": total, "due_today": due, "new_unscheduled": new}


async def mark_mastered(
    db: AsyncSession, *, student_id: uuid.UUID, wrong_record_id: uuid.UUID, is_mastered: bool,
) -> WrongRecord:
    """手动标记/取消掌握(前台直读新表):wrong_record.status = mastered|open。"""
    wr = (await db.execute(
        sa.select(WrongRecord).where(
            WrongRecord.id == wrong_record_id, WrongRecord.student_id == student_id)
    )).scalar_one_or_none()
    if wr is None:
        raise AppError(code=404, message="错题不存在或无权访问")
    if is_mastered:
        wr.status = "mastered"
        wr.mastered_at = _dt.datetime.now(_dt.timezone.utc)
        wr.mastery_source = "manual"
    else:
        wr.status = "open"
        wr.mastered_at = None
    await db.flush()
    return wr


async def to_wq_out_fields(db: AsyncSession, wr: WrongRecord) -> dict:
    """把 wrong_record(+ platform/uploaded 题面)映射成旧 WrongQuestionOut 字段(前台无感)。"""
    from app.models.d16_question_domain import PlatformQuestion, UploadedQuestion
    stem = correct = qtype = student_ans = None
    difficulty = None
    options = explanation = None
    source = wr.q_scope   # platform|uploaded → 前端据此走 KP-First 展示(内置解析),不走老图像 AI 诊断
    if wr.q_scope == "uploaded":
        uq = (await db.execute(
            sa.select(UploadedQuestion).where(UploadedQuestion.id == wr.question_id)
        )).scalar_one_or_none()
        if uq:
            stem, student_ans, correct, qtype = uq.stem, uq.student_answer, uq.correct_answer, uq.question_type
    elif wr.q_scope == "platform":   # 练习/模拟考做错的平台仿真题(KP-First 新路径)
        pq = (await db.execute(
            sa.select(PlatformQuestion).where(PlatformQuestion.id == wr.question_id)
        )).scalar_one_or_none()
        if pq:
            stem, correct, qtype, difficulty = pq.stem, pq.answer, str(pq.question_type or ""), pq.difficulty
            explanation = pq.explanation
            options = pq.options if isinstance(pq.options, list) else None
    return {
        "options": options, "explanation": explanation, "source": source,
        "id": wr.id, "student_id": wr.student_id, "source_image_url": "",
        "question_text": stem,
        "student_answer": student_ans,
        "correct_answer": correct,
        "question_type": qtype,
        "difficulty": difficulty, "tags": None,
        "is_mastered": wr.status == "mastered", "mastered_at": wr.mastered_at,
        "created_at": wr.created_at, "updated_at": wr.created_at, "ocr_status": None,
        "review_count": wr.review_count, "easiness_factor": wr.easiness_factor,
        "review_interval_days": wr.review_interval_days,
        "next_review_at": wr.next_review_at, "last_review_at": wr.last_review_at,
    }


async def advance_due_wrongs_on_node(
    db: AsyncSession, *, student_id: uuid.UUID, node_id: uuid.UUID | None,
    today: _dt.date | None = None,
) -> int:
    """「两者结合」次通道:练习答对某 node → 该 node 下**今日到期**的 open 错题各推进一步 SM-2
    (quality=4)。仅推进/顺延复习,**不静默判掌握**——真正订正仍须重做原题或复习队列答对。
    返回被推进的错题数。"""
    if node_id is None:
        return 0
    today = today or _dt.date.today()
    wrs = list((await db.execute(
        sa.select(WrongRecord).where(
            WrongRecord.student_id == student_id, WrongRecord.node_id == node_id,
            WrongRecord.status == "open", WrongRecord.next_review_at.isnot(None),
            WrongRecord.next_review_at <= today)
    )).scalars().all())
    for wr in wrs:
        r = sm2_update(
            quality=4, review_count=wr.review_count,
            easiness_factor=Decimal(str(wr.easiness_factor)),
            review_interval_days=wr.review_interval_days, today=today,
        )
        wr.review_count = r.review_count
        wr.easiness_factor = r.easiness_factor
        wr.review_interval_days = r.review_interval_days
        wr.next_review_at = r.next_review_at
        wr.last_review_at = today
    if wrs:
        await db.flush()
    return len(wrs)


async def _resolve_question(db: AsyncSession, wr: WrongRecord) -> dict | None:
    """取错题底层题面(客观判分/重做展示用):correct/coarse_type/options/explanation。题被删返回 None。"""
    from app.models.d16_question_domain import PlatformQuestion, UploadedQuestion
    if wr.q_scope == "platform":
        pq = (await db.execute(
            sa.select(PlatformQuestion).where(PlatformQuestion.id == wr.question_id)
        )).scalar_one_or_none()
        if pq is None:
            return None
        opts = pq.options if isinstance(pq.options, list) else None
        return {"correct": pq.answer or "", "coarse": "单选" if opts else "填空",
                "options": opts, "explanation": pq.explanation or ""}
    uq = (await db.execute(
        sa.select(UploadedQuestion).where(UploadedQuestion.id == wr.question_id)
    )).scalar_one_or_none()
    if uq is None:
        return None
    return {"correct": uq.correct_answer or "", "coarse": uq.question_type or "填空",
            "options": None, "explanation": uq.explanation or ""}


async def _grade_and_log(
    db: AsyncSession, *, student_id: uuid.UUID, wr: WrongRecord, user_answer: str,
) -> tuple[bool, dict]:
    """客观判分 + 写 KP-First 真值(answer_log)。返回 (是否答对, 题面payload)。"""
    from app.services.question_service import _grade
    from app.services import mastery_judge_service
    payload = await _resolve_question(db, wr)
    if payload is None:
        raise AppError(code=404, message="原题已不存在，无法重做")
    correct = _grade(payload["coarse"], payload["correct"], user_answer)
    # 重做/复习的作答同样写入 answer_log(feature='review'),纳入 KP-First 真值与个人图谱
    await mastery_judge_service.log_answer(
        db, student_id=student_id, q_scope=wr.q_scope, question_id=wr.question_id,
        node_id=wr.node_id, is_correct=correct, feature="review")
    # 加权掌握度(m139):订正做对(每题首次)→ corrected_count;订正又做错(每次)→ redo_wrong_count。
    # log_answer 已确保该 node 的 student_kp 行存在;node 为空的错题不计。
    if wr.node_id is not None:
        from app.models.d16_question_domain import AnswerLog, StudentKp
        if correct:
            # 首次订正成功?数该题 feature='review' 且答对的 answer_log(含刚写入的这条);==1 即首次
            n_ok = (await db.execute(
                sa.select(sa.func.count()).select_from(AnswerLog).where(
                    AnswerLog.student_id == student_id,
                    AnswerLog.question_id == wr.question_id,
                    AnswerLog.feature == "review", AnswerLog.is_correct.is_(True),
                )
            )).scalar_one()
            if n_ok == 1:
                await db.execute(
                    sa.update(StudentKp)
                    .where(StudentKp.student_id == student_id, StudentKp.node_id == wr.node_id)
                    .values(corrected_count=StudentKp.corrected_count + 1)
                )
        else:
            await db.execute(
                sa.update(StudentKp)
                .where(StudentKp.student_id == student_id, StudentKp.node_id == wr.node_id)
                .values(redo_wrong_count=StudentKp.redo_wrong_count + 1)
            )
    return correct, payload


async def redo(
    db: AsyncSession, *, student_id: uuid.UUID, wrong_record_id: uuid.UUID,
    user_answer: str, today: _dt.date | None = None,
) -> dict:
    """主动重做订正(错题详情入口):客观重做那道错题。答对 → 立即订正(mastered, source=redo);
    答错 → 保持 open、SM-2 归零、今日重排。返回判分结果供前端展示。"""
    today = today or _dt.date.today()
    wr = (await db.execute(
        sa.select(WrongRecord).where(
            WrongRecord.id == wrong_record_id, WrongRecord.student_id == student_id)
    )).scalar_one_or_none()
    if wr is None:
        raise AppError(code=404, message="错题不存在")

    correct, payload = await _grade_and_log(db, student_id=student_id, wr=wr, user_answer=user_answer)
    if correct:
        wr.status = "mastered"
        wr.mastered_at = _dt.datetime.now(_dt.timezone.utc)
        wr.mastery_source = "redo"
    else:
        wr.status = "open"
        wr.mastered_at = None
        wr.mastery_source = None
        wr.review_count = 0
        wr.review_interval_days = 1
        wr.next_review_at = today
        wr.last_review_at = today
    await db.flush()
    return {
        "is_correct": correct, "correct_answer": payload["correct"],
        "explanation": payload["explanation"], "mastered": correct,
        "next_review_at": wr.next_review_at, "review_count": wr.review_count,
    }


async def submit_review(
    db: AsyncSession, *, student_id: uuid.UUID, wrong_record_id: uuid.UUID,
    user_answer: str, today: _dt.date | None = None,
) -> dict:
    """复习队列客观重做判分(取代旧主观自评):真正重新作答该错题 → 客观判分驱动 SM-2。
    答对=quality5 推进、答错=quality2 归零;连续达标 → 掌握(source=review)。"""
    today = today or _dt.date.today()
    wr = (await db.execute(
        sa.select(WrongRecord).where(
            WrongRecord.id == wrong_record_id, WrongRecord.student_id == student_id)
    )).scalar_one_or_none()
    if wr is None:
        raise AppError(code=404, message="错题不存在")

    correct, payload = await _grade_and_log(db, student_id=student_id, wr=wr, user_answer=user_answer)
    quality = 5 if correct else 2   # 客观对错映射 SM-2 质量,不再主观自评
    r = sm2_update(
        quality=quality, review_count=wr.review_count,
        easiness_factor=Decimal(str(wr.easiness_factor)),
        review_interval_days=wr.review_interval_days, today=today,
    )
    wr.review_count = r.review_count
    wr.easiness_factor = r.easiness_factor
    wr.review_interval_days = r.review_interval_days
    wr.next_review_at = r.next_review_at
    wr.last_review_at = today

    mastered = correct and r.review_count >= 3 and r.review_interval_days >= _MASTER_MIN_INTERVAL
    if mastered:
        wr.status = "mastered"
        wr.mastered_at = _dt.datetime.now(_dt.timezone.utc)
        wr.mastery_source = "review"
    await db.flush()
    return {
        "is_correct": correct, "correct_answer": payload["correct"],
        "explanation": payload["explanation"], "mastered": mastered,
        "next_review_at": wr.next_review_at, "review_count": wr.review_count,
    }
