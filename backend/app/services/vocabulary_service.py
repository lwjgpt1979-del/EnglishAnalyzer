"""词力通词汇学习业务逻辑（P1 / D-100）。

SM-2（SuperMemo 2）间隔重复调度，每名学生每个单词独立维护记忆状态。
- 答对：repetitions +1，间隔走 1→3→7→15→30 天，level 升级
- 答错：repetitions 重置 0，间隔 1 天（当日/次日复习），level 回 new
- 犹豫（记得但不确定）：不升级、间隔不延长
每日新词上限按会员档位（free=5/basic=10/pro=30/promax=50；后台可配置留后续）。
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import and_, func, literal, or_, select, union_all
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d1_users import User
from app.models.d4_knowledge import CurriculumUnit, CurriculumWord
from app.models.d5_learning import (
    StudentVocabCandidate,
    StudentVocabSetting,
    VocabularyLearning,
    VocabularyWord,
)
from app.models.d14_v2_semesters import PurchasedSemester
from app.schemas.vocabulary import (
    DailyTaskOut,
    VocabAnswerResult,
    WordCardOut,
)
from app.services import membership_service

# 抽生词时跳过的高频虚词（即便命中词典也不入候选，避免噪声）
_STOPWORDS = {
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "her", "was",
    "one", "our", "out", "his", "has", "had", "him", "she", "they", "their",
    "this", "that", "these", "those", "with", "from", "have", "will", "your",
    "what", "when", "who", "how", "why", "which", "there", "here", "then",
    "than", "into", "about", "would", "could", "should", "been", "were",
}

_DAILY_NEW_LIMIT = {"free": 5, "basic": 10, "pro": 30, "promax": 50}
_INTERVALS = {1: 1, 2: 3, 3: 7, 4: 15}  # repetitions → interval_days；>=5 取 30


async def _ordered_new_words(
    db: AsyncSession, *, student: User, limit: int | None = None,
) -> list[VocabularyWord]:
    """按优先级返回该生未学过的新词（跨来源去重）。

    优先级：P1 当前学期教材词 > P2 其他来源候选词(试卷/错题) > P3 过往购买学期教材词。
    同一个词出现在多来源时取最高优先级。scope 内无可学新词时回退全局按难度
    （兼容内容未铺/新用户，不至于空页）。
    """
    learned = (
        select(VocabularyLearning.word_id)
        .where(VocabularyLearning.student_id == student.id)
        .scalar_subquery()
    )
    pref = (
        student.preferred_textbook_version,
        student.preferred_grade,
        student.preferred_semester,
    )
    parts = []
    # P1 当前学期教材词
    if all(pref):
        parts.append(
            select(CurriculumWord.word_id.label("wid"), literal(1).label("p"))
            .join(CurriculumUnit, CurriculumUnit.id == CurriculumWord.unit_id)
            .where(
                CurriculumUnit.textbook_version == pref[0],
                CurriculumUnit.grade == pref[1],
                CurriculumUnit.semester == pref[2],
            )
        )
    # P2 其他来源候选词
    parts.append(
        select(StudentVocabCandidate.word_id.label("wid"), literal(2).label("p"))
        .where(StudentVocabCandidate.student_id == student.id)
    )
    # P3 过往购买学期（排除当前学期）教材词
    purchased = (await db.execute(
        select(
            PurchasedSemester.textbook_version,
            PurchasedSemester.grade,
            PurchasedSemester.semester,
        ).where(PurchasedSemester.user_id == student.id)
    )).all()
    past = [(t, g, s) for (t, g, s) in purchased if (t, g, s) != pref]
    if past:
        cond = or_(*[
            and_(
                CurriculumUnit.textbook_version == t,
                CurriculumUnit.grade == g,
                CurriculumUnit.semester == s,
            ) for (t, g, s) in past
        ])
        parts.append(
            select(CurriculumWord.word_id.label("wid"), literal(3).label("p"))
            .join(CurriculumUnit, CurriculumUnit.id == CurriculumWord.unit_id)
            .where(cond)
        )

    union_q = union_all(*parts).subquery()
    ranked = (
        select(union_q.c.wid, func.min(union_q.c.p).label("p"))
        .group_by(union_q.c.wid).subquery()
    )
    scoped = (
        select(VocabularyWord)
        .join(ranked, ranked.c.wid == VocabularyWord.id)
        .where(VocabularyWord.id.not_in(learned))
        .order_by(ranked.c.p, VocabularyWord.difficulty, VocabularyWord.id)
    )
    if limit is not None:
        scoped = scoped.limit(limit)
    rows = list((await db.execute(scoped)).scalars().all())
    if rows:
        return rows

    # 回退：scope 内无可学新词 → 全局按难度
    g = (
        select(VocabularyWord)
        .where(VocabularyWord.id.not_in(learned))
        .order_by(VocabularyWord.difficulty, VocabularyWord.id)
    )
    if limit is not None:
        g = g.limit(limit)
    return list((await db.execute(g)).scalars().all())


async def add_source_candidates(
    db: AsyncSession, *, student_id: uuid.UUID, text: str, source: str,
) -> int:
    """从一段英文文本里抽出命中词典的生词，加入该生"其他来源"候选池(P2)。

    只收录已在全局词典(vocabulary_words)里的词（带释义/媒体，可学）；
    去停用词；UNIQUE(student,word) 保证不重复。返回新增条数。失败不抛（best-effort）。
    """
    if not text:
        return 0
    tokens = {t.lower() for t in re.findall(r"[A-Za-z]{3,}", text)}
    tokens -= _STOPWORDS
    if not tokens:
        return 0
    rows = (await db.execute(
        select(VocabularyWord.id).where(func.lower(VocabularyWord.word).in_(tokens))
    )).scalars().all()
    if not rows:
        return 0
    stmt = pg_insert(StudentVocabCandidate).values([
        {"id": uuid.uuid4(), "student_id": student_id, "word_id": wid, "source": source}
        for wid in rows
    ]).on_conflict_do_nothing(index_elements=["student_id", "word_id"])
    result = await db.execute(stmt)
    return result.rowcount or 0


async def add_manual_word(
    db: AsyncSession, *, student_id: uuid.UUID, word: str,
) -> dict:
    """用户手动添加生词到自己的词源池（source='manual'）。仅收录词典已有的词。

    返回 {added, found, word?, already?}。found=False 表示词典暂未收录。
    """
    w = (word or "").strip().lower()
    if not w:
        return {"added": False, "found": False, "message": "请输入单词"}
    row = (await db.execute(
        select(VocabularyWord.id, VocabularyWord.word)
        .where(func.lower(VocabularyWord.word) == w)
    )).first()
    if row is None:
        return {"added": False, "found": False, "message": "词典暂未收录该词，换一个试试"}
    stmt = pg_insert(StudentVocabCandidate).values(
        id=uuid.uuid4(), student_id=student_id, word_id=row[0], source="manual",
    ).on_conflict_do_nothing(index_elements=["student_id", "word_id"])
    res = await db.execute(stmt)
    return {"added": True, "found": True, "word": row[1], "already": (res.rowcount or 0) == 0}


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


def _new_target(new_limit: int, new_learned_today: int, new_words_remaining: int) -> int:
    """今日新词目标：词库新词足够取档位上限；不足则学完所有可学即达标。"""
    return min(new_limit, new_learned_today + new_words_remaining)


async def compute_today_progress(db: AsyncSession, *, student_id: uuid.UUID) -> dict:
    """计算今日任务完成度（复习全完成 + 新词全学完）。"""
    now = datetime.now(timezone.utc)
    today = now.date()
    day_start = datetime.combine(today, time.min, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    review_due = (await db.execute(
        select(func.count()).select_from(VocabularyLearning).where(
            VocabularyLearning.student_id == student_id,
            VocabularyLearning.next_review_at <= now,
        )
    )).scalar_one()

    new_learned_today = (await db.execute(
        select(func.count()).select_from(VocabularyLearning).where(
            VocabularyLearning.student_id == student_id,
            VocabularyLearning.created_at >= day_start,
            VocabularyLearning.created_at < day_end,
        )
    )).scalar_one()

    # 剩余可学新词：与选词同口径（按学期优先级 scope，回退全局）
    student = (await db.execute(
        select(User).where(User.id == student_id)
    )).scalar_one()
    new_words_remaining = len(await _ordered_new_words(db, student=student))

    new_limit = await _daily_new_limit(db, student_id=student_id)
    target = _new_target(new_limit, int(new_learned_today), int(new_words_remaining))
    review_done = int(review_due) == 0
    new_done = int(new_learned_today) >= target
    return {
        "review_due": int(review_due),
        "review_done": review_done,
        "new_learned_today": int(new_learned_today),
        "new_target": target,
        "new_done": new_done,
        "all_done": review_done and new_done,
    }


def _to_card(w: VocabularyWord, *, level: str, is_new: bool) -> WordCardOut:
    pub = str(getattr(w, "media_status", "draft")) == "published"
    return WordCardOut(
        word_id=w.id,
        word=w.word,
        phonetic=w.phonetic,
        definitions=w.definitions,
        examples=w.examples,
        phrases=w.phrases,
        difficulty=w.difficulty,
        level=level,
        is_new=is_new,
        image_urls=(w.image_urls if pub else None),
        en_description=(w.en_description if pub else None),
        word_audio_url=(w.word_audio_url if pub else None),
        en_desc_audio_url=(w.en_desc_audio_url if pub else None),
    )


# ── 学习设置（每生一份，不再绑定会员档位）────────────────────────────────────
_WPG_MIN, _WPG_MAX = 1, 50
_REP_MIN, _REP_MAX = 1, 5


async def get_vocab_settings(db: AsyncSession, *, student_id: uuid.UUID) -> dict:
    row = (await db.execute(
        select(StudentVocabSetting).where(StudentVocabSetting.student_id == student_id)
    )).scalar_one_or_none()
    if row is None:
        return {"words_per_group": 5, "reps_per_group": 1}
    return {"words_per_group": int(row.words_per_group), "reps_per_group": int(row.reps_per_group)}


async def set_vocab_settings(
    db: AsyncSession, *, student_id: uuid.UUID, words_per_group: int, reps_per_group: int,
) -> dict:
    wpg = max(_WPG_MIN, min(int(words_per_group), _WPG_MAX))
    rep = max(_REP_MIN, min(int(reps_per_group), _REP_MAX))
    row = (await db.execute(
        select(StudentVocabSetting).where(StudentVocabSetting.student_id == student_id)
    )).scalar_one_or_none()
    if row is None:
        db.add(StudentVocabSetting(
            id=uuid.uuid4(), student_id=student_id,
            words_per_group=wpg, reps_per_group=rep))
    else:
        row.words_per_group, row.reps_per_group = wpg, rep
    await db.flush()
    return {"words_per_group": wpg, "reps_per_group": rep}


async def get_daily_task(db: AsyncSession, *, student_id: uuid.UUID) -> DailyTaskOut:
    """返回一组学习内容：到期复习词（全部）+ 新词（按用户设置「每组词数」，不再按会员档位）。"""
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

    # 新词：按优先级（当前学期教材 > 其他来源 > 过往学期）选取、跨来源去重，
    # limit = 用户设置的「每组词数」（不再绑定会员档位）
    settings = await get_vocab_settings(db, student_id=student_id)
    new_limit = settings["words_per_group"]
    student = (await db.execute(
        select(User).where(User.id == student_id)
    )).scalar_one()
    new_rows = await _ordered_new_words(db, student=student, limit=new_limit)
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
