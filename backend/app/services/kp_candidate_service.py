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


async def list_roots(db: AsyncSession) -> list[dict]:
    """知识图谱根目录(顶层分类,parent_id 为空)选项——多选过滤下拉的单一真源。排除已停用。"""
    rows = (await db.execute(
        sa.select(KnowledgeNode.id, KnowledgeNode.name, KnowledgeNode.code, KnowledgeNode.axis)
        .where(KnowledgeNode.parent_id.is_(None), KnowledgeNode.status != "retired")
        .order_by(KnowledgeNode.axis, KnowledgeNode.code))).all()
    return [{"id": str(i), "name": n, "code": c, "axis": a} for i, n, c, a in rows]


async def _descendant_ids(db: AsyncSession, root_ids: list) -> list:
    """递归取所选根目录下的**全部后代节点 id**(含根本身)。按真实 parent_id 树,不靠 code 前缀
    (大量 m-* 节点 code 不带根前缀,前缀过滤会漏)。"""
    sql = sa.text(
        "WITH RECURSIVE sub AS ("
        "  SELECT id FROM knowledge_nodes WHERE id IN :roots"
        "  UNION ALL"
        "  SELECT kn.id FROM knowledge_nodes kn JOIN sub ON kn.parent_id = sub.id"
        ") SELECT id FROM sub"
    ).bindparams(sa.bindparam("roots", expanding=True))
    return list((await db.execute(sql, {"roots": [str(r) for r in root_ids]})).scalars().all())


async def list_nodes_overview(
    db: AsyncSession, *, axis: str | None = None, stage: str | None = None,
    status: str | None = None, q: str | None = None, linked: str | None = None,
    root_ids: list | None = None, skip: int = 0, limit: int = 20,
) -> tuple[list[dict], int]:
    """知识图谱总览(D1):节点分页 + 每节点摘要(讲解完整度/引用单元/引用真题/别名数)。
    root_ids:多选根目录过滤——只出这些根节点子树下的节点(含根)。"""
    from sqlalchemy.dialects.postgresql import JSONB
    from app.models.d16_question_domain import PlatformQuestionKp

    base = sa.select(KnowledgeNode)
    if axis:
        base = base.where(KnowledgeNode.axis == axis)
    if status:
        base = base.where(KnowledgeNode.status == status)
    if q:
        base = base.where(KnowledgeNode.name.ilike(f"%{q}%"))
    if root_ids:
        sub_ids = await _descendant_ids(db, root_ids)
        base = base.where(KnowledgeNode.id.in_(sub_ids))
    if stage:                                   # JSONB:空(适用全部)或含该学段
        base = base.where(sa.or_(
            KnowledgeNode.applicable_stages.is_(None),
            KnowledgeNode.applicable_stages.op("@>")(sa.cast([stage], JSONB))))
    # 关联筛选:unit=已关联教材单元 / question=已关联真题 / both=两者同时关联(EXISTS 子查询)
    if linked in ("unit", "both"):
        base = base.where(sa.select(UnitNode.node_id).where(UnitNode.node_id == KnowledgeNode.id).exists())
    if linked in ("question", "both"):
        base = base.where(
            sa.select(PlatformQuestionKp.node_id)
            .where(PlatformQuestionKp.node_id == KnowledgeNode.id).exists())
    total = (await db.execute(sa.select(sa.func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(
        base.order_by(KnowledgeNode.name).offset(skip).limit(limit))).scalars().all()
    ids = [r.id for r in rows]
    if not ids:
        return [], total

    async def _counts(stmt):
        return {nid: c for nid, c in (await db.execute(stmt)).all()}
    # 讲解完整度:已填讲解环节数(kp_lecture);分母 = 该考点类型模板环节数
    from app.services import kp_lecture_service as kl
    lec_filled = await kl.filled_counts(db, node_ids=ids)
    lec_published = await kl.filled_counts(db, node_ids=ids, published_only=True)
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
        "status": r.status, "applicable_stages": r.applicable_stages, "source": r.source,
        "lecture_filled": int(lec_filled.get(r.id, 0)), "lecture_total": len(kl.template_for(r.code)),
        "lecture_published": int(lec_published.get(r.id, 0)),
        "unit_refs": int(units.get(r.id, 0)),
        "question_refs": int(ques.get(r.id, 0)), "alias_count": int(aliases.get(r.id, 0)),
    } for r in rows]
    return items, total


