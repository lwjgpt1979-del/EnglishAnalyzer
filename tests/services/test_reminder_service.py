"""打卡提醒编排测试（D-108）。"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.database import _async_session_factory
from app.models.d5_learning import StudyCheckin
from app.models.d9_system import Notification
from app.services import reminder_service


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _student(s) -> uuid.UUID:
    from app.services.auth_service import upsert_user
    u = await upsert_user(s, openid=f"rem_{uuid.uuid4().hex[:8]}")
    await s.flush()
    return u.id


def _today():
    return datetime.now(timezone.utc).date()


def _add(s, sid, d):
    s.add(StudyCheckin(id=uuid.uuid4(), student_id=sid, checkin_date=d,
                       new_words_count=1, review_done=True, streak_days=1))


@pytest.mark.asyncio
async def test_find_targets(db_session):
    a = await _student(db_session)  # 昨日有、今日无 → 命中
    b = await _student(db_session)  # 今日已打 → 不命中
    c = await _student(db_session)  # 仅前天 → 不命中
    _add(db_session, a, _today() - timedelta(days=1))
    _add(db_session, b, _today() - timedelta(days=1))
    _add(db_session, b, _today())
    _add(db_session, c, _today() - timedelta(days=2))
    await db_session.flush()
    targets = await reminder_service.find_reminder_targets(db_session)
    ids = {t[0] for t in targets}
    assert a in ids
    assert b not in ids
    assert c not in ids


@pytest.mark.asyncio
async def test_run_reminders_emits_notification(db_session):
    a = await _student(db_session)
    _add(db_session, a, _today() - timedelta(days=1))
    await db_session.flush()
    res = await reminder_service.run_checkin_reminders(db_session)
    assert res["notified"] >= 1
    rows = (await db_session.execute(
        select(Notification).where(
            Notification.user_id == a, Notification.type == "checkin_reminder")
    )).scalars().all()
    assert len(rows) == 1 and rows[0].channel == "study"
