"""R0.4 候选知识点审核(超管):approve / merge别名 / reject。

消费 R0.3 受控匹配落下的 kp_candidate(pending):
  - approve  → 建正式 knowledge_node(active) + 候选名进别名;候选 approved
  - merge    → 把候选名并为某已有节点的别名(治碎片化的灵魂);候选 merged
  - reject   → 候选 rejected(理由记入 context_sample)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.exceptions import AppError
from app.models.d15_knowledge_graph import KnowledgeNode, NodeAlias, KpCandidate
from app.models.d17_curriculum_kg import UnitNode
from app.services.kp_normalize import normalize_kp_name

# 候选来源 → 节点来源(KnowledgeNode.source ∈ seed|textbook|exam)
_SOURCE_MAP = {"textbook": "textbook", "exam": "exam"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _backfill_unit_edges(db, node_id: uuid.UUID, source_ref: dict | None) -> None:
    """候选若带来源单元(source_ref.unit_ids,R1 教材抽取写入)→ 审核后回填 unit_node 边。"""
    for uid in (source_ref or {}).get("unit_ids", []):
        try:
            unit_uuid = uid if isinstance(uid, uuid.UUID) else uuid.UUID(str(uid))
        except (ValueError, AttributeError):
            continue
        await db.execute(
            pg_insert(UnitNode)
            .values(unit_id=unit_uuid, node_id=node_id, source="manual")
            .on_conflict_do_nothing(index_elements=["unit_id", "node_id"])
        )


async def _materialize_pending_content(db, node_id: uuid.UUID, norm: str) -> int:
    """候选出 node 后 → 取该 KP 名暂存的讲解(pending_kp_content)物化为 node_resource lecture,
    并删除已物化行。返回物化条数(生成内容不丢:未命中时暂存,审核后到位)。"""
    from app.models.d11_v2_curriculum import PendingKpContent
    from app.services import node_resource_service as nrs
    rows = (await db.execute(
        sa.select(PendingKpContent).where(PendingKpContent.kp_name_norm == norm)
    )).scalars().all()
    count = 0
    for r in rows:
        if r.dimension not in nrs._DIMENSIONS:
            continue
        # 走 C1 版本流:挂到既有节点若已有发布内容,产生待审版本而非覆盖
        await nrs.submit_lecture_version(
            db, node_id=node_id, dimension=r.dimension, content_md=r.content_md,
            source=r.generated_by or "ai_full", status_if_new="draft")
        await db.delete(r)
        count += 1
    if count:
        await db.flush()
    return count


async def _get_pending(db: AsyncSession, candidate_id: uuid.UUID) -> KpCandidate:
    cand = (await db.execute(
        sa.select(KpCandidate).where(KpCandidate.id == candidate_id)
    )).scalar_one_or_none()
    if cand is None:
        raise AppError(code=404, message="候选知识点不存在")
    if cand.status != "pending":
        raise AppError(code=409, message=f"候选已处理(当前状态 {cand.status})")
    return cand


async def _gen_node_code(db: AsyncSession, name_norm: str) -> str:
    """稳定可读编码 kp-<norm>;冲突则补短随机后缀(绝不复用 auto_ 随机风格)。"""
    base = f"kp-{name_norm[:48]}"
    exists = (await db.execute(
        sa.select(KnowledgeNode.id).where(KnowledgeNode.code == base)
    )).scalar_one_or_none()
    if exists is None:
        return base
    return f"{base[:54]}-{uuid.uuid4().hex[:6]}"


async def list_candidates(
    db: AsyncSession, *, status: str = "pending", axis: str | None = None,
    skip: int = 0, limit: int = 50,
) -> tuple[list[KpCandidate], int]:
    """按状态分页查候选(默认 pending,按 occur_count 高频优先)。"""
    base = sa.select(KpCandidate).where(KpCandidate.status == status)
    if axis is not None:
        base = base.where(KpCandidate.suggested_axis == axis)
    total: int = (await db.execute(
        sa.select(sa.func.count()).select_from(base.subquery())
    )).scalar_one()
    rows = (await db.execute(
        base.order_by(KpCandidate.occur_count.desc(), KpCandidate.created_at)
        .offset(skip).limit(limit)
    )).scalars().all()
    return list(rows), total


async def list_nodes_overview(
    db: AsyncSession, *, axis: str | None = None, stage: str | None = None,
    status: str | None = None, q: str | None = None, skip: int = 0, limit: int = 20,
) -> tuple[list[dict], int]:
    """知识图谱总览(D1):节点分页 + 每节点摘要(六维完整度/引用单元/引用真题/别名数)。"""
    from sqlalchemy.dialects.postgresql import JSONB
    from app.models.d16_question_domain import PlatformQuestionKp
    from app.models.d19_node_resource import NodeResource

    base = sa.select(KnowledgeNode)
    if axis:
        base = base.where(KnowledgeNode.axis == axis)
    if status:
        base = base.where(KnowledgeNode.status == status)
    if q:
        base = base.where(KnowledgeNode.name.ilike(f"%{q}%"))
    if stage:                                   # JSONB:空(适用全部)或含该学段
        base = base.where(sa.or_(
            KnowledgeNode.applicable_stages.is_(None),
            KnowledgeNode.applicable_stages.op("@>")(sa.cast([stage], JSONB))))
    total = (await db.execute(sa.select(sa.func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(
        base.order_by(KnowledgeNode.name).offset(skip).limit(limit))).scalars().all()
    ids = [r.id for r in rows]
    if not ids:
        return [], total

    async def _counts(stmt):
        return {nid: c for nid, c in (await db.execute(stmt)).all()}
    dims = await _counts(
        sa.select(NodeResource.node_id, sa.func.count(sa.distinct(NodeResource.dimension)))
        .where(NodeResource.node_id.in_(ids), NodeResource.resource_type == "lecture")
        .group_by(NodeResource.node_id))
    units = await _counts(
        sa.select(UnitNode.node_id, sa.func.count()).where(UnitNode.node_id.in_(ids))
        .group_by(UnitNode.node_id))
    ques = await _counts(
        sa.select(PlatformQuestionKp.node_id, sa.func.count())
        .where(PlatformQuestionKp.node_id.in_(ids)).group_by(PlatformQuestionKp.node_id))
    aliases = await _counts(
        sa.select(NodeAlias.node_id, sa.func.count()).where(NodeAlias.node_id.in_(ids))
        .group_by(NodeAlias.node_id))
    items = [{
        "id": r.id, "axis": r.axis, "node_kind": r.node_kind, "name": r.name, "code": r.code,
        "status": r.status, "applicable_stages": r.applicable_stages,
        "dims_filled": int(dims.get(r.id, 0)), "unit_refs": int(units.get(r.id, 0)),
        "question_refs": int(ques.get(r.id, 0)), "alias_count": int(aliases.get(r.id, 0)),
    } for r in rows]
    return items, total


async def node_tree(db: AsyncSession, *, axis: str | None = None) -> list[dict]:
    """受控知识树(E1):按 parent_id 组装嵌套(排除已停用)。"""
    stmt = sa.select(KnowledgeNode).where(KnowledgeNode.status != "retired")
    if axis:
        stmt = stmt.where(KnowledgeNode.axis == axis)
    rows = (await db.execute(stmt.order_by(KnowledgeNode.sort_order, KnowledgeNode.name))).scalars().all()
    nodes = {r.id: {"id": r.id, "name": r.name, "axis": r.axis, "node_kind": r.node_kind,
                    "status": r.status, "code": r.code, "parent_id": r.parent_id, "children": []}
             for r in rows}
    roots: list[dict] = []
    for r in rows:
        item = nodes[r.id]
        parent = nodes.get(r.parent_id) if r.parent_id else None
        (parent["children"] if parent else roots).append(item)
    return roots


async def create_node(
    db: AsyncSession, *, name: str, parent_id: uuid.UUID | None = None, axis: str | None = None,
    node_kind: str | None = None, applicable_stages: list[str] | None = None,
) -> KnowledgeNode:
    """在树上手建节点:有 parent 则继承其轴;否则需显式 axis。"""
    if not name.strip():
        raise AppError(code=400, message="名称不能为空")
    if parent_id is not None:
        parent = await db.get(KnowledgeNode, parent_id)
        if parent is None:
            raise AppError(code=404, message="父节点不存在")
        axis = parent.axis
    elif axis not in ("knowledge", "ability", "exam"):
        raise AppError(code=400, message="顶层节点需指定 axis(knowledge/ability/exam)")
    nid = uuid.uuid4()
    node = KnowledgeNode(
        id=nid, axis=axis, node_kind=node_kind or None, name=name.strip(),
        code=f"m-{uuid.uuid4().hex[:10]}", applicable_stages=applicable_stages or None,
        status="active", source="manual", parent_id=parent_id)
    db.add(node)
    db.add(NodeAlias(id=uuid.uuid4(), node_id=nid, alias=name.strip(),
                     alias_norm=normalize_kp_name(name), source="manual"))
    await db.flush()
    return node


async def set_parent(db: AsyncSession, *, node_id: uuid.UUID, parent_id: uuid.UUID | None) -> KnowledgeNode:
    """移动节点(改 parent)。禁跨轴、禁成环。parent_id=None 升为顶层。"""
    node = await db.get(KnowledgeNode, node_id)
    if node is None:
        raise AppError(code=404, message="节点不存在")
    if parent_id is not None:
        if parent_id == node_id:
            raise AppError(code=400, message="不能挂到自身")
        parent = await db.get(KnowledgeNode, parent_id)
        if parent is None:
            raise AppError(code=404, message="父节点不存在")
        if parent.axis != node.axis:
            raise AppError(code=400, message="不能跨轴移动")
        cur = parent                                  # 防环:目标不能是自己的后代
        while cur is not None:
            if cur.id == node_id:
                raise AppError(code=400, message="不能挂到自己的子孙下(成环)")
            cur = await db.get(KnowledgeNode, cur.parent_id) if cur.parent_id else None
    node.parent_id = parent_id
    await db.flush()
    return node


async def node_detail(db: AsyncSession, *, node_id: uuid.UUID) -> dict:
    """节点详情(D2):基础字段 + 别名 + 引用单元 + 引用真题 + 六维完整度 + 学生掌握分布。"""
    from app.models.d4_knowledge import CurriculumUnit
    from app.models.d16_question_domain import PlatformQuestion, PlatformQuestionKp, StudentKp
    from app.models.d19_node_resource import NodeResource
    from app.services.node_resource_service import LECTURE_DIMENSIONS

    node = await db.get(KnowledgeNode, node_id)
    if node is None:
        raise AppError(code=404, message="节点不存在")

    aliases = [{"alias": a, "source": s} for a, s in (await db.execute(
        sa.select(NodeAlias.alias, NodeAlias.source).where(NodeAlias.node_id == node_id)
        .order_by(NodeAlias.alias))).all()]

    units = [{"unit_id": uid, "unit_title": title, "textbook_version": tv, "grade": g, "semester": sem}
             for uid, title, tv, g, sem in (await db.execute(
                 sa.select(CurriculumUnit.id, CurriculumUnit.unit_title, CurriculumUnit.textbook_version,
                           CurriculumUnit.grade, CurriculumUnit.semester)
                 .join(UnitNode, UnitNode.unit_id == CurriculumUnit.id)
                 .where(UnitNode.node_id == node_id)
                 .order_by(CurriculumUnit.textbook_version, CurriculumUnit.grade,
                           CurriculumUnit.semester, CurriculumUnit.unit_no))).all()]

    qbtype = dict((await db.execute(
        sa.select(PlatformQuestion.type, sa.func.count())
        .join(PlatformQuestionKp, PlatformQuestionKp.question_id == PlatformQuestion.id)
        .where(PlatformQuestionKp.node_id == node_id).group_by(PlatformQuestion.type))).all())

    lec = {dim: {"id": rid, "status": st} for rid, dim, st in (await db.execute(
        sa.select(NodeResource.id, NodeResource.dimension, NodeResource.status)
        .where(NodeResource.node_id == node_id, NodeResource.resource_type == "lecture"))).all() if dim}
    dims = {d: lec.get(d) for d in LECTURE_DIMENSIONS}

    m = (await db.execute(sa.select(
        sa.func.count(), sa.func.avg(StudentKp.mastery),
        sa.func.count().filter(StudentKp.mastery >= 0.7),
        sa.func.count().filter(sa.and_(StudentKp.mastery >= 0.4, StudentKp.mastery < 0.7)),
        sa.func.count().filter(StudentKp.mastery < 0.4),
    ).where(StudentKp.node_id == node_id, StudentKp.mastery.isnot(None)))).one()
    mastery = {"learners": int(m[0]), "avg": round(float(m[1]), 3) if m[1] is not None else None,
               "mastered": int(m[2]), "mid": int(m[3]), "weak": int(m[4])}

    return {
        "id": node.id, "axis": node.axis, "node_kind": node.node_kind, "name": node.name,
        "code": node.code, "status": node.status, "applicable_stages": node.applicable_stages,
        "description": node.description, "source": node.source,
        "dims": dims, "aliases": aliases, "units": units,
        "question_real": int(qbtype.get("real", 0)), "question_sim": int(qbtype.get("sim", 0)),
        "mastery": mastery,
    }


async def update_node(
    db: AsyncSession, *, node_id: uuid.UUID, name: str | None = None, node_kind: str | None = None,
    applicable_stages: list[str] | None = None, description: str | None = None,
) -> KnowledgeNode:
    node = await db.get(KnowledgeNode, node_id)
    if node is None:
        raise AppError(code=404, message="节点不存在")
    if name is not None:
        if not name.strip():
            raise AppError(code=400, message="名称不能为空")
        node.name = name.strip()
    if node_kind is not None:
        node.node_kind = node_kind or None
    if applicable_stages is not None:
        node.applicable_stages = applicable_stages or None
    if description is not None:
        node.description = description or None
    await db.flush()
    return node


async def set_node_status(db: AsyncSession, *, node_id: uuid.UUID, status: str) -> KnowledgeNode:
    if status not in ("active", "retired"):
        raise AppError(code=400, message="状态仅支持 active / retired")
    node = await db.get(KnowledgeNode, node_id)
    if node is None:
        raise AppError(code=404, message="节点不存在")
    node.status = status
    await db.flush()
    return node


async def list_nodes(
    db: AsyncSession, *, axis: str | None = None, stage: str | None = None,
    q: str | None = None, limit: int = 20,
) -> list[KnowledgeNode]:
    """merge 目标选择器 / 别名预览:按 axis、学段、名称模糊查 active 节点。"""
    stmt = sa.select(KnowledgeNode).where(KnowledgeNode.status == "active")
    if axis is not None:
        stmt = stmt.where(KnowledgeNode.axis == axis)
    if q:
        stmt = stmt.where(KnowledgeNode.name.ilike(f"%{q}%"))
    rows = (await db.execute(stmt.order_by(KnowledgeNode.name).limit(limit))).scalars().all()
    # 学段软过滤(JSONB,Python 侧判,避免方言细节)
    if stage:
        rows = [r for r in rows if not r.applicable_stages or stage in r.applicable_stages]
    return list(rows)


async def approve(
    db: AsyncSession, *, candidate_id: uuid.UUID, axis: str,
    stage: str | None = None, node_kind: str | None = None,
    parent_id: uuid.UUID | None = None, reviewer_id: uuid.UUID,
) -> KnowledgeNode:
    """通过 → 建 active 节点 + 候选名进别名。名已被占用则拒绝(应改用 merge)。"""
    cand = await _get_pending(db, candidate_id)
    norm = cand.name_norm or normalize_kp_name(cand.raw_name)

    dup = (await db.execute(
        sa.select(NodeAlias.node_id).where(NodeAlias.alias_norm == norm)
    )).scalar_one_or_none()
    if dup is not None:
        raise AppError(code=409, message="该写法已归属某节点,请改用『归并』而非新建")

    node = KnowledgeNode(
        id=uuid.uuid4(), axis=axis, node_kind=node_kind,
        name=cand.raw_name, code=await _gen_node_code(db, norm),
        applicable_stages=([stage] if stage else None),
        status="active", source=_SOURCE_MAP.get(cand.source_type or "", "seed"),
        parent_id=parent_id,
    )
    db.add(node)
    await db.flush()
    db.add(NodeAlias(id=uuid.uuid4(), node_id=node.id, alias=cand.raw_name,
                     alias_norm=norm, source="merge"))
    cand.status = "approved"
    cand.merged_into_node_id = node.id
    cand.reviewed_by = reviewer_id
    cand.reviewed_at = _now()
    await db.flush()
    await _backfill_unit_edges(db, node.id, cand.source_ref)   # R1:回填来源单元的边
    await _materialize_pending_content(db, node.id, norm)       # 生成内容物化为 lecture
    return node


async def merge(
    db: AsyncSession, *, candidate_id: uuid.UUID, target_node_id: uuid.UUID,
    reviewer_id: uuid.UUID,
) -> KnowledgeNode:
    """归并 → 候选名作为目标节点的别名(杜绝碎片化)。名已占用别处则拒绝。"""
    cand = await _get_pending(db, candidate_id)
    norm = cand.name_norm or normalize_kp_name(cand.raw_name)

    target = (await db.execute(
        sa.select(KnowledgeNode).where(KnowledgeNode.id == target_node_id)
    )).scalar_one_or_none()
    if target is None:
        raise AppError(code=404, message="目标节点不存在")

    existing = (await db.execute(
        sa.select(NodeAlias.node_id).where(NodeAlias.alias_norm == norm)
    )).scalar_one_or_none()
    if existing is not None and existing != target_node_id:
        raise AppError(code=409, message="该写法已归属其它节点,不可归并")
    if existing is None:
        db.add(NodeAlias(id=uuid.uuid4(), node_id=target_node_id, alias=cand.raw_name,
                         alias_norm=norm, source="merge"))
    cand.status = "merged"
    cand.merged_into_node_id = target_node_id
    cand.reviewed_by = reviewer_id
    cand.reviewed_at = _now()
    await db.flush()
    await _backfill_unit_edges(db, target_node_id, cand.source_ref)   # R1:回填来源单元的边
    await _materialize_pending_content(db, target_node_id, norm)      # 生成内容物化为 lecture
    return target


async def reject(
    db: AsyncSession, *, candidate_id: uuid.UUID, reason: str, reviewer_id: uuid.UUID,
) -> KpCandidate:
    """驳回 → 状态 rejected,理由记入 context_sample(模型无独立 reason 列)。"""
    cand = await _get_pending(db, candidate_id)
    sample = dict(cand.context_sample or {})
    sample["reject_reason"] = reason
    cand.context_sample = sample
    cand.status = "rejected"
    cand.reviewed_by = reviewer_id
    cand.reviewed_at = _now()
    await db.flush()
    return cand
