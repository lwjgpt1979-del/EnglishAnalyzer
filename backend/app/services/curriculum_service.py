"""V2 课程浏览 service（D-079 / M2）。

职责：
1. persist_unit() — 把 curriculum_ai_service 输出 upsert 入 6 张表（幂等）
2. is_unit_locked() — unit_no=1 永远免费，其余按 PurchasedSemester 判断
3. list_units / get_unit_detail / get_kp_contents — 给 API 用的 read 函数
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d4_knowledge import (
    CurriculumUnit,
    KnowledgePoint,
    UnitKnowledgePoint,
    CurriculumWord,
)
from app.models.d5_learning import VocabularyWord
from app.models.d11_v2_curriculum import KnowledgePointContent
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

async def persist_unit(db: AsyncSession, *, ai_unit: AIGeneratedUnit) -> CurriculumUnit:
    """把 AI 生成的单元结构 upsert 入 6 张表，返回 CurriculumUnit。幂等。"""
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

        # contents 4 维度
        for dim, md in kp_in.contents.items():
            c_q = await db.execute(
                select(KnowledgePointContent).where(
                    KnowledgePointContent.knowledge_point_id == kp.id,
                    KnowledgePointContent.dimension == dim,
                )
            )
            kpc = c_q.scalar_one_or_none()
            if kpc is None:
                db.add(KnowledgePointContent(
                    id=uuid.uuid4(),
                    knowledge_point_id=kp.id,
                    dimension=dim,  # type: ignore[arg-type]
                    content_md=md,
                    status="published",
                    generated_by="ai_full",
                ))
            else:
                kpc.content_md = md

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

    contents = (await db.execute(
        select(KnowledgePointContent).where(
            KnowledgePointContent.knowledge_point_id == kp_id,
        )
    )).scalars().all()
    return [KPContentOut(
        dimension=str(c.dimension),
        content_md=c.content_md,
        audio_url=c.audio_url,
    ) for c in contents]
