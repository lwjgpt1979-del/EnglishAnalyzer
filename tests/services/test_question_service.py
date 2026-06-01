"""question_service 测试。"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.config import settings
from app.core.database import _async_session_factory
from app.models.d3_wrong_questions import WrongQuestion
from app.models.d4_knowledge import KnowledgePoint, WrongQuestionKnowledgePoint
from app.models.d12_v2_exams import SimulatedQuestion
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
