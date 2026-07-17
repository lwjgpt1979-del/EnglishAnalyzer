"""语法使用统计(超管):把「独立题等未匹配上知识图谱的语法」与「图谱里已有的语法」
放一张表里按使用口径对比,并支持把高频未匹配语法**人工收编进知识图谱**。

口径(与产品确认一致):
  - 未匹配语法:命中该语法名的**学生数** = student_grammar_node 里 ref_node_id 为空的行按 name_norm 聚合(每学生每名一行)。
  - 图谱语法:两列——
      · 引用学生数 = ref_node_id 指向该节点的 student_grammar_node 行数(上传作业里匹配上它的学生);
      · 学习人数   = 该节点上有掌握台账(StudentKp.mastery 非空)的学生数(实际学过/练过)。
两侧「引用学生数」同源同口径,直接可比,便于判断「哪个未匹配语法很多学生遇到 → 值得收编」。

收编 = 在语法子树(词法/句法)下选父节点手建/复用节点(kp_candidate_service.create_node,
按归一名去重),并把所有同名(name_norm)的未匹配个人语法行回填 ref_node_id —— 个人语法即变
「已入图谱」,后续上传按别名自动命中,不再新建个人节点。
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import StudentKp
from app.models.d27_student_grammar import StudentGrammarNode as SGN
from app.services import grammar_node_service, kp_candidate_service


async def unmatched_grammar_usage(
    db: AsyncSession, *, q: str | None = None, skip: int = 0, limit: int = 30,
) -> dict:
    """未匹配上图谱的语法(独立题等)按语法名聚合的使用统计,按命中学生数高频优先。

    返回 {items:[{name, name_norm, anchor_code, student_count, paper_count, last_seen}], total}
      total = 去重后的语法名数(分页基数)。
    """
    grouped = (
        select(
            SGN.name_norm.label("name_norm"),
            func.min(SGN.name).label("name"),
            func.min(SGN.anchor_code).label("anchor_code"),
            func.count().label("student_count"),
            func.count(func.distinct(SGN.source_paper_id)).label("paper_count"),
            func.max(SGN.created_at).label("last_seen"),
        )
        .where(SGN.ref_node_id.is_(None))
    )
    if q and q.strip():
        grouped = grouped.where(SGN.name.ilike(f"%{q.strip()}%"))
    grouped = grouped.group_by(SGN.name_norm)

    total = (await db.execute(
        select(func.count()).select_from(grouped.subquery()))).scalar_one()

    rows = (await db.execute(
        grouped.order_by(sa.desc("student_count"), sa.asc("name"))
        .offset(skip).limit(limit))).all()
    items = [{
        "name": r.name, "name_norm": r.name_norm, "anchor_code": r.anchor_code,
        "student_count": int(r.student_count), "paper_count": int(r.paper_count),
        "last_seen": r.last_seen.isoformat() if r.last_seen else None,
    } for r in rows]
    return {"items": items, "total": int(total)}


async def kg_grammar_usage(
    db: AsyncSession, *, q: str | None = None, skip: int = 0, limit: int = 30,
) -> dict:
    """图谱里的语法节点(词法/句法子树 active)使用统计,按 引用学生数+学习人数 高频优先。

    返回 {items:[{node_id, name, code, ref_student_count, learner_count}], total}
    语法节点仅几百个,一次取全量算计数后在内存排序分页(便宜且能按使用度排序)。
    """
    sub_ids = await grammar_node_service.grammar_subtree_ids(db)
    if not sub_ids:
        return {"items": [], "total": 0}
    sub_ids = list(sub_ids)

    ref_counts = dict((await db.execute(
        select(SGN.ref_node_id, func.count())
        .where(SGN.ref_node_id.in_(sub_ids)).group_by(SGN.ref_node_id))).all())
    learner_counts = dict((await db.execute(
        select(StudentKp.node_id, func.count())
        .where(StudentKp.node_id.in_(sub_ids), StudentKp.mastery.isnot(None))
        .group_by(StudentKp.node_id))).all())

    node_q = (select(KnowledgeNode.id, KnowledgeNode.name, KnowledgeNode.code)
              .where(KnowledgeNode.id.in_(sub_ids), KnowledgeNode.status == "active"))
    if q and q.strip():
        node_q = node_q.where(KnowledgeNode.name.ilike(f"%{q.strip()}%"))
    nodes = (await db.execute(node_q)).all()

    items = [{
        "node_id": str(nid), "name": name, "code": code,
        "ref_student_count": int(ref_counts.get(nid, 0)),
        "learner_count": int(learner_counts.get(nid, 0)),
    } for nid, name, code in nodes]
    items.sort(key=lambda x: (-(x["ref_student_count"] + x["learner_count"]), x["name"]))
    total = len(items)
    return {"items": items[skip:skip + limit], "total": total}


async def grammar_parent_options(
    db: AsyncSession, *, q: str | None = None, limit: int = 50,
) -> list[dict]:
    """收编时的父节点选择器:语法子树(词法/句法)下的 active 节点(粗点/细点都可当父),按 code 排。"""
    sub_ids = await grammar_node_service.grammar_subtree_ids(db)
    if not sub_ids:
        return []
    node_q = (select(KnowledgeNode.id, KnowledgeNode.name, KnowledgeNode.code)
              .where(KnowledgeNode.id.in_(list(sub_ids)), KnowledgeNode.status == "active"))
    if q and q.strip():
        node_q = node_q.where(KnowledgeNode.name.ilike(f"%{q.strip()}%"))
    rows = (await db.execute(node_q.order_by(KnowledgeNode.code).limit(limit))).all()
    return [{"id": str(nid), "name": name, "code": code} for nid, name, code in rows]


async def promote_unmatched_grammar(
    db: AsyncSession, *, name: str, name_norm: str, parent_id: uuid.UUID,
) -> dict:
    """把某未匹配语法收编进知识图谱:在所选父节点(语法子树内)下建/复用节点,
    并把所有同名(name_norm)的未匹配个人语法行回填 ref_node_id(即变「已入图谱」)。

    返回 {node_id, code, name, backfilled}。父节点须在词法/句法子树内(否则拒绝,避免建歪位置)。
    """
    from app.core.exceptions import AppError
    sub_ids = await grammar_node_service.grammar_subtree_ids(db)
    if parent_id not in sub_ids:
        raise AppError(code=400, message="父节点必须在语法子树(词法/句法)内")

    node = await kp_candidate_service.create_node(db, name=name.strip(), parent_id=parent_id)
    res = await db.execute(
        update(SGN).where(SGN.ref_node_id.is_(None), SGN.name_norm == name_norm)
        .values(ref_node_id=node.id))
    await db.commit()
    return {"node_id": str(node.id), "code": node.code, "name": node.name,
            "backfilled": int(res.rowcount or 0)}
