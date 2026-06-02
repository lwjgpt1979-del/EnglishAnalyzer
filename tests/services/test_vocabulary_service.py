"""词力通 vocabulary_service + schemas 测试（P1 / D-100）。"""
import uuid

import pytest
import pytest_asyncio

from app.core.database import _async_session_factory


# ─── Task 1: schema 冒烟 ──────────────────────────────────────────────

def test_schemas_construct():
    from app.schemas.vocabulary import (
        WordCardOut, DailyTaskOut, VocabAnswerIn, VocabAnswerResult,
    )
    card = WordCardOut(
        word_id=uuid.uuid4(), word="frequently", phonetic="ˈfriːkwəntli",
        definitions=[{"pos": "adv.", "meaning": "频繁地"}], examples=None,
        difficulty=3, level="new", is_new=True,
    )
    task = DailyTaskOut(
        new_words=[card], review_words=[], new_count=1, review_count=0, new_limit=5,
    )
    assert task.new_count == 1 and task.new_limit == 5
    ans_in = VocabAnswerIn(word_id=card.word_id, correct=True)
    assert ans_in.hesitant is False
    res = VocabAnswerResult(
        word_id=card.word_id, level="learning", repetitions=1,
        interval_days=1, next_review_at="2026-06-04T00:00:00+00:00",
    )
    assert res.repetitions == 1


# ─── Task 2: SM-2 纯函数 ──────────────────────────────────────────────

def test_sm2_correct_progression():
    """连续答对：interval 走 1→3→7→15→30。"""
    from app.services import vocabulary_service
    reps, iv, ef = 0, 1, 2.5
    seq = []
    for _ in range(6):
        reps, iv, ef = vocabulary_service.sm2(
            correct=True, hesitant=False, repetitions=reps, interval_days=iv, ef=ef,
        )
        seq.append(iv)
    assert seq[:5] == [1, 3, 7, 15, 30]
    assert seq[5] == 30  # 掌握后长期维护


def test_sm2_wrong_resets():
    from app.services import vocabulary_service
    reps, iv, ef = vocabulary_service.sm2(
        correct=False, hesitant=False, repetitions=3, interval_days=7, ef=2.5,
    )
    assert reps == 0 and iv == 1


def test_sm2_hesitant_no_advance():
    from app.services import vocabulary_service
    reps, iv, ef = vocabulary_service.sm2(
        correct=True, hesitant=True, repetitions=2, interval_days=3, ef=2.5,
    )
    assert reps == 2 and iv == 3


def test_level_for():
    from app.services import vocabulary_service
    assert vocabulary_service._level_for(0) == "new"
    assert vocabulary_service._level_for(1) == "learning"
    assert vocabulary_service._level_for(2) == "learning"
    assert vocabulary_service._level_for(3) == "review"
    assert vocabulary_service._level_for(5) == "mastered"


# ─── Task 2: DB 集成 ──────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _make_student(s) -> uuid.UUID:
    from app.services.auth_service import upsert_user
    u = await upsert_user(s, openid=f"vocab_stu_{uuid.uuid4().hex[:8]}")
    await s.flush()
    return u.id


async def _seed_words(s, n: int) -> list[uuid.UUID]:
    from app.models.d5_learning import VocabularyWord
    ids = []
    for i in range(n):
        w = VocabularyWord(
            id=uuid.uuid4(), word=f"vocabtest_{uuid.uuid4().hex[:6]}",
            phonetic="ˈtest", definitions=[{"pos": "n.", "meaning": f"测试{i}"}],
            examples=None, difficulty=1,
        )
        s.add(w)
        ids.append(w.id)
    await s.flush()
    return ids


@pytest.mark.asyncio
async def test_daily_task_new_within_free_limit(db_session):
    """free 档（无会员）每日新词 ≤ 5。"""
    from app.services import vocabulary_service
    sid = await _make_student(db_session)
    await _seed_words(db_session, 8)
    task = await vocabulary_service.get_daily_task(db_session, student_id=sid)
    assert task.new_limit == 5
    assert task.new_count <= 5
    assert all(c.is_new for c in task.new_words)


@pytest.mark.asyncio
async def test_submit_creates_then_levels_up(db_session):
    """首次提交建 learning 行；答对 level 升级、next_review_at 在未来。"""
    from datetime import datetime, timezone
    from app.services import vocabulary_service
    sid = await _make_student(db_session)
    [wid] = await _seed_words(db_session, 1)
    r1 = await vocabulary_service.submit_answer(
        db_session, student_id=sid, word_id=wid, correct=True, hesitant=False,
    )
    assert r1.repetitions == 1 and r1.level == "learning"
    assert datetime.fromisoformat(r1.next_review_at) > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_submit_wrong_resets(db_session):
    from app.services import vocabulary_service
    sid = await _make_student(db_session)
    [wid] = await _seed_words(db_session, 1)
    await vocabulary_service.submit_answer(db_session, student_id=sid, word_id=wid, correct=True, hesitant=False)
    r = await vocabulary_service.submit_answer(db_session, student_id=sid, word_id=wid, correct=False, hesitant=False)
    assert r.repetitions == 0 and r.level == "new" and r.interval_days == 1


@pytest.mark.asyncio
async def test_learned_word_not_in_new(db_session):
    """已学过的词不再出现在新词列表。"""
    from app.services import vocabulary_service
    sid = await _make_student(db_session)
    ids = await _seed_words(db_session, 3)
    await vocabulary_service.submit_answer(db_session, student_id=sid, word_id=ids[0], correct=True, hesitant=False)
    task = await vocabulary_service.get_daily_task(db_session, student_id=sid)
    new_ids = {c.word_id for c in task.new_words}
    assert ids[0] not in new_ids
