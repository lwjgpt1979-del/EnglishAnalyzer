"""作文 AI 精修 service 测试（D-109）。"""
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.core.exceptions import AppError
from app.models.d2_payments import Membership
from app.services import essay_service


@pytest.fixture(autouse=True)
def _force_llm_dev_mock(monkeypatch):
    """强制 dev-mock，绝不真打付费 LLM（无论 .env 是否配真实 key）。"""
    monkeypatch.setattr(essay_service, "is_llm_dev_mode", lambda: True)


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _student(s, tier: str | None) -> uuid.UUID:
    from app.services.auth_service import upsert_user
    u = await upsert_user(s, openid=f"essay_{uuid.uuid4().hex[:8]}")
    await s.flush()
    if tier:
        s.add(Membership(id=uuid.uuid4(), user_id=u.id, tier=tier,
                         started_at=datetime.now(timezone.utc), is_active=True))
        await s.flush()
    return u.id


@pytest.mark.asyncio
async def test_polish_pro_devmock(db_session):
    sid = await _student(db_session, "pro")
    essay = await essay_service.polish_essay(
        db_session, student_id=sid, original_text="I am very good at English.", essay_type="话题作文")
    assert str(essay.status) == "completed"
    assert essay.polished_text
    assert len(essay.dimensions["scores"]) == 4
    assert "total" in essay.dimensions
    assert isinstance(essay.dimensions["issues"], list)


@pytest.mark.asyncio
async def test_polish_free_forbidden(db_session):
    sid = await _student(db_session, None)  # 无会员 = free
    with pytest.raises(AppError):
        await essay_service.polish_essay(db_session, student_id=sid, original_text="hello")


@pytest.mark.asyncio
async def test_pro_monthly_limit(db_session):
    sid = await _student(db_session, "pro")
    for _ in range(3):
        await essay_service.polish_essay(db_session, student_id=sid, original_text="essay text")
    with pytest.raises(AppError):
        await essay_service.polish_essay(db_session, student_id=sid, original_text="essay text 4")


@pytest.mark.asyncio
async def test_promax_unlimited(db_session):
    sid = await _student(db_session, "promax")
    for _ in range(5):
        e = await essay_service.polish_essay(db_session, student_id=sid, original_text="essay text")
    assert str(e.status) == "completed"
