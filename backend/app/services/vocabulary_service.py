"""词力通词汇学习业务逻辑（P1 / D-100）。

SM-2（SuperMemo 2）间隔重复调度，每名学生每个单词独立维护记忆状态。
- 答对：repetitions +1，间隔走 1→3→7→15→30 天，level 升级
- 答错：repetitions 重置 0，间隔 1 天（当日/次日复习），level 回 new
- 犹豫（记得但不确定）：不升级、间隔不延长
每日新词上限按会员档位（free=5/basic=10/pro=30/promax=50；后台可配置留后续）。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d5_learning import VocabularyLearning, VocabularyWord
from app.schemas.vocabulary import (
    DailyTaskOut,
    VocabAnswerResult,
    WordCardOut,
)
from app.services import membership_service

_DAILY_NEW_LIMIT = {"free": 5, "basic": 10, "pro": 30, "promax": 50}
_INTERVALS = {1: 1, 2: 3, 3: 7, 4: 15}  # repetitions → interval_days；>=5 取 30


def _level_for(repetitions: int) -> str:
    if repetitions <= 0:
        return "new"
    if repetitions <= 2:
        return "learning"
    if repetitions == 3:
        return "review"
    return "mastered"


def sm2(
    *, correct: bool, hesitant: bool, repetitions: int, interval_days: int, ef: float,
) -> tuple[int, int, float]:
    """返回 (repetitions, interval_days, ef)。q: 对=5 / 犹豫=3 / 错=2。"""
    q = 2 if not correct else (3 if hesitant else 5)
    ef = max(1.3, ef + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)))
    if q < 3:  # 答错：重置
        return 0, 1, ef
    if hesitant:  # 犹豫：不升级、间隔不延长
        return repetitions, max(1, interval_days), ef
    repetitions += 1
    interval = _INTERVALS.get(repetitions, 30)
    return repetitions, interval, ef


async def _daily_new_limit(db: AsyncSession, *, student_id: uuid.UUID) -> int:
    m = await membership_service.get_active_membership(db, user_id=student_id)
    tier = str(m.tier) if m else "free"
    return _DAILY_NEW_LIMIT.get(tier, 5)


def _to_card(w: VocabularyWord, *, level: str, is_new: bool) -> WordCardOut:
    pub = str(getattr(w, "media_status", "draft")) == "published"
    return WordCardOut(
        word_id=w.id,
        word=w.word,
        phonetic=w.phonetic,
        definitions=w.definitions,
        examples=w.examples,
        difficulty=w.difficulty,
        level=level,
        is_new=is_new,
        image_urls=(w.image_urls if pub else None),
        en_description=(w.en_description if pub else None),
        word_audio_url=(w.word_audio_url if pub else None),
        en_desc_audio_url=(w.en_desc_audio_url if pub else None),
    )


async def get_daily_task(db: AsyncSession, *, student_id: uuid.UUID) -> DailyTaskOut:
    """返回今日任务：到期复习词（全部）+ 新词（按档位上限）。"""
    now = datetime.now(timezone.utc)

    # 复习词：到期的 learning 记录 join 词
    review_rows = (await db.execute(
        select(VocabularyLearning, VocabularyWord)
        .join(VocabularyWord, VocabularyWord.id == VocabularyLearning.word_id)
        .where(
            VocabularyLearning.student_id == student_id,
            VocabularyLearning.next_review_at <= now,
        )
        # 错词优先复习（D-103）：错词最前、错得多的更靠前，再按到期时间
        .order_by(
            VocabularyLearning.is_wrong.desc(),
            VocabularyLearning.wrong_count.desc(),
            VocabularyLearning.next_review_at,
        )
    )).all()
    review_words = [_to_card(w, level=str(lr.level), is_new=False) for lr, w in review_rows]

    # 新词：该生无 learning 记录的词，按难度升序，limit 档位上限
    new_limit = await _daily_new_limit(db, student_id=student_id)
    learned_subq = (
        select(VocabularyLearning.word_id)
        .where(VocabularyLearning.student_id == student_id)
        .scalar_subquery()
    )
    new_rows = (await db.execute(
        select(VocabularyWord)
        .where(VocabularyWord.id.not_in(learned_subq))
        .order_by(VocabularyWord.difficulty, VocabularyWord.id)
        .limit(new_limit)
    )).scalars().all()
    new_words = [_to_card(w, level="new", is_new=True) for w in new_rows]

    return DailyTaskOut(
        new_words=new_words,
        review_words=review_words,
        new_count=len(new_words),
        review_count=len(review_words),
        new_limit=new_limit,
    )


async def submit_answer(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    word_id: uuid.UUID,
    correct: bool,
    hesitant: bool = False,
) -> VocabAnswerResult:
    """提交一次作答，按 SM-2 更新该生该词的记忆状态。"""
    now = datetime.now(timezone.utc)
    lr = (await db.execute(
        select(VocabularyLearning).where(
            VocabularyLearning.student_id == student_id,
            VocabularyLearning.word_id == word_id,
        )
    )).scalar_one_or_none()

    if lr is None:
        # 新词首学：以初始态进 SM-2
        reps, interval, ef = sm2(
            correct=correct, hesitant=hesitant, repetitions=0, interval_days=1, ef=2.5,
        )
        lr = VocabularyLearning(
            id=uuid.uuid4(),
            student_id=student_id,
            word_id=word_id,
            interval_days=interval,
            repetitions=reps,
            easiness_factor=ef,
            next_review_at=now + timedelta(days=interval),
            last_reviewed_at=now,
            level=_level_for(reps),
            is_wrong=(not correct),               # 首学答错即入错词本（D-103）
            wrong_count=(0 if correct else 1),
        )
        db.add(lr)
    else:
        reps, interval, ef = sm2(
            correct=correct, hesitant=hesitant,
            repetitions=lr.repetitions, interval_days=lr.interval_days,
            ef=float(lr.easiness_factor),
        )
        lr.repetitions = reps
        lr.interval_days = interval
        lr.easiness_factor = ef
        lr.next_review_at = now + timedelta(days=interval)
        lr.last_reviewed_at = now
        lr.level = _level_for(reps)
        # 错词本联动（D-103）：答错入本+计数；答对升 mastered 移出
        if not correct:
            lr.is_wrong = True
            lr.wrong_count = (lr.wrong_count or 0) + 1
        elif _level_for(reps) == "mastered":
            lr.is_wrong = False

    await db.flush()
    return VocabAnswerResult(
        word_id=word_id,
        level=_level_for(reps),
        repetitions=reps,
        interval_days=interval,
        next_review_at=(now + timedelta(days=interval)).isoformat(),
    )


async def list_wrong_words(
    db: AsyncSession, *, student_id: uuid.UUID, skip: int = 0, limit: int = 50,
) -> tuple[list[tuple[VocabularyLearning, VocabularyWord]], int]:
    """该生错词本：is_wrong=True 的词，按 wrong_count 降序（错得多的在前）。"""
    base = (
        select(VocabularyLearning, VocabularyWord)
        .join(VocabularyWord, VocabularyWord.id == VocabularyLearning.word_id)
        .where(
            VocabularyLearning.student_id == student_id,
            VocabularyLearning.is_wrong.is_(True),
        )
    )
    total: int = (await db.execute(
        select(func.count()).select_from(base.subquery())
    )).scalar_one()
    rows = (await db.execute(
        base.order_by(VocabularyLearning.wrong_count.desc()).offset(skip).limit(limit)
    )).all()
    return list(rows), total