_GRP_PREFIX = {"词法": "cf", "句法": "jf", "阅读": "rc", "听力": "lt", "作文": "wr"}


async def _exam_stats_options(db, q) -> dict:
    """统计页筛选下拉的可选项(取真题里实际存在的值)。"""
    async def _vals(col):
        rows = (await db.execute(sa.select(col).where(q.type == "real", col.isnot(None), col != "")
                                 .distinct().order_by(col))).scalars().all()
        return list(rows)
    regions = (await db.execute(
        sa.select(q.region_code, q.region_name).where(
            q.type == "real", q.region_code.isnot(None), q.region_code != "")
        .distinct().order_by(q.region_name))).all()
    return {
        "textbooks": await _vals(q.textbook_version),
        "stages": await _vals(q.stage),
        "grades": await _vals(q.grade),
        "regions": [{"code": c, "name": n} for c, n in regions],
    }


async def exam_type_stats(db: AsyncSession, *, grp: str | None = None,
                          textbook: str | None = None, stage: str | None = None,
                          grade: str | None = None, region_code: str | None = None,
                          exam_type: str | None = None) -> dict:
    """按考点统计已挂**真题**的考试类型分布(普通/中考/高考)。

    返回 {totals,items,options};items 按合计降序。grp 按 code 前缀筛;
    textbook/stage/grade/region_code(前缀)/exam_type 按题元信息筛。
    """
    from app.models.d16_question_domain import PlatformQuestion, PlatformQuestionKp
    q = PlatformQuestion
    conds = [q.type == "real"]
    if textbook:
        conds.append(q.textbook_version == textbook)
    if stage:
        conds.append(q.stage == stage)
    if grade:
        conds.append(q.grade == grade)
    if region_code:
        conds.append(q.region_code.like(f"{region_code}%"))
    if exam_type == "普通":
        conds.append(sa.or_(q.exam_type.is_(None), q.exam_type.in_(["", "普通"])))
    elif exam_type:
        conds.append(q.exam_type == exam_type)
    et = sa.func.coalesce(sa.func.nullif(q.exam_type, ""), "普通")
    rows = (await db.execute(
        sa.select(PlatformQuestionKp.node_id, et.label("et"),
                  sa.func.count(sa.distinct(PlatformQuestionKp.question_id)))
        .join(q, q.id == PlatformQuestionKp.question_id)
        .where(*conds)
        .group_by(PlatformQuestionKp.node_id, et))).all()
    agg: dict = {}
    for nid, etv, cnt in rows:
        d = agg.setdefault(nid, {"普通": 0, "中考": 0, "高考": 0})
        d[etv if etv in d else "普通"] += int(cnt)
    options = await _exam_stats_options(db, q)
    if not agg:
        return {"totals": {"普通": 0, "中考": 0, "高考": 0, "合计": 0}, "items": [], "options": options}
    info = (await db.execute(sa.select(KnowledgeNode.id, KnowledgeNode.name, KnowledgeNode.code)
                             .where(KnowledgeNode.id.in_(list(agg))))).all()
    pref = _GRP_PREFIX.get(grp or "")
    items: list[dict] = []
    for nid, name, code in info:
        if pref and not (code or "").startswith(pref):
            continue
        d = agg[nid]
        items.append({"id": str(nid), "name": name, "code": code, **d,
                      "合计": d["普通"] + d["中考"] + d["高考"]})
    items.sort(key=lambda x: -x["合计"])
    totals = {k: sum(it[k] for it in items) for k in ("普通", "中考", "高考")}
    totals["合计"] = sum(totals.values())
    return {"totals": totals, "items": items, "options": options}


# ── 知识树内存缓存(滑动 5 分钟;节点有增删改时失效)────────────────────────
import time as _time

_TREE_CACHE: dict[tuple, tuple[float, list]] = {}   # (axis,with_counts,stage) -> (到期单调时刻, 数据)
_TREE_TTL = 300.0                                    # 5 分钟


def invalidate_node_tree_cache() -> None:
    """知识图谱节点有增删改 → 清树缓存,下次重建。"""
    _TREE_CACHE.clear()


