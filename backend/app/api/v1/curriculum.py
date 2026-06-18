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


@router.get("/knowledge-points/{node_id}/contents")
async def get_kp_contents(
    node_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
):
    """某知识 node 的六维讲解(R8.4:路径 id 即 node_id)。"""
    contents = await curriculum_service.get_kp_contents(
        db, user_id=current_user.id, node_id=node_id,
    )
    return make_ok([c.model_dump(mode="json") for c in contents])


@router.get("/knowledge-points/{node_id}/mastery")
async def get_kp_mastery(
    node_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
):
    """当前用户对某知识 node 的掌握(R8.4:读 student_kp,node 维度)。"""
    from sqlalchemy import select as _select
    from app.models.d15_knowledge_graph import KnowledgeNode
    from app.models.d16_question_domain import StudentKp

    node = (await db.execute(
        _select(KnowledgeNode).where(KnowledgeNode.id == node_id)
    )).scalar_one_or_none()
    if node is None:
        return make_ok(None)

    sk = (await db.execute(
        _select(StudentKp).where(
            StudentKp.student_id == current_user.id,
            StudentKp.node_id == node_id,
        )
    )).scalar_one_or_none()

    if sk is None:
        return make_ok({"kp_name": node.name, "correct_count": 0, "wrong_count": 0,
                        "total": 0, "accuracy": None, "last_activity_at": None})
    correct = max((sk.practice_count or 0) - (sk.wrong_count or 0), 0)
    total = correct + (sk.wrong_count or 0)
    return make_ok({
        "kp_name": node.name,
        "correct_count": correct,
        "wrong_count": sk.wrong_count or 0,
        "total": total,
        "accuracy": round(correct / total, 4) if total else None,
        "last_activity_at": sk.last_practice_at.isoformat() if sk.last_practice_at else None,
    })


@router.get("/units/{unit_id}/mastery-summary")
async def get_unit_mastery_summary(
    unit_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
):
    """该单元每个知识 node 的掌握(R8.4:unit_node → knowledge_nodes,读 student_kp)。"""
    from sqlalchemy import select as _select
    from app.models.d15_knowledge_graph import KnowledgeNode
    from app.models.d16_question_domain import StudentKp
    from app.models.d17_curriculum_kg import UnitNode

    nodes = (await db.execute(
        _select(KnowledgeNode)
        .join(UnitNode, UnitNode.node_id == KnowledgeNode.id)
        .where(UnitNode.unit_id == unit_id)
    )).scalars().all()
    node_ids = [n.id for n in nodes]

    sk_rows = (await db.execute(
        _select(StudentKp).where(
            StudentKp.student_id == current_user.id,
            StudentKp.node_id.in_(node_ids),
        )
    )).scalars().all() if node_ids else []
    sk_map = {sk.node_id: sk for sk in sk_rows}

    result = []
    for n in nodes:
        sk = sk_map.get(n.id)
        correct = max((sk.practice_count or 0) - (sk.wrong_count or 0), 0) if sk else 0
        total = correct + (sk.wrong_count or 0) if sk else 0
        result.append({
            "kp_id": str(n.id),
            "kp_name": n.name,
            "kp_category": str(n.node_kind) if n.node_kind else None,
            "correct_count": correct,
            "wrong_count": (sk.wrong_count or 0) if sk else 0,
            "total": total,
            "accuracy": round(correct / total, 4) if total else None,
            "last_activity_at": sk.last_practice_at.isoformat() if sk and sk.last_practice_at else None,
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
