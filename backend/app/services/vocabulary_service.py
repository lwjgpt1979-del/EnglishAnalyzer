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

    优先级：P0 个人体系命中 > pin 优先学 > P1 考纲主词源(按学段:初中→中考/高中→高考) >
    P2 当前学期教材词 > P3 其他来源候选(试卷/错题) > P4 过往学期教材 > P5 通用词库(opt-in)。
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
    # P0 个人体系命中词(KP-First R5):student_kp(in_scope)→ vocab_node → 词,最高优先
    from app.models.d16_question_domain import StudentKp
    from app.models.d18_vocab_kg import VocabNode
    parts.append(
        select(VocabNode.word_id.label("wid"), literal(0).label("p"))
        .join(StudentKp, StudentKp.node_id == VocabNode.node_id)
        .where(StudentKp.student_id == student.id, StudentKp.in_scope.is_(True))
    )
    # P1 考纲主词源(按学段):初中→中考(junior)、高中→高考(senior)考纲词表,作为词力通主词源;
    #    无对应学段考纲词表时回退到下面的教材等来源。
    pg = student.preferred_grade or ""
    stage_level = "junior" if "初中" in pg else ("senior" if "高中" in pg else None)
    if stage_level:
        from app.models.d18_vocab_kg import VocabList, VocabListItem
        parts.append(
            select(VocabListItem.word_id.label("wid"), literal(1).label("p"))
            .join(VocabList, VocabList.id == VocabListItem.list_id)
            .where(VocabList.exam_level == stage_level, VocabList.status == "published")
        )
    # P2 当前学期教材词
    if all(pref):
        parts.append(
            select(CurriculumWord.word_id.label("wid"), literal(2).label("p"))
            .join(CurriculumUnit, CurriculumUnit.id == CurriculumWord.unit_id)
            .where(
                CurriculumUnit.textbook_version == pref[0],
                CurriculumUnit.grade == pref[1],
                CurriculumUnit.semester == pref[2],
            )
        )
    # P(-1) 优先学(R9.6):学生主动 pin 的词排在所有来源最前,priority 级别越高越靠前
    parts.append(
        select(StudentVocabCandidate.word_id.label("wid"),
               (literal(-1) - StudentVocabCandidate.priority).label("p"))
        .where(StudentVocabCandidate.student_id == student.id, StudentVocabCandidate.priority > 0)
    )
    # P3 其他来源候选词
    parts.append(
        select(StudentVocabCandidate.word_id.label("wid"), literal(3).label("p"))
        .where(StudentVocabCandidate.student_id == student.id)
    )
    # P4 过往购买学期（排除当前学期）教材词
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
            select(CurriculumWord.word_id.label("wid"), literal(4).label("p"))
            .join(CurriculumUnit, CurriculumUnit.id == CurriculumWord.unit_id)
            .where(cond)
        )

    # P4 通用词库(opt-in):学生开了 include_general_vocab → 加该词库(或任一已发布库)的词,最低优先
    setting = (await db.execute(
        select(StudentVocabSetting).where(StudentVocabSetting.student_id == student.id)
    )).scalar_one_or_none()
    if setting is not None and getattr(setting, "include_general_vocab", False):
        from app.models.d18_vocab_kg import VocabListItem, VocabList
        gp = select(VocabListItem.word_id.label("wid"), literal(5).label("p"))
        if setting.general_vocab_list_id is not None:
            gp = gp.where(VocabListItem.list_id == setting.general_vocab_list_id)
        else:
            gp = gp.join(VocabList, VocabList.id == VocabListItem.list_id).where(
                VocabList.status == "published")
        parts.append(gp)

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


async def log_pron(db: AsyncSession, *, student_id: uuid.UUID, reference_text: str, result: dict) -> None:
    """记录一次跟读发音评测，供学情报表/趋势。best-effort，失败不抛。"""
    from app.models.d5_learning import VocabPronLog
    try:
        ref = (reference_text or "").strip()
        wid = None
        if ref and len(ref.split()) == 1:
            row = (await db.execute(
                select(VocabularyWord.id).where(func.lower(VocabularyWord.word) == ref.lower())
            )).first()
            wid = row[0] if row else None
        weak = [w.get("word") for w in (result.get("words") or [])
                if isinstance(w, dict) and (w.get("score", 100) or 100) < 80 and w.get("word")]
        db.add(VocabPronLog(
            id=uuid.uuid4(), student_id=student_id, reference_text=ref[:200], word_id=wid,
            overall=int(result.get("overall") or 0),
            accuracy=result.get("accuracy"), fluency=result.get("fluency"),
            completion=result.get("completion"), weak=weak or None))
        await db.flush()
    except Exception:  # noqa: BLE001
        pass


