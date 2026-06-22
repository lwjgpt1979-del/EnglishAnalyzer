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
    row = await checkin_service._upsert_checkin(db_session, student_id=sid, new_words_count=5, review_done=True)
    assert row.streak_days == 1 and row.new_words_count == 5


@pytest.mark.asyncio
async def test_consecutive_day_streak_increments(db_session):
    sid = await _student(db_session)
    for n in (3, 2, 1):  # today-3, today-2, today-1 真实连续
        db_session.add(StudyCheckin(
            id=uuid.uuid4(), student_id=sid, checkin_date=_today() - timedelta(days=n),
            new_words_count=1, review_done=True, streak_days=0))
    await db_session.flush()
    row = await checkin_service._upsert_checkin(db_session, student_id=sid, new_words_count=2, review_done=True)
    assert row.streak_days == 4


@pytest.mark.asyncio
async def test_broken_streak_resets(db_session):
    sid = await _student(db_session)
    db_session.add(StudyCheckin(
        id=uuid.uuid4(), student_id=sid, checkin_date=_today() - timedelta(days=2),
        new_words_count=1, review_done=True, streak_days=9))
    await db_session.flush()
    row = await checkin_service._upsert_checkin(db_session, student_id=sid, new_words_count=1, review_done=True)
    assert row.streak_days == 1


@pytest.mark.asyncio
async def test_same_day_idempotent(db_session):
    sid = await _student(db_session)
    r1 = await checkin_service._upsert_checkin(db_session, student_id=sid, new_words_count=5, review_done=True)
    r2 = await checkin_service._upsert_checkin(db_session, student_id=sid, new_words_count=8, review_done=True)
    assert r1.id == r2.id and r2.streak_days == 1 and r2.new_words_count == 8


@pytest.mark.asyncio
async def test_status(db_session):
    sid = await _student(db_session)
    for n in range(7, 0, -1):  # today-7 .. today-1 真实连续 7 天
        db_session.add(StudyCheckin(
            id=uuid.uuid4(), student_id=sid, checkin_date=_today() - timedelta(days=n),
            new_words_count=1, review_done=True, streak_days=0))
    await db_session.flush()
    st = await checkin_service.get_checkin_status(db_session, student_id=sid)
    assert st["checked_in_today"] is False
    assert st["current_streak"] == 7
    assert st["longest_streak"] == 7
    await checkin_service._upsert_checkin(db_session, student_id=sid, new_words_count=2, review_done=True)
    st2 = await checkin_service.get_checkin_status(db_session, student_id=sid)
    assert st2["checked_in_today"] is True and st2["current_streak"] == 8 and st2["longest_streak"] == 8


# ─── D-105: record_checkin 严格校验闸门 ──────────────────────────────

async def _seed_words(s, n: int) -> list[uuid.UUID]:
    from app.models.d5_learning import VocabularyWord
    ids = []
    for i in range(n):
        w = VocabularyWord(
            id=uuid.uuid4(), word=f"ckwords_{uuid.uuid4().hex[:6]}",
            phonetic="ˈtest", definitions=[{"pos": "n.", "meaning": f"测试{i}"}],
            examples=None, difficulty=1,
        )
        s.add(w)
        ids.append(w.id)
    await s.flush()
    return ids


@pytest.mark.asyncio
async def test_record_checkin_records_without_quota_gate(db_session):
    """record_checkin 不再按 quota 卡门槛（日历=学习日志）：今日未学满也照记当日。

    progress 仍反映「未完成」(all_done False)，但 record_checkin 现在恒写当日行。
    """
    sid = await _student(db_session)
    await _seed_words(db_session, 10)  # 词库有未学新词、本人今日未学
    row, progress = await checkin_service.record_checkin(db_session, student_id=sid)
    assert progress["all_done"] is False           # 今日确未学满
    assert row is not None                          # 但仍记当日（无门槛闸）
    assert row.new_words_count == 0
    assert await checkin_service._row_for(db_session, sid, _today()) is not None


@pytest.mark.asyncio
async def test_record_checkin_writes_when_complete(db_session):
    """今日学满 free 上限(5)且无到期复习 → 写打卡、streak=1。"""
    from app.models.d5_learning import VocabularyLearning
    sid = await _student(db_session)
    wids = await _seed_words(db_session, 5)
    now = datetime.now(timezone.utc)
    for wid in wids:
        db_session.add(VocabularyLearning(
            id=uuid.uuid4(), student_id=sid, word_id=wid,
            interval_days=1, repetitions=1, easiness_factor=2.5,
            next_review_at=now + timedelta(days=1),
            level="learning", created_at=now,
        ))
    await db_session.flush()
    row, progress = await checkin_service.record_checkin(db_session, student_id=sid)
    assert progress["all_done"] is True
    assert row is not None and row.streak_days == 1
    assert row.new_words_count == 5 and row.review_done is True


