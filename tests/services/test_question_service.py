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
from app.services import question_ai_service, question_service
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


@pytest.mark.asyncio
async def test_persist_questions_creates_5_rows(db_session, seeded_kp):
    qs = await question_ai_service.generate_questions(
        kp_name=seeded_kp.name, kp_category="grammar", kp_description="d", count=5,
    )
    created = await question_service.persist_questions(
        db_session, kp_id=seeded_kp.id, questions=qs,
    )
    await db_session.flush()
    assert len(created) == 5

    rows = (await db_session.execute(
        select(SimulatedQuestion).where(SimulatedQuestion.knowledge_point_id == seeded_kp.id)
    )).scalars().all()
    assert len(rows) >= 5


@pytest.mark.asyncio
async def test_persist_idempotent(db_session, seeded_kp):
    qs = await question_ai_service.generate_questions(
        kp_name=seeded_kp.name, kp_category="grammar", kp_description="d", count=5,
    )
    await question_service.persist_questions(db_session, kp_id=seeded_kp.id, questions=qs)
    await db_session.flush()
    cnt1 = len((await db_session.execute(
        select(SimulatedQuestion).where(SimulatedQuestion.knowledge_point_id == seeded_kp.id)
    )).scalars().all())

    await question_service.persist_questions(db_session, kp_id=seeded_kp.id, questions=qs)
    await db_session.flush()
    cnt2 = len((await db_session.execute(
        select(SimulatedQuestion).where(SimulatedQuestion.knowledge_point_id == seeded_kp.id)
    )).scalars().all())
    assert cnt1 == cnt2


@pytest.mark.asyncio
async def test_persist_writes_dimension(db_session, seeded_kp):
    """persist_questions 传 dimension 时写入每行。"""
    qs = await question_ai_service.generate_questions(
        kp_name=seeded_kp.name, kp_category="vocabulary", kp_description="d",
        dimension="dictation", count=3,
    )
    created = await question_service.persist_questions(
        db_session, kp_id=seeded_kp.id, questions=qs, dimension="dictation",
    )
    await db_session.flush()
    assert len(created) == 3
    assert all(str(r.dimension) == "dictation" for r in created)


@pytest.mark.asyncio
async def test_persist_defaults_to_draft(db_session, seeded_kp):
    """不传 status 时，新题默认进 draft（审核闸门，M5）。"""
    qs = await question_ai_service.generate_questions(
        kp_name=seeded_kp.name, kp_category="grammar", kp_description="d", count=3,
    )
    created = await question_service.persist_questions(
        db_session, kp_id=seeded_kp.id, questions=qs,
    )
    await db_session.flush()
    assert all(str(r.status) == "draft" for r in created)


@pytest.mark.asyncio
async def test_persist_accepts_explicit_status(db_session, seeded_kp):
    """显式传 status='published' 时直接发布（seed / 可信内容用）。"""
    qs = await question_ai_service.generate_questions(
        kp_name=seeded_kp.name, kp_category="grammar", kp_description="d", count=2,
    )
    created = await question_service.persist_questions(
        db_session, kp_id=seeded_kp.id, questions=qs, status="published",
    )
    await db_session.flush()
    assert all(str(r.status) == "published" for r in created)


@pytest.mark.asyncio
async def test_list_for_review_filters_status(db_session, seeded_kp):
    """运营待审列表按 status 过滤；草稿题不出现在 published 列表里。"""
    qs = await question_ai_service.generate_questions(
        kp_name=seeded_kp.name, kp_category="grammar", kp_description="d", count=3,
    )
    await question_service.persist_questions(db_session, kp_id=seeded_kp.id, questions=qs)  # draft
    await db_session.flush()
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
    qs = await question_ai_service.generate_questions(
        kp_name=seeded_kp.name, kp_category="grammar", kp_description="d", count=1,
    )
    [sq] = await question_service.persist_questions(
        db_session, kp_id=seeded_kp.id, questions=qs,
    )
    await db_session.flush()
    reviewed = await question_service.review_question(
        db_session, question_id=sq.id, approve=True,
    )
    assert str(reviewed.status) == "published"