async def vocab_overview(db: AsyncSession, *, student_id: uuid.UUID) -> dict:
    """学生词力通学情总览：各熟练度词数 + 待学 + 错词 + 连续天数 + 发音概况。"""
    from collections import Counter
    from app.models.d5_learning import VocabPronLog
    from app.services import checkin_service

    # 各熟练度计数
    rows = (await db.execute(
        select(VocabularyLearning.level, func.count())
        .where(VocabularyLearning.student_id == student_id)
        .group_by(VocabularyLearning.level)
    )).all()
    by_level = {str(lv): int(c) for lv, c in rows}
    learned_total = sum(by_level.values())
    # 错词数
    wrong_total = (await db.execute(
        select(func.count()).select_from(VocabularyLearning).where(
            VocabularyLearning.student_id == student_id, VocabularyLearning.is_wrong.is_(True))
    )).scalar_one()
    # 到期待复习
    now = datetime.now(timezone.utc)
    due_total = (await db.execute(
        select(func.count()).select_from(VocabularyLearning).where(
            VocabularyLearning.student_id == student_id, VocabularyLearning.next_review_at <= now)
    )).scalar_one()
    # 可学新词（scope 口径）
    student = (await db.execute(select(User).where(User.id == student_id))).scalar_one()
    remaining_new = len(await _ordered_new_words(db, student=student))

    # 连续天数
    st = await checkin_service.get_checkin_status(db, student_id=student_id)

    # 发音概况（最近 50 次）
    plogs = (await db.execute(
        select(VocabPronLog).where(VocabPronLog.student_id == student_id)
        .order_by(VocabPronLog.created_at.desc()).limit(50)
    )).scalars().all()
    plogs = list(reversed(plogs))   # 时间正序
    pron = None
    if plogs:
        def _avg(vals):
            v = [x for x in vals if x is not None]
            return int(round(sum(v) / len(v))) if v else None
        bars = [int(p.overall) for p in plogs]
        wc: Counter = Counter()
        for p in plogs:
            for w in (p.weak or []):
                wc[str(w)] += 1
        trend = "flat"
        if len(bars) >= 2:
            mid = len(bars) // 2
            f, s = _avg(bars[:mid]) or 0, _avg(bars[mid:]) or 0
            trend = "up" if s - f >= 5 else ("down" if f - s >= 5 else "flat")
        pron = {
            "count": len(plogs), "avg": _avg(bars),
            "accuracy": _avg([p.accuracy for p in plogs]),
            "fluency": _avg([p.fluency for p in plogs]),
            "completion": _avg([p.completion for p in plogs]),
            "weak_words": [w for w, _ in wc.most_common(8)],
            "trend": trend, "bars": bars[-14:],
        }

    return {
        "mastered": by_level.get("mastered", 0),
        "review": by_level.get("review", 0),
        "learning": by_level.get("learning", 0),
        "new_learned": by_level.get("new", 0),
        "learned_total": learned_total,
        "wrong_total": int(wrong_total),
        "due_total": int(due_total),
        "remaining_new": remaining_new,
        "current_streak": st["current_streak"],
        "longest_streak": st["longest_streak"],
        "pron": pron,
    }


