"""KP-First 学生出题/判分单一入口(退役 simulated_questions,练习域统一到 platform_question)。

铁律:**只服务 platform_question,不复制成本地题、不碰任何老表**(simulated_questions/
sim_practice_records/ai_questions 全不涉及)。作答只写 KP-First 真值:
- answer_log + student_kp(node 投影,掌握卡数据源)—— mastery_judge_service.log_answer
- wrong_record(d16 错题中心/复习队列)—— wrong_center_service.record_wrong(答错时)

取题优先级(用户需求):真题派生仿真(parent_real_id 非空)> 兜底仿真(is_fallback)> LLM 现生成。
无已发布仿真时:有真题母题→generate_sim_from_real;无母题→generate_fallback_sim。**兜底默认上架**。
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import Passage, PlatformQuestion, PlatformQuestionKp
from app.schemas.questions import (
    ExamItemResult, ExamResultOut, PracticeResultOut, SimQuestionOut,
)
from app.services import wrong_center_service
from app.services import mastery_judge_service
from app.services.question_service import _grade   # 纯字符串判分,无老表耦合,可复用

_FALLBACK_DIM = "grammar"   # node 直接反向出题的默认维度(语法混合);后续可按 node 类别细分


def _coarse_type(pq: PlatformQuestion) -> str:
    """platform 细题型 → 判分粗类型(_grade 用)。有选项=单选类;无选项=填空类。"""
    return "单选" if pq.options else "填空"


def _sim_query(node_id: uuid.UUID, exclude_ids: set | None = None):
    """挂本 node 的已发布·未下架·**有 4 选项**的单选仿真(真题派生优先→兜底→时间)。

    只出「可点选单选」(options 非空):小程序对无选项的填空/判断渲染体验差,且语法混合
    生成器会把填空/判断误标成「单选」却不带 options —— 这里按 options 非空硬过滤掉。
    exclude_ids:排除已做过的题(自适应去重用)。
    """
    q = (
        sa.select(PlatformQuestion)
        .join(PlatformQuestionKp, PlatformQuestionKp.question_id == PlatformQuestion.id)
        .where(
            PlatformQuestionKp.node_id == node_id,
            PlatformQuestion.type == "sim",
            PlatformQuestion.status == "published",
            PlatformQuestion.deprecated_at.is_(None),
            PlatformQuestion.answer.isnot(None),
            # 只出真·选项数组:JSONB 里空选项存的是 json null(IS NOT NULL 判不掉),用 jsonb_typeof
            sa.func.jsonb_typeof(PlatformQuestion.options) == "array",
        )
    )
    if exclude_ids:
        q = q.where(PlatformQuestion.id.not_in(exclude_ids))
    return q.order_by(
        PlatformQuestion.parent_real_id.isnot(None).desc(),   # 真题派生优先
        PlatformQuestion.is_fallback.asc(),
        PlatformQuestion.created_at,
    )


async def _fetch_sim(
    db: AsyncSession, node_id: uuid.UUID, count: int, exclude_ids: set | None = None,
) -> list[PlatformQuestion]:
    rows = list((await db.execute(
        _sim_query(node_id, exclude_ids).limit(count))).scalars().all())
    # 二次兜底:排除空数组(极少数 options=[] 的脏数据)
    return [r for r in rows if isinstance(r.options, list) and len(r.options) >= 2]


async def _generate_once(db: AsyncSession, node_id: uuid.UUID, want: int) -> None:
    """生成一批已发布仿真:有真题母题→派生;无母题→node 反向出题(默认上架)。

    兜底语法混合生成器约六成产出是可点选单选,故按 want 多要一点,配合外层循环补齐。
    """
    from app.services import platform_question_service as pqs

    real_ids = list((await db.execute(
        sa.select(PlatformQuestion.id)
        .join(PlatformQuestionKp, PlatformQuestionKp.question_id == PlatformQuestion.id)
        .where(PlatformQuestionKp.node_id == node_id,
               PlatformQuestion.type == "real",
               PlatformQuestion.status == "published")
        .limit(3))).scalars().all())
    try:
        if real_ids:
            await pqs.generate_sim_from_real(
                db, real_id=real_ids[0], count=want, status="published")
        else:
            await pqs.generate_fallback_sim(
                db, node_id=node_id, count=want + 3,   # 混题型仅约六成单选,多要 3 道补损耗
                status="published", dimension=_FALLBACK_DIM, force=True)
    except Exception as exc:  # noqa: BLE001 生成失败不阻断:返回已有题(可能少于 count)
        import logging
        logging.getLogger(__name__).warning("generate_once failed node=%s: %s", node_id, exc)


async def _passages(db: AsyncSession, rows: list[PlatformQuestion]) -> dict[uuid.UUID, str]:
    """题组短文(完形/阅读的 block_id → 短文正文),供前端展示上下文。"""
    bids = {r.block_id for r in rows if r.block_id}
    if not bids:
        return {}
    prows = (await db.execute(
        sa.select(Passage.id, Passage.text).where(Passage.id.in_(bids)))).all()
    return {pid: txt for pid, txt in prows}


async def serve_by_node(
    db: AsyncSession, *, node_id: uuid.UUID, count: int, exclude_ids: set | None = None,
) -> list[SimQuestionOut]:
    """出 count 道题:已发布 platform 仿真优先;不足则现生成(默认上架)后再取。不写任何老表。

    exclude_ids:排除已做过的题(自适应组题去重用,不传=不排除)。
    """
    node = (await db.execute(
        sa.select(KnowledgeNode).where(KnowledgeNode.id == node_id))).scalar_one_or_none()
    if node is None:
        raise AppError(code=404, message="知识点不存在")

    rows = await _fetch_sim(db, node_id, count, exclude_ids)
    # 不足则现生成补齐(有界重试:混题型每轮约六成可用,最多 3 轮防死循环)
    for _ in range(3):
        if len(rows) >= count:
            break
        await _generate_once(db, node_id, count - len(rows))
        await db.flush()
        rows = await _fetch_sim(db, node_id, count, exclude_ids)

    passages = await _passages(db, rows)
    return [SimQuestionOut(
        id=pq.id,
        question_type="单选",   # serve 只出可点选单选,题型统一(前端渲染选项)
        stem=pq.stem,
        options=list(pq.options) if isinstance(pq.options, list) else None,
        difficulty=int(pq.difficulty or 3),
        kp_name=node.name,
        passage=passages.get(pq.block_id) if pq.block_id else None,
    ) for pq in rows]


async def _load(db: AsyncSession, question_id: uuid.UUID) -> tuple[PlatformQuestion, uuid.UUID | None]:
    pq = (await db.execute(
        sa.select(PlatformQuestion).where(PlatformQuestion.id == question_id))).scalar_one_or_none()
    if pq is None:
        raise AppError(code=404, message="题目不存在")
    node_id = (await db.execute(
        sa.select(PlatformQuestionKp.node_id)
        .where(PlatformQuestionKp.question_id == question_id).limit(1))).scalar_one_or_none()
    return pq, node_id


async def _judge_one(
    db: AsyncSession, *, student_id: uuid.UUID, question_id: uuid.UUID,
    user_answer: str, feature: str,
) -> tuple[PlatformQuestion, bool, uuid.UUID | None]:
    """判一题 + 写 KP-First 真值(answer_log/student_kp)+ 答错写 wrong_record。返回 (题, 对错, 错题id)。"""
    pq, node_id = await _load(db, question_id)
    correct = _grade(_coarse_type(pq), pq.answer or "", user_answer)
    await mastery_judge_service.log_answer(
        db, student_id=student_id, q_scope="platform", question_id=pq.id,
        node_id=node_id, is_correct=correct, feature=feature)
    wq_id: uuid.UUID | None = None
    if not correct:
        wq_id = await wrong_center_service.record_wrong(
            db, student_id=student_id, q_scope="platform", question_id=pq.id, node_id=node_id)
    return pq, correct, wq_id


async def submit_one(
    db: AsyncSession, *, student_id: uuid.UUID, question_id: uuid.UUID, user_answer: str,
) -> PracticeResultOut:
    pq, correct, wq_id = await _judge_one(
        db, student_id=student_id, question_id=question_id,
        user_answer=user_answer, feature="practice")
    return PracticeResultOut(
        correct=correct, correct_answer=pq.answer or "",
        explanation=pq.explanation or "", wrong_question_id=wq_id)


async def submit_exam(
    db: AsyncSession, *, student_id: uuid.UUID, answers: list,
) -> ExamResultOut:
    """模拟考批量判分。KP-First 无独立成绩快照表,成绩由 answer_log(feature='exam')聚合。"""
    items: list[ExamItemResult] = []
    correct_count = 0
    for a in answers:
        pq, correct, wq_id = await _judge_one(
            db, student_id=student_id, question_id=a.question_id,
            user_answer=a.user_answer, feature="exam")
        if correct:
            correct_count += 1
        items.append(ExamItemResult(
            question_id=pq.id, correct=correct, correct_answer=pq.answer or "",
            user_answer=a.user_answer, explanation=pq.explanation or "", wrong_question_id=wq_id))
    return ExamResultOut(total=len(items), correct_count=correct_count, items=items)