@pytest.mark.asyncio
async def test_review_reject_retires(db_session, seeded_kp):
    """审核驳回 → status=retired。"""
    qs = await question_ai_service.generate_questions(
        kp_name=seeded_kp.name, kp_category="grammar", kp_description="d", count=1,
    )
    [sq] = await question_service.persist_questions(
        db_session, kp_id=seeded_kp.id, questions=qs,
    )
    await db_session.flush()
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


@pytest.mark.asyncio
async def test_list_filters_by_dimension(db_session, seeded_kp):
    """list_questions_by_kp 给 dimension 时只返回该维度的题。"""
    for dim, cat in (("listening", "grammar"), ("dictation", "vocabulary")):
        qs = await question_ai_service.generate_questions(
            kp_name=seeded_kp.name, kp_category=cat, kp_description="d",
            dimension=dim, count=3,
        )
        await question_service.persist_questions(
            db_session, kp_id=seeded_kp.id, questions=qs, dimension=dim,
            status="published",
        )
    await db_session.flush()

    listening = await question_service.list_questions_by_kp(
        db_session, kp_id=seeded_kp.id, dimension="listening", limit=20,
    )
    assert len(listening) == 3
    assert all(q.question_type in ("单选", "阅读") for q in listening)

    dictation = await question_service.list_questions_by_kp(
        db_session, kp_id=seeded_kp.id, dimension="dictation", limit=20,
    )
    assert len(dictation) == 3
    assert all(q.question_type == "填空" for q in dictation)


@pytest.mark.asyncio
async def test_list_without_dimension_returns_all(db_session, seeded_kp):
    """不传 dimension 时不过滤（向后兼容）。"""
    for dim in ("listening", "dictation"):
        qs = await question_ai_service.generate_questions(
            kp_name=seeded_kp.name, kp_category="grammar", kp_description="d",
            dimension=dim, count=3,
        )
        await question_service.persist_questions(
            db_session, kp_id=seeded_kp.id, questions=qs, dimension=dim,
            status="published",
        )
    await db_session.flush()
    allq = await question_service.list_questions_by_kp(
        db_session, kp_id=seeded_kp.id, limit=20,
    )
    assert len(allq) == 6


@pytest.mark.asyncio
async def test_grading_single_choice_strict_equal(db_session, seeded_kp):
    q = SimulatedQuestion(
        id=uuid.uuid4(), knowledge_point_id=seeded_kp.id,
        question_type="单选", stem="X", options=["A", "B", "C", "D"],
        answer="B", explanation="...", difficulty=1, status="published",
    )
    db_session.add(q)
    await db_session.flush()
    user = await upsert_user(db_session, openid=f"q_{uuid.uuid4().hex[:6]}")
    await db_session.flush()

    r1 = await question_service.submit_attempt(
        db_session, user_id=user.id, question_id=q.id, user_answer="B",
    )
    assert r1.correct is True
    assert r1.wrong_question_id is None

    r2 = await question_service.submit_attempt(
        db_session, user_id=user.id, question_id=q.id, user_answer="A",
    )
    assert r2.correct is False
    assert r2.correct_answer == "B"
    assert r2.wrong_question_id is not None


@pytest.mark.asyncio
async def test_grading_fill_case_insensitive_multi_answer(db_session, seeded_kp):
    q = SimulatedQuestion(
        id=uuid.uuid4(), knowledge_point_id=seeded_kp.id,
        question_type="填空", stem="X", options=None,
        answer="goes|go", explanation="...", difficulty=1, status="published",
    )
    db_session.add(q)
    await db_session.flush()
    user = await upsert_user(db_session, openid=f"q_{uuid.uuid4().hex[:6]}")
    await db_session.flush()

    r1 = await question_service.submit_attempt(db_session, user_id=user.id, question_id=q.id, user_answer="goes")
    assert r1.correct is True
    r2 = await question_service.submit_attempt(db_session, user_id=user.id, question_id=q.id, user_answer="GO ")
    assert r2.correct is True
    r3 = await question_service.submit_attempt(db_session, user_id=user.id, question_id=q.id, user_answer="went")
    assert r3.correct is False


