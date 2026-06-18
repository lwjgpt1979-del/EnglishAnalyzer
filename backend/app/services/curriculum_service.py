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

async def _match_kp_node(db: AsyncSession, kp_name: str | None) -> uuid.UUID | None:
    """旧 KP 名 → 受控匹配新知识 node(use_llm=False,廉价);未命中返回 None(落候选)。"""
    if not kp_name:
        return None
    from app.services.kp_match_service import match_kp
    m = await match_kp(db, raw_name=kp_name, axis_hint="knowledge",
                       source_type="textbook", use_llm=False)
    return m.node_id


async def _stash_pending_content(
    db: AsyncSession, *, kp_name: str, dimension: str, content_md: str,
    source_unit_id: uuid.UUID | None,
) -> None:
    """KP 未命中 node 时暂存讲解(按 kp_name_norm+dimension upsert),候选审核后物化为 lecture。"""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.models.d11_v2_curriculum import PendingKpContent
    from app.services.kp_normalize import normalize_kp_name
    norm = normalize_kp_name(kp_name)
    if not norm:
        return
    await db.execute(
        pg_insert(PendingKpContent)
        .values(id=uuid.uuid4(), kp_name_norm=norm, dimension=dimension,
                content_md=content_md, source_unit_id=source_unit_id, generated_by="ai_full")
        .on_conflict_do_update(
            constraint="uix_pending_kp_dim",
            set_={"content_md": content_md, "source_unit_id": source_unit_id,
                  "updated_at": func.now()},
        )
    )


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

    # 2. knowledge_points + 3. unit_knowledge_points + 4. knowledge_point_contents
    for kp_in in ai_unit.knowledge_points:
        kp_q = await db.execute(
            select(KnowledgePoint).where(KnowledgePoint.code == kp_in.code)
        )
        kp = kp_q.scalar_one_or_none()
        if kp is None:
            kp = KnowledgePoint(
                id=uuid.uuid4(),
                code=kp_in.code,
                name=kp_in.name,
                category=kp_in.category,  # type: ignore[arg-type]
                description=kp_in.description,
                applicable_grades=[ai_unit.grade],
                applicable_textbooks=[ai_unit.textbook_version],
            )
            db.add(kp)
            await db.flush()
        else:
            kp.name = kp_in.name
            kp.description = kp_in.description

        # link
        link_q = await db.execute(
            select(UnitKnowledgePoint).where(
                UnitKnowledgePoint.unit_id == cu.id,
                UnitKnowledgePoint.knowledge_point_id == kp.id,
            )
        )
        if link_q.scalar_one_or_none() is None:
            db.add(UnitKnowledgePoint(unit_id=cu.id, knowledge_point_id=kp.id))

        # contents 多维度 → KP-First 直写 node_resource lecture(挂句法/知识 node);停写旧 knowledge_point_contents。
        # KP 命中 node → 写 lecture;未命中(落候选)→ 暂存 pending_kp_content,候选审核后物化(内容不丢)。
        from app.services import node_resource_service as nrs
        node_id = await _match_kp_node(db, kp.name)
        for dim, md in kp_in.contents.items():
            if dim not in nrs._DIMENSIONS:
                continue  # node_resource lecture 仅六维;dictation 等非教学维跳过
            if node_id is not None:
                await nrs.upsert_lecture(
                    db, node_id=node_id, dimension=dim, content_md=md,
                    generated_by="ai_full", status=content_status,
                )
            else:
                await _stash_pending_content(db, kp_name=kp.name, dimension=dim,
                                             content_md=md, source_unit_id=cu.id)

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
    await db.execute(
        _sa.delete(UnitKnowledgePoint).where(UnitKnowledgePoint.unit_id.in_(unit_ids))
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

    out: list[UnitOut] = []
    for u in units:
        kp_count = len(
            (await db.execute(
                select(UnitKnowledgePoint).where(UnitKnowledgePoint.unit_id == u.id)
            )).scalars().all()
        )
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

    kp_rows = (await db.execute(
        select(KnowledgePoint).join(
            UnitKnowledgePoint,
            UnitKnowledgePoint.knowledge_point_id == KnowledgePoint.id,
        ).where(UnitKnowledgePoint.unit_id == u.id)
        .order_by(KnowledgePoint.sort_order, KnowledgePoint.code)
    )).scalars().all()
    kps = [KnowledgePointOut(
        id=kp.id, code=kp.code, name=kp.name,
        category=str(kp.category), description=kp.description,
    ) for kp in kp_rows]

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
    kp_id: uuid.UUID,
) -> list[KPContentOut]:
    """返回某知识点的 4 维度内容。受其所属单元的锁约束。"""
    cu = (await db.execute(
        select(CurriculumUnit).join(
            UnitKnowledgePoint,
            UnitKnowledgePoint.unit_id == CurriculumUnit.id,
        ).where(UnitKnowledgePoint.knowledge_point_id == kp_id)
        .order_by(CurriculumUnit.unit_no)
    )).scalars().first()
    if cu is None:
        raise AppError(code=404, message="知识点未关联任何单元")

    locked = await is_unit_locked(
        db, user_id=user_id,
        textbook_version=cu.textbook_version, grade=cu.grade,
        semester=str(cu.semester), unit_no=cu.unit_no,
    )
    if locked:
        raise AppError(code=403, message="该知识点所属单元需购买学期会员后解锁")

    # KP-First 直切:讲解读 node_resource(挂新 knowledge_nodes)。旧 kp → 名 → match_kp → node。
    from app.models.d4_knowledge import KnowledgePoint
    from app.models.d19_node_resource import NodeResource

    kp_name = (await db.execute(
        select(KnowledgePoint.name).where(KnowledgePoint.id == kp_id)
    )).scalar_one_or_none()
    node_id = await _match_kp_node(db, kp_name)
    if node_id is None:
        return []
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

    # 每个单元的 KP 数
    kp_counts: dict[uuid.UUID, int] = dict(
        (await db.execute(
            select(UnitKnowledgePoint.unit_id, func.count())
            .where(UnitKnowledgePoint.unit_id.in_(unit_ids))
            .group_by(UnitKnowledgePoint.unit_id)
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
        ))
    return result