async def class_vocab_stats(
    db: AsyncSession, *, students: list[tuple],
) -> dict:
    """班级词力通统计：人均学词/掌握、错词、发音均分、班级薄弱词、活跃数、逐生明细。

    students: [(student_id, nickname), ...]
    """
    from collections import Counter
    from datetime import timedelta
    from app.models.d5_learning import VocabPronLog, StudyCheckin

    ids = [s[0] for s in students]
    names = {s[0]: (s[1] or "学生") for s in students}
    n = len(ids)
    if not ids:
        return {"student_count": 0, "total_learned": 0, "total_mastered": 0,
                "avg_learned": 0, "avg_mastered": 0, "wrong_total": 0,
                "active_count": 0, "pron": None, "class_weak_words": [], "students": []}

    # 学词/掌握（按生分组）
    learned: dict = {}
    mastered: dict = {}
    rows = (await db.execute(
        select(VocabularyLearning.student_id, VocabularyLearning.level, func.count())
        .where(VocabularyLearning.student_id.in_(ids))
        .group_by(VocabularyLearning.student_id, VocabularyLearning.level)
    )).all()
    for sid, lv, c in rows:
        learned[sid] = learned.get(sid, 0) + int(c)
        if str(lv) == "mastered":
            mastered[sid] = mastered.get(sid, 0) + int(c)
    # 错词
    wrong: dict = {}
    wrows = (await db.execute(
        select(VocabularyLearning.student_id, func.count())
        .where(VocabularyLearning.student_id.in_(ids), VocabularyLearning.is_wrong.is_(True))
        .group_by(VocabularyLearning.student_id)
    )).all()
    for sid, c in wrows:
        wrong[sid] = int(c)
    # 发音均分（按生）
    pron_avg: dict = {}
    prows = (await db.execute(
        select(VocabPronLog.student_id, func.avg(VocabPronLog.overall), func.count())
        .where(VocabPronLog.student_id.in_(ids))
        .group_by(VocabPronLog.student_id)
    )).all()
    pron_tested = 0
    for sid, avg, c in prows:
        pron_avg[sid] = int(round(float(avg))) if avg is not None else None
        pron_tested += 1
    # 班级薄弱词（聚合所有跟读 weak）
    wc: Counter = Counter()
    wkrows = (await db.execute(
        select(VocabPronLog.weak).where(VocabPronLog.student_id.in_(ids), VocabPronLog.weak.isnot(None))
    )).all()
    for (weak,) in wkrows:
        for w in (weak or []):
            wc[str(w)] += 1
    # 活跃（近7天有学习记录）
    since = datetime.now(timezone.utc).date() - timedelta(days=7)
    active_rows = (await db.execute(
        select(func.count(func.distinct(StudyCheckin.student_id)))
        .where(StudyCheckin.student_id.in_(ids), StudyCheckin.checkin_date >= since)
    )).scalar_one()

    total_learned = sum(learned.values())
    total_mastered = sum(mastered.values())
    pron_vals = [v for v in pron_avg.values() if v is not None]
    class_pron_avg = int(round(sum(pron_vals) / len(pron_vals))) if pron_vals else None

    rows_out = sorted(
        [{
            "student_id": str(sid), "nickname": names[sid],
            "learned": learned.get(sid, 0), "mastered": mastered.get(sid, 0),
            "wrong": wrong.get(sid, 0), "pron_avg": pron_avg.get(sid),
        } for sid in ids],
        key=lambda r: (-r["mastered"], -r["learned"]),
    )

    return {
        "student_count": n,
        "total_learned": total_learned,
        "total_mastered": total_mastered,
        "avg_learned": round(total_learned / n, 1),
        "avg_mastered": round(total_mastered / n, 1),
        "wrong_total": sum(wrong.values()),
        "active_count": int(active_rows),
        "pron": ({"tested_students": pron_tested, "avg": class_pron_avg}
                 if pron_tested else None),
        "class_weak_words": [w for w, _ in wc.most_common(8)],
        "students": rows_out,
    }


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
    return {"added": True, "found": True, "word": row[1], "word_id": str(row[0]),
            "already": (res.rowcount or 0) == 0}


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


def _derive_gate(is_new: bool, lr=None) -> str:
    """三关(A)派生:新词=form(走满形→义→用);复习词=首个未达标维度。
    义关=接收(mastery_recep),用关=产出(mastery_prod)+迁移(transfer_ok);阈值复用 vocab_probe。"""
    if is_new or lr is None:
        return "form"
    from app.services.vocab_probe_service import PROD_MASTERED, RECEP_MASTERED
    if float(lr.mastery_recep or 0) < RECEP_MASTERED:
        return "meaning"
    if float(lr.mastery_prod or 0) < PROD_MASTERED or not bool(lr.transfer_ok):
        return "use"
    return "done"


