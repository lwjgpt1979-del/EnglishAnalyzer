"""词力通词汇学习 API（P1 / D-100）。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.vocabulary import (
    CheckinBadge,
    CheckinResult,
    CheckinStatusOut,
    DailyTaskOut,
    MakeUpIn,
    MakeUpResult,
    ShadowScoreIn,
    ShadowScoreResult,
    StudentCalendarOut,
    VocabAnswerIn,
    VocabAnswerResult,
    WrongWordItem,
    WrongWordListOut,
)
from app.services import (
    checkin_service, pronunciation_service, speech_score_service, vocabulary_service,
)

from pydantic import BaseModel, Field

router = APIRouter(prefix="/vocabulary", tags=["vocabulary"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


class VocabSettings(BaseModel):
    words_per_group: int = Field(5, ge=1, le=50)
    reps_per_group: int = Field(1, ge=1, le=5)


@router.get("/settings", response_model=BaseResponse[VocabSettings])
async def get_settings(db: DbDep, current_user: UserDep):
    """词力通学习设置：每组词数 / 每组遍数（每生一份，不绑定会员档位）。"""
    s = await vocabulary_service.get_vocab_settings(db, student_id=current_user.id)
    return make_ok(VocabSettings(**s))


@router.put("/settings", response_model=BaseResponse[VocabSettings])
async def put_settings(body: VocabSettings, db: DbDep, current_user: UserDep):
    s = await vocabulary_service.set_vocab_settings(
        db, student_id=current_user.id,
        words_per_group=body.words_per_group, reps_per_group=body.reps_per_group)
    await db.commit()
    return make_ok(VocabSettings(**s))


@router.get("/daily-task", response_model=BaseResponse[DailyTaskOut])
async def daily_task(db: DbDep, current_user: UserDep):
    """今日词力通任务：到期复习词 + 新词（按会员档位上限）。"""
    await get_rls_db(db, str(current_user.id))
    task = await vocabulary_service.get_daily_task(db, student_id=current_user.id)
    return make_ok(task)


@router.post("/shadow-score", response_model=BaseResponse[ShadowScoreResult])
async def shadow_score(body: ShadowScoreIn, current_user: UserDep):
    """跟读发音评分：对单词/例句的跟读录音评分（腾讯 SOE；无密钥/无音频走 dev-mock）。"""
    import base64 as _b64
    audio_bytes = b""
    if body.audio:
        try:
            audio_bytes = _b64.b64decode(body.audio)
        except Exception:  # noqa: BLE001
            audio_bytes = b""
    mode = "word" if len(body.reference_text.split()) <= 1 else "sentence"
    result = await pronunciation_service.assess(
        reference_text=body.reference_text, audio_bytes=audio_bytes or None,
        mode=mode, audio_format=body.audio_format or "mp3")
    return make_ok(ShadowScoreResult(**result))


@router.post("/answer", response_model=BaseResponse[VocabAnswerResult])
async def answer(body: VocabAnswerIn, db: DbDep, current_user: UserDep):
    """提交一次作答，按 SM-2 更新记忆状态。"""
    await get_rls_db(db, str(current_user.id))
    result = await vocabulary_service.submit_answer(
        db,
        student_id=current_user.id,
        word_id=body.word_id,
        correct=body.correct,
        hesitant=body.hesitant,
    )
    await db.commit()
    return make_ok(result)


@router.get("/wrong-words", response_model=BaseResponse[WrongWordListOut])
async def wrong_words(db: DbDep, current_user: UserDep, skip: int = 0, limit: int = 50):
    """错词本：列出该生答错且未掌握的词（错得多的在前）。"""
    await get_rls_db(db, str(current_user.id))
    rows, total = await vocabulary_service.list_wrong_words(
        db, student_id=current_user.id, skip=skip, limit=limit,
    )

    def _pub(w) -> bool:
        return str(getattr(w, "media_status", "draft")) == "published"

    items = [
        WrongWordItem(
            word_id=w.id, word=w.word, phonetic=w.phonetic, definitions=w.definitions,
            wrong_count=lr.wrong_count, level=str(lr.level),
            image_urls=(w.image_urls if _pub(w) else None),
            en_description=(w.en_description if _pub(w) else None),
            word_audio_url=(w.word_audio_url if _pub(w) else None),
            en_desc_audio_url=(w.en_desc_audio_url if _pub(w) else None),
        )
        for lr, w in rows
    ]
    return make_ok(WrongWordListOut(total=total, items=items))


@router.post("/checkin", response_model=BaseResponse[CheckinResult])
async def checkin(db: DbDep, current_user: UserDep):
    """词力通完成会话打卡：后端实算今日完成度，达标才发放。"""
    await get_rls_db(db, str(current_user.id))
    row, progress = await checkin_service.record_checkin(db, student_id=current_user.id)
    if row is None:
        return make_ok(CheckinResult(
            completed=False,
            review_due=progress["review_due"],
            new_learned_today=progress["new_learned_today"],
            new_target=progress["new_target"],
        ))
    await db.commit()
    return make_ok(CheckinResult(
        completed=True,
        checkin_date=row.checkin_date.isoformat(),
        streak_days=row.streak_days,
        new_words_count=row.new_words_count,
        review_done=row.review_done,
        review_due=progress["review_due"],
        new_learned_today=progress["new_learned_today"],
        new_target=progress["new_target"],
    ))


@router.get("/checkin/status", response_model=BaseResponse[CheckinStatusOut])
async def checkin_status(db: DbDep, current_user: UserDep):
    """打卡状态：今日是否已打 + 当前连续 + 历史最高。"""
    await get_rls_db(db, str(current_user.id))
    st = await checkin_service.get_checkin_status(db, student_id=current_user.id)
    return make_ok(CheckinStatusOut(**st))


@router.get("/checkin/calendar", response_model=BaseResponse[StudentCalendarOut])
async def checkin_calendar(
    db: DbDep, current_user: UserDep, year: int | None = None, month: int | None = None,
):
    """学生本月打卡热力图 + 里程碑徽章。"""
    from datetime import datetime, timezone
    await get_rls_db(db, str(current_user.id))
    now = datetime.now(timezone.utc)
    cal = await checkin_service.get_month_calendar(
        db, student_id=current_user.id, year=year or now.year, month=month or now.month,
    )
    badges = checkin_service._badges(cal["longest_streak"])
    return make_ok(StudentCalendarOut(
        **cal, badges=[CheckinBadge(**b) for b in badges],
    ))


@router.post("/checkin/make-up", response_model=BaseResponse[MakeUpResult])
async def checkin_make_up(body: MakeUpIn, db: DbDep, current_user: UserDep):
    """补签某漏签日（恢复连续）。"""
    from datetime import date as _date
    await get_rls_db(db, str(current_user.id))
    d = _date.fromisoformat(body.date)
    res = await checkin_service.make_up_checkin(db, student_id=current_user.id, d=d)
    await db.commit()
    return make_ok(MakeUpResult(**res))