@pytest.mark.asyncio
async def test_grading_judge_strict(db_session, seeded_kp):
    q = SimulatedQuestion(
        id=uuid.uuid4(), knowledge_point_id=seeded_kp.id,
        question_type="判断", stem="X", options=None,
        answer="错", explanation="...", difficulty=1, status="published",
    )
    db_session.add(q)
    await db_session.flush()
    user = await upsert_user(db_session, openid=f"q_{uuid.uuid4().hex[:6]}")
    await db_session.flush()

    r1 = await question_service.submit_attempt(db_session, user_id=user.id, question_id=q.id, user_answer="错")
    assert r1.correct is True
    r2 = await question_service.submit_attempt(db_session, user_id=user.id, question_id=q.id, user_answer="对")
    assert r2.correct is False


@pytest.mark.asyncio
async def test_wrong_attempt_creates_wrong_question_with_kp_link(db_session, seeded_kp):
    """错题应自动写 wrong_questions + wrong_question_knowledge_points + 映射 question_type 到合法 enum。"""
    q = SimulatedQuestion(
        id=uuid.uuid4(), knowledge_point_id=seeded_kp.id,
        question_type="判断", stem="判断题干样本", options=None,
        answer="对", explanation="解析", difficulty=2, status="published",
    )
    db_session.add(q)
    await db_session.flush()
    user = await upsert_user(db_session, openid=f"q_{uuid.uuid4().hex[:6]}")
    await db_session.flush()

    r = await question_service.submit_attempt(
        db_session, user_id=user.id, question_id=q.id, user_answer="错",
    )
    assert r.wrong_question_id is not None

    wq = (await db_session.execute(
        select(WrongQuestion).where(WrongQuestion.id == r.wrong_question_id)
    )).scalar_one()
    assert wq.student_id == user.id
    assert "判断题干样本" in (wq.question_text or "")
    assert wq.student_answer == "错"
    assert wq.correct_answer == "对"
    # 判断现在有独立 enum 值，不再降级 "其他"
    assert str(wq.question_type) == "判断"
    # source_image_url 非空（满足 NOT NULL）
    assert wq.source_image_url

    # KP 链接也已建
    link = (await db_session.execute(
        select(WrongQuestionKnowledgePoint).where(
            WrongQuestionKnowledgePoint.wrong_question_id == wq.id,
            WrongQuestionKnowledgePoint.knowledge_point_id == seeded_kp.id,
        )
    )).scalar_one_or_none()
    assert link is not None


@pytest.mark.asyncio
async def test_wrong_fill_blank_keeps_type(db_session, seeded_kp):
    """填空错题映射到独立 enum "填空"，不再降级 "其他"。"""
    q = SimulatedQuestion(
        id=uuid.uuid4(), knowledge_point_id=seeded_kp.id,
        question_type="填空", stem="He ___ (go) to school.", options=None,
        answer="goes", explanation="第三人称单数", difficulty=2, status="published",
    )
    db_session.add(q)
    await db_session.flush()
    user = await upsert_user(db_session, openid=f"q_{uuid.uuid4().hex[:6]}")
    await db_session.flush()

    r = await question_service.submit_attempt(
        db_session, user_id=user.id, question_id=q.id, user_answer="go",
    )
    assert r.wrong_question_id is not None
    wq = (await db_session.execute(
        select(WrongQuestion).where(WrongQuestion.id == r.wrong_question_id)
    )).scalar_one()
    assert str(wq.question_type) == "填空"


# ─── M3b: 4 new types + batch ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_grading_cloze_strict_upper_equal(db_session, seeded_kp):
    """完型 同 单选 判分。"""
    q = SimulatedQuestion(
        id=uuid.uuid4(), knowledge_point_id=seeded_kp.id,
        question_type="完型", stem="Tom ___ to school.",
        options=["A. go", "B. goes", "C. going", "D. went"],
        answer="B", explanation="...", difficulty=1, status="published",
    )
    db_session.add(q)
    await db_session.flush()
    user = await upsert_user(db_session, openid=f"q_{uuid.uuid4().hex[:6]}")
    await db_session.flush()

    r_ok = await question_service.submit_attempt(db_session, user_id=user.id, question_id=q.id, user_answer="b")
    assert r_ok.correct is True
    r_no = await question_service.submit_attempt(db_session, user_id=user.id, question_id=q.id, user_answer="A")
    assert r_no.correct is False


