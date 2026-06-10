"""学情诊断报告 API。"""
from __future__ import annotations

import base64
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.diagnosis import DiagnosisReport
from app.services import diagnosis_service, pdf_service

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


@router.get("/regression-alerts")
async def get_my_regression_alerts(db: DbDep, current_user: UserDep):
    """返回当前学生的知识点退步预警（轻量，不含完整报告）。"""
    await get_rls_db(db, str(current_user.id))
    from app.services import regression_service
    alerts = await regression_service.detect_regressions(db, student_id=current_user.id)
    return make_ok(alerts)


class PdfExportOut(BaseModel):
    pdf_base64: str
    filename: str


@router.get("/export-pdf", response_model=BaseResponse[PdfExportOut])
async def export_diagnosis_pdf(db: DbDep, current_user: UserDep):
    """生成学情诊断报告 PDF，返回 base64 编码内容。

    前端拿到 base64 后：
    1. 解码写入本地临时文件（FileSystemManager.writeFile）
    2. uni.openDocument 打开 PDF 预览
    """
    await get_rls_db(db, str(current_user.id))
    report = await diagnosis_service.get_diagnosis_report(
        db, student_id=current_user.id
    )
    student_name: str | None = current_user.nickname or None
    pdf_bytes = pdf_service.generate_diagnosis_pdf(report, student_name=student_name)
    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    filename = f"学情报告_{date.today().strftime('%Y%m%d')}.pdf"
    return make_ok(PdfExportOut(pdf_base64=pdf_b64, filename=filename))
