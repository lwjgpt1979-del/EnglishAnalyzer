"""老师出卷 service 测试（D-113）。"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.database import _async_session_factory
from app.core.exceptions import AppError
from app.models.d7_teacher import ClassStudent
from app.models.d9_system import Notification
from app.services import assignment_service, class_service


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _teacher(s) -> uuid.UUID:
    from app.services.auth_service import upsert_user
    u = await upsert_user(s, openid=f"t_{uuid.uuid4().hex[:8]}")
    u.role = "teacher"  # type: ignore[assignment]
    await s.flush()
    return u.id


async def _class_with_student(s, teacher_id):
    cls = await class_service.create_class(s, teacher_id=teacher_id, name="一班")
    from app.services.auth_service import upsert_user
    stu = await upsert_user(s, openid=f"s_{uuid.uuid4().hex[:8]}")
    await s.flush()
    s.add(ClassStudent(class_id=cls.id, student_id=stu.id, joined_at=datetime.now(timezone.utc)))
    await s.flush()
    return cls, stu.id


_Q = [{"stem": "1+1=?", "answer": "2"}]


@pytest.mark.asyncio
async def test_create_assignment_draft(db_session):
    tid = await _teacher(db_session)
    cls, _ = await _class_with_student(db_session, tid)
    a = await assignment_service.create_assignment(
        db_session, teacher_id=tid, class_id=cls.id, title="作业1", questions=_Q)
    assert str(a.status) == "draft" and a.title == "作业1"


@pytest.mark.asyncio
async def test_create_other_class_forbidden(db_session):
    tid = await _teacher(db_session)
    other_tid = await _teacher(db_session)
    cls, _ = await _class_with_student(db_session, other_tid)
    with pytest.raises(AppError):
        await assignment_service.create_assignment(
            db_session, teacher_id=tid, class_id=cls.id, title="x", questions=_Q)


@pytest.mark.asyncio
async def test_publish_notifies_students(db_session):
    tid = await _teacher(db_session)
    cls, sid = await _class_with_student(db_session, tid)
    a = await assignment_service.create_assignment(
        db_session, teacher_id=tid, class_id=cls.id, title="作业1", questions=_Q)
    pub = await assignment_service.publish_assignment(db_session, teacher_id=tid, assignment_id=a.id)
    assert str(pub.status) == "published" and pub.published_at is not None
    n = (await db_session.execute(
        select(Notification).where(Notification.user_id == sid, Notification.type == "assignment")
    )).scalars().all()
    assert len(n) >= 1


@pytest.mark.asyncio
async def test_close_assignment(db_session):
    tid = await _teacher(db_session)
    cls, _ = await _class_with_student(db_session, tid)
    a = await assignment_service.create_assignment(
        db_session, teacher_id=tid, class_id=cls.id, title="x", questions=_Q)
    await assignment_service.publish_assignment(db_session, teacher_id=tid, assignment_id=a.id)
    closed = await assignment_service.close_assignment(db_session, teacher_id=tid, assignment_id=a.id)
    assert str(closed.status) == "closed"


@pytest.mark.asyncio
async def test_grade_submission(db_session):
    tid = await _teacher(db_session)
    cls, sid = await _class_with_student(db_session, tid)
    a = await assignment_service.create_assignment(
        db_session, teacher_id=tid, class_id=cls.id, title="x", questions=_Q)
    await assignment_service.publish_assignment(db_session, teacher_id=tid, assignment_id=a.id)
    sub = await assignment_service.submit_assignment(
        db_session, student_id=sid, assignment_id=a.id, answers=[{"index": 0, "answer": "2"}])
    graded = await assignment_service.grade_submission(
        db_session, teacher_id=tid, submission_id=sub.id, score=95)
    assert float(graded.score) == 95.0


@pytest.mark.asyncio
async def test_grade_other_teacher_forbidden(db_session):
    tid = await _teacher(db_session)
    other = await _teacher(db_session)
    cls, sid = await _class_with_student(db_session, tid)
    a = await assignment_service.create_assignment(
        db_session, teacher_id=tid, class_id=cls.id, title="x", questions=_Q)
    await assignment_service.publish_assignment(db_session, teacher_id=tid, assignment_id=a.id)
    sub = await assignment_service.submit_assignment(
        db_session, student_id=sid, assignment_id=a.id, answers=[])
    with pytest.raises(AppError):
        await assignment_service.grade_submission(
            db_session, teacher_id=other, submission_id=sub.id, score=10)


# ─── 学生端可见性 / 边界 ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_received_visibility(db_session):
    tid = await _teacher(db_session)
    cls, sid = await _class_with_student(db_session, tid)
    # 未发布
    draft = await assignment_service.create_assignment(
        db_session, teacher_id=tid, class_id=cls.id, title="草稿", questions=_Q)
    # 已发布
    pub = await assignment_service.create_assignment(
        db_session, teacher_id=tid, class_id=cls.id, title="已发", questions=_Q)
    await assignment_service.publish_assignment(db_session, teacher_id=tid, assignment_id=pub.id)
    got = await assignment_service.list_received(db_session, student_id=sid)
    ids = {a.id for a, _ in got}
    assert pub.id in ids and draft.id not in ids


@pytest.mark.asyncio
async def test_get_for_student_other_class_forbidden(db_session):
    tid = await _teacher(db_session)
    cls, _ = await _class_with_student(db_session, tid)
    a = await assignment_service.create_assignment(
        db_session, teacher_id=tid, class_id=cls.id, title="x", questions=_Q)
    await assignment_service.publish_assignment(db_session, teacher_id=tid, assignment_id=a.id)
    from app.services.auth_service import upsert_user
    outsider = await upsert_user(db_session, openid=f"out_{uuid.uuid4().hex[:8]}")
    await db_session.flush()
    with pytest.raises(AppError):
        await assignment_service.get_for_student(db_session, student_id=outsider.id, assignment_id=a.id)


@pytest.mark.asyncio
async def test_submit_upsert_and_due(db_session):
    tid = await _teacher(db_session)
    cls, sid = await _class_with_student(db_session, tid)
    a = await assignment_service.create_assignment(
        db_session, teacher_id=tid, class_id=cls.id, title="x", questions=_Q)
    await assignment_service.publish_assignment(db_session, teacher_id=tid, assignment_id=a.id)
    s1 = await assignment_service.submit_assignment(db_session, student_id=sid, assignment_id=a.id, answers=[1])
    s2 = await assignment_service.submit_assignment(db_session, student_id=sid, assignment_id=a.id, answers=[2])
    assert s1.id == s2.id and s2.answers == [2]  # upsert 同行


@pytest.mark.asyncio
async def test_submit_after_due_rejected(db_session):
    tid = await _teacher(db_session)
    cls, sid = await _class_with_student(db_session, tid)
    a = await assignment_service.create_assignment(
        db_session, teacher_id=tid, class_id=cls.id, title="x", questions=_Q,
        due_at=datetime.now(timezone.utc) - timedelta(days=1))
    await assignment_service.publish_assignment(db_session, teacher_id=tid, assignment_id=a.id)
    with pytest.raises(AppError):
        await assignment_service.submit_assignment(db_session, student_id=sid, assignment_id=a.id, answers=[1])
