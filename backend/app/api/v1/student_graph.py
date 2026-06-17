"""R4 学生个人知识图谱 API(KP-First):我的知识地图 / 教材纳入 / 掌握趋势。"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AppError
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.kp import (
    EnrollOut, StudentGraphItem, StudentGraphOut, StudentGraphSummary,
    StudentTrendOut, StudentTrendPoint,
)
from app.services import student_graph_service as sg

router = APIRouter(prefix="/student-kp", tags=["student-kp"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.get("/graph", response_model=BaseResponse[StudentGraphOut])
async def my_graph(db: DbDep, current_user: UserDep, include_all: bool = False):
    """我的知识地图:默认只亮已练/已错;include_all=true 展开教材全集。"""
    items = await sg.get_graph(db, student_id=current_user.id, include_all=include_all)
    summary = await sg.graph_summary(db, student_id=current_user.id)
    return make_ok(StudentGraphOut(
        summary=StudentGraphSummary(**summary),
        items=[StudentGraphItem(**it) for it in items],
    ))


@router.post("/enroll", response_model=BaseResponse[EnrollOut])
async def enroll(db: DbDep, current_user: UserDep):
    """按当前教材偏好显式重同步:把该教材应学全集 KP 纳入个人体系。"""
    v, g, s = (current_user.preferred_textbook_version,
               current_user.preferred_grade, current_user.preferred_semester)
    if not (v and g and s):
        raise AppError(code=400, message="请先设置教材版本/年级/学期")
    n = await sg.enroll_textbook(db, student_id=current_user.id,
                                 textbook_version=v, grade=g, semester=str(s))
    await db.commit()
    return make_ok(EnrollOut(enrolled=n))


@router.get("/trend", response_model=BaseResponse[StudentTrendOut])
async def trend(node_id: uuid.UUID, db: DbDep, current_user: UserDep, days: int = 30):
    """某 KP(node)掌握趋势:按日 accuracy(数据源 answer_log)。"""
    pts = await sg.node_trend(db, student_id=current_user.id, node_id=node_id, days=days)
    return make_ok(StudentTrendOut(
        node_id=node_id, points=[StudentTrendPoint(**p) for p in pts]))
