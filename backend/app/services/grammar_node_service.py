"""R10 语法节点取数(规范受控树 knowledge_nodes 的「词法 + 句法」子树)。

R10 语法掌握判定 re-base 到 knowledge_nodes:语法点 = 词法/句法 子树的叶子节点。
掌握落到叶子细点,粗点(有子节点)做 rollup。学段用 applicable_stages(小/初/高)。
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d15_knowledge_graph import KnowledgeNode

_GRAMMAR_ROOTS = ("词法", "句法")   # 语法两大顶层


async def _grammar_root_ids(db: AsyncSession) -> list:
    return (await db.execute(
        sa.select(KnowledgeNode.id).where(
            KnowledgeNode.parent_id.is_(None),
            KnowledgeNode.axis == "knowledge",
            KnowledgeNode.name.in_(_GRAMMAR_ROOTS)))).scalars().all()


async def grammar_subtree_ids(db: AsyncSession) -> set:
    """词法/句法 下全部后代节点 id(含根)。"""
    roots = await _grammar_root_ids(db)
    ids, frontier = set(roots), list(roots)
    while frontier:
        ch = (await db.execute(
            sa.select(KnowledgeNode.id).where(KnowledgeNode.parent_id.in_(frontier)))).scalars().all()
        ch = [c for c in ch if c not in ids]
        ids.update(ch)
        frontier = ch
    return ids


async def is_grammar_node(db: AsyncSession, node_id: uuid.UUID) -> bool:
    return node_id in (await grammar_subtree_ids(db))


async def grammar_leaf_nodes(db: AsyncSession, *, stage: str | None = "初", limit: int = 400) -> list[dict]:
    """语法子树的「叶子细点」(无子节点、active),按 词法<句法 → sort_order 排难度序。
    stage 非空时按 applicable_stages 过滤(小/初/高);为空则不限学段。"""
    sub = await grammar_subtree_ids(db)
    if not sub:
        return []
    roots = await _grammar_root_ids(db)
    root_rank = {r: i for i, r in enumerate(roots)}
    parents = set((await db.execute(
        sa.select(KnowledgeNode.parent_id).where(KnowledgeNode.parent_id.isnot(None)))).scalars().all())
    rows = (await db.execute(
        sa.select(KnowledgeNode.id, KnowledgeNode.name, KnowledgeNode.parent_id,
                  KnowledgeNode.sort_order, KnowledgeNode.applicable_stages)
        .where(KnowledgeNode.id.in_(sub), KnowledgeNode.status == "active"))).all()

    # 找每个叶子所属的顶层根(用于难度排序:词法在前)
    async def _root_of(nid, pid):
        cur = pid
        # 简化:沿 parent 上溯到顶层(子树不深)
        guard = 0
        while cur is not None and cur not in root_rank and guard < 20:
            par = (await db.execute(
                sa.select(KnowledgeNode.parent_id).where(KnowledgeNode.id == cur))).scalar_one_or_none()
            cur = par
            guard += 1
        return cur

    out = []
    for nid, name, pid, so, stages in rows:
        if nid in parents:        # 非叶子(粗点)跳过
            continue
        if stage and not (stages and stage in stages):
            continue
        out.append({"kp_id": str(nid), "name": name, "_pid": pid, "_so": so or 0})
    # 排序:词法<句法 → sort_order → 名称
    for d in out:
        rid = await _root_of(uuid.UUID(d["kp_id"]), d["_pid"])
        d["_rr"] = root_rank.get(rid, 99)
    out.sort(key=lambda d: (d["_rr"], d["_so"], d["name"]))
    return [{"kp_id": d["kp_id"], "name": d["name"]} for d in out[:limit]]
