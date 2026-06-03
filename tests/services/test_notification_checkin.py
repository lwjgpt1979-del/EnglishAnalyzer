"""打卡提醒站内消息测试（D-108）。"""
import uuid

import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.services import notification_service


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _student(s) -> uuid.UUID:
    from app.services.auth_service import upsert_user
    u = await upsert_user(s, openid=f"notif_{uuid.uuid4().hex[:8]}")
    await s.flush()
    return u.id


@pytest.mark.asyncio
async def test_emit_checkin_reminder(db_session):
    sid = await _student(db_session)
    n = await notification_service.emit_checkin_reminder(
        db_session, user_id=sid, streak_days=5)
    assert str(n.type) == "checkin_reminder"
    assert n.channel == "study"
    assert "5" in n.content