def _to_card(w: VocabularyWord, *, level: str, is_new: bool, lr=None) -> WordCardOut:
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
        gate=_derive_gate(is_new, lr),
        image_urls=(w.image_urls if pub else None),
        en_description=(w.en_description if pub else None),
        word_audio_url=(w.word_audio_url if pub else None),
        en_desc_audio_url=(w.en_desc_audio_url if pub else None),
    )


# ── 学习设置（每生一份，不再绑定会员档位）────────────────────────────────────
_WPG_MIN, _WPG_MAX = 1, 50
_REP_MIN, _REP_MAX = 1, 5


def _setting_dict(row) -> dict:
    if row is None:
        return {"words_per_group": 5, "reps_per_group": 1, "wrong_carry_threshold": 2,
                "include_general_vocab": False, "general_vocab_list_id": None}
    return {
        "words_per_group": int(row.words_per_group),
        "reps_per_group": int(row.reps_per_group),
        "wrong_carry_threshold": int(getattr(row, "wrong_carry_threshold", 2) or 2),
        "include_general_vocab": bool(getattr(row, "include_general_vocab", False)),
        "general_vocab_list_id": (str(row.general_vocab_list_id)
                                  if getattr(row, "general_vocab_list_id", None) else None),
    }


async def get_vocab_settings(db: AsyncSession, *, student_id: uuid.UUID) -> dict:
    row = (await db.execute(
        select(StudentVocabSetting).where(StudentVocabSetting.student_id == student_id)
    )).scalar_one_or_none()
    return _setting_dict(row)


async def set_vocab_settings(
    db: AsyncSession, *, student_id: uuid.UUID, words_per_group: int, reps_per_group: int,
    wrong_carry_threshold: int = 2, include_general_vocab: bool = False,
    general_vocab_list_id: uuid.UUID | None = None,
) -> dict:
    wpg = max(_WPG_MIN, min(int(words_per_group), _WPG_MAX))
    rep = max(_REP_MIN, min(int(reps_per_group), _REP_MAX))
    thr = max(1, min(int(wrong_carry_threshold), 5))
    row = (await db.execute(
        select(StudentVocabSetting).where(StudentVocabSetting.student_id == student_id)
    )).scalar_one_or_none()
    if row is None:
        row = StudentVocabSetting(
            id=uuid.uuid4(), student_id=student_id,
            words_per_group=wpg, reps_per_group=rep, wrong_carry_threshold=thr,
            include_general_vocab=include_general_vocab, general_vocab_list_id=general_vocab_list_id)
        db.add(row)
    else:
        row.words_per_group, row.reps_per_group, row.wrong_carry_threshold = wpg, rep, thr
        row.include_general_vocab = include_general_vocab
        row.general_vocab_list_id = general_vocab_list_id
    await db.flush()
    return _setting_dict(row)


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
    review_words = [_to_card(w, level=str(lr.level), is_new=False, lr=lr) for lr, w in review_rows]

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


async def get_daily_task_scoped(db: AsyncSession, *, student_id: uuid.UUID,
                                word_ids: list[uuid.UUID]) -> DailyTaskOut:
    """限定在给定 word_ids(某单元/批次)内的一组学习内容,结构同 daily-task,供单词精讲用。
    review=这些词里到期的;new=这些词里尚无学习记录的(按「每组词数」限量,保持传入顺序)。
    学完一组后前端 reload 再取下一组——已学词进入复习/移出新词,自然逐组推进整批。"""
    if not word_ids:
        return DailyTaskOut(new_words=[], review_words=[], new_count=0, review_count=0, new_limit=0)
    now = datetime.now(timezone.utc)
    wids = list(dict.fromkeys(word_ids))
    settings = await get_vocab_settings(db, student_id=student_id)
    new_limit = settings["words_per_group"]
    # 复习:这些词里到期的学习记录(错词优先,同 daily-task);限「每组词数」——
    # 范围内没排上的到期词下一组 reload 再来(逐组推进,避免一组把整个范围的到期词全上)。
    review_rows = (await db.execute(
        select(VocabularyLearning, VocabularyWord)
        .join(VocabularyWord, VocabularyWord.id == VocabularyLearning.word_id)
        .where(VocabularyLearning.student_id == student_id,
               VocabularyLearning.word_id.in_(wids),
               VocabularyLearning.next_review_at <= now)
        .order_by(VocabularyLearning.is_wrong.desc(), VocabularyLearning.wrong_count.desc(),
                  VocabularyLearning.next_review_at)
        .limit(new_limit))).all()
    review_words = [_to_card(w, level=str(lr.level), is_new=False, lr=lr) for lr, w in review_rows]
    # 新词:这些词里尚无学习记录的,按传入顺序取前「每组词数」个
    learned = set((await db.execute(
        select(VocabularyLearning.word_id).where(
            VocabularyLearning.student_id == student_id,
            VocabularyLearning.word_id.in_(wids)))).scalars().all())
    new_ids = [wid for wid in wids if wid not in learned][:new_limit]
    new_map = {w.id: w for w in (await db.execute(
        select(VocabularyWord).where(VocabularyWord.id.in_(new_ids)))).scalars().all()} if new_ids else {}
    new_words = [_to_card(new_map[wid], level="new", is_new=True) for wid in new_ids if wid in new_map]
    return DailyTaskOut(new_words=new_words, review_words=review_words,
                        new_count=len(new_words), review_count=len(review_words), new_limit=new_limit)


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