async def node_tree(db: AsyncSession, *, axis: str | None = None,
                    with_counts: bool = False, stage: str | None = None) -> list[dict]:
    """受控知识树(E1):按 parent_id 组装嵌套(排除已停用)。

    内存缓存:滑动 5 分钟(每次命中续期);节点增删改调 invalidate_node_tree_cache() 失效。
    with_counts=True 时,每个节点附 unit_refs/question_refs(教材单元 / 真题挂载数),
    分类节点取其**整棵子树聚合**(自身+所有后代直接挂载之和),便于一眼看哪类挂得多。
    stage(小|初|高)过滤,包含式(高⊇初⊇小):保留「未标学段(通用脚手架/分类)
    或含该学段及更低学段」的节点(看初中卷=小+初考点,看高中=全部)。
    """
    _ckey = (axis, with_counts, stage)
    _now = _time.monotonic()
    _hit = _TREE_CACHE.get(_ckey)
    if _hit is not None and _hit[0] > _now:
        _TREE_CACHE[_ckey] = (_now + _TREE_TTL, _hit[1])   # 滑动续期
        return _hit[1]

    stmt = sa.select(KnowledgeNode).where(KnowledgeNode.status != "retired")
    if axis:
        stmt = stmt.where(KnowledgeNode.axis == axis)
    if stage:
        from sqlalchemy.dialects.postgresql import JSONB
        _rank = {"小": 0, "初": 1, "高": 2}
        allowed = [s for s, r in _rank.items() if r <= _rank.get(stage, 99)]
        conds = [KnowledgeNode.applicable_stages.is_(None)]
        conds += [KnowledgeNode.applicable_stages.op("@>")(sa.cast([s], JSONB)) for s in allowed]
        stmt = stmt.where(sa.or_(*conds))
    rows = (await db.execute(stmt.order_by(KnowledgeNode.sort_order, KnowledgeNode.name))).scalars().all()
    nodes = {r.id: {"id": r.id, "name": r.name, "axis": r.axis, "node_kind": r.node_kind,
                    "status": r.status, "code": r.code, "parent_id": r.parent_id,
                    "applicable_stages": r.applicable_stages, "source": r.source, "children": []}
             for r in rows}

    if with_counts:
        from app.models.d16_question_domain import PlatformQuestion, PlatformQuestionKp
        from app.models.d17_curriculum_kg import UnitNode
        units = dict((await db.execute(
            sa.select(UnitNode.node_id, sa.func.count()).group_by(UnitNode.node_id))).all())
        reals = dict((await db.execute(
            sa.select(PlatformQuestionKp.node_id, sa.func.count())
            .join(PlatformQuestion, PlatformQuestion.id == PlatformQuestionKp.question_id)
            .where(PlatformQuestion.type == "real")
            .group_by(PlatformQuestionKp.node_id))).all())
        for nid, item in nodes.items():
            item["unit_refs"] = int(units.get(nid, 0))
            item["question_refs"] = int(reals.get(nid, 0))

    roots: list[dict] = []
    for r in rows:
        item = nodes[r.id]
        parent = nodes.get(r.parent_id) if r.parent_id else None
        (parent["children"] if parent else roots).append(item)

    if with_counts:                       # 后序聚合:子树求和
        def _rollup(n: dict) -> tuple[int, int]:
            u, q = n["unit_refs"], n["question_refs"]
            for c in n["children"]:
                cu, cq = _rollup(c)
                u += cu; q += cq
            n["unit_refs"], n["question_refs"] = u, q
            return u, q
        for r in roots:
            _rollup(r)
    _TREE_CACHE[_ckey] = (_time.monotonic() + _TREE_TTL, roots)
    return roots


async def create_node(
    db: AsyncSession, *, name: str, parent_id: uuid.UUID | None = None, axis: str | None = None,
    node_kind: str | None = None, applicable_stages: list[str] | None = None,
) -> KnowledgeNode:
    """在树上手建节点:有 parent 则继承其轴;否则需显式 axis。

    归一化同名考点已存在 → **复用**(返回已有节点),避免别名唯一约束冲突(原会 500)与重复建点:
    缺口建议「新建」若该考点其实已存在,等价于直接挂已有考点。
    """
    if not name.strip():
        raise AppError(code=400, message="名称不能为空")
    norm = normalize_kp_name(name)
    existing = (await db.execute(
        sa.select(KnowledgeNode).join(NodeAlias, NodeAlias.node_id == KnowledgeNode.id)
        .where(NodeAlias.alias_norm == norm).limit(1))).scalar_one_or_none()
    if existing is not None:
        return existing
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
    invalidate_node_tree_cache()
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
    invalidate_node_tree_cache()
    return node


