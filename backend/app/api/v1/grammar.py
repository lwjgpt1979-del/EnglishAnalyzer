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
from app.services import grammar_probe_service, grammar_placement_service, paper_prior_service
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


class GroupQuizIn(BaseModel):
    kp_ids: list[str] = Field(..., description="参与混合检测的语法点 id 列表")


class GroupSubmitIn(BaseModel):
    answers: dict[str, str] = Field(..., description="{kp_id: 所选选项}")


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


@router.get("/kp/{kp_id}/transfer", response_model=BaseResponse[dict])
async def get_kp_transfer(kp_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """取迁移题:同语法点的全新语境单选(检验真懂、非背题)。无题→probe=null。"""
    await get_rls_db(db, str(current_user.id))
    kp = (await db.execute(select(KnowledgePoint).where(KnowledgePoint.id == kp_id))).scalar_one_or_none()
    if kp is None:
        return make_ok({"probe": None})
    out = await grammar_probe_service.transfer_probe(db, student_id=current_user.id, kp=kp)
    await db.commit()
    return make_ok(out or {"probe": None})


@router.post("/kp/{kp_id}/transfer-submit", response_model=BaseResponse[dict])
async def submit_kp_transfer(kp_id: uuid.UUID, body: ProbeSubmitIn, db: DbDep, current_user: UserDep):
    """提交迁移题:transferred(真懂)/ memorized(疑似背题);通过置 transfer_ok。"""
    await get_rls_db(db, str(current_user.id))
    res = await grammar_probe_service.submit_transfer(
        db, student_id=current_user.id, kp_id=kp_id, key=body.key, answer=body.answer)
    await db.commit()
    return make_ok(res)


@router.post("/group-mixed/probes", response_model=BaseResponse[dict])
async def group_mixed_probes(body: GroupQuizIn, db: DbDep, current_user: UserDep):
    """成组混合检测题面(多点混考、不标规则,反经验主义)。<2 题返回 degraded。"""
    await get_rls_db(db, str(current_user.id))
    out = await grammar_probe_service.group_mixed_quiz(
        db, student_id=current_user.id, kp_ids=body.kp_ids)
    await db.commit()
    return make_ok(out)


@router.post("/group-mixed/submit", response_model=BaseResponse[dict])
async def group_mixed_submit(body: GroupSubmitIn, db: DbDep, current_user: UserDep):
    """提交成组检测:逐点判分 → 识别掌握度(BKT)。"""
    await get_rls_db(db, str(current_user.id))
    res = await grammar_probe_service.submit_group_mixed(
        db, student_id=current_user.id, answers=body.answers)
    await db.commit()
    return make_ok(res)


@router.get("/retentions/due", response_model=BaseResponse[dict])
async def get_due_retentions(db: DbDep, current_user: UserDep):
    """到期待复测的语法点列表(四维已达、隔期到期)。"""
    await get_rls_db(db, str(current_user.id))
    rows = await grammar_probe_service.due_retentions(db, student_id=current_user.id)
    return make_ok({"items": rows})


@router.get("/kp/{kp_id}/retention", response_model=BaseResponse[dict])
async def get_kp_retention(kp_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """取该点复测题(同点新语境,隔期用)。无题→probe=null。"""
    await get_rls_db(db, str(current_user.id))
    kp = (await db.execute(select(KnowledgePoint).where(KnowledgePoint.id == kp_id))).scalar_one_or_none()
    if kp is None:
        return make_ok({"probe": None})
    out = await grammar_probe_service.retention_probe(db, student_id=current_user.id, kp=kp)
    await db.commit()
    return make_ok(out or {"probe": None})


@router.post("/kp/{kp_id}/retention-submit", response_model=BaseResponse[dict])
async def submit_kp_retention(kp_id: uuid.UUID, body: ProbeSubmitIn, db: DbDep, current_user: UserDep):
    """提交复测:retained(仍记得,间隔拉长)/ forgotten(遗忘,重新进入学习)。"""
    await get_rls_db(db, str(current_user.id))
    res = await grammar_probe_service.submit_retention(
        db, student_id=current_user.id, kp_id=kp_id, key=body.key, answer=body.answer)
    await db.commit()
    return make_ok(res)


@router.get("/kp/{kp_id}/status", response_model=BaseResponse[dict])
async def get_kp_status(kp_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """该语法点对该生的诚实掌握标签 + 各维度 + 证据。"""
    await get_rls_db(db, str(current_user.id))
    res = await grammar_probe_service.kp_status(db, student_id=current_user.id, kp_id=kp_id)
    return make_ok(res)


# ── 分级测验(CAT 冷启动,R10.6)───────────────────────────────────────────
class PlacementStartIn(BaseModel):
    textbook: str | None = Field(None, description="教材版本,如 译林版")
    grade: str | None = Field(None, description="目标年级,如 八年级")
    kp_ids: list[str] | None = Field(None, description="可选:显式题库(按难度顺序),覆盖自动圈定")
    use_paper_priors: bool = Field(True, description="是否先融合纸质错题先验")


class PlacementAnswerIn(BaseModel):
    session_id: uuid.UUID
    kp_id: str = Field(..., description="当前题的知识点 id")
    chosen: str = Field(..., description="所选选项")


@router.post("/placement/start", response_model=BaseResponse[dict])
async def placement_start(body: PlacementStartIn, db: DbDep, current_user: UserDep):
    """开始语法分级测验:圈题库 → 返回首题(自适应)。"""
    await get_rls_db(db, str(current_user.id))
    res = await grammar_placement_service.start(
        db, student_id=current_user.id, textbook=body.textbook, grade=body.grade,
        kp_ids=body.kp_ids, use_paper_priors=body.use_paper_priors)
    await db.commit()
    return make_ok(res)


@router.get("/paper-priors", response_model=BaseResponse[dict])
async def get_paper_priors(db: DbDep, current_user: UserDep):
    """预览纸质错题折算的语法薄弱点(找洞,不写库)。"""
    await get_rls_db(db, str(current_user.id))
    res = await paper_prior_service.compute_paper_priors(db, student_id=current_user.id)
    return make_ok(res)


@router.post("/paper-priors/apply", response_model=BaseResponse[dict])
async def apply_paper_priors(db: DbDep, current_user: UserDep):
    """把纸质错题先验写入掌握台账(prior_source=paper,不覆盖实练掌握)。"""
    await get_rls_db(db, str(current_user.id))
    res = await paper_prior_service.apply_paper_priors(db, student_id=current_user.id)
    await db.commit()
    return make_ok(res)


@router.post("/placement/answer", response_model=BaseResponse[dict])
async def placement_answer(body: PlacementAnswerIn, db: DbDep, current_user: UserDep):
    """提交一题 → 自适应路由,返回下一题或结束(含热力图)。"""
    await get_rls_db(db, str(current_user.id))
    res = await grammar_placement_service.answer(
        db, student_id=current_user.id, session_id=body.session_id, kp_id=body.kp_id, chosen=body.chosen)
    await db.commit()
    return make_ok(res)


@router.get("/placement/result", response_model=BaseResponse[dict])
async def placement_result(session_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """取分级测验结果:掌握热力图 + 学习起点线。"""
    await get_rls_db(db, str(current_user.id))
    res = await grammar_placement_service.result(db, student_id=current_user.id, session_id=session_id)
    return make_ok(res)
