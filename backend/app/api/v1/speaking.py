"""AI 口语对话练习 API。

学生侧（小程序）用微信同声传译做语音识别拿到文本，或直接打字，POST 到 /reply；
后端返回 AI 英文回复 + 纠错 + 回复语音（COS 直链）。stage 控制语速/难度。
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.exceptions import AppError
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.services import speaking_dialogue_service as svc

router = APIRouter(prefix="/speaking", tags=["speaking"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


def _stage(user: User) -> str:
    g = getattr(user, "preferred_grade", None) or ""
    if "小学" in g:
        return "primary"
    if "高中" in g:
        return "senior"
    return "junior"


class StartIn(BaseModel):
    scenario_key: str


class TurnIn(BaseModel):
    role: str
    text: str


class ReplyIn(BaseModel):
    scenario_key: str
    user_text: str = Field(..., min_length=1, max_length=500)
    history: list[TurnIn] = []


@router.get("/scenarios", response_model=BaseResponse[dict])
async def scenarios(current_user: UserDep, db: DbDep):
    """口语对话场景：因材施教的个性化场景（学期/词力通/错题）+ 通用预设。"""
    custom = await svc.list_personalized(db, current_user.id)
    return make_ok({"custom": custom, "preset": svc.list_scenarios()})


@router.post("/start", response_model=BaseResponse[dict])
async def start(body: StartIn, current_user: UserDep, db: DbDep):
    """开始某场景：返回 AI 开场白 + 语音。"""
    try:
        return make_ok(await svc.opening(
            db, student_id=current_user.id,
            scenario_key=body.scenario_key, stage=_stage(current_user)))
    except ValueError:
        raise AppError(code=404, message="场景不存在")


@router.post("/reply", response_model=BaseResponse[dict])
async def reply(body: ReplyIn, current_user: UserDep, db: DbDep):
    """学生说一句 → AI 回复 + 纠错 + 回复语音。"""
    try:
        return make_ok(await svc.reply(
            db, student_id=current_user.id, scenario_key=body.scenario_key,
            history=[t.model_dump() for t in body.history],
            user_text=body.user_text, stage=_stage(current_user)))
    except ValueError:
        raise AppError(code=404, message="场景不存在")


class SummaryIn(BaseModel):
    scenario_key: str
    history: list[TurnIn] = []


@router.post("/summary", response_model=BaseResponse[dict])
async def summary(body: SummaryIn, current_user: UserDep, db: DbDep):
    """对话结束 → 本次练习评价（评分 + 亮点 + 改进 + 鼓励）。"""
    try:
        return make_ok(await svc.summarize(
            db, student_id=current_user.id, scenario_key=body.scenario_key,
            history=[t.model_dump() for t in body.history],
            stage=_stage(current_user)))
    except ValueError as e:
        if "no user turns" in str(e):
            raise AppError(code=400, message="还没开口说话，先聊几句再评价吧")
        raise AppError(code=404, message="场景不存在")
