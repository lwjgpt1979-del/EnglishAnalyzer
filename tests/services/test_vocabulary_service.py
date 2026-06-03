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


@pytest.mark.asyncio
async def test_daily_task_includes_published_media_only(db_session):
    """daily-task 词卡只带 published 媒体；draft 媒体不下发。"""
    from app.models.d5_learning import VocabularyWord
    from app.services import vocabulary_service
    sid = await _make_student(db_session)
    w_pub = VocabularyWord(
        id=uuid.uuid4(), word=f"pub_{uuid.uuid4().hex[:6]}", phonetic="p",
        definitions=[{"pos": "n.", "meaning": "x"}], examples=None, difficulty=0,
        image_urls=["https://i/1.png"], en_description="desc",
        word_audio_url="https://a/w.mp3", en_desc_audio_url="https://a/d.mp3",
        media_status="published",
    )
    w_draft = VocabularyWord(
        id=uuid.uuid4(), word=f"dft_{uuid.uuid4().hex[:6]}", phonetic="d",
        definitions=[{"pos": "n.", "meaning": "y"}], examples=None, difficulty=0,
        image_urls=["https://i/2.png"], en_description="hidden", media_status="draft",
    )
    db_session.add_all([w_pub, w_draft])
    await db_session.flush()
    task = await vocabulary_service.get_daily_task(db_session, student_id=sid)
    by_id = {c.word_id: c for c in task.new_words}
    assert by_id[w_pub.id].image_urls == ["https://i/1.png"]
    assert by_id[w_pub.id].en_description == "desc"
    assert by_id[w_pub.id].word_audio_url == "https://a/w.mp3"
    assert by_id[w_draft.id].image_urls is None
    assert by_id[w_draft.id].en_description is None


# ─── 错词本（D-103）──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_wrong_answer_marks_wrong_book(db_session):
    from sqlalchemy import select as _sel
    from app.models.d5_learning import VocabularyLearning
    from app.services import vocabulary_service
    sid = await _make_student(db_session)
    [wid] = await _seed_words(db_session, 1)
    await vocabulary_service.submit_answer(db_session, student_id=sid, word_id=wid, correct=False)
    lr = (await db_session.execute(_sel(VocabularyLearning).where(
        VocabularyLearning.student_id == sid, VocabularyLearning.word_id == wid))).scalar_one()
    assert lr.is_wrong is True and lr.wrong_count == 1


@pytest.mark.asyncio
async def test_mastered_removes_from_wrong_book(db_session):
    from sqlalchemy import select as _sel
    from app.models.d5_learning import VocabularyLearning
    from app.services import vocabulary_service
    sid = await _make_student(db_session)
    [wid] = await _seed_words(db_session, 1)
    await vocabulary_service.submit_answer(db_session, student_id=sid, word_id=wid, correct=False)
    for _ in range(5):
        await vocabulary_service.submit_answer(db_session, student_id=sid, word_id=wid, correct=True)
    lr = (await db_session.execute(_sel(VocabularyLearning).where(
        VocabularyLearning.student_id == sid, VocabularyLearning.word_id == wid))).scalar_one()
    assert lr.level == "mastered" and lr.is_wrong is False


@pytest.mark.asyncio
async def test_list_wrong_words(db_session):
    from app.services import vocabulary_service
    sid = await _make_student(db_session)
    ids = await _seed_words(db_session, 3)
    await vocabulary_service.submit_answer(db_session, student_id=sid, word_id=ids[0], correct=False)
    await vocabulary_service.submit_answer(db_session, student_id=sid, word_id=ids[1], correct=False)
    await vocabulary_service.submit_answer(db_session, student_id=sid, word_id=ids[1], correct=False)
    await db_session.flush()
    rows, total = await vocabulary_service.list_wrong_words(db_session, student_id=sid)
    assert total == 2
    assert rows[0][1].id == ids[1]  # 错 2 次的排最前


# ─── D-105: 完成度计算 ────────────────────────────────────────────────

def test_new_target_pure():
    from app.services.vocabulary_service import _new_target
    # 词库新词充足：取档位上限
    assert _new_target(5, 0, 100) == 5
    assert _new_target(5, 3, 100) == 5
    # 词库新词不足：学完所有可学即收缩（已学3+剩0=3）
    assert _new_target(5, 3, 0) == 3
    assert _new_target(5, 1, 2) == 3


@pytest.mark.asyncio
async def test_progress_fresh_student_not_done(db_session):
    """全新学生：无到期复习（review_done True），但今日未学新词 → all_done False。"""
    from app.services import vocabulary_service
    sid = await _make_student(db_session)
    await _seed_words(db_session, 10)  # 词库有未学新词
    p = await vocabulary_service.compute_today_progress(db_session, student_id=sid)
    assert p["review_due"] == 0 and p["review_done"] is True
    assert p["new_learned_today"] == 0
    assert p["new_target"] == 5  # free 档上限
    assert p["new_done"] is False and p["all_done"] is False


@pytest.mark.asyncio
async def test_progress_due_review_blocks(db_session):
    """有到期复习词 → review_done False、all_done False。"""
    from datetime import datetime, timedelta, timezone
    from app.models.d5_learning import VocabularyLearning
    from app.services import vocabulary_service
    sid = await _make_student(db_session)
    [wid] = await _seed_words(db_session, 1)
    now = datetime.now(timezone.utc)
    db_session.add(VocabularyLearning(
        id=uuid.uuid4(), student_id=sid, word_id=wid,
        interval_days=1, repetitions=1, easiness_factor=2.5,
        next_review_at=now - timedelta(days=1),  # 已到期
        level="learning",
    ))
    await db_session.flush()
    p = await vocabulary_service.compute_today_progress(db_session, student_id=sid)
    assert p["review_due"] >= 1 and p["review_done"] is False
    assert p["all_done"] is False


@pytest.mark.asyncio
async def test_progress_all_done_when_new_learned(db_session):
    """今日学满 free 上限(5)且无到期复习 → all_done True。"""
    from datetime import datetime, timedelta, timezone
    from app.models.d5_learning import VocabularyLearning
    from app.services import vocabulary_service
    sid = await _make_student(db_session)
    wids = await _seed_words(db_session, 5)
    now = datetime.now(timezone.utc)
    for wid in wids:
        db_session.add(VocabularyLearning(
            id=uuid.uuid4(), student_id=sid, word_id=wid,
            interval_days=1, repetitions=1, easiness_factor=2.5,
            next_review_at=now + timedelta(days=1),  # 未到期
            level="learning", created_at=now,
        ))
    await db_session.flush()
    p = await vocabulary_service.compute_today_progress(db_session, student_id=sid)
    assert p["review_due"] == 0
    assert p["new_learned_today"] == 5
    assert p["new_target"] == 5
    assert p["new_done"] is True and p["all_done"] is True
