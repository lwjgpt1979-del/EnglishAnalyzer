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
from app.services import writing_grade_service as wgs

router = APIRouter(prefix="/admin", tags=["admin-analysis"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
AdminDep = Annotated[User, Depends(require_role("platform_admin"))]


class SuggestAnalysisIn(BaseModel):
    question_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=50)
    force: bool = False       # True=忽略暂存重新解析;False=已暂存/已确认的秒读不重跑


class ConfirmAnalysisIn(BaseModel):
    analysis: dict
    force: bool = False       # True=人工忽略程序校验(判定误报)强制写库,记 validation_skipped 审计


class ConfirmBatchItem(BaseModel):
    question_id: uuid.UUID
    analysis: dict


class ConfirmBatchIn(BaseModel):
    items: list[ConfirmBatchItem] = Field(..., min_length=1, max_length=50)


@router.post("/question-analysis/suggest", response_model=BaseResponse[list])
async def suggest_question_analysis_api(body: SuggestAnalysisIn, db: DbDep, admin: AdminDep):
    """AI 生成题目层解析**建议**并暂存(meta.analysis_draft),按题型分发:完型=双轴;阅读=rc技能+定位句。
    已暂存/已确认的秒读不重跑(force=True 强制重解析);人工确认才正式写库。"""
    items = await qas.suggest_analysis(
        db, question_ids=body.question_ids, force=body.force)
    return make_ok(items)


@router.put("/platform-questions/{question_id}/analysis", response_model=BaseResponse[dict])
async def confirm_question_analysis_api(
    question_id: uuid.UUID, body: ConfirmAnalysisIn, db: DbDep, admin: AdminDep,
):
    """人工确认解析并写库(唯一写入口;服务端重校验,不合格 400;force=True 人工忽略校验强制写)。"""
    saved = await qas.confirm_analysis(
        db, question_id=question_id, analysis=body.analysis, admin_id=admin.id, force=body.force)
    await db.commit()
    return make_ok(saved)


@router.post("/question-analysis/confirm-batch", response_model=BaseResponse[dict])
async def confirm_analysis_batch_api(body: ConfirmBatchIn, db: DbDep, admin: AdminDep):
    """批量确认写库(降人工:一键采纳校验通过项):逐条硬校验,返回 {confirmed, failed}。
    失败项带原因不写库,不影响其余;整批一次 commit。"""
    res = await qas.confirm_analysis_batch(
        db, items=[it.model_dump() for it in body.items], admin_id=admin.id)
    await db.commit()
    return make_ok(res)


@router.get("/vocab/option-role-stats", response_model=BaseResponse[dict])
async def vocab_option_role_stats_api(
    db: DbDep, admin: AdminDep,
    q: str | None = None,
    pool: str = "option_vocab_slot",
    exam_type: str | None = "中考",
    group_by: str = "word",
    region_level: str | None = None,
    region_code: str | None = None,
    min_correct: int = 0,
    min_distractor: int = 0,
    sort: str = "correct_count_desc",
    skip: int = 0,
    limit: int = 50,
):
    """词 × 主考/干扰统计,或按省/市汇总(group_by=region)。"""
    from app.services import option_vocab_stats_service as ovs
    data = await ovs.word_role_stats(
        db, pool=pool, exam_type=exam_type or None, group_by=group_by,
        region_level=region_level, region_code=region_code, q=q,
        min_correct=min_correct, min_distractor=min_distractor,
        sort=sort, skip=skip, limit=min(limit, 100))
    return make_ok(data)


@router.get("/vocab/{word_id}/platform-questions", response_model=BaseResponse[dict])
async def list_word_platform_questions_api(
    word_id: uuid.UUID, db: DbDep, admin: AdminDep,
    role: str = "correct", pool: str = "option_vocab_slot",
    exam_type: str | None = None, region_code: str | None = None,
    skip: int = 0, limit: int = 50,
):
    """按词反查真题:role=correct|distractor|any;pool/exam_type/region_code 筛选。"""
    from app.services import option_vocab_service as ovs
    if role not in ("correct", "distractor", "any"):
        role = "correct"
    items, total, word = await ovs.list_platform_questions_for_word(
        db, word_id=word_id, role=role, pool=pool or None,
        exam_type=exam_type, region_code=region_code,
        skip=skip, limit=min(limit, 100))
    return make_ok({
        "items": items, "total": total, "role": role, "word": word,
        "pool": pool, "exam_type": exam_type, "region_code": region_code,
    })


class WritingRubricUpdate(BaseModel):
    full_score: int | None = Field(None, ge=1, le=100)
    accuracy_pass_ratio: float | None = Field(None, ge=0, le=1)
    organization_pass_ratio: float | None = Field(None, ge=0, le=1)
    richness_min_targets: int | None = Field(None, ge=0, le=10)


@router.get("/writing-rubric", response_model=BaseResponse[dict])
async def get_writing_rubric_api(db: DbDep, admin: AdminDep):
    """读书面表达评分量表(满分/各维达标线);缺失返回默认兜底。"""
    return make_ok(await wgs.get_writing_rubric(db))


@router.put("/writing-rubric", response_model=BaseResponse[dict])
async def update_writing_rubric_api(body: WritingRubricUpdate, db: DbDep, admin: AdminDep):
    """运营改写作评分量表(满分/达标线),写 system_configs.writing_rubric。"""
    saved = await wgs.update_writing_rubric(
        db, rubric=body.model_dump(exclude_none=True), updated_by=admin.id)
    await db.commit()
    return make_ok(saved)


# ── 按地区·年份批量解析并采纳入选项词统计 ─────────────────────────────

class PipelineScanIn(BaseModel):
    region_code: str = Field(..., min_length=2, max_length=12)
    year: int | None = None
    types: list[str] = Field(default_factory=list)


class PipelineRunIn(BaseModel):
    paper_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=80)
    types: list[str] = Field(default_factory=list)
    concurrency: int = Field(6, ge=2, le=12)
    auto_adopt: bool = True
    force_suggest: bool = False
    region_code: str | None = None
    region_name: str | None = None
    year: int | None = None


