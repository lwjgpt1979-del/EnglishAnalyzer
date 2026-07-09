"""考点讲解(kp_lecture)admin API——按考点类型的教学环节:补全 / AI 生成 / 发布。

取代旧 node_resource 六维讲解。写库遵循「AI 只出草稿、人工确认后发布」铁律。
独立模块,避免与 admin.py 并发改动冲突。
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_role
from app.models.d1_users import User
from app.models.d15_knowledge_graph import KnowledgeNode
from app.schemas.base import BaseResponse, make_ok
from app.services import kp_lecture_service as kl

router = APIRouter(prefix="/admin/knowledge-nodes", tags=["admin-kp-lecture"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
AdminDep = Annotated[User, Depends(require_role("platform_admin"))]


class SectionIn(BaseModel):
    content_md: str | None = None
    media_url: str | None = None


class StatusIn(BaseModel):
    status: str = Field(..., pattern="^(draft|published)$")


class BulkGenIn(BaseModel):
    node_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=50)


@router.post("/bulk-generate-lecture", response_model=BaseResponse[dict])
async def bulk_generate_lecture(body: BulkGenIn, db: DbDep, admin: AdminDep):
    """批量:对勾选的多个考点并发 AI 生成各自缺失的讲解环节(草稿)。单次≤50 个考点。"""
    return make_ok(await kl.generate_bulk_missing(db, node_ids=body.node_ids))


async def _node(db: AsyncSession, node_id: uuid.UUID) -> KnowledgeNode:
    node = await db.get(KnowledgeNode, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="节点不存在")
    return node


@router.get("/{node_id}/lecture", response_model=BaseResponse[dict])
async def get_lecture(node_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """该考点的讲解:按类型模板列出各环节(含未填占位)+ 完整度。admin 全见(草稿+已发布)。"""
    node = await _node(db, node_id)
    return make_ok(await kl.list_sections(db, node_id=node_id, code=node.code))


# ⚠ 静态段路由必须放在 /{section_key} 动态路由**之前**,否则 publish-all 会被当成 section_key(FastAPI 按注册顺序匹配)
@router.put("/{node_id}/lecture/publish-all", response_model=BaseResponse[dict])
async def publish_all(node_id: uuid.UUID, body: StatusIn, db: DbDep, admin: AdminDep):
    """整考点一键发布 / 下架其全部讲解环节。"""
    n = await kl.set_status_all(db, node_id=node_id, status=body.status)
    return make_ok({"updated": n, "status": body.status})


@router.put("/{node_id}/lecture/{section_key}", response_model=BaseResponse[dict])
async def upsert_section(node_id: uuid.UUID, section_key: str, body: SectionIn,
                         db: DbDep, admin: AdminDep):
    """人工写/改一个讲解环节(草稿)。"""
    node = await _node(db, node_id)
    try:
        r = await kl.upsert_section(db, node_id=node_id, code=node.code, section_key=section_key,
                                    content_md=body.content_md, media_url=body.media_url, source="manual")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return make_ok(r)


@router.post("/{node_id}/lecture/{section_key}/generate", response_model=BaseResponse[dict])
async def generate_section(node_id: uuid.UUID, section_key: str, db: DbDep, admin: AdminDep):
    """AI 生成某讲解环节 → 落草稿(source=ai),人工确认后再发布。"""
    node = await _node(db, node_id)
    try:
        md = await kl.generate_section(db, code=node.code, name=node.name, section_key=section_key)
        r = await kl.upsert_section(db, node_id=node_id, code=node.code, section_key=section_key,
                                    content_md=md, source="ai")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return make_ok({**r, "content_md": md})


@router.post("/{node_id}/lecture/generate-missing", response_model=BaseResponse[dict])
async def generate_missing(node_id: uuid.UUID, db: DbDep, admin: AdminDep):
    """AI 一键生成所有「还没内容」的环节(均落草稿)。返回新生成的环节数。"""
    node = await _node(db, node_id)
    data = await kl.list_sections(db, node_id=node_id, code=node.code)
    made = 0
    for s in data["sections"]:
        if s["has_content"]:
            continue
        md = await kl.generate_section(db, code=node.code, name=node.name, section_key=s["section_key"])
        await kl.upsert_section(db, node_id=node_id, code=node.code, section_key=s["section_key"],
                                content_md=md, source="ai")
        made += 1
    return make_ok({"generated": made})


@router.put("/{node_id}/lecture/{section_key}/status", response_model=BaseResponse[dict])
async def set_section_status(node_id: uuid.UUID, section_key: str, body: StatusIn,
                             db: DbDep, admin: AdminDep):
    """发布 / 下架某讲解环节。"""
    n = await kl.set_status(db, node_id=node_id, section_key=section_key, status=body.status)
    return make_ok({"updated": n, "status": body.status})


@router.delete("/{node_id}/lecture/{section_key}", response_model=BaseResponse[dict])
async def delete_section(node_id: uuid.UUID, section_key: str, db: DbDep, admin: AdminDep):
    """删除某讲解环节。"""
    n = await kl.delete_section(db, node_id=node_id, section_key=section_key)
    return make_ok({"deleted": n})