@pytest.mark.asyncio
async def test_grading_reading_strict_upper_equal(db_session, seeded_kp):
    q = SimulatedQuestion(
        id=uuid.uuid4(), knowledge_point_id=seeded_kp.id,
        question_type="阅读", stem="Long passage... Question: which?",
        options=["A. x", "B. y", "C. z", "D. w"],
        answer="C", explanation="...", difficulty=2, status="published",
    )
    db_session.add(q)
    await db_session.flush()
    user = await upsert_user(db_session, openid=f"q_{uuid.uuid4().hex[:6]}")
    await db_session.flush()

    r_ok = await question_service.submit_attempt(db_session, user_id=user.id, question_id=q.id, user_answer="C")
    assert r_ok.correct is True


@pytest.mark.asyncio
async def test_grading_writing_always_correct(db_session, seeded_kp):
    """写作 不打分，任意非空答案视为完成。"""
    q = SimulatedQuestion(
        id=uuid.uuid4(), knowledge_point_id=seeded_kp.id,
        question_type="写作", stem="写 50 字短文。",
        options=None,
        answer="参考范文 sample...", explanation="...", difficulty=3, status="published",
    )
    db_session.add(q)
    await db_session.flush()
    user = await upsert_user(db_session, openid=f"q_{uuid.uuid4().hex[:6]}")
    await db_session.flush()

    r = await question_service.submit_attempt(db_session, user_id=user.id, question_id=q.id, user_answer="My short essay here")
    assert r.correct is True
    assert r.wrong_question_id is None  # 永远不落错题


@pytest.mark.asyncio
async def test_grading_match_sort_equal(db_session, seeded_kp):
    """连线 set 比较忽略顺序。"""
    q = SimulatedQuestion(
        id=uuid.uuid4(), knowledge_point_id=seeded_kp.id,
        question_type="连线", stem="...",
        options=None,
        answer="1-A|2-B|3-C", explanation="...", difficulty=1, status="published",
    )
    db_session.add(q)
    await db_session.flush()
    user = await upsert_user(db_session, openid=f"q_{uuid.uuid4().hex[:6]}")
    await db_session.flush()

    # 顺序不同也对
    r_ok = await question_service.submit_attempt(db_session, user_id=user.id, question_id=q.id, user_answer="3-C|1-A|2-B")
    assert r_ok.correct is True
    # 一对错了就 false
    r_no = await question_service.submit_attempt(db_session, user_id=user.id, question_id=q.id, user_answer="1-A|2-C|3-B")
    assert r_no.correct is False


@pytest.mark.asyncio
async def test_submit_exam_attempts_batch(db_session, seeded_kp):
    """3 题批量提交：2 对 1 错。"""
    from app.schemas.questions import PracticeAttemptIn

    qs_data = [
        ("单选", ["A. x", "B. y", "C. z", "D. w"], "B"),
        ("判断", None, "对"),
        ("填空", None, "goes"),
    ]
    q_ids = []
    for qtype, opts, ans in qs_data:
        q = SimulatedQuestion(
            id=uuid.uuid4(), knowledge_point_id=seeded_kp.id,
            question_type=qtype, stem=f"Q {qtype}",
            options=opts, answer=ans, explanation="exp",
            difficulty=1, status="published",
        )
        db_session.add(q)
        q_ids.append(q.id)
    await db_session.flush()
    user = await upsert_user(db_session, openid=f"q_{uuid.uuid4().hex[:6]}")
    await db_session.flush()

    answers = [
        PracticeAttemptIn(question_id=q_ids[0], user_answer="B"),       # 对
        PracticeAttemptIn(question_id=q_ids[1], user_answer="错"),      # 错
        PracticeAttemptIn(question_id=q_ids[2], user_answer="goes"),    # 对
    ]
    result = await question_service.submit_exam_attempts(
        db_session, user_id=user.id, answers=answers,
    )
    assert result.total == 3
    assert result.correct_count == 2
    assert len(result.items) == 3
    assert result.items[0].correct is True
    assert result.items[1].correct is False
    assert result.items[1].wrong_question_id is not None
    assert result.items[2].correct is True


