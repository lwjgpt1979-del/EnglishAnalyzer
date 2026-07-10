"""adaptive_question_service — 按薄弱知识点智能出题（KP-First）。

R8 KP-First:弱项来源从「错题 AI 分析(knowledge_points)」切到 student_kp(node 掌握台账),
出题走 question_serve_service.serve_by_node(platform 仿真优先→现生成兜底,answer_log 去重)。
原基于 simulated_questions/sim_practice_records/KnowledgePoint 的种子已随退役表一并迁移。
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import _async_session_factory
from app.models.d1_users import User
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import (
    AnswerLog,
    PlatformQuestion,
    PlatformQuestionKp,
    StudentKp,
)


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def force_dev_mode(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-placeholder-for-test")


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _async_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def student(db: AsyncSession) -> User:
    u = User(
        id=uuid.uuid4(),
        openid=f"test_openid_{uuid.uuid4().hex[:8]}",
        nickname="TDD学生",
        role="student",
        is_active=True,
    )
    db.add(u)
    await db.flush()
    return u


async def _make_node(db: AsyncSession, name: str) -> KnowledgeNode:
    node = KnowledgeNode(
        id=uuid.uuid4(),
        axis="knowledge",
        node_kind="句法",
        name=name,
        code=f"TST_{uuid.uuid4().hex[:8]}",
        status="active",
        source="seed",
    )
    db.add(node)
    await db.flush()
    return node


async def _make_weak(db: AsyncSession, student: User, node: KnowledgeNode) -> None:
    """把某 node 记为该生薄弱项(有练习记录、正确率低、在学习范围内)。"""
    db.add(StudentKp(
        student_id=student.id, node_id=node.id,
        practice_count=4, wrong_count=3, in_scope=True,
    ))
    await db.flush()


@pytest_asyncio.fixture
async def kp(db: AsyncSession) -> KnowledgeNode:
    return await _make_node(db, "现在完成时")


@pytest_asyncio.fixture
async def kp2(db: AsyncSession) -> KnowledgeNode:
    return await _make_node(db, "被动语态")


@pytest_asyncio.fixture
async def weak_kp(db: AsyncSession, student: User, kp: KnowledgeNode) -> KnowledgeNode:
    """把 kp 标为薄弱项，让自适应有可出题的弱 node。"""
    await _make_weak(db, student, kp)
    return kp


# ── tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_adaptive_set_returns_questions(
    db: AsyncSession,
    student: User,
    kp: KnowledgeNode,
    weak_kp,
):
    """有薄弱知识点时，应返回至少1道题。"""
    from app.services import adaptive_question_service

    result = await adaptive_question_service.get_adaptive_set(
        db, student_id=student.id, total=5
    )

    assert result.questions, "薄弱点有数据时必须返回题目"
    assert len(result.questions) <= 5
    assert result.weak_kp_names, "必须返回薄弱知识点名称列表"


@pytest.mark.asyncio
async def test_get_adaptive_set_no_data_returns_empty(
    db: AsyncSession,
    student: User,
):
    """没有任何薄弱记录时，返回空题集（不报错）。"""
    from app.services import adaptive_question_service

    result = await adaptive_question_service.get_adaptive_set(
        db, student_id=student.id, total=5
    )

    assert result.questions == []
    assert result.weak_kp_names == []


@pytest.mark.asyncio
async def test_get_adaptive_set_excludes_already_done(
    db: AsyncSession,
    student: User,
    kp: KnowledgeNode,
    weak_kp,
):
    """已做过的题（answer_log 里有记录）不应重复出现。"""
    from app.services import adaptive_question_service

    # 该 node 已发布一道 platform 仿真题
    q_id = uuid.uuid4()
    db.add(PlatformQuestion(
        id=q_id, type="sim", is_fallback=True, status="published",
        question_type="单选", stem="占位题干", options=["A. x", "B. y", "C. z", "D. w"],
        answer="B", explanation="占位解析", difficulty=1,
    ))
    await db.flush()
    db.add(PlatformQuestionKp(question_id=q_id, node_id=kp.id))
    # 记录该生已做过这道题(answer_log 真值)
    db.add(AnswerLog(
        id=uuid.uuid4(), student_id=student.id, q_scope="platform",
        question_id=q_id, is_correct=False, feature="practice", node_id=kp.id,
    ))
    await db.flush()

    result = await adaptive_question_service.get_adaptive_set(
        db, student_id=student.id, total=5
    )
    result_ids = {q.id for q in result.questions}
    assert q_id not in result_ids, "已做过的题不应再次出现"


@pytest.mark.asyncio
async def test_get_adaptive_set_respects_total_limit(
    db: AsyncSession,
    student: User,
    kp: KnowledgeNode,
    kp2: KnowledgeNode,
    weak_kp,
):
    """返回题目数量不超过 total 参数。"""
    from app.services import adaptive_question_service

    # kp2 也标为薄弱项
    await _make_weak(db, student, kp2)

    result = await adaptive_question_service.get_adaptive_set(
        db, student_id=student.id, total=3
    )
    assert len(result.questions) <= 3


# R8 KP-First 已退役 test_to_enum_type_maps_fill_types:
# _to_enum_type 是老「物化 simulated_questions 时的题型枚举映射」辅助,KP-First 出题直接
# 走 platform_question(serve_by_node 统一出单选),不再物化,该辅助已删。
