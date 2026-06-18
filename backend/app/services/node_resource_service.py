"""R6 知识节点资源(KP-First):多类型资源 生成/审核/读取(挂 knowledge_nodes)。

resource_type:lecture(六维度,upsert by dimension)/ video / example / essay / mindmap。
旧 knowledge_point_contents 不动;本服务只写新 node_resource。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d19_node_resource import NodeResource

_TYPES = {"lecture", "video", "example", "essay", "mindmap"}
_DIMENSIONS = {"listening", "vocabulary", "grammar", "reading", "translation", "writing"}


async def upsert_lecture(
    db: AsyncSession, *, node_id: uuid.UUID, dimension: str, content_md: str,
    media_url: str | None = None, generated_by: str = "manual", status: str = "draft",
) -> uuid.UUID:
    """六维度讲解:按 (node, lecture, dimension) upsert(更新正文/音频)。返回资源 id。"""
    if dimension not in _DIMENSIONS:
        raise AppError(code=400, message=f"非法维度 {dimension}")
    stmt = (
        pg_insert(NodeResource)
        .values(id=uuid.uuid4(), node_id=node_id, resource_type="lecture", dimension=dimension,
                content_md=content_md, media_url=media_url, generated_by=generated_by, status=status)
        .on_conflict_do_update(
            constraint="uix_node_resource_identity",
            set_={"content_md": content_md, "media_url": media_url, "updated_at": sa.func.now()},
        )
        .returning(NodeResource.id)
    )
    rid = (await db.execute(stmt)).scalar_one()
    await db.flush()
    return rid


async def add_resource(
    db: AsyncSession, *, node_id: uuid.UUID, resource_type: str, title: str | None = None,
    content_md: str | None = None, media_url: str | None = None,
    resource_json=None, generated_by: str = "manual", status: str = "draft",
) -> NodeResource:
    """新增非讲解资源(video/example/essay/mindmap)。lecture 请用 upsert_lecture。"""
    if resource_type not in _TYPES:
        raise AppError(code=400, message=f"非法资源类型 {resource_type}")
    if resource_type == "lecture":
        raise AppError(code=400, message="lecture 请用 upsert_lecture(需 dimension)")
    r = NodeResource(
        id=uuid.uuid4(), node_id=node_id, resource_type=resource_type, dimension=None,
        title=title, content_md=content_md, media_url=media_url, resource_json=resource_json,
        generated_by=generated_by, status=status,
    )
    db.add(r)
    await db.flush()
    return r


async def list_for_review(
    db: AsyncSession, *, status: str | None = "draft", node_id: uuid.UUID | None = None,
    resource_type: str | None = None, skip: int = 0, limit: int = 20,
) -> tuple[list[NodeResource], int]:
    base = sa.select(NodeResource)
    if status is not None:
        base = base.where(NodeResource.status == status)
    if node_id is not None:
        base = base.where(NodeResource.node_id == node_id)
    if resource_type is not None:
        base = base.where(NodeResource.resource_type == resource_type)
    total = (await db.execute(sa.select(sa.func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(
        base.order_by(NodeResource.created_at).offset(skip).limit(limit))).scalars().all()
    return list(rows), total


async def review(db: AsyncSession, *, resource_id: uuid.UUID, approve: bool, reviewer_id: uuid.UUID) -> NodeResource:
    r = (await db.execute(sa.select(NodeResource).where(NodeResource.id == resource_id))).scalar_one_or_none()
    if r is None:
        raise AppError(code=404, message="资源不存在")
    r.status = "published" if approve else "retired"
    r.reviewed_by = reviewer_id
    r.reviewed_at = datetime.now(timezone.utc)
    await db.flush()
    return r


async def update_resource(
    db: AsyncSession, *, resource_id: uuid.UUID, content_md: str | None = None,
    media_url: str | None = None, title: str | None = None, resource_json=None,
) -> NodeResource:
    r = (await db.execute(sa.select(NodeResource).where(NodeResource.id == resource_id))).scalar_one_or_none()
    if r is None:
        raise AppError(code=404, message="资源不存在")
    if content_md is not None:
        r.content_md = content_md
    if media_url is not None:
        r.media_url = media_url
    if title is not None:
        r.title = title
    if resource_json is not None:
        r.resource_json = resource_json
    if r.generated_by == "ai_full":
        r.generated_by = "ai_with_human_review"
    await db.flush()
    return r


async def list_published(
    db: AsyncSession, *, node_id: uuid.UUID, resource_type: str | None = None
) -> list[NodeResource]:
    """学生读:某 node 的已发布资源(可按类型)。"""
    stmt = sa.select(NodeResource).where(
        NodeResource.node_id == node_id, NodeResource.status == "published")
    if resource_type is not None:
        stmt = stmt.where(NodeResource.resource_type == resource_type)
    return list((await db.execute(
        stmt.order_by(NodeResource.resource_type, NodeResource.sort_order))).scalars().all())
