"""V2 课程浏览 service（D-079 / M2）。

职责：
1. persist_unit() — 把 curriculum_ai_service 输出 upsert 入 6 张表（幂等）
2. is_unit_locked() — unit_no=1 永远免费，其余按 PurchasedSemester 判断
3. list_units / get_unit_detail / get_kp_contents — 给 API 用的 read 函数
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d4_knowledge import (
    CurriculumUnit,
    CurriculumUnitPassage,
    KnowledgePoint,
    UnitKnowledgePoint,
    CurriculumWord,
)
from app.models.d5_learning import VocabularyWord
from app.schemas.curriculum import (
    AIGeneratedUnit,
    KnowledgePointOut,
    KPContentOut,
    UnitDetailOut,
    UnitOut,
    WordOut,
)
from app.services import semester_service


# ─── Persist ────────────────────────────────────────────────────────────────

async def _park_pending_content(
    db: AsyncSession, *, norm: str, dimension: str, content_md: str, unit_id: uuid.UUID,
) -> None:
    """E2:未命中树上节点时,把该 KP 名某维讲解暂存(按 norm+dim 覆盖),
    待人工把候选挂到树上后 _materialize_pending_content 物化为 node_resource。"""
    from app.models.d11_v2_curriculum import PendingKpContent
    existing = (await db.execute(
        select(PendingKpContent).where(
            PendingKpContent.kp_name_norm == norm,
            PendingKpContent.dimension == dimension)
    )).scalar_one_or_none()
    if existing is not None:
        existing.content_md = content_md
        existing.source_unit_id = unit_id
    else:
        db.add(PendingKpContent(
            id=uuid.uuid4(), kp_name_norm=norm, dimension=dimension,
            content_md=content_md, source_unit_id=unit_id, generated_by="ai_full"))
    await db.flush()


async def persist_unit_passages(db: AsyncSession, *, unit_id: uuid.UUID, passages: list) -> int:
    """落库单元析出的短文(听力/阅读/写作)。整体覆盖该单元的旧短文(重生成幂等)。"""
    from sqlalchemy import delete
    await db.execute(delete(CurriculumUnitPassage).where(CurriculumUnitPassage.unit_id == unit_id))
    n = 0
    for i, p in enumerate(passages):
        text = (getattr(p, "text", "") or "").strip()
        if not text:
            continue
        db.add(CurriculumUnitPassage(
            id=uuid.uuid4(), unit_id=unit_id, kind=p.kind,
            title=(getattr(p, "title", None) or None), text=text, sort_order=i))
        n += 1
    await db.flush()
    return n


async def textbook_word_stats(db: AsyncSession, *, textbook: str | None = None,
                              grade: str | None = None, top: int = 200) -> dict:
    """教材高频词统计:某教材版+年级下,每个词出现在多少个单元(出现单元数=教材内词频)。

    返回 {totals:{词数,高频词数(≥2单元),最高出现单元数}, items:[{word,unit_count,gloss,star}], options}。
    """
    import sqlalchemy as _sa
    from app.models.d5_learning import VocabularyWord
    uq = _sa.select(CurriculumUnit.id)
    if textbook:
        uq = uq.where(CurriculumUnit.textbook_version == textbook)
    if grade:
        uq = uq.where(CurriculumUnit.grade == grade)
    rows = (await db.execute(
        _sa.select(CurriculumWord.word_id, _sa.func.count(_sa.distinct(CurriculumWord.unit_id)))
        .where(CurriculumWord.unit_id.in_(uq))
        .group_by(CurriculumWord.word_id))).all()
    wc = {wid: int(c) for wid, c in rows}
    # 选项:教材版/年级(取有词的)
    opt_rows = (await db.execute(
        _sa.select(CurriculumUnit.textbook_version, CurriculumUnit.grade).distinct()
        .where(CurriculumUnit.id.in_(_sa.select(CurriculumWord.unit_id).distinct())))).all()
    options = {
        "textbooks": sorted({t for t, _g in opt_rows}),
        "grades": sorted({g for _t, g in opt_rows}),
    }
    if not wc:
        return {"totals": {"words": 0, "high_freq": 0, "max_units": 0}, "items": [], "options": options}
    info = (await db.execute(_sa.select(
        VocabularyWord.id, VocabularyWord.word, VocabularyWord.definitions, VocabularyWord.star)
        .where(VocabularyWord.id.in_(list(wc))))).all()

    def _gloss(defs) -> str:
        if isinstance(defs, list) and defs:
            d0 = defs[0]
            if isinstance(d0, dict):
                return f"{d0.get('pos', '')} {d0.get('meaning', '')}".strip()
        return ""

    items = [{"word": w, "unit_count": wc.get(wid, 0), "gloss": _gloss(defs), "star": int(star or 0)}
             for wid, w, defs, star in info]
    items.sort(key=lambda x: (-x["unit_count"], x["word"].lower()))
    totals = {"words": len(items),
              "high_freq": sum(1 for it in items if it["unit_count"] >= 2),
              "max_units": max((it["unit_count"] for it in items), default=0)}
    return {"totals": totals, "items": items[:top], "options": options}


async def persist_unit(
    db: AsyncSession,
    *,
    ai_unit: AIGeneratedUnit,
    content_status: str = "draft",
) -> CurriculumUnit:
    """把 AI 生成的单元结构 upsert 入 6 张表，返回 CurriculumUnit。幂等。

    content_status 默认 "draft"（M5 审核闸门）：新生成的知识点内容先进草稿，
    需运营审核后才对学生可见；seed 脚本 / 可信内容可显式传 "published"。
    """
    # 1. curriculum_units（按 textbook+grade+semester+unit_no 唯一）
    cu_q = await db.execute(
        select(CurriculumUnit).where(
            CurriculumUnit.textbook_version == ai_unit.textbook_version,
            CurriculumUnit.grade == ai_unit.grade,
            CurriculumUnit.semester == ai_unit.semester,
            CurriculumUnit.unit_no == ai_unit.unit_no,
        )
    )
    cu = cu_q.scalar_one_or_none()
    if cu is None:
        cu = CurriculumUnit(
            id=uuid.uuid4(),
            textbook_version=ai_unit.textbook_version,
            grade=ai_unit.grade,
            semester=ai_unit.semester,  # type: ignore[arg-type]
            unit_no=ai_unit.unit_no,
            unit_title=ai_unit.unit_title,
        )
        db.add(cu)
        await db.flush()
    else:
        cu.unit_title = ai_unit.unit_title

    # 2. 知识点 → E2 受控映射:AI 知识点名 match_kp 到受控树上的既有节点。
    #    命中 → 建 unit_node 边 + 版本化挂讲解;未命中 → 落候选(附 unit 来源)+ 暂存六维内容,
    #    待人工把候选挂到树上后物化。**不再自建节点**(知识点骨架由后台受控树定义)。
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.models.d17_curriculum_kg import UnitNode
    from app.services import node_resource_service as nrs
    from app.services import curriculum_kp_service as ckp
    from app.services.kp_match_service import match_kp
    from app.services.kp_normalize import stages_from_grades, normalize_kp_name
    stages = stages_from_grades([ai_unit.grade])
    stage = stages[0] if stages else None
    for kp_in in ai_unit.knowledge_points:
        if not kp_in.name or not kp_in.name.strip():
            continue
        dims = [(d, md) for d, md in kp_in.contents.items() if d in nrs._DIMENSIONS]
        r = await match_kp(
            db, raw_name=kp_in.name, axis_hint="knowledge", stage_hint=stage,
            source_type="textbook", source_ref={"unit_ids": [str(cu.id)]})
        if r.node_id is not None:                       # 命中受控树节点 → 挂内容 + 建边
            await db.execute(
                pg_insert(UnitNode)
                .values(unit_id=cu.id, node_id=r.node_id, source="ai_extract")
                .on_conflict_do_nothing(index_elements=["unit_id", "node_id"]))
            for dim, md in dims:
                await nrs.submit_lecture_version(
                    db, node_id=r.node_id, dimension=dim, content_md=md,
                    source="ai_full", status_if_new=content_status,
                    origin_ref={"flow": "generate", "unit_id": str(cu.id)})
        elif r.candidate_id is not None:                # 未命中 → 候选 + 暂存内容,待人工挂树
            await ckp._attach_unit_to_candidate(db, r.candidate_id, cu.id)
            norm = normalize_kp_name(kp_in.name)
            for dim, md in dims:
                await _park_pending_content(db, norm=norm, dimension=dim, content_md=md, unit_id=cu.id)

    # 5. vocabulary_words + 6. curriculum_words
    for w_in in ai_unit.words:
        w_q = await db.execute(
            select(VocabularyWord).where(VocabularyWord.word == w_in.word)
        )
        w = w_q.scalar_one_or_none()
        if w is None:
            w = VocabularyWord(
                id=uuid.uuid4(),
                word=w_in.word,
                phonetic=w_in.phonetic,
                definitions=w_in.definitions,
                examples=w_in.examples,
                difficulty=w_in.difficulty,
            )
            db.add(w)
            await db.flush()

        cw_q = await db.execute(
            select(CurriculumWord).where(
                CurriculumWord.unit_id == cu.id,
                CurriculumWord.word_id == w.id,
            )
        )
        if cw_q.scalar_one_or_none() is None:
            db.add(CurriculumWord(
                unit_id=cu.id,
                word_id=w.id,
                is_core=w_in.is_core,
            ))

    return cu


# ─── Admin：批量生成 ────────────────────────────────────────────────────────

async def reset_semester(
    db: AsyncSession,
    *,
    textbook_version: str,
    grade: str,
    semester: str,
) -> int:
    """删除指定学期的所有单元（按 FK 顺序先删子表再删主表）。

    返回删除的单元数。用于重新生成前清场。
    """
    import sqlalchemy as _sa
    from app.models.d4_knowledge import CurriculumWord

    # 先查出目标单元 ID
    rows = list((await db.execute(
        select(CurriculumUnit).where(
            CurriculumUnit.textbook_version == textbook_version,
            CurriculumUnit.grade == grade,
            CurriculumUnit.semester == semester,
        )
    )).scalars().all())
    if not rows:
        return 0

    unit_ids = [cu.id for cu in rows]

    # 按 FK 顺序删子表，再删主表（避免 FK violation）
    from app.models.d4_knowledge import UnitKnowledgePoint
    from app.models.d17_curriculum_kg import UnitNode
    await db.execute(
        _sa.delete(UnitNode).where(UnitNode.unit_id.in_(unit_ids))   # R8.4:单元↔node 边
    )
    await db.execute(
        _sa.delete(UnitKnowledgePoint).where(UnitKnowledgePoint.unit_id.in_(unit_ids))  # 旧桥(兼容)
    )
    await db.execute(
        _sa.delete(CurriculumWord).where(CurriculumWord.unit_id.in_(unit_ids))
    )
    await db.execute(
        _sa.delete(CurriculumUnit).where(CurriculumUnit.id.in_(unit_ids))
    )
    await db.flush()
    return len(rows)


async def generate_semester(
    db: AsyncSession,
    *,
    textbook_version: str,
    grade: str,
    semester: str,
    unit_count: int = 6,
    content_status: str = "published",
    reset: bool = True,
) -> list[dict]:
    """清场后用真实 AI 生成指定学期全部单元（M2）。

    返回逐单元结果列表：[{unit_no, unit_title, kp_count, status}, ...]
    content_status="published" 让内容立即对学生可见（管理员已做质量担保）。
    """
    from app.services import curriculum_ai_service

    if reset:
        deleted = await reset_semester(
            db, textbook_version=textbook_version, grade=grade, semester=semester,
        )

    results = []
    for unit_no in range(1, unit_count + 1):
        ai_unit = await curriculum_ai_service.generate_unit(
            textbook_version=textbook_version,
            grade=grade,
            semester=semester,
            unit_no=unit_no,
        )
        cu = await persist_unit(db, ai_unit=ai_unit, content_status=content_status)
        await db.flush()
        # R1:生成后自动对齐知识图谱(防御式,失败不阻断生成)
        from app.services import curriculum_kp_service
        await curriculum_kp_service.extract_for_ai_unit(db, unit_id=cu.id, ai_unit=ai_unit)
        results.append({
            "unit_no": unit_no,
            "unit_title": ai_unit.unit_title,
            "kp_count": len(ai_unit.knowledge_points),
            "word_count": len(ai_unit.words),
            "status": "ok",
        })

    return results


# ─── Paywall ────────────────────────────────────────────────────────────────

async def is_unit_locked(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    textbook_version: str,
    grade: str,
    semester: str,
    unit_no: int,
) -> bool:
    """unit_no=1 永远免费；其余按 PurchasedSemester 判断。"""
    if unit_no == 1:
        return False
    ok, _, _ = await semester_service.query_access(
        db, user_id=user_id,
        textbook_version=textbook_version, grade=grade, semester=semester,
    )
    return not ok


# ─── Read APIs ──────────────────────────────────────────────────────────────

async def list_units(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    textbook_version: str,
    grade: str,
    semester: str,
) -> list[UnitOut]:
    r = await db.execute(
        select(CurriculumUnit).where(
            CurriculumUnit.textbook_version == textbook_version,
            CurriculumUnit.grade == grade,
            CurriculumUnit.semester == semester,
        ).order_by(CurriculumUnit.unit_no)
    )
    units = list(r.scalars().all())

    from app.models.d17_curriculum_kg import UnitNode
    out: list[UnitOut] = []
    for u in units:
        kp_count = (await db.execute(
            select(func.count()).select_from(UnitNode).where(UnitNode.unit_id == u.id)
        )).scalar_one()
        locked = await is_unit_locked(
            db, user_id=user_id,
            textbook_version=textbook_version, grade=grade, semester=semester,
            unit_no=u.unit_no,
        )
        out.append(UnitOut(
            id=u.id,
            textbook_version=u.textbook_version,
            grade=u.grade,
            semester=str(u.semester),
            unit_no=u.unit_no,
            unit_title=u.unit_title,
            locked=locked,
            kp_count=kp_count,
        ))
    return out


async def get_unit_detail(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    unit_id: uuid.UUID,
) -> UnitDetailOut:
    u = (await db.execute(
        select(CurriculumUnit).where(CurriculumUnit.id == unit_id)
    )).scalar_one_or_none()
    if u is None:
        raise AppError(code=404, message="单元不存在")

    locked = await is_unit_locked(
        db, user_id=user_id,
        textbook_version=u.textbook_version, grade=u.grade, semester=str(u.semester),
        unit_no=u.unit_no,
    )
    if locked:
        raise AppError(code=403, message="该单元需购买学期会员后解锁")

    # R8.4:知识点来自 unit_node → knowledge_nodes(id 即 node_id),不再读旧 knowledge_points
    from app.models.d15_knowledge_graph import KnowledgeNode
    from app.models.d17_curriculum_kg import UnitNode
    node_rows = (await db.execute(
        select(KnowledgeNode).join(UnitNode, UnitNode.node_id == KnowledgeNode.id)
        .where(UnitNode.unit_id == u.id)
        .order_by(KnowledgeNode.sort_order, KnowledgeNode.code)
    )).scalars().all()
    kps = [KnowledgePointOut(
        id=n.id, code=n.code, name=n.name,
        category=str(n.node_kind or ""), description=n.description,
    ) for n in node_rows]

    w_rows = (await db.execute(
        select(VocabularyWord).join(
            CurriculumWord, CurriculumWord.word_id == VocabularyWord.id,
        ).where(CurriculumWord.unit_id == u.id)
        .order_by(CurriculumWord.sort_order, VocabularyWord.word)
    )).scalars().all()
    words = [WordOut(
        id=w.id, word=w.word, phonetic=w.phonetic,
        definitions=w.definitions or [], difficulty=w.difficulty,
    ) for w in w_rows]

    return UnitDetailOut(
        id=u.id,
        textbook_version=u.textbook_version,
        grade=u.grade,
        semester=str(u.semester),
        unit_no=u.unit_no,
        unit_title=u.unit_title,
        locked=False,
        kp_count=len(kps),
        knowledge_points=kps,
        words=words,
    )


async def get_kp_contents(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    node_id: uuid.UUID,
) -> list[KPContentOut]:
    """返回某知识 node 的六维讲解(R8.4:入参为 node_id)。受其所属单元的锁约束。"""
    from app.models.d17_curriculum_kg import UnitNode
    from app.models.d19_node_resource import NodeResource

    cu = (await db.execute(
        select(CurriculumUnit).join(
            UnitNode, UnitNode.unit_id == CurriculumUnit.id,
        ).where(UnitNode.node_id == node_id)
        .order_by(CurriculumUnit.unit_no)
    )).scalars().first()
    if cu is not None:
        locked = await is_unit_locked(
            db, user_id=user_id,
            textbook_version=cu.textbook_version, grade=cu.grade,
            semester=str(cu.semester), unit_no=cu.unit_no,
        )
        if locked:
            raise AppError(code=403, message="该知识点所属单元需购买学期会员后解锁")

    contents = (await db.execute(
        select(NodeResource).where(
            NodeResource.node_id == node_id,
            NodeResource.resource_type == "lecture",
            NodeResource.status == "published",
        )
    )).scalars().all()
    return [KPContentOut(
        dimension=str(c.dimension or ""),
        content_md=c.content_md or "",
        audio_url=c.media_url,
    ) for c in contents]


# ─── 运营审核/编辑 ──────────────────────────────────────────────────────────────
# 旧 knowledge_point_contents 内容审核已退役:内容生成直写 node_resource(lecture),
# 审核统一走 NodeResources 后台页(node_resource_service.list_for_review/review)。


async def search_kps(
    db: AsyncSession,
    *,
    q: str,
    limit: int = 10,
) -> list[KnowledgePoint]:
    """按名称模糊搜索知识点（ILIKE）。q 为空则不过滤，返回前 limit 条。"""
    stmt = select(KnowledgePoint).order_by(KnowledgePoint.name)
    if q:
        stmt = stmt.where(KnowledgePoint.name.ilike(f"%{q}%"))
    stmt = stmt.limit(limit)
    return list((await db.execute(stmt)).scalars().all())


@dataclass
class UnitContentStat:
    """单个课程单元的内容完成度统计。"""
    unit_id: uuid.UUID
    textbook_version: str
    grade: str
    semester: str
    unit_no: int
    unit_title: str
    kp_count: int
    content_count: int
    content_rate: float   # content_count / (kp_count * 6)，0-1
    unit_pdf_url: str | None = None   # 拆出的单元独立 PDF(COS)


async def list_units_with_stats(db: AsyncSession) -> list[UnitContentStat]:
    """列出所有课程单元及内容完成度，供 Admin 课程管理页使用。"""
    units = (await db.execute(
        select(CurriculumUnit).order_by(
            CurriculumUnit.textbook_version,
            CurriculumUnit.grade,
            CurriculumUnit.semester,
            CurriculumUnit.unit_no,
        )
    )).scalars().all()

    if not units:
        return []

    unit_ids = [u.id for u in units]

    # 每个单元的 KP 数(R8.4:unit_node 边)
    from app.models.d17_curriculum_kg import UnitNode as _UN
    kp_counts: dict[uuid.UUID, int] = dict(
        (await db.execute(
            select(_UN.unit_id, func.count())
            .where(_UN.unit_id.in_(unit_ids))
            .group_by(_UN.unit_id)
        )).all()
    )

    # 每个单元的讲解内容数:KP-First 经 unit_node → node 的 node_resource lecture(左连接,无则 0)
    from app.models.d17_curriculum_kg import UnitNode
    from app.models.d19_node_resource import NodeResource
    content_rows = (await db.execute(
        select(UnitNode.unit_id, func.count(NodeResource.id))
        .join(
            NodeResource,
            (NodeResource.node_id == UnitNode.node_id)
            & (NodeResource.resource_type == "lecture"),
            isouter=True,
        )
        .where(UnitNode.unit_id.in_(unit_ids))
        .group_by(UnitNode.unit_id)
    )).all()
    content_counts: dict[uuid.UUID, int] = dict(content_rows)

    result: list[UnitContentStat] = []
    for u in units:
        kc = kp_counts.get(u.id, 0)
        cc = content_counts.get(u.id, 0)
        rate = round(cc / (kc * 6), 4) if kc > 0 else 0.0
        result.append(UnitContentStat(
            unit_id=u.id,
            textbook_version=u.textbook_version,
            grade=str(u.grade),
            semester=str(u.semester),
            unit_no=u.unit_no,
            unit_title=u.unit_title or "",
            kp_count=kc,
            content_count=cc,
            content_rate=min(rate, 1.0),
            unit_pdf_url=u.unit_pdf_url,
        ))
    return result
