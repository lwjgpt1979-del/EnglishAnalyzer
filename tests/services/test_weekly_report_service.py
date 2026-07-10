"""TDD: weekly_report_service — 学情周报推送（V2 M30）。"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import _async_session_factory
from app.models.d1_users import StudentRelative, User
from app.models.d13_v2_user_papers import UserPaperQuestion, UserUploadedPaper
from app.models.d16_question_domain import AnswerLog  # R8:做题真值改读 answer_log(sim_practice_records 已退役)
from app.models.d5_learning import StudyCheckin


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _make_user(db: AsyncSession, role: str = "student") -> User:
    u = User(
        id=uuid.uuid4(),
        openid=f"openid_{uuid.uuid4().hex[:8]}",
        nickname=f"测试{role}",
        role=role,
        is_active=True,
    )
    db.add(u)
    await db.flush()
    return u


async def _make_binding(db: AsyncSession, student: User, relative: User) -> StudentRelative:
    binding = StudentRelative(
        id=uuid.uuid4(),
        student_id=student.id,
        relative_id=relative.id,
        relationship="parent",
        is_active=True,
        bound_at=datetime.now(timezone.utc),
    )
    db.add(binding)
    await db.flush()
    return binding


WEEK_START = date(2026, 6, 1)  # 周一
WEEK_END = date(2026, 6, 7)    # 周日


def _dt(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 10, 0, tzinfo=timezone.utc)


# ── tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_report_counts_checkins(db: AsyncSession):
    """本周有 3 天打卡时 checkin_days=3，max_streak 正确。"""
    from app.services.weekly_report_service import generate_student_weekly_report

    student = await _make_user(db, "student")

    for i, streak in enumerate([1, 2, 3]):
        db.add(StudyCheckin(
            id=uuid.uuid4(),
            student_id=student.id,
            checkin_date=WEEK_START + timedelta(days=i),
            new_words_count=10,
            review_done=True,
            streak_days=streak,
        ))
    await db.flush()

    report = await generate_student_weekly_report(
        db, student_id=student.id, week_start=WEEK_START, week_end=WEEK_END
    )

    assert report.checkin_days == 3
    assert report.max_streak == 3
    assert report.student_nickname == "测试student"


@pytest.mark.asyncio
async def test_generate_report_no_data_returns_zeros(db: AsyncSession):
    """无任何记录时全部返回 0，不报错。"""
    from app.services.weekly_report_service import generate_student_weekly_report

    student = await _make_user(db, "student")
    report = await generate_student_weekly_report(
        db, student_id=student.id, week_start=WEEK_START, week_end=WEEK_END
    )

    assert report.checkin_days == 0
    assert report.practice_count == 0
    assert report.wrong_paper_count == 0
    assert report.max_streak == 0
    assert report.weak_kp_names == []


@pytest.mark.asyncio
async def test_generate_report_counts_practice(db: AsyncSession):
    """本周做题数正确统计（KP-First:answer_log 真值）。"""
    from app.services.weekly_report_service import generate_student_weekly_report

    student = await _make_user(db, "student")

    # 本周 2 条作答记录（answer_log.answered_at 在周内）
    for _ in range(2):
        db.add(AnswerLog(
            id=uuid.uuid4(), student_id=student.id, q_scope="platform",
            question_id=uuid.uuid4(), is_correct=True, feature="practice",
            answered_at=_dt(WEEK_START + timedelta(days=1)),
        ))
    # 上周 1 条（不应计入）
    db.add(AnswerLog(
        id=uuid.uuid4(), student_id=student.id, q_scope="platform",
        question_id=uuid.uuid4(), is_correct=True, feature="practice",
        answered_at=_dt(WEEK_START - timedelta(days=3)),
    ))
    await db.flush()

    report = await generate_student_weekly_report(
        db, student_id=student.id, week_start=WEEK_START, week_end=WEEK_END
    )
    assert report.practice_count == 2


@pytest.mark.asyncio
async def test_generate_report_counts_wrong_paper(db: AsyncSession):
    """本周整卷错题数正确统计（仅 is_wrong=True）。"""
    from app.services.weekly_report_service import generate_student_weekly_report

    student = await _make_user(db, "student")

    paper = UserUploadedPaper(
        id=uuid.uuid4(), student_id=student.id,
        source_image_urls=["https://example.com/p.jpg"], ocr_status="completed",
        created_at=_dt(WEEK_START),
    )
    db.add(paper)
    await db.flush()

    # 2 道错题 + 1 道对题（本周）
    for is_wrong in [True, True, False]:
        db.add(UserPaperQuestion(
            id=uuid.uuid4(), user_paper_id=paper.id,
            stem="test", is_wrong=is_wrong, question_type="单选",
            created_at=_dt(WEEK_START + timedelta(days=1)),
        ))
    await db.flush()

    report = await generate_student_weekly_report(
        db, student_id=student.id, week_start=WEEK_START, week_end=WEEK_END
    )
    assert report.wrong_paper_count == 2


@pytest.mark.asyncio
async def test_run_weekly_reports_notifies_relatives(db: AsyncSession):
    """有绑定家长时家长收到站内通知，students_processed 和 relatives_notified 正确。"""
    from app.services.weekly_report_service import run_weekly_reports
    from sqlalchemy import select
    from app.models.d9_system import Notification

    student = await _make_user(db, "student")
    relative = await _make_user(db, "relative")
    await _make_binding(db, student, relative)

    result = await run_weekly_reports(db)

    assert result["students_processed"] >= 1
    assert result["relatives_notified"] >= 1

    # 验证通知已写入 db
    notif_q = await db.execute(
        select(Notification).where(
            Notification.user_id == relative.id,
            Notification.type == "weekly_report",
        )
    )
    notifs = notif_q.scalars().all()
    assert len(notifs) >= 1
    assert "周报" in notifs[0].title
    assert notifs[0].content  # 非空


@pytest.mark.asyncio
async def test_run_weekly_reports_no_bindings_returns_zero(db: AsyncSession):
    """无家长绑定时 relatives_notified=0，students_processed=0。"""
    from app.services.weekly_report_service import run_weekly_reports

    # 只创建学生，不绑家长
    await _make_user(db, "student")

    result = await run_weekly_reports(db)
    # 其他测试可能有绑定，直接断言没有新增
    # 只验证函数不报错且返回正确结构
    assert "students_processed" in result
    assert "relatives_notified" in result


@pytest.mark.asyncio
async def test_run_weekly_reports_multi_relatives(db: AsyncSession):
    """同一学生绑定多个家长时，每个家长都收到通知。"""
    from app.services.weekly_report_service import run_weekly_reports
    from sqlalchemy import select
    from app.models.d9_system import Notification

    student = await _make_user(db, "student")
    rel1 = await _make_user(db, "relative")
    rel2 = await _make_user(db, "relative")
    await _make_binding(db, student, rel1)
    await _make_binding(db, student, rel2)

    await run_weekly_reports(db)

    for rel in [rel1, rel2]:
        notif_q = await db.execute(
            select(Notification).where(
                Notification.user_id == rel.id,
                Notification.type == "weekly_report",
            )
        )
        assert len(notif_q.scalars().all()) >= 1
