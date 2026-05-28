"""消息中心测试（Module 7B / D-074）。"""
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.schemas.notifications import NotificationOut, NotificationListOut, UnreadCountOut
from app.services.auth_service import upsert_user
from app.services.notification_service import (
    emit,
    emit_analysis_done,
    emit_teacher_comment,
    emit_membership,
    list_notifications,
    unread_count,
    mark_read,
    mark_all_read,
    delete_read,
    _channel_for,
)


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def user(db_session):
    u = await upsert_user(db_session, openid=f"notif_{uuid.uuid4().hex[:8]}")
    await db_session.flush()
    return u


def test_channel_mapping():
    assert _channel_for("analysis_done") == "study"
    assert _channel_for("membership") == "membership"
    assert _channel_for("bind_request") == "relative"
    assert _channel_for("system") == "system"
    assert _channel_for("unknown_xxx") == "system"


def test_notification_out_schema():
    out = NotificationOut(
        id=uuid.uuid4(), type="system", channel="system",
        title="t", content="c", is_read=False, read_at=None,
        created_at=datetime.now(timezone.utc), expires_at=None, meta=None,
    )
    assert out.channel == "system"


@pytest.mark.asyncio
async def test_emit_and_list(db_session, user):
    await emit_analysis_done(db_session, user_id=user.id, wq_id=uuid.uuid4())
    await emit_teacher_comment(db_session, user_id=user.id, wq_id=uuid.uuid4(), teacher_id=uuid.uuid4())
    await db_session.flush()

    items, total, unread = await list_notifications(db_session, user_id=user.id)
    assert total == 2
    assert unread == 2
    assert items[0].meta is not None


@pytest.mark.asyncio
async def test_filter_by_channel(db_session, user):
    await emit_analysis_done(db_session, user_id=user.id, wq_id=uuid.uuid4())
    await emit_membership(db_session, user_id=user.id, title="到期", content="即将到期")
    await db_session.flush()

    items, total, _ = await list_notifications(db_session, user_id=user.id, channel="membership")
    assert total == 1
    assert items[0].channel == "membership"


@pytest.mark.asyncio
async def test_mark_read(db_session, user):
    n = await emit_analysis_done(db_session, user_id=user.id, wq_id=uuid.uuid4())
    await db_session.flush()

    updated = await mark_read(db_session, user_id=user.id, notif_id=n.id)
    assert updated.is_read is True
    assert updated.read_at is not None


@pytest.mark.asyncio
async def test_mark_all_read(db_session, user):
    for _ in range(3):
        await emit_analysis_done(db_session, user_id=user.id, wq_id=uuid.uuid4())
    await db_session.flush()

    affected = await mark_all_read(db_session, user_id=user.id)
    assert affected == 3
    assert await unread_count(db_session, user_id=user.id) == 0


@pytest.mark.asyncio
async def test_delete_read(db_session, user):
    n1 = await emit_analysis_done(db_session, user_id=user.id, wq_id=uuid.uuid4())
    await emit_analysis_done(db_session, user_id=user.id, wq_id=uuid.uuid4())
    await db_session.flush()
    await mark_read(db_session, user_id=user.id, notif_id=n1.id)

    deleted = await delete_read(db_session, user_id=user.id)
    assert deleted == 1
    items, total, _ = await list_notifications(db_session, user_id=user.id)
    assert total == 1


@pytest.mark.asyncio
async def test_emit_membership_with_order(db_session, user):
    oid = uuid.uuid4()
    n = await emit_membership(db_session, user_id=user.id, title="支付成功", content="感谢", order_id=oid)
    await db_session.flush()
    assert n.meta == {"order_id": str(oid)}
    assert n.channel == "membership"