@pytest.mark.asyncio
async def test_exam_attempts_records_session_history(db_session, seeded_kp):
    """模拟考批量提交后落一行成绩快照，可经 get_exam_history 取回。"""
    from app.schemas.questions import PracticeAttemptIn

    qs_data = [
        ("单选", ["A. x", "B. y", "C. z", "D. w"], "B"),
        ("判断", None, "对"),
    ]
    q_ids = []
    for qtype, opts, ans in qs_data:
        q = SimulatedQuestion(
            id=uuid.uuid4(), knowledge_point_id=seeded_kp.id,
            question_type=qtype, stem=f"Hist Q {qtype}",
            options=opts, answer=ans, explanation="exp",
            difficulty=1, status="published",
        )
        db_session.add(q)
        q_ids.append(q.id)
    await db_session.flush()
    user = await upsert_user(db_session, openid=f"q_{uuid.uuid4().hex[:6]}")
    await db_session.flush()

    answers = [
        PracticeAttemptIn(question_id=q_ids[0], user_answer="B"),   # 对
        PracticeAttemptIn(question_id=q_ids[1], user_answer="错"),  # 错
    ]
    await question_service.submit_exam_attempts(
        db_session, user_id=user.id, answers=answers,
    )

    hist = await question_service.get_exam_history(db_session, user_id=user.id)
    assert hist.total_exams == 1
    assert hist.items[0].total == 2
    assert hist.items[0].correct_count == 1
    assert hist.items[0].accuracy == 0.5


@pytest.mark.asyncio
async def test_exam_history_latest_first(db_session, seeded_kp):
    """两场模拟考，get_exam_history 最新在前。"""
    from app.schemas.questions import PracticeAttemptIn

    q = SimulatedQuestion(
        id=uuid.uuid4(), knowledge_point_id=seeded_kp.id,
        question_type="单选", stem=f"Multi-exam Q {uuid.uuid4().hex[:6]}",
        options=["A. x", "B. y", "C. z", "D. w"], answer="B",
        explanation="exp", difficulty=1, status="published",
    )
    db_session.add(q)
    await db_session.flush()
    user = await upsert_user(db_session, openid=f"q_{uuid.uuid4().hex[:6]}")
    await db_session.flush()

    # 第一场答对，第二场答错
    await question_service.submit_exam_attempts(
        db_session, user_id=user.id,
        answers=[PracticeAttemptIn(question_id=q.id, user_answer="B")],
    )
    await question_service.submit_exam_attempts(
        db_session, user_id=user.id,
        answers=[PracticeAttemptIn(question_id=q.id, user_answer="A")],
    )

    hist = await question_service.get_exam_history(db_session, user_id=user.id)
    assert hist.total_exams == 2
    # 最新（第二场，accuracy 0）在前
    assert hist.items[0].accuracy == 0.0
    assert hist.items[1].accuracy == 1.0


# ─── 练习闭环增强：错题查重 + 做对标 mastered ─────────────────────────────

async def _make_single(db_session, seeded_kp, answer="B"):
    q = SimulatedQuestion(
        id=uuid.uuid4(), knowledge_point_id=seeded_kp.id,
        question_type="单选", stem=f"Dedup Q {uuid.uuid4().hex[:6]}",
        options=["A. x", "B. y", "C. z", "D. w"],
        answer=answer, explanation="exp", difficulty=1, status="published",
    )
    db_session.add(q)
    await db_session.flush()
    return q


async def _count_wq(db_session, user_id, stem) -> int:
    rows = (await db_session.execute(
        select(WrongQuestion).where(
            WrongQuestion.student_id == user_id,
            WrongQuestion.question_text == stem,
        )
    )).scalars().all()
    return len(rows)


@pytest.mark.asyncio
async def test_wrong_twice_dedups_to_single_row(db_session, seeded_kp):
    """同一用户同一题连错两次 → wrong_questions 只 1 行（查重）。"""
    q = await _make_single(db_session, seeded_kp)
    user = await upsert_user(db_session, openid=f"q_{uuid.uuid4().hex[:6]}")
    await db_session.flush()

    r1 = await question_service.submit_attempt(db_session, user_id=user.id, question_id=q.id, user_answer="A")
    r2 = await question_service.submit_attempt(db_session, user_id=user.id, question_id=q.id, user_answer="C")
    assert r1.correct is False and r2.correct is False
    # 两次返回同一个 wrong_question_id
    assert r1.wrong_question_id == r2.wrong_question_id
    assert await _count_wq(db_session, user.id, q.stem) == 1


