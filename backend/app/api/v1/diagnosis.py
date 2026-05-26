"""学情诊断报告 API。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.diagnosis import DiagnosisReport
from app.services import diagnosis_service

router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.get("/report", response_model=BaseResponse[DiagnosisReport])
async def get_my_diagnosis_report(db: DbDep, current_user: UserDep):
    """返回当前学生的学情诊断报告。

    基于所有已提交错题及 AI 分析结果实时聚合，无缓存。
    """
    await get_rls_db(db, str(current_user.id))
    report = await diagnosis_service.get_diagnosis_report(
        db, student_id=current_user.id
    )
    return make_ok(report)
