"""听力练习 API（听力跟读模块·精听）。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.listening import ListeningBrief, ListeningDetail
from app.services import listening_service

router = APIRouter(prefix="/listening", tags=["listening"])

UserDep = Annotated[User, Depends(get_current_user)]


@router.get("/exercises", response_model=BaseResponse[list[ListeningBrief]])
async def list_exercises(current_user: UserDep):
    """听力素材列表（不含答案/原文）。"""
    return make_ok([ListeningBrief(**e) for e in listening_service.list_exercises()])


@router.get("/exercises/{exercise_id}", response_model=BaseResponse[ListeningDetail])
async def get_exercise(exercise_id: str, current_user: UserDep):
    """听力素材详情（含原文与答案，前端控制听前不展示）。"""
    return make_ok(ListeningDetail(**listening_service.get_exercise(exercise_id)))