# ─── D-106: 当月打卡日历 ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_calendar_two_days_this_month(db_session):
    """当月 2 天打卡 → days 长度 2、checked_count 2、按日期升序。"""
    sid = await _student(db_session)
    t = _today()
    d1 = t.replace(day=1)
    d2 = t.replace(day=2)
    db_session.add_all([
        StudyCheckin(id=uuid.uuid4(), student_id=sid, checkin_date=d1,
                     new_words_count=5, review_done=True, streak_days=1),
        StudyCheckin(id=uuid.uuid4(), student_id=sid, checkin_date=d2,
                     new_words_count=3, review_done=True, streak_days=2),
    ])
    await db_session.flush()
    cal = await checkin_service.get_month_calendar(
        db_session, student_id=sid, year=t.year, month=t.month)
    assert cal["year"] == t.year and cal["month"] == t.month
    assert cal["checked_count"] == 2
    assert [d["date"] for d in cal["days"]] == [d1.isoformat(), d2.isoformat()]
    assert cal["days"][0]["new_words_count"] == 5


@pytest.mark.asyncio
async def test_calendar_excludes_other_months(db_session):
    """上月/下月行不计入当月。"""
    from datetime import date
    sid = await _student(db_session)
    db_session.add_all([
        StudyCheckin(id=uuid.uuid4(), student_id=sid, checkin_date=date(2026, 6, 15),
                     new_words_count=5, review_done=True, streak_days=1),
        StudyCheckin(id=uuid.uuid4(), student_id=sid, checkin_date=date(2026, 5, 31),
                     new_words_count=5, review_done=True, streak_days=1),
        StudyCheckin(id=uuid.uuid4(), student_id=sid, checkin_date=date(2026, 7, 1),
                     new_words_count=5, review_done=True, streak_days=1),
    ])
    await db_session.flush()
    cal = await checkin_service.get_month_calendar(
        db_session, student_id=sid, year=2026, month=6)
    assert cal["checked_count"] == 1
    assert cal["days"][0]["date"] == "2026-06-15"


@pytest.mark.asyncio
async def test_calendar_empty_month(db_session):
    """空月 → days 空、checked_count 0。"""
    sid = await _student(db_session)
    cal = await checkin_service.get_month_calendar(
        db_session, student_id=sid, year=2099, month=1)
    assert cal["days"] == [] and cal["checked_count"] == 0
    assert cal["current_streak"] == 0 and cal["longest_streak"] == 0


# ─── D-107: 动态 streak + 徽章 ────────────────────────────────────────

def test_compute_streaks_pure():
    from datetime import date as _d
    from app.services.checkin_service import _compute_streaks
    today = _d(2026, 6, 10)
    assert _compute_streaks({_d(2026,6,8), _d(2026,6,9), _d(2026,6,10)}, today) == (3, 3)
    assert _compute_streaks({_d(2026,6,8), _d(2026,6,9)}, today) == (2, 2)
    assert _compute_streaks({_d(2026,6,8)}, today) == (0, 1)
    assert _compute_streaks(set(), today) == (0, 0)
    assert _compute_streaks({_d(2026,6,7), _d(2026,6,8), _d(2026,6,9), _d(2026,6,10)}, today) == (4, 4)


def test_badges_thresholds():
    from app.services.checkin_service import _badges
    b0 = _badges(0)
    assert all(x["unlocked"] is False for x in b0)
    b7 = _badges(7)
    assert b7[0]["unlocked"] is True and b7[1]["unlocked"] is False
    b100 = _badges(100)
    assert all(x["unlocked"] is True for x in b100)
    assert [x["level"] for x in b0] == ["bronze", "silver", "gold"]


# ─── D-107: 补签 ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_make_up_restores_streak(db_session):
    """今日已打 + 前日已打、昨日漏 → 补昨日后连续应为 3。"""
    sid = await _student(db_session)
    for n in (2, 0):  # 前天、今天
        db_session.add(StudyCheckin(
            id=uuid.uuid4(), student_id=sid, checkin_date=_today() - timedelta(days=n),
            new_words_count=1, review_done=True, streak_days=0))
    await db_session.flush()
    res = await checkin_service.make_up_checkin(
        db_session, student_id=sid, d=_today() - timedelta(days=1))
    assert res["current_streak"] == 3
    assert res["date"] == (_today() - timedelta(days=1)).isoformat()


@pytest.mark.asyncio
async def test_make_up_already_checked_rejected(db_session):
    from app.core.exceptions import AppError
    sid = await _student(db_session)
    db_session.add(StudyCheckin(
        id=uuid.uuid4(), student_id=sid, checkin_date=_today() - timedelta(days=1),
        new_words_count=1, review_done=True, streak_days=1))
    await db_session.flush()
    with pytest.raises(AppError):
        await checkin_service.make_up_checkin(db_session, student_id=sid, d=_today() - timedelta(days=1))


@pytest.mark.asyncio
async def test_make_up_future_rejected(db_session):
    from app.core.exceptions import AppError
    sid = await _student(db_session)
    with pytest.raises(AppError):
        await checkin_service.make_up_checkin(db_session, student_id=sid, d=_today() + timedelta(days=1))