# ── 词力通·考试出词(中考/高考 考纲词+短语 × 频档;P2)─────────────────────────────
def resolve_exam_target(user: "User") -> str:
    """学生考试目标:显式 exam_target 优先;否则按年级派生(含「高」→senior,否则 junior)。"""
    t = getattr(user, "exam_target", None)
    if t in ("junior", "senior"):
        return t
    return "senior" if "高" in (user.preferred_grade or "") else "junior"


_TRACK_TITLE = {"word": "单词", "phrase": "短语"}
_BAND_LABEL = {"high": "高频", "mid": "中频", "low": "低频", "none": "未分档"}


async def exam_vocab_overview(db: AsyncSession, *, student: "User") -> dict:
    """词力通考试页概览:两轨(单词/短语)× 频档(高/中/低)的 total/studied。
    未上架对应考纲词库 → available=False(前端提示词库未上架)。"""
    from app.services import vocab_list_service as vls
    target = resolve_exam_target(student)
    label = "高考" if target == "senior" else "中考"
    word_list = await vls.resolve_word_list(db, exam_level=target)
    phrase_list = await vls.resolve_phrase_list(db, exam_level=target)
    if word_list is None and phrase_list is None:
        return {"exam_target": target, "exam_label": label, "available": False, "tracks": []}

    async def _track(wtype: str, list_id):
        if list_id is None:
            return None
        ov = await vls.exam_band_overview(db, list_id=list_id, student_id=student.id)
        # 只显示有词的档(未反哺库/短语库全落未分档;避免一堆「暂无」的空频档行)
        order = ("high", "mid", "low", "none")
        bands = [{"band": b, "label": _BAND_LABEL[b], "total": ov[b]["total"], "studied": ov[b]["studied"]}
                 for b in order if ov[b]["total"] > 0]
        return {"type": wtype, "title": _TRACK_TITLE[wtype],
                "total": sum(x["total"] for x in bands),
                "studied": sum(x["studied"] for x in bands), "bands": bands}

    tracks = [t for t in (await _track("word", word_list), await _track("phrase", phrase_list)) if t]
    return {"exam_target": target, "exam_label": label, "available": True, "tracks": tracks}


async def exam_daily_task(db: AsyncSession, *, student: "User", wtype: str, band: str) -> DailyTaskOut:
    """某轨×频档 的今日一组任务:单词轨→考纲词库、短语轨→短语库,限定该档词集(复用 scoped 流)。"""
    from app.core.exceptions import AppError
    from app.services import vocab_list_service as vls
    target = resolve_exam_target(student)
    list_id = (await vls.resolve_phrase_list(db, exam_level=target)) if wtype == "phrase" \
        else (await vls.resolve_word_list(db, exam_level=target))
    if list_id is None:
        raise AppError(code=400, message="该轨的词库尚未上架")
    word_ids = await vls.band_word_ids(db, list_id=list_id, band=band)
    if not word_ids:
        raise AppError(code=404, message="该档暂无词条")
    return await get_daily_task_scoped(db, student_id=student.id, word_ids=word_ids)
