"""V2 课程浏览 API（D-079 / M2）。"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.kp import NodeResourceItem, NodeResourceListOut
from app.services import curriculum_service

router = APIRouter(prefix="/curriculum", tags=["curriculum"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.get("/nodes/{node_id}/resources", response_model=BaseResponse[NodeResourceListOut])
async def get_node_resources(
    node_id: uuid.UUID, db: DbDep, current_user: UserDep, resource_type: str | None = None,
):
    """学生读:某知识节点的已发布学习资源(R6,讲解/视频/例句/范文/思维导图)。"""
    from app.services import node_resource_service as nrs
    rows = await nrs.list_published(db, node_id=node_id, resource_type=resource_type)
    return make_ok(NodeResourceListOut(
        total=len(rows),
        items=[NodeResourceItem(
            id=r.id, node_id=r.node_id, resource_type=r.resource_type, dimension=r.dimension,
            title=r.title, content_md=r.content_md, media_url=r.media_url,
            resource_json=r.resource_json, status=r.status,
        ) for r in rows],
    ))


@router.get("/units")
async def list_units(
    db: DbDep,
    current_user: UserDep,
    textbook_version: str = Query(...),
    grade: str = Query(...),
    semester: str = Query(..., description="上 / 下"),
):
    items = await curriculum_service.list_units(
        db,
        user_id=current_user.id,
        textbook_version=textbook_version,
        grade=grade,
        semester=semester,
    )
    return make_ok([i.model_dump(mode="json") for i in items])


@router.get("/units/{unit_id}")
async def get_unit_detail(
    unit_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
):
    detail = await curriculum_service.get_unit_detail(
        db, user_id=current_user.id, unit_id=unit_id,
    )
    return make_ok(detail.model_dump(mode="json"))


@router.get("/knowledge-points/{kp_id}/contents")
async def get_kp_contents(
    kp_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
):
    contents = await curriculum_service.get_kp_contents(
        db, user_id=current_user.id, kp_id=kp_id,
    )
    return make_ok([c.model_dump(mode="json") for c in contents])


@router.get("/knowledge-points/{kp_id}/mastery")
async def get_kp_mastery(
    kp_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
):
    """返回当前用户对某 KP 的掌握台账（按 kp.name 匹配）。"""
    from sqlalchemy import select as _select
    from app.models.d4_knowledge import KnowledgePoint, StudentKpMastery

    kp = (await db.execute(
        _select(KnowledgePoint).where(KnowledgePoint.id == kp_id)
    )).scalar_one_or_none()
    if kp is None:
        return make_ok(None)

    m = (await db.execute(
        _select(StudentKpMastery).where(
            StudentKpMastery.student_id == current_user.id,
            StudentKpMastery.kp_key == kp.name,
        )
    )).scalar_one_or_none()

    if m is None:
        return make_ok({"kp_name": kp.name, "correct_count": 0, "wrong_count": 0,
                        "total": 0, "accuracy": None, "last_activity_at": None})
    total = m.correct_count + m.wrong_count
    return make_ok({
        "kp_name": kp.name,
        "correct_count": m.correct_count,
        "wrong_count": m.wrong_count,
        "total": total,
        "accuracy": round(m.correct_count / total, 4) if total else None,
        "last_activity_at": m.last_activity_at.isoformat() if m.last_activity_at else None,
    })


@router.get("/units/{unit_id}/mastery-summary")
async def get_unit_mastery_summary(
    unit_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
):
    """返回该单元每个 KP 的掌握情况（正确率、练习次数、最近练习时间）。"""
    from sqlalchemy import select as _select
    from app.models.d4_knowledge import KnowledgePoint, StudentKpMastery, UnitKnowledgePoint

    rows = (await db.execute(
        _select(KnowledgePoint)
        .join(UnitKnowledgePoint, UnitKnowledgePoint.knowledge_point_id == KnowledgePoint.id)
        .where(UnitKnowledgePoint.unit_id == unit_id)
    )).scalars().all()

    kp_keys = [r.name for r in rows]
    mastery_rows = (await db.execute(
        _select(StudentKpMastery).where(
            StudentKpMastery.student_id == current_user.id,
            StudentKpMastery.kp_key.in_(kp_keys),
        )
    )).scalars().all()
    mastery_map = {m.kp_key: m for m in mastery_rows}

    result = []
    for kp in rows:
        m = mastery_map.get(kp.name)
        total = (m.correct_count + m.wrong_count) if m else 0
        result.append({
            "kp_id": str(kp.id),
            "kp_name": kp.name,
            "kp_category": str(kp.category) if kp.category else None,
            "correct_count": m.correct_count if m else 0,
            "wrong_count": m.wrong_count if m else 0,
            "total": total,
            "accuracy": round(m.correct_count / total, 4) if total else None,
            "last_activity_at": m.last_activity_at.isoformat() if m and m.last_activity_at else None,
        })
    return make_ok(result)


@router.get("/kps/search")
async def search_knowledge_points(
    db: DbDep,
    q: str = Query("", description="搜索关键词（知识点名称模糊匹配）"),
    limit: int = Query(10, ge=1, le=20, description="最多返回条数"),
):
    """按知识点名称模糊搜索，供前端选择目标 KP。无需会员。"""
    from app.schemas.curriculum import KPSearchItem
    kps = await curriculum_service.search_kps(db, q=q, limit=limit)
    return make_ok([
        KPSearchItem(
            id=kp.id,
            name=kp.name,
            category=str(kp.category),
            description=kp.description if hasattr(kp, "description") else None,
        ).model_dump(mode="json")
        for kp in kps
    ])
