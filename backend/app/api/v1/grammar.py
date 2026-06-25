"""R10.1 语法掌握 · 学生端探针接口(识别 + 纠错)。"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.database import get_db, get_rls_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.services import grammar_probe_service
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.d4_knowledge import KnowledgePoint

router = APIRouter(prefix="/grammar", tags=["grammar"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


class ProbeSubmitIn(BaseModel):
    key: str = Field(..., description="探针 key,如 recognize:0 / detect:1")
    answer: str = Field(..., description="所选选项")


class ProduceSubmitIn(BaseModel):
    sentence: str = Field(..., description="学生用该语法点造的英文句子")


@router.get("/kp/{kp_id}/probes", response_model=BaseResponse[dict])
async def get_kp_probes(kp_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """取该语法点的识别 + 纠错探针题面(不含答案)+ 当前各维掌握度。"""
    await get_rls_db(db, str(current_user.id))
    kp = (await db.execute(select(KnowledgePoint).where(KnowledgePoint.id == kp_id))).scalar_one_or_none()
    if kp is None:
        return make_ok({"kp_id": str(kp_id), "probes": [], "recognize": 0, "detect": 0, "mastered": False})
    out = await grammar_probe_service.comprehension_probes(db, student_id=current_user.id, kp=kp)
    await db.commit()
    return make_ok(out)


@router.post("/kp/{kp_id}/probe", response_model=BaseResponse[dict])
async def submit_kp_probe(kp_id: uuid.UUID, body: ProbeSubmitIn, db: DbDep, current_user: UserDep):
    """提交一道探针:判分 + 诊断 + 各维掌握度(BKT)。"""
    await get_rls_db(db, str(current_user.id))
    res = await grammar_probe_service.submit_probe(
        db, student_id=current_user.id, kp_id=kp_id, key=body.key, answer=body.answer)
    await db.commit()
    return make_ok(res)


@router.post("/kp/{kp_id}/produce", response_model=BaseResponse[dict])
async def submit_kp_produce(kp_id: uuid.UUID, body: ProduceSubmitIn, db: DbDep, current_user: UserDep):
    """提交造句(产出维):LLM 维度 rubric 评分 → 产出掌握度(BKT)。"""
    await get_rls_db(db, str(current_user.id))
    res = await grammar_probe_service.submit_produce(
        db, student_id=current_user.id, kp_id=kp_id, sentence=body.sentence)
    await db.commit()
    return make_ok(res)
