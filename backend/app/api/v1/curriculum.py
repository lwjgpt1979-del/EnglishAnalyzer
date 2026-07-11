"""V2 课程浏览 API（D-079 / M2）。"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.services import curriculum_service

router = APIRouter(prefix="/curriculum", tags=["curriculum"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.get("/options")
async def get_preference_options(db: DbDep, current_user: UserDep):
    """学生偏好可选值(教材版本/年级/学期)——后台单一真源,前端不再写死。"""
    return make_ok(await curriculum_service.preference_options(db))


@router.get("/grammar-tree")
async def get_grammar_tree(db: DbDep, current_user: UserDep):
    """个人语法树(教材进度驱动,分组可视):词法/句法 → 二级分类 → 已学/未学项 + 个人自建节点。
    未设年级/学期 → has_progress=false。"""
    from app.services import grammar_progress_service
    return make_ok(await grammar_progress_service.grammar_tree_grouped(db, student_id=current_user.id))


@router.get("/units")
async def list_units(
    db: DbDep,
    current_user: UserDep,
    textbook_version: str = Query(...),
    grade: str = Query(...),
    semester: str = Query(..., description="上 / 下"),
):
    items = await curriculum_service.list_units(
        db,
        user_id=current_user.id,
        textbook_version=textbook_version,
        grade=grade,
        semester=semester,
    )
    return make_ok([i.model_dump(mode="json") for i in items])


@router.get("/units/{unit_id}")
async def get_unit_detail(
    unit_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
):
    detail = await curriculum_service.get_unit_detail(
        db, user_id=current_user.id, unit_id=unit_id,
    )
    return make_ok(detail.model_dump(mode="json"))


@router.get("/knowledge-points/{node_id}/contents")
async def get_kp_contents(
    node_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
):
    """某知识 node 的六维讲解(R8.4:路径 id 即 node_id)。"""
    contents = await curriculum_service.get_kp_contents(
        db, user_id=current_user.id, node_id=node_id,
    )
    return make_ok([c.model_dump(mode="json") for c in contents])


@router.get("/knowledge-points/{node_id}/textbook-sentences")
async def get_textbook_sentences(
    node_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
    unit_id: uuid.UUID | None = Query(None, description="给了则只取该单元的原句；否则取该考点在所有已发布单元的原句"),
):
    """本考点在教材单元原文中抽取的**原始例句**(结构化解析产物 UnitSection.node_id=node → 句子)。
    只取已发布单元(C 端可见性);unit_id 给了则收敛到「本单元」。用于知识点页「看例句」补教材原句。"""
    from sqlalchemy import select as _select
    from app.models.d22_unit_structured import UnitSection, UnitSectionSentence
    from app.models.d4_knowledge import CurriculumUnit

    stmt = (
        _select(UnitSectionSentence.text, UnitSectionSentence.difficulty)
        .join(UnitSection, UnitSection.id == UnitSectionSentence.section_id)
        .join(CurriculumUnit, CurriculumUnit.id == UnitSection.unit_id)
        .where(UnitSection.node_id == node_id, CurriculumUnit.status == "published")
    )
    if unit_id is not None:
        stmt = stmt.where(UnitSection.unit_id == unit_id)
    stmt = stmt.order_by(UnitSection.sort_order, UnitSectionSentence.sort_order)
    rows = (await db.execute(stmt)).all()
    return make_ok([{"text": t, "difficulty": d} for t, d in rows])


@router.get("/knowledge-points/{node_id}/mastery")
async def get_kp_mastery(
    node_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
):
    """当前用户对某知识 node 的掌握(R8.4:读 student_kp,node 维度)。"""
    from sqlalchemy import select as _select
    from app.models.d15_knowledge_graph import KnowledgeNode
    from app.models.d16_question_domain import StudentKp

    node = (await db.execute(
        _select(KnowledgeNode).where(KnowledgeNode.id == node_id)
    )).scalar_one_or_none()
    if node is None:
        return make_ok(None)

    sk = (await db.execute(
        _select(StudentKp).where(
            StudentKp.student_id == current_user.id,
            StudentKp.node_id == node_id,
        )
    )).scalar_one_or_none()

    if sk is None:
        return make_ok({"kp_name": node.name, "correct_count": 0, "wrong_count": 0,
                        "total": 0, "accuracy": None, "mastery": None, "mastery_events": 0,
                        "fa_correct": 0, "fa_wrong": 0, "corrected_count": 0, "redo_wrong_count": 0,
                        "last_activity_at": None})
    from app.services.kp_mastery_service import weighted_mastery, grammar_overrides
    correct = max((sk.practice_count or 0) - (sk.wrong_count or 0), 0)
    total = correct + (sk.wrong_count or 0)
    # 语法类考点掌握度由四维派生(与 g4-card 详情一致);其余用加权口径
    g_over = await grammar_overrides(db, student_id=current_user.id, nodes_with_code=[(node_id, node.code)])
    mastery, events = g_over.get(node_id) or weighted_mastery(
        sk.fa_correct, sk.fa_wrong, sk.corrected_count, sk.redo_wrong_count)
    return make_ok({
        "kp_name": node.name,
        "correct_count": correct,
        "wrong_count": sk.wrong_count or 0,
        "total": total,
        "accuracy": round(correct / total, 4) if total else None,  # 兼容:原始正确率
        "mastery": mastery,             # 加权掌握度 0–1(展示口径)
        "mastery_events": events,       # 事件数 C;< 10 证据不足
        # 掌握度四计数器(供前端「掌握度详情」展开算式)
        "fa_correct": sk.fa_correct or 0,
        "fa_wrong": sk.fa_wrong or 0,
        "corrected_count": sk.corrected_count or 0,
        "redo_wrong_count": sk.redo_wrong_count or 0,
        "last_activity_at": sk.last_practice_at.isoformat() if sk.last_practice_at else None,
    })


@router.get("/units/{unit_id}/mastery-summary")
async def get_unit_mastery_summary(
    unit_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
):
    """该单元每个知识 node 的掌握(R8.4:unit_node → knowledge_nodes,读 student_kp)。"""
    from sqlalchemy import select as _select
    from app.models.d15_knowledge_graph import KnowledgeNode
    from app.models.d16_question_domain import StudentKp
    from app.models.d17_curriculum_kg import UnitNode

    nodes = (await db.execute(
        _select(KnowledgeNode)
        .join(UnitNode, UnitNode.node_id == KnowledgeNode.id)
        .where(UnitNode.unit_id == unit_id)
    )).scalars().all()
    node_ids = [n.id for n in nodes]

    sk_rows = (await db.execute(
        _select(StudentKp).where(
            StudentKp.student_id == current_user.id,
            StudentKp.node_id.in_(node_ids),
        )
    )).scalars().all() if node_ids else []
    sk_map = {sk.node_id: sk for sk in sk_rows}

    from app.services.kp_mastery_service import weighted_mastery, grammar_overrides
    # 语法类考点掌握度由四维派生(与详情一致);其余用加权口径
    g_over = await grammar_overrides(
        db, student_id=current_user.id, nodes_with_code=[(n.id, n.code) for n in nodes])
    result = []
    for n in nodes:
        sk = sk_map.get(n.id)
        correct = max((sk.practice_count or 0) - (sk.wrong_count or 0), 0) if sk else 0
        total = correct + (sk.wrong_count or 0) if sk else 0
        if n.id in g_over:
            mastery, events = g_over[n.id]
        elif sk:
            mastery, events = weighted_mastery(
                sk.fa_correct, sk.fa_wrong, sk.corrected_count, sk.redo_wrong_count)
        else:
            mastery, events = None, 0
        result.append({
            "kp_id": str(n.id),
            "kp_name": n.name,
            "kp_category": str(n.node_kind) if n.node_kind else None,
            "correct_count": correct,
            "wrong_count": (sk.wrong_count or 0) if sk else 0,
            "total": total,
            "accuracy": round(correct / total, 4) if total else None,  # 兼容:原始正确率
            "mastery": mastery,             # 加权掌握度 0–1(展示口径)
            "mastery_events": events,       # 事件数 C;< 10 证据不足
            "last_activity_at": sk.last_practice_at.isoformat() if sk and sk.last_practice_at else None,
        })
    return make_ok(result)


@router.get("/kps/search")
async def search_knowledge_points(
    db: DbDep,
    q: str = Query("", description="搜索关键词（知识点名称模糊匹配）"),
    limit: int = Query(10, ge=1, le=20, description="最多返回条数"),
):
    """按知识 node 名称模糊搜索，供前端选择目标知识点。无需会员。

    R8 Phase5b:改搜 knowledge_nodes(单一真源);category 复用 node_kind。
    """
    from app.schemas.curriculum import KPSearchItem
    nodes = await curriculum_service.search_kps(db, q=q, limit=limit)
    return make_ok([
        KPSearchItem(
            id=n.id,
            name=n.name,
            category=str(n.node_kind or ""),
            description=n.description,
        ).model_dump(mode="json")
        for n in nodes
    ])
