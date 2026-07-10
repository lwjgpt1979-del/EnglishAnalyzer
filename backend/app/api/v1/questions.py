"""V2 仿真题 + 练习 API（D-079 / M3a）。"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import make_ok
from app.schemas.questions import AdaptiveSetOut, ExamAttemptIn, PracticeAttemptIn, SimQuestionOut
from app.services import adaptive_question_service, question_serve_service

router = APIRouter(prefix="/questions", tags=["questions"])


@router.get("/kp/{kp_id}/practice-questions")
async def list_practice_questions(
    kp_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(5, ge=1, le=20),
    dimension: str | None = Query(None, description="(已弃用)老维度过滤，KP-First 不再使用"),
):
    """KP-First:按知识 node 出题(platform 真题派生仿真优先 → 现生成兜底,默认上架)。

    kp_id 传的是 knowledge_nodes.id。底层走 question_serve_service,不碰 simulated_questions。
    """
    items = await question_serve_service.serve_by_node(
        db, node_id=kp_id, count=limit, student_id=current_user.id)   # 题源=错题+未做过,随机
    await db.commit()   # 可能触发现生成(写 platform_question),需提交
    return make_ok([i.model_dump(mode="json") for i in items])


@router.post("/practice-attempts")
async def submit_practice_attempt(
    body: PracticeAttemptIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await question_serve_service.submit_one(
        db,
        student_id=current_user.id,
        question_id=body.question_id,
        user_answer=body.user_answer,
    )
    await db.commit()  # answer_log/wrong_record 落库要 commit
    return make_ok(result.model_dump(mode="json"))


@router.post("/exam-attempts")
async def submit_exam_attempts(
    body: ExamAttemptIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """模拟考批量提交:一次判 N 题,答错落 wrong_record,返回总分 + 每题结果。"""
    result = await question_serve_service.submit_exam(
        db,
        student_id=current_user.id,
        answers=body.items,
    )
    await db.commit()
    return make_ok(result.model_dump(mode="json"))


# R8 Phase6a-2 part3 已退役:GET /kp-accuracy、/exam-history(读冻结的 sim_practice_records/
# sim_exam_sessions)。知识点正确率与诊断页 kp_dimension(answer_log/node)重复;模考历史读冻结表已空。


@router.get("/adaptive-set", response_model=None)
async def get_adaptive_set(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    total: int = Query(5, ge=1, le=10, description="本次出题总数"),
    unit_id: uuid.UUID | None = Query(None, description="单元 ID；传入时只推该单元弱项 KP"),
):
    """智能出题：根据学生薄弱知识点自动组卷，返回未做过的推荐题目。

    - 不传 unit_id：全局弱项模式（历史所有 KP 正确率最低的）
    - 传 unit_id：单元维度模式（该单元 KP 中正确率最低 / 未练习的优先）
    """
    result = await adaptive_question_service.get_adaptive_set(
        db, student_id=current_user.id, total=total, unit_id=unit_id
    )
    await db.commit()   # 可能触发现生成(写 platform_question),需提交
    # KP-First:adaptive 直接返回 SimQuestionOut(已带 kp_name/passage),无需再映射
    return make_ok(
        AdaptiveSetOut(questions=result.questions, weak_kp_names=result.weak_kp_names).model_dump(mode="json")
    )


# R8 Phase6a-2 part3 已退役:GET /exam-rank(班级模考排名,读冻结的 sim_exam_sessions)。
# 日后可基于 answer_log(feature='exam')重建为节点化新特性。