async def node_detail(db: AsyncSession, *, node_id: uuid.UUID) -> dict:
    """节点详情(D2):基础字段 + 别名 + 引用单元 + 引用真题 + 讲解完整度(按类型) + 学生掌握分布。"""
    from app.models.d4_knowledge import CurriculumUnit
    from app.models.d16_question_domain import PlatformQuestion, PlatformQuestionKp, StudentKp
    from app.services import kp_lecture_service as kl

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

    lecture = await kl.list_sections(db, node_id=node_id, code=node.code)   # 讲解:模板环节 + 完整度

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
        "lecture": lecture, "aliases": aliases, "units": units,
        "question_real": int(qbtype.get("real", 0)), "question_sim": int(qbtype.get("sim", 0)),
        "mastery": mastery,
    }


async def node_hub(db: AsyncSession, *, node_id: uuid.UUID) -> dict:
    """知识点详情枢纽(F 方案):详解正文 + 反向关联(教材/真题/仿真)+ 关系边。"""
    from app.models.d4_knowledge import CurriculumUnit
    from app.models.d15_knowledge_graph import NodeRelation
    from app.models.d16_question_domain import (
        PlatformQuestion, PlatformQuestionKp, PlatformPaper,
    )
    from app.services import kp_lecture_service as kl

    node = await db.get(KnowledgeNode, node_id)
    if node is None:
        raise AppError(code=404, message="知识点不存在")

    # 讲解正文:按考点类型的教学环节(含完整度)
    lectures = (await kl.list_sections(db, node_id=node_id, code=node.code))["sections"]

    # 反向 · 教材单元
    units = [{"unit_id": uid, "unit_title": title, "textbook_version": tv, "grade": g, "semester": sem}
             for uid, title, tv, g, sem in (await db.execute(
                 sa.select(CurriculumUnit.id, CurriculumUnit.unit_title, CurriculumUnit.textbook_version,
                           CurriculumUnit.grade, CurriculumUnit.semester)
                 .join(UnitNode, UnitNode.unit_id == CurriculumUnit.id)
                 .where(UnitNode.node_id == node_id)
                 .order_by(CurriculumUnit.textbook_version, CurriculumUnit.grade))).all()]

    # 反向 · 真题 / 仿真(挂本点的题,带题干摘要 + 所属试卷)
    qrows = (await db.execute(
        sa.select(PlatformQuestion.id, PlatformQuestion.type, PlatformQuestion.question_no,
                  PlatformQuestion.section, PlatformQuestion.stem, PlatformQuestion.status,
                  PlatformQuestion.parent_real_id, PlatformPaper.name)
        .join(PlatformQuestionKp, PlatformQuestionKp.question_id == PlatformQuestion.id)
        .outerjoin(PlatformPaper, PlatformPaper.id == PlatformQuestion.paper_id)
        .where(PlatformQuestionKp.node_id == node_id)
        .order_by(PlatformQuestion.type, PlatformQuestion.created_at).limit(200))).all()
    real_qs, sim_qs = [], []
    for qid, qtype, qno, sec, stem, st, parent, pname in qrows:
        item = {"id": qid, "question_no": qno, "section": sec,
                "stem": (stem or "")[:120], "status": st, "paper_name": pname}
        (real_qs if qtype == "real" else sim_qs).append(item)

    # 关系边(双向)
    rels = []
    for fid, tid, rel in (await db.execute(
        sa.select(NodeRelation.from_node_id, NodeRelation.to_node_id, NodeRelation.relation)
        .where(sa.or_(NodeRelation.from_node_id == node_id, NodeRelation.to_node_id == node_id)))).all():
        other = tid if fid == node_id else fid
        n2 = await db.get(KnowledgeNode, other)
        if n2 is not None:
            rels.append({"node_id": other, "name": n2.name, "code": n2.code, "relation": rel})

    return {
        "id": node.id, "name": node.name, "code": node.code, "status": node.status,
        "node_kind": node.node_kind, "description": node.description,
        "lectures": lectures, "units": units,
        "real_questions": real_qs, "sim_questions": sim_qs, "relations": rels,
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
    invalidate_node_tree_cache()
    return node


async def set_node_status(db: AsyncSession, *, node_id: uuid.UUID, status: str) -> KnowledgeNode:
    if status not in ("active", "retired"):
        raise AppError(code=400, message="状态仅支持 active / retired")
    node = await db.get(KnowledgeNode, node_id)
    if node is None:
        raise AppError(code=404, message="节点不存在")
    node.status = status
    await db.flush()
    invalidate_node_tree_cache()
    return node


async def delete_node(db: AsyncSession, *, node_id: uuid.UUID) -> dict:
    """硬删除一个知识节点(连带其各种挂边)。**有子节点则拒绝**(防误删整棵子树,需先删/移子节点)。

    清理无 DB 级联的引用边(别名/关系/单元边/词汇边/长难句边/真题·上传题·学生 KP 边);
    node_resource、unit_passage_kp 由 DB 级联删;unit_section.node_id 由 DB 置空;
    answer_log.node_id 无 FK 约束(留存事件,不动)。删的是节点本身,不影响共享词汇/题目主表。
    """
    from app.models.d15_knowledge_graph import NodeAlias, NodeRelation
    from app.models.d17_curriculum_kg import UnitNode
    from app.models.d18_vocab_kg import VocabNode
    from app.models.d20_long_sentence import LongSentenceNode
    from app.models.d16_question_domain import PlatformQuestionKp, UploadedQuestionKp, StudentKp

    node = await db.get(KnowledgeNode, node_id)
    if node is None:
        raise AppError(code=404, message="节点不存在")
    kids = (await db.execute(sa.select(sa.func.count()).select_from(KnowledgeNode)
                             .where(KnowledgeNode.parent_id == node_id))).scalar_one()
    if kids:
        raise AppError(code=400, message=f"该节点下还有 {kids} 个子节点,请先删除或移走子节点再删本节点")

    await db.execute(sa.delete(NodeAlias).where(NodeAlias.node_id == node_id))
    await db.execute(sa.delete(NodeRelation).where(
        (NodeRelation.from_node_id == node_id) | (NodeRelation.to_node_id == node_id)))
    await db.execute(sa.delete(UnitNode).where(UnitNode.node_id == node_id))
    await db.execute(sa.delete(VocabNode).where(VocabNode.node_id == node_id))
    await db.execute(sa.delete(LongSentenceNode).where(LongSentenceNode.node_id == node_id))
    await db.execute(sa.delete(PlatformQuestionKp).where(PlatformQuestionKp.node_id == node_id))
    await db.execute(sa.delete(UploadedQuestionKp).where(UploadedQuestionKp.node_id == node_id))
    await db.execute(sa.delete(StudentKp).where(StudentKp.node_id == node_id))
    await db.delete(node)
    await db.flush()
    invalidate_node_tree_cache()
    return {"deleted": str(node_id)}


async def list_children(db: AsyncSession, *, node_id: uuid.UUID) -> list[dict]:
    """某节点的直接子节点(供「编辑子考点」弹框):id/name/code/status/source/child_count。"""
    rows = (await db.execute(
        sa.select(KnowledgeNode.id, KnowledgeNode.name, KnowledgeNode.code,
                  KnowledgeNode.status, KnowledgeNode.source)
        .where(KnowledgeNode.parent_id == node_id)
        .order_by(KnowledgeNode.sort_order, KnowledgeNode.name))).all()
    ids = [r.id for r in rows]
    counts: dict = {}
    if ids:
        cc = (await db.execute(
            sa.select(KnowledgeNode.parent_id, sa.func.count())
            .where(KnowledgeNode.parent_id.in_(ids))
            .group_by(KnowledgeNode.parent_id))).all()
        counts = {pid: n for pid, n in cc}
    return [{"id": str(r.id), "name": r.name, "code": r.code, "status": r.status,
             "source": r.source, "child_count": int(counts.get(r.id, 0))} for r in rows]


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
    invalidate_node_tree_cache()
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
