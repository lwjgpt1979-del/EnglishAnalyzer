"""词力通打卡 service 测试（P1 / D-104）。"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.models.d5_learning import StudyCheckin
from app.services import checkin_service


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _student(s) -> uuid.UUID:
    from app.services.auth_service import upsert_user
    u = await upsert_user(s, openid=f"checkin_{uuid.uuid4().hex[:8]}")
    await s.flush()
    return u.id


def _today():
    return datetime.now(timezone.utc).date()


@pytest.mark.asyncio
async def test_first_checkin_streak_1(db_session):
    sid = await _student(db_session)
    row = await checkin_service.record_checkin(db_session, student_id=sid, new_words_count=5, review_done=True)
    assert row.streak_days == 1 and row.new_words_count == 5


@pytest.mark.asyncio
async def test_consecutive_day_streak_increments(db_session):
    sid = await _student(db_session)
    db_session.add(StudyCheckin(
        id=uuid.uuid4(), student_id=sid, checkin_date=_today() - timedelta(days=1),
        new_words_count=3, review_done=True, streak_days=3))
    await db_session.flush()
    row = await checkin_service.record_checkin(db_session, student_id=sid, new_words_count=2, review_done=True)
    assert row.streak_days == 4


@pytest.mark.asyncio
async def test_broken_streak_resets(db_session):
    sid = await _student(db_session)
    db_session.add(StudyCheckin(
        id=uuid.uuid4(), student_id=sid, checkin_date=_today() - timedelta(days=2),
        new_words_count=1, review_done=True, streak_days=9))
    await db_session.flush()
    row = await checkin_service.record_checkin(db_session, student_id=sid, new_words_count=1, review_done=True)
    assert row.streak_days == 1


@pytest.mark.asyncio
async def test_same_day_idempotent(db_session):
    sid = await _student(db_session)
    r1 = await checkin_service.record_checkin(db_session, student_id=sid, new_words_count=5, review_done=True)
    r2 = await checkin_service.record_checkin(db_session, student_id=sid, new_words_count=8, review_done=True)
    assert r1.id == r2.id and r2.streak_days == 1 and r2.new_words_count == 8


@pytest.mark.asyncio
async def test_status(db_session):
    sid = await _student(db_session)
    db_session.add(StudyCheckin(
        id=uuid.uuid4(), student_id=sid, checkin_date=_today() - timedelta(days=1),
        new_words_count=1, review_done=True, streak_days=7))
    await db_session.flush()
    st = await checkin_service.get_checkin_status(db_session, student_id=sid)
    assert st["checked_in_today"] is False
    assert st["current_streak"] == 7
    assert st["longest_streak"] == 7
    await checkin_service.record_checkin(db_session, student_id=sid, new_words_count=2, review_done=True)
    st2 = await checkin_service.get_checkin_status(db_session, student_id=sid)
    assert st2["checked_in_today"] is True and st2["current_streak"] == 8 and st2["longest_streak"] == 8
