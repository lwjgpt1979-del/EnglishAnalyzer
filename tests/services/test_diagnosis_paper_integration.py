"""诊断报告结构化维度（kp_dimension）测试。

R8 KP-First:诊断 kp_dimension 已改按 answer_log.node_id 聚合(diagnosis_service §206),
不再读老 user_paper KP 链(user_paper_question_knowledge_points 表已退役)。原「整卷错题 KP
计入 kp_dimension」及「整卷答对题不计入」两用例依赖已退役的 user_paper KP 链,一并退役;
此处仅保留「无任何练习记录 → kp_dimension 为空」的存活覆盖。
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import _async_session_factory
from app.models.d1_users import User


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


@pytest_asyncio.fixture
async def student_id(db: AsyncSession) -> uuid.UUID:
    """创建真实 User 以满足 FK 约束。"""
    sid = uuid.uuid4()
    db.add(User(id=sid, openid=f"diag_{sid.hex[:8]}", role="student", is_active=True))
    await db.flush()
    return sid


@pytest.mark.asyncio
async def test_diagnosis_kp_dim_no_paper_wrong_returns_empty(db, student_id):
    """没有任何练习记录时 kp_dimension 为空列表。"""
    from app.services.diagnosis_service import _aggregate_structured_dimensions

    kp_dim, _ = await _aggregate_structured_dimensions(db, student_id=student_id)
    assert kp_dim == []
