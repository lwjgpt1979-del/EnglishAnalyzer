"""详解(node_resource lecture)→ AI 拆成更细的子考点(供"详解拆分审核"页人工确认后挂入)。

不自动建节点:split_lecture 只返回 AI 建议的子考点名 + 该考点已有子节点(便于查重);
人工在审核页逐条 ✓ → 走 kp_candidate_service.create_node 在该考点下建子考点(source=manual)。
"""
from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d19_node_resource import NodeResource
from app.services.llm_provider import chat_completion, is_llm_dev_mode

_SYS = (
    "你是初中英语教研专家。下面给出一个【考点】及其【详解】。请把详解里实际讲到的知识,"
    "拆成若干个更细、可独立作为知识图谱叶子的【子考点】。要求:每个子考点名称简洁(≤20字)、"
    "互不重叠、紧扣详解内容;只拆详解真正涵盖的点,不臆造;返回 3-8 个。"
    "严格输出 JSON,不要解释。"
)


async def _children_names(db: AsyncSession, node_id: uuid.UUID) -> list[str]:
    rows = (await db.execute(sa.select(KnowledgeNode.name)
                             .where(KnowledgeNode.parent_id == node_id))).scalars().all()
    return list(rows)


async def split_lecture(db: AsyncSession, node_id: uuid.UUID) -> dict:
    """读该考点的详解 → AI 拆出子考点名(去重已有子节点)。返回 {node_id,name,code,content,subs,existing}。"""
    node = await db.get(KnowledgeNode, node_id)
    if node is None:
        from app.core.exceptions import AppError
        raise AppError(code=404, message="考点不存在")
    content = (await db.execute(
        sa.select(NodeResource.content_md).where(
            NodeResource.node_id == node_id, NodeResource.resource_type == "lecture")
        .order_by(NodeResource.updated_at.desc()).limit(1))).scalar() or ""
    existing = await _children_names(db, node_id)
    base = {"node_id": str(node_id), "name": node.name, "code": node.code,
            "content": content, "existing": existing}
    if not content.strip() or is_llm_dev_mode():
        return {**base, "subs": []}
    user = (f"【考点】{node.name}\n【详解】\n{content[:3500]}\n\n"
            f"{('【该考点已有子考点,勿重复】' + '、'.join(existing)) if existing else ''}\n"
            '请拆成 3-8 个子考点。返回 JSON:{"subs":["子考点名", ...]}。')
    try:
        resp = await chat_completion(system_prompt=_SYS, user_prompt=user,
                                     max_tokens=1024, response_format={"type": "json_object"})
        data = json.loads(resp.choices[0].message.content or "{}")
    except Exception:  # noqa: BLE001
        return {**base, "subs": []}
    seen = {e.strip() for e in existing}
    subs: list[str] = []
    for s in (data.get("subs") or []):
        nm = str(s).strip()[:40]
        if nm and nm not in seen:
            seen.add(nm)
            subs.append(nm)
    return {**base, "subs": subs[:10]}


async def list_lecture_nodes(db: AsyncSession, *, grp: str | None = None,
                             skip: int = 0, limit: int = 20) -> tuple[list[dict], int]:
    """列出"有详解"的考点(供拆分审核):返回 (items[{id,name,code,content,child_count}], total)。"""
    has_lec = sa.exists().where(sa.and_(
        NodeResource.node_id == KnowledgeNode.id, NodeResource.resource_type == "lecture"))
    base = sa.select(KnowledgeNode).where(
        KnowledgeNode.axis == "knowledge", KnowledgeNode.status == "active", has_lec)
    if grp == "词法":
        base = base.where(KnowledgeNode.code.like("cf%"))
    elif grp == "句法":
        base = base.where(KnowledgeNode.code.like("jf%"))
    total = (await db.execute(sa.select(sa.func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(base.order_by(KnowledgeNode.code).offset(skip).limit(limit))).scalars().all()
    ids = [r.id for r in rows]
    if not ids:
        return [], total
    kids = dict((await db.execute(
        sa.select(KnowledgeNode.parent_id, sa.func.count())
        .where(KnowledgeNode.parent_id.in_(ids)).group_by(KnowledgeNode.parent_id))).all())
    contents = dict((await db.execute(
        sa.select(NodeResource.node_id, NodeResource.content_md)
        .where(NodeResource.node_id.in_(ids), NodeResource.resource_type == "lecture"))).all())
    items = [{"id": r.id, "name": r.name, "code": r.code,
              "content": (contents.get(r.id) or "")[:500],
              "child_count": int(kids.get(r.id, 0))} for r in rows]
    return items, total