@pytest.mark.asyncio
async def test_correct_after_wrong_marks_mastered(db_session, seeded_kp):
    """先错后对 → 既存错题 is_mastered=True + mastered_at 落值。"""
    q = await _make_single(db_session, seeded_kp)
    user = await upsert_user(db_session, openid=f"q_{uuid.uuid4().hex[:6]}")
    await db_session.flush()

    await question_service.submit_attempt(db_session, user_id=user.id, question_id=q.id, user_answer="A")
    await question_service.submit_attempt(db_session, user_id=user.id, question_id=q.id, user_answer="B")

    wq = (await db_session.execute(
        select(WrongQuestion).where(
            WrongQuestion.student_id == user.id,
            WrongQuestion.question_text == q.stem,
        )
    )).scalar_one()
    assert wq.is_mastered is True
    assert wq.mastered_at is not None


@pytest.mark.asyncio
async def test_rewrong_unmasters(db_session, seeded_kp):
    """错→对（mastered）→再错 → is_mastered 回退 False、mastered_at 清空，仍 1 行。"""
    q = await _make_single(db_session, seeded_kp)
    user = await upsert_user(db_session, openid=f"q_{uuid.uuid4().hex[:6]}")
    await db_session.flush()

    await question_service.submit_attempt(db_session, user_id=user.id, question_id=q.id, user_answer="A")
    await question_service.submit_attempt(db_session, user_id=user.id, question_id=q.id, user_answer="B")  # 对 → mastered
    await question_service.submit_attempt(db_session, user_id=user.id, question_id=q.id, user_answer="D")  # 再错

    wq = (await db_session.execute(
        select(WrongQuestion).where(
            WrongQuestion.student_id == user.id,
            WrongQuestion.question_text == q.stem,
        )
    )).scalar_one()
    assert wq.is_mastered is False
    assert wq.mastered_at is None
    assert await _count_wq(db_session, user.id, q.stem) == 1


# ─── 学情：知识点正确率聚合（D-085）─────────────────────────────────────────

@pytest.mark.asyncio
async def test_attempt_logs_sim_practice_record(db_session, seeded_kp):
    """每次作答（对/错都）落 sim_practice_records 一行。"""
    from app.models.d12_v2_exams import SimPracticeRecord

    q = await _make_single(db_session, seeded_kp)
    user = await upsert_user(db_session, openid=f"q_{uuid.uuid4().hex[:6]}")
    await db_session.flush()

    await question_service.submit_attempt(db_session, user_id=user.id, question_id=q.id, user_answer="A")  # 错
    await question_service.submit_attempt(db_session, user_id=user.id, question_id=q.id, user_answer="B")  # 对

    recs = (await db_session.execute(
        select(SimPracticeRecord).where(
            SimPracticeRecord.student_id == user.id,
            SimPracticeRecord.simulated_question_id == q.id,
        )
    )).scalars().all()
    assert len(recs) == 2
    assert {r.is_correct for r in recs} == {True, False}
    assert all(r.knowledge_point_id == seeded_kp.id for r in recs)


@pytest.mark.asyncio
async def test_kp_accuracy_aggregates_rate(db_session, seeded_kp):
    """get_kp_accuracy 按 KP 聚合：3 次作答 2 对 → accuracy=0.6667。"""
    q = await _make_single(db_session, seeded_kp)
    user = await upsert_user(db_session, openid=f"q_{uuid.uuid4().hex[:6]}")
    await db_session.flush()

    await question_service.submit_attempt(db_session, user_id=user.id, question_id=q.id, user_answer="B")  # 对
    await question_service.submit_attempt(db_session, user_id=user.id, question_id=q.id, user_answer="A")  # 错
    await question_service.submit_attempt(db_session, user_id=user.id, question_id=q.id, user_answer="B")  # 对

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

    await question_service.submit_attempt(db_session, user_id=user.id, question_id=q1.id, user_answer="B")  # 对
    await question_service.submit_attempt(db_session, user_id=user.id, question_id=q2.id, user_answer="A")  # 错

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
