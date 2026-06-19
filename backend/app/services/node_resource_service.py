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
    resource_type: str | None = None, unit_id: uuid.UUID | None = None,
    skip: int = 0, limit: int = 20,
) -> tuple[list[NodeResource], int]:
    base = sa.select(NodeResource)
    if status is not None:
        base = base.where(NodeResource.status == status)
    if node_id is not None:
        base = base.where(NodeResource.node_id == node_id)
    if resource_type is not None:
        base = base.where(NodeResource.resource_type == resource_type)
    if unit_id is not None:                       # 按单元过滤:取该单元对齐的节点
        from app.models.d17_curriculum_kg import UnitNode
        base = base.where(NodeResource.node_id.in_(
            sa.select(UnitNode.node_id).where(UnitNode.unit_id == unit_id)))
    total = (await db.execute(sa.select(sa.func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(
        base.order_by(NodeResource.created_at).offset(skip).limit(limit))).scalars().all()
    return list(rows), total


LECTURE_DIMENSIONS = ["listening", "vocabulary", "grammar", "reading", "translation", "writing"]


async def unit_content_overview(db: AsyncSession, *, unit_id: uuid.UUID) -> list[dict]:
    """单元补全总览:该单元每个对齐节点 × 六维讲解的状态(缺失/草稿/已发布)。

    返回 [{node_id, name, dims: {dimension: {id, status, has_content} | None}}]，
    供发布前预览完整度 + 一键补全缺失维度。
    """
    from app.models.d15_knowledge_graph import KnowledgeNode
    from app.models.d17_curriculum_kg import UnitNode
    node_rows = (await db.execute(
        sa.select(KnowledgeNode.id, KnowledgeNode.name)
        .join(UnitNode, UnitNode.node_id == KnowledgeNode.id)
        .where(UnitNode.unit_id == unit_id)
        .order_by(KnowledgeNode.name)
    )).all()
    node_ids = [r[0] for r in node_rows]
    by_node: dict[uuid.UUID, dict[str, dict]] = {}
    if node_ids:
        lrows = (await db.execute(
            sa.select(NodeResource.id, NodeResource.node_id, NodeResource.dimension,
                      NodeResource.status, NodeResource.content_md)
            .where(NodeResource.node_id.in_(node_ids), NodeResource.resource_type == "lecture")
        )).all()
        for rid, nid, dim, status, content in lrows:
            if dim:
                by_node.setdefault(nid, {})[dim] = {
                    "id": rid, "status": status, "has_content": bool((content or "").strip())}
    return [
        {"node_id": nid, "name": name,
         "dims": {d: by_node.get(nid, {}).get(d) for d in LECTURE_DIMENSIONS}}
        for nid, name in node_rows
    ]


async def publish_unit(db: AsyncSession, *, unit_id: uuid.UUID, reviewer_id: uuid.UUID) -> dict:
    """一键发布整单元:把该单元所有对齐节点下 draft/reviewing 的讲解置 published。

    返回 {published, already_published, missing_dims}。missing_dims 为仍缺讲解的
    (节点×维度)数,供前端发布前提示(不阻断,由前端决定是否继续)。
    """
    from app.models.d17_curriculum_kg import UnitNode
    node_ids = (await db.execute(
        sa.select(UnitNode.node_id).where(UnitNode.unit_id == unit_id))).scalars().all()
    if not node_ids:
        return {"published": 0, "already_published": 0, "missing_dims": 0}
    now = datetime.now(timezone.utc)
    res = await db.execute(
        sa.update(NodeResource)
        .where(NodeResource.node_id.in_(node_ids),
               NodeResource.resource_type == "lecture",
               NodeResource.status.in_(["draft", "reviewing"]))
        .values(status="published", reviewed_by=reviewer_id, reviewed_at=now)
    )
    published = res.rowcount or 0
    already = (await db.execute(
        sa.select(sa.func.count()).select_from(NodeResource)
        .where(NodeResource.node_id.in_(node_ids),
               NodeResource.resource_type == "lecture",
               NodeResource.status == "published"))).scalar_one() - published
    overview = await unit_content_overview(db, unit_id=unit_id)
    missing = sum(1 for n in overview for d in LECTURE_DIMENSIONS if n["dims"][d] is None)
    await db.flush()
    return {"published": published, "already_published": already, "missing_dims": missing}


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
