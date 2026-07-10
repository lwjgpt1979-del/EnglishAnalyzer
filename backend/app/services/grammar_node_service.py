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
    stage 非空时按 applicable_stages 过滤(小/初/高);为空则不限学段。

    性能:全子树一次取 (id,parent_id,...) 建内存映射,顶层根上溯在内存走 —— 避免旧版
    对每个叶子逐层发 DB 查询(400 叶 × 树深 = 上千次往返,~7s)导致「语法精进」页加载慢。"""
    sub = await grammar_subtree_ids(db)
    if not sub:
        return []
    roots = await _grammar_root_ids(db)
    root_rank = {r: i for i, r in enumerate(roots)}
    # 全子树(不限 status)一次取,建 id→parent_id 内存映射 + 判叶子(子树内谁被当过父)
    rows = (await db.execute(
        sa.select(KnowledgeNode.id, KnowledgeNode.name, KnowledgeNode.parent_id,
                  KnowledgeNode.sort_order, KnowledgeNode.applicable_stages, KnowledgeNode.status)
        .where(KnowledgeNode.id.in_(sub)))).all()
    parent_map = {r[0]: r[2] for r in rows}
    has_child = {r[2] for r in rows if r[2] is not None}   # 有子节点者 = 非叶子

    def _root_of(nid):
        cur, guard = nid, 0
        while cur is not None and cur not in root_rank and guard < 30:
            cur = parent_map.get(cur)
            guard += 1
        return cur

    out = []
    for nid, name, pid, so, stages, status in rows:
        if status != "active" or nid in has_child:   # 非 active 或 非叶子(粗点)跳过
            continue
        if stage and not (stages and stage in stages):
            continue
        out.append({"kp_id": str(nid), "name": name,
                    "_rr": root_rank.get(_root_of(nid), 99), "_so": so or 0})
    # 排序:词法<句法 → sort_order → 名称
    out.sort(key=lambda d: (d["_rr"], d["_so"], d["name"]))
    return [{"kp_id": d["kp_id"], "name": d["name"]} for d in out[:limit]]
