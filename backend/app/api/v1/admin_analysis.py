"""真题「题目层解析」admin API(试点:阅读)。独立模块,避免与 admin.py 并发改动冲突。

AI 只出建议(POST /suggest);人工确认(PUT /{id}/analysis)是唯一写库入口。
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_role
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.services import question_analysis_service as qas

router = APIRouter(prefix="/admin", tags=["admin-analysis"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
AdminDep = Annotated[User, Depends(require_role("platform_admin"))]


class SuggestAnalysisIn(BaseModel):
    question_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=50)


class ConfirmAnalysisIn(BaseModel):
    analysis: dict


@router.post("/question-analysis/suggest", response_model=BaseResponse[list])
async def suggest_question_analysis_api(body: SuggestAnalysisIn, db: DbDep, admin: AdminDep):
    """AI 生成题目层解析**建议**(不落库),按题型分发:完型=双轴(载体槽程序判+线索);
    阅读=rc技能+定位句。逐条带程序校验结果(线索句子串/枚举/图谱编码)。"""
    items = await qas.suggest_analysis(db, question_ids=body.question_ids)
    return make_ok(items)


@router.put("/platform-questions/{question_id}/analysis", response_model=BaseResponse[dict])
async def confirm_question_analysis_api(
    question_id: uuid.UUID, body: ConfirmAnalysisIn, db: DbDep, admin: AdminDep,
):
    """人工确认解析并写库(唯一写入口;服务端重校验,不合格 400)。"""
    saved = await qas.confirm_analysis(
        db, question_id=question_id, analysis=body.analysis, admin_id=admin.id)
    await db.commit()
    return make_ok(saved)
