"""question_service 测试。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.config import settings
from app.core.database import _async_session_factory
from app.models.d3_wrong_questions import WrongQuestion
from app.models.d4_knowledge import KnowledgePoint, WrongQuestionKnowledgePoint
from app.models.d7_teacher import Class, ClassStudent
from app.models.d12_v2_exams import SimExamSession, SimulatedQuestion
from app.services import question_service
from app.services.auth_service import upsert_user


@pytest.fixture(autouse=True)
def force_dev_mode(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-placeholder-for-test")


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


@pytest_asyncio.fixture
async def seeded_kp(db_session):
    kp = KnowledgePoint(
        id=uuid.uuid4(),
        code=f"test-kp-{uuid.uuid4().hex[:6]}",
        name="测试 KP",
        category="grammar",
        description="测试用",
        applicable_grades=["小学5年级"],
        applicable_textbooks=["译林版"],
    )
    db_session.add(kp)
    await db_session.flush()
    return kp


# NOTE: test_persist_* 全部删除 —— persist_questions 已随退役 SimulatedQuestion
# 写入子系统一并移除；下方保留的 list_for_review / review_question 测试改用直插种子。


async def _seed_sim(db_session, kp, *, count=1, status="draft",
                    question_type="单选", dimension=None):
    """直插 SimulatedQuestion（替代已退役的 persist_questions）。返回创建的行列表。"""
    rows = []
    has_opts = question_type in ("单选", "阅读", "完型")
    for i in range(count):
        sq = SimulatedQuestion(
            id=uuid.uuid4(), knowledge_point_id=kp.id,
            question_type=question_type, stem=f"占位题干 {i} {uuid.uuid4().hex[:6]}",
            options=["A. x", "B. y", "C. z", "D. w"] if has_opts else None,
            answer="B", explanation="占位解析", difficulty=1,
            dimension=dimension, status=status,
        )
        db_session.add(sq)
        rows.append(sq)
    await db_session.flush()
    return rows


@pytest.mark.asyncio
async def test_list_for_review_filters_status(db_session, seeded_kp):
    """运营待审列表按 status 过滤；草稿题不出现在 published 列表里。"""
    await _seed_sim(db_session, seeded_kp, count=3, status="draft")
    rows, total = await question_service.list_questions_for_review(
        db_session, status="draft", kp_id=seeded_kp.id,
    )
    assert total == 3 and len(rows) == 3
    rows_pub, total_pub = await question_service.list_questions_for_review(
        db_session, status="published", kp_id=seeded_kp.id,
    )
    assert total_pub == 0 and rows_pub == []


@pytest.mark.asyncio
async def test_review_approve_publishes(db_session, seeded_kp):
    """审核通过 → status=published。"""
    [sq] = await _seed_sim(db_session, seeded_kp, count=1, status="draft")
    reviewed = await question_service.review_question(
        db_session, question_id=sq.id, approve=True,
    )
    assert str(reviewed.status) == "published"


@pytest.mark.asyncio
async def test_review_reject_retires(db_session, seeded_kp):
    """审核驳回 → status=retired。"""
    [sq] = await _seed_sim(db_session, seeded_kp, count=1, status="draft")
    reviewed = await question_service.review_question(
        db_session, question_id=sq.id, approve=False,
    )
    assert str(reviewed.status) == "retired"


@pytest.mark.asyncio
async def test_review_missing_question_raises(db_session):
    """审核不存在的题抛 AppError。"""
    from app.core.exceptions import AppError
    with pytest.raises(AppError):
        await question_service.review_question(
            db_session, question_id=uuid.uuid4(), approve=True,
        )


# NOTE: test_list_filters_by_dimension / test_list_without_dimension_returns_all 已删除
# —— list_questions_by_kp 已随退役 SimulatedQuestion 子系统一并移除。


# NOTE: 判分 / 错题落库 / 掌握回退 相关测试全部删除 —— submit_attempt /
# submit_exam_attempts / _record_wrong / _mark_mastered / _log_attempt 已退役。
# 判分纯函数 _grade 仍在,但已无独立测试(可另建);读函数测试见下。


@pytest.mark.asyncio
async def test_exam_attempts_records_session_history(db_session, seeded_kp):
    """模拟考成绩快照(SimExamSession)可经 get_exam_history 取回。

    原经 submit_exam_attempts 落库(已退役)，改直插 SimExamSession，
    仍覆盖 get_exam_history(存活的读函数)。
    """
    from app.models.d12_v2_exams import SimExamSession

    user = await upsert_user(db_session, openid=f"q_{uuid.uuid4().hex[:6]}")
    await db_session.flush()

    db_session.add(SimExamSession(
        id=uuid.uuid4(), student_id=user.id,
        total=2, correct_count=1, accuracy=0.5,
    ))
    await db_session.flush()

    hist = await question_service.get_exam_history(db_session, user_id=user.id)
    assert hist.total_exams == 1
    assert hist.items[0].total == 2
    assert hist.items[0].correct_count == 1
    assert hist.items[0].accuracy == 0.5


@pytest.mark.asyncio
async def test_exam_history_latest_first(db_session, seeded_kp):
    """两场模拟考，get_exam_history 最新在前(按 created_at 降序)。"""
    from datetime import timedelta

    from app.models.d12_v2_exams import SimExamSession

    user = await upsert_user(db_session, openid=f"q_{uuid.uuid4().hex[:6]}")
    await db_session.flush()

    now = datetime.now(timezone.utc)
    # 第一场答对(accuracy 1.0，较早)，第二场答错(accuracy 0.0，较晚)
    db_session.add(SimExamSession(
        id=uuid.uuid4(), student_id=user.id,
        total=1, correct_count=1, accuracy=1.0, created_at=now - timedelta(minutes=1),
    ))
    db_session.add(SimExamSession(
        id=uuid.uuid4(), student_id=user.id,
        total=1, correct_count=0, accuracy=0.0, created_at=now,
    ))
    await db_session.flush()

    hist = await question_service.get_exam_history(db_session, user_id=user.id)
    assert hist.total_exams == 2
    # 最新（第二场，accuracy 0）在前
    assert hist.items[0].accuracy == 0.0
    assert hist.items[1].accuracy == 1.0


# ─── 学情：知识点正确率聚合（D-085）─────────────────────────────────────────
#
# NOTE: test_wrong_twice_dedups_to_single_row / test_correct_after_wrong_marks_mastered /
# test_rewrong_unmasters / test_attempt_logs_sim_practice_record 已删除
# —— 均直接测退役的 submit_attempt(判分/错题查重/mastered 回退/落 sim_practice_records)。
# 下方 get_kp_accuracy 测试保留，改直插 SimPracticeRecord 造种子。


async def _make_single(db_session, seeded_kp, answer="B"):
    """建一道仿真题（供 SimPracticeRecord 外键引用）。"""
    q = SimulatedQuestion(
        id=uuid.uuid4(), knowledge_point_id=seeded_kp.id,
        question_type="单选", stem=f"KP Q {uuid.uuid4().hex[:6]}",
        options=["A. x", "B. y", "C. z", "D. w"],
        answer=answer, explanation="exp", difficulty=1, status="published",
    )
    db_session.add(q)
    await db_session.flush()
    return q


async def _add_practice_record(db_session, *, user_id, question_id, kp_id, is_correct):
    """直插一行 sim_practice_records（替代退役的 submit_attempt 落库）。"""
    from app.models.d12_v2_exams import SimPracticeRecord
    db_session.add(SimPracticeRecord(
        id=uuid.uuid4(), student_id=user_id, simulated_question_id=question_id,
        knowledge_point_id=kp_id, is_correct=is_correct,
        user_answer="B" if is_correct else "A",
    ))
    await db_session.flush()


@pytest.mark.asyncio
async def test_kp_accuracy_aggregates_rate(db_session, seeded_kp):
    """get_kp_accuracy 按 KP 聚合：3 次作答 2 对 → accuracy=0.6667。"""
    q = await _make_single(db_session, seeded_kp)
    user = await upsert_user(db_session, openid=f"q_{uuid.uuid4().hex[:6]}")
    await db_session.flush()

    for correct in (True, False, True):
        await _add_practice_record(
            db_session, user_id=user.id, question_id=q.id,
            kp_id=seeded_kp.id, is_correct=correct,
        )

    out = await question_service.get_kp_accuracy(db_session, user_id=user.id)
    assert out.total_attempts == 3
    assert out.overall_accuracy == round(2 / 3, 4)
    assert len(out.items) == 1
    item = out.items[0]
    assert item.knowledge_point_id == seeded_kp.id
    assert item.knowledge_point_name == seeded_kp.name
    assert item.attempts == 3
    assert item.correct == 2
    assert item.accuracy == round(2 / 3, 4)


@pytest.mark.asyncio
async def test_kp_accuracy_weakest_first(db_session, seeded_kp):
    """多 KP 时按正确率升序（弱项在前）。"""
    # 第二个 KP
    kp2 = KnowledgePoint(
        id=uuid.uuid4(), code=f"test-kp-{uuid.uuid4().hex[:6]}",
        name="测试 KP 2", category="grammar", description="d",
        applicable_grades=["小学5年级"], applicable_textbooks=["译林版"],
    )
    db_session.add(kp2)
    await db_session.flush()

    q1 = await _make_single(db_session, seeded_kp)   # KP1：全对
    q2 = await _make_single(db_session, kp2)          # KP2：全错
    user = await upsert_user(db_session, openid=f"q_{uuid.uuid4().hex[:6]}")
    await db_session.flush()

    await _add_practice_record(
        db_session, user_id=user.id, question_id=q1.id,
        kp_id=seeded_kp.id, is_correct=True,
    )
    await _add_practice_record(
        db_session, user_id=user.id, question_id=q2.id,
        kp_id=kp2.id, is_correct=False,
    )

    out = await question_service.get_kp_accuracy(db_session, user_id=user.id)
    assert len(out.items) == 2
    # 弱项（KP2 accuracy=0）在前
    assert out.items[0].knowledge_point_id == kp2.id
    assert out.items[0].accuracy == 0.0
    assert out.items[1].knowledge_point_id == seeded_kp.id
    assert out.items[1].accuracy == 1.0


# ─── 班级排名（学生端百分位，D-088）─────────────────────────────────────────

async def _make_class(db_session, *, teacher_id: uuid.UUID, name: str = "测试班级") -> Class:
    cls = Class(id=uuid.uuid4(), teacher_id=teacher_id, name=name)
    db_session.add(cls)
    await db_session.flush()
    return cls


async def _enroll(db_session, *, class_id: uuid.UUID, student_id: uuid.UUID) -> None:
    db_session.add(ClassStudent(
        class_id=class_id, student_id=student_id,
        joined_at=datetime.now(timezone.utc),
    ))
    await db_session.flush()


async def _add_exam_session(db_session, *, student_id: uuid.UUID, accuracy: float) -> None:
    """直接落一行模拟考成绩快照（total/correct_count 仅为占位，排名只看 accuracy）。"""
    db_session.add(SimExamSession(
        id=uuid.uuid4(), student_id=student_id,
        total=10, correct_count=int(round(accuracy * 10)), accuracy=accuracy,
    ))
    await db_session.flush()


@pytest.mark.asyncio
async def test_exam_rank_not_in_class(db_session):
    """不在任何班级 → in_class=False, ranked=False。"""
    user = await upsert_user(db_session, openid=f"rk_{uuid.uuid4().hex[:6]}")
    await db_session.flush()

    out = await question_service.get_exam_rank(db_session, user_id=user.id)
    assert out.in_class is False
    assert out.ranked is False
    assert out.my_rank is None
    assert out.percentile is None


@pytest.mark.asyncio
async def test_exam_rank_in_class_no_exam(db_session):
    """在班级但本人没有模拟考成绩 → in_class=True, ranked=False, 带 class_name。"""
    teacher = await upsert_user(db_session, openid=f"rk_t_{uuid.uuid4().hex[:6]}")
    student = await upsert_user(db_session, openid=f"rk_s_{uuid.uuid4().hex[:6]}")
    await db_session.flush()
    cls = await _make_class(db_session, teacher_id=teacher.id, name="五年级一班")
    await _enroll(db_session, class_id=cls.id, student_id=student.id)

    out = await question_service.get_exam_rank(db_session, user_id=student.id)
    assert out.in_class is True
    assert out.ranked is False
    assert out.class_name == "五年级一班"
    assert out.my_rank is None


@pytest.mark.asyncio
async def test_exam_rank_ranks_by_avg_accuracy(db_session):
    """三人同班，按平均正确率降序排名 + 百分位 + 班级均值（不暴露他人）。"""
    teacher = await upsert_user(db_session, openid=f"rk_t_{uuid.uuid4().hex[:6]}")
    me = await upsert_user(db_session, openid=f"rk_me_{uuid.uuid4().hex[:6]}")
    higher = await upsert_user(db_session, openid=f"rk_hi_{uuid.uuid4().hex[:6]}")
    lower = await upsert_user(db_session, openid=f"rk_lo_{uuid.uuid4().hex[:6]}")
    await db_session.flush()

    cls = await _make_class(db_session, teacher_id=teacher.id)
    for sid in (me.id, higher.id, lower.id):
        await _enroll(db_session, class_id=cls.id, student_id=sid)

    # me：两场 0.4 + 0.6 → 平均 0.5
    await _add_exam_session(db_session, student_id=me.id, accuracy=0.4)
    await _add_exam_session(db_session, student_id=me.id, accuracy=0.6)
    # higher：0.9（高于我）
    await _add_exam_session(db_session, student_id=higher.id, accuracy=0.9)
    # lower：0.3（低于我）
    await _add_exam_session(db_session, student_id=lower.id, accuracy=0.3)

    out = await question_service.get_exam_rank(db_session, user_id=me.id)
    assert out.in_class is True
    assert out.ranked is True
    assert out.total_ranked == 3
    assert out.my_rank == 2  # higher 在我前面
    assert out.my_avg_accuracy == 0.5
    # 班级均值 = (0.5 + 0.9 + 0.3) / 3 = 0.5667
    assert out.class_avg_accuracy == round((0.5 + 0.9 + 0.3) / 3, 4)
    # 百分位：我领先 1 人（lower），排除自己后 2 人里领先 1 → 0.5
    assert out.percentile == 0.5


@pytest.mark.asyncio
async def test_exam_rank_single_ranked_student_null_percentile(db_session):
    """班级里只有本人有模拟考成绩 → rank=1, percentile=None（无可比对象）。"""
    teacher = await upsert_user(db_session, openid=f"rk_t_{uuid.uuid4().hex[:6]}")
    me = await upsert_user(db_session, openid=f"rk_me_{uuid.uuid4().hex[:6]}")
    other = await upsert_user(db_session, openid=f"rk_ot_{uuid.uuid4().hex[:6]}")
    await db_session.flush()

    cls = await _make_class(db_session, teacher_id=teacher.id)
    await _enroll(db_session, class_id=cls.id, student_id=me.id)
    await _enroll(db_session, class_id=cls.id, student_id=other.id)
    # 只有 me 有成绩，other 没考
    await _add_exam_session(db_session, student_id=me.id, accuracy=0.7)

    out = await question_service.get_exam_rank(db_session, user_id=me.id)
    assert out.ranked is True
    assert out.total_ranked == 1
    assert out.my_rank == 1
    assert out.percentile is None
    assert out.my_avg_accuracy == 0.7