@router.post("/option-vocab-pipeline/scan", response_model=BaseResponse[dict])
async def option_vocab_pipeline_scan_api(body: PipelineScanIn, db: DbDep, admin: AdminDep):
    """扫描省/市/年份下各卷:勾选题型中尚未 option_vocab_ready 的待跑题。"""
    from app.services import option_vocab_pipeline_service as pipe
    return make_ok(await pipe.scan(
        db, region_code=body.region_code, year=body.year, types=body.types))


@router.post("/option-vocab-pipeline/run", response_model=BaseResponse[dict])
async def option_vocab_pipeline_run_api(body: PipelineRunIn, db: DbDep, admin: AdminDep):
    """启动后台跑批:suggest(多线程)→通过项 confirm 写 ready。返回 job_id 供轮询。"""
    from app.services import option_vocab_pipeline_service as pipe
    job_id = await pipe.start_run(
        paper_ids=body.paper_ids,
        types=body.types,
        concurrency=body.concurrency,
        auto_adopt=body.auto_adopt,
        force_suggest=body.force_suggest,
        admin_id=admin.id,
        region_code=body.region_code,
        region_name=body.region_name,
        year=body.year,
    )
    return make_ok({"job_id": job_id})


@router.get("/option-vocab-pipeline/jobs", response_model=BaseResponse[dict])
async def option_vocab_pipeline_jobs_api(admin: AdminDep, limit: int = 20):
    """最近跑批列表(落库,含进行中实时进度)。"""
    from app.services import option_vocab_pipeline_service as pipe
    items = await pipe.list_jobs(limit=limit)
    return make_ok({"items": items, "total": len(items)})


@router.get("/option-vocab-pipeline/jobs/{job_id}", response_model=BaseResponse[dict])
async def option_vocab_pipeline_job_api(job_id: str, admin: AdminDep):
    """轮询跑批进度(内存优先,否则读库)。"""
    from app.services import option_vocab_pipeline_service as pipe
    from app.core.exceptions import AppError
    job = await pipe.get_job(job_id)
    if job is None:
        raise AppError(code=404, message="任务不存在或已过期")
    return make_ok(job)