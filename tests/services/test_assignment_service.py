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


# ─── D-114: 自动判分 + 错题归库 ──────────────────────────────────────

def test_normalize_and_autojudge():
    from app.services.assignment_service import _normalize_answers, _auto_judge
    assert _normalize_answers([{"index": 0, "answer": "A"}, {"index": 1, "answer": "B"}]) == {0: "A", 1: "B"}
    assert _normalize_answers({"0": "A", "1": "B"}) == {0: "A", 1: "B"}
    assert _normalize_answers(["A", "B"]) == {0: "A", 1: "B"}
    qs = [{"stem": "q1", "answer": "A"}, {"stem": "q2", "answer": "B"}]
    score, wrong = _auto_judge(qs, [{"index": 0, "answer": "A"}, {"index": 1, "answer": "X"}])
    assert score == 50.0 and len(wrong) == 1 and wrong[0]["correct_answer"] == "B"
    # 纯主观（无 answer）
    s2, w2 = _auto_judge([{"stem": "写作"}], [{"index": 0, "answer": "..."}])
    assert s2 is None and w2 == []


@pytest.mark.asyncio
async def test_submit_autograde_all_correct(db_session):
    from app.models.d3_wrong_questions import WrongQuestion
    from sqlalchemy import func
    tid = await _teacher(db_session)
    cls, sid = await _class_with_student(db_session, tid)
    a = await assignment_service.create_assignment(
        db_session, teacher_id=tid, class_id=cls.id, title="x",
        questions=[{"stem": "1+1", "answer": "2"}, {"stem": "2+2", "answer": "4"}])
    await assignment_service.publish_assignment(db_session, teacher_id=tid, assignment_id=a.id)
    sub = await assignment_service.submit_assignment(
        db_session, student_id=sid, assignment_id=a.id,
        answers=[{"index": 0, "answer": "2"}, {"index": 1, "answer": "4"}])
    assert float(sub.score) == 100.0
    cnt = (await db_session.execute(
        select(func.count()).select_from(WrongQuestion).where(
            WrongQuestion.student_id == sid,
            WrongQuestion.source_image_url == f"assignment://{a.id}"))).scalar_one()
    assert cnt == 0


@pytest.mark.asyncio
async def test_submit_autograde_wrong_into_wrongbook(db_session):
    from app.models.d3_wrong_questions import WrongQuestion
    from sqlalchemy import func
    tid = await _teacher(db_session)
    cls, sid = await _class_with_student(db_session, tid)
    a = await assignment_service.create_assignment(
        db_session, teacher_id=tid, class_id=cls.id, title="x",
        questions=[{"stem": "1+1", "answer": "2"}, {"stem": "2+2", "answer": "4"}])
    await assignment_service.publish_assignment(db_session, teacher_id=tid, assignment_id=a.id)
    sub = await assignment_service.submit_assignment(
        db_session, student_id=sid, assignment_id=a.id,
        answers=[{"index": 0, "answer": "2"}, {"index": 1, "answer": "5"}])
    assert float(sub.score) == 50.0

    def _wrong_count():
        return db_session.execute(
            select(func.count()).select_from(WrongQuestion).where(
                WrongQuestion.student_id == sid,
                WrongQuestion.source_image_url == f"assignment://{a.id}"))

    assert (await _wrong_count()).scalar_one() == 1
    # 重复提交纠正 → 旧错题清除、score 更新
    await assignment_service.submit_assignment(
        db_session, student_id=sid, assignment_id=a.id,
        answers=[{"index": 0, "answer": "2"}, {"index": 1, "answer": "4"}])
    assert (await _wrong_count()).scalar_one() == 0


@pytest.mark.asyncio
async def test_submit_subjective_no_score(db_session):
    tid = await _teacher(db_session)
    cls, sid = await _class_with_student(db_session, tid)
    a = await assignment_service.create_assignment(
        db_session, teacher_id=tid, class_id=cls.id, title="x",
        questions=[{"stem": "谈谈你的看法"}])  # 无 answer
    await assignment_service.publish_assignment(db_session, teacher_id=tid, assignment_id=a.id)
    sub = await assignment_service.submit_assignment(
        db_session, student_id=sid, assignment_id=a.id, answers=[{"index": 0, "answer": "我的看法..."}])
    assert sub.score is None


# ─── D-115: 作业统计大盘 ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_assignment_stats(db_session):
    from app.models.d7_teacher import ClassStudent
    from app.services.auth_service import upsert_user
    tid = await _teacher(db_session)
    cls, sid1 = await _class_with_student(db_session, tid)
    # 再加 2 个学生（共 3 人）
    s2 = await upsert_user(db_session, openid=f"s_{uuid.uuid4().hex[:8]}"); await db_session.flush()
    s3 = await upsert_user(db_session, openid=f"s_{uuid.uuid4().hex[:8]}"); await db_session.flush()
    db_session.add_all([
        ClassStudent(class_id=cls.id, student_id=s2.id, joined_at=datetime.now(timezone.utc)),
        ClassStudent(class_id=cls.id, student_id=s3.id, joined_at=datetime.now(timezone.utc)),
    ])
    await db_session.flush()
    a = await assignment_service.create_assignment(
        db_session, teacher_id=tid, class_id=cls.id, title="x",
        questions=[{"stem": "1+1", "answer": "2"}, {"stem": "2+2", "answer": "4"}])
    await assignment_service.publish_assignment(db_session, teacher_id=tid, assignment_id=a.id)
    # sid1 全对(100)，s2 一半(50)
    await assignment_service.submit_assignment(db_session, student_id=sid1, assignment_id=a.id,
        answers=[{"index": 0, "answer": "2"}, {"index": 1, "answer": "4"}])
    await assignment_service.submit_assignment(db_session, student_id=s2.id, assignment_id=a.id,
        answers=[{"index": 0, "answer": "2"}, {"index": 1, "answer": "X"}])
    st = await assignment_service.get_assignment_stats(db_session, teacher_id=tid, assignment_id=a.id)
    assert st["total_students"] == 3
    assert st["submitted_count"] == 2
    assert st["completion_rate"] == 0.67
    assert st["avg_score"] == 75.0
    assert st["max_score"] == 100.0 and st["min_score"] == 50.0
    pq = {p["index"]: p for p in st["per_question"]}
    assert pq[0]["correct"] == 2 and pq[0]["total"] == 2 and pq[0]["rate"] == 1.0
    assert pq[1]["correct"] == 1 and pq[1]["rate"] == 0.5


@pytest.mark.asyncio
async def test_assignment_stats_other_teacher_404(db_session):
    other = await _teacher(db_session)
    tid = await _teacher(db_session)
    cls, _ = await _class_with_student(db_session, tid)
    a = await assignment_service.create_assignment(
        db_session, teacher_id=tid, class_id=cls.id, title="x", questions=_Q)
    with pytest.raises(AppError):
        await assignment_service.get_assignment_stats(db_session, teacher_id=other, assignment_id=a.id)
