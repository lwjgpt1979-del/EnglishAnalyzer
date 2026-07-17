"""词力通词汇学习 API（P1 / D-100）。"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query
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
    vocab_probe_service, vocab_pin_service,
)

from pydantic import BaseModel, Field

router = APIRouter(prefix="/vocabulary", tags=["vocabulary"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


class VocabSettings(BaseModel):
    words_per_group: int = Field(5, ge=1, le=50)
    reps_per_group: int = Field(1, ge=1, le=5)
    wrong_carry_threshold: int = Field(2, ge=1, le=5)
    include_general_vocab: bool = False                 # 通用词库 opt-in(R5 收尾)
    general_vocab_list_id: uuid.UUID | None = None      # 指定通用词库;空=任一已发布库


class AddWordIn(BaseModel):
    word: str = Field(..., min_length=1, max_length=60)


@router.post("/add-word", response_model=BaseResponse[dict])
async def add_word(body: AddWordIn, db: DbDep, current_user: UserDep):
    """用户手动添加生词到自己的词源池（仅词典已有的词）。"""
    await get_rls_db(db, str(current_user.id))
    res = await vocabulary_service.add_manual_word(
        db, student_id=current_user.id, word=body.word)
    if res.get("added"):
        await db.commit()
        # 增量钩子:学生主动加的词大概率马上会学到,后台预生成理解探针
        if res.get("word_id"):
            vocab_probe_service.enqueue_probe_gen([res["word_id"]])
    return make_ok(res)


@router.get("/overview", response_model=BaseResponse[dict])
async def vocab_overview(db: DbDep, current_user: UserDep):
    """学生词力通学情总览：词数分布 + 错词 + 待复习 + 连续天数 + 发音概况。"""
    await get_rls_db(db, str(current_user.id))
    return make_ok(await vocabulary_service.vocab_overview(db, student_id=current_user.id))


@router.get("/settings", response_model=BaseResponse[VocabSettings])
async def get_settings(db: DbDep, current_user: UserDep):
    """词力通学习设置：每组词数 / 每组遍数（每生一份，不绑定会员档位）。"""
    s = await vocabulary_service.get_vocab_settings(db, student_id=current_user.id)
    return make_ok(VocabSettings(**s))


@router.put("/settings", response_model=BaseResponse[VocabSettings])
async def put_settings(body: VocabSettings, db: DbDep, current_user: UserDep):
    s = await vocabulary_service.set_vocab_settings(
        db, student_id=current_user.id,
        words_per_group=body.words_per_group, reps_per_group=body.reps_per_group,
        wrong_carry_threshold=body.wrong_carry_threshold,
        include_general_vocab=body.include_general_vocab,
        general_vocab_list_id=body.general_vocab_list_id)
    await db.commit()
    return make_ok(VocabSettings(**s))


@router.get("/daily-task", response_model=BaseResponse[DailyTaskOut])
async def daily_task(db: DbDep, current_user: UserDep):
    """今日词力通任务：到期复习词 + 新词（按会员档位上限）。"""
    await get_rls_db(db, str(current_user.id))
    task = await vocabulary_service.get_daily_task(db, student_id=current_user.id)
    return make_ok(task)


@router.post("/shadow-score", response_model=BaseResponse[ShadowScoreResult])
async def shadow_score(body: ShadowScoreIn, db: DbDep, current_user: UserDep):
    """跟读发音评分（会员专享）：对单词/例句的跟读录音评分（腾讯 SOE）。

    无有效会员 → 402，前端引导开通会员。
    """
    from app.services import entitlement_service
    await entitlement_service.require_feature(
        db, user_id=current_user.id, key="vocab.shadow", code=402,
        message="跟读为会员专享功能，开通会员后即可使用 🎤")
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
    # 记录发音评测，供学情报表（best-effort）
    try:
        await get_rls_db(db, str(current_user.id))
        await vocabulary_service.log_pron(
            db, student_id=current_user.id, reference_text=body.reference_text, result=result)
        await db.commit()
    except Exception:  # noqa: BLE001
        pass
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


@router.get("/{word_id}/probes", response_model=BaseResponse[dict])
async def get_word_probes(word_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """R9 理解探针:语境句 + 接收(cloze/多义)+ 产出(搭配 colloc / 造句 produce),不含答案。"""
    from app.core.exceptions import AppError
    from app.models.d5_learning import VocabularyWord, VocabularyLearning
    import sqlalchemy as sa
    await get_rls_db(db, str(current_user.id))
    word = (await db.execute(sa.select(VocabularyWord).where(VocabularyWord.id == word_id))).scalar_one_or_none()
    if word is None:
        raise AppError(code=404, message="单词不存在")
    out = await vocab_probe_service.comprehension_probes(db, student_id=current_user.id, word=word)
    await db.commit()   # ensure_probes 可能写了 probes_json 缓存
    lr = (await db.execute(sa.select(VocabularyLearning).where(
        VocabularyLearning.student_id == current_user.id, VocabularyLearning.word_id == word_id))).scalar_one_or_none()
    recep = float(lr.mastery_recep) if (lr and lr.mastery_recep is not None) else 0.0
    prod = float(lr.mastery_prod) if (lr and lr.mastery_prod is not None) else 0.0
    transfer_ok = bool(lr.transfer_ok) if lr else False
    return make_ok({
        "context": out["context"],
        "probes": [{"key": p["key"], "kind": p["kind"], "prompt": p["prompt"], "options": p["options"]} for p in out["probes"]],
        "produce": out.get("produce"),
        "recep": round(recep, 4), "prod": round(prod, 4), "transfer_ok": transfer_ok,
        "mastered": recep >= vocab_probe_service.RECEP_MASTERED and prod >= vocab_probe_service.PROD_MASTERED and transfer_ok,
    })


@router.get("/{word_id}/transfer", response_model=BaseResponse[dict])
async def get_word_transfer(word_id: uuid.UUID, db: DbDep, current_user: UserDep, exclude: str = ""):
    """R9.3 迁移题:同词新语境的语境填空(与 exclude 原句不同)。无新语境→probe 为空。"""
    from app.core.exceptions import AppError
    from app.models.d5_learning import VocabularyWord
    import sqlalchemy as sa
    await get_rls_db(db, str(current_user.id))
    word = (await db.execute(sa.select(VocabularyWord).where(VocabularyWord.id == word_id))).scalar_one_or_none()
    if word is None:
        raise AppError(code=404, message="单词不存在")
    out = await vocab_probe_service.transfer_probe(db, student_id=current_user.id, word=word, exclude_text=exclude or None)
    await db.commit()
    if not out:
        return make_ok({"context": None, "probe": None})
    return make_ok({"context": out["context"],
                    "probe": {"key": out["probe"]["key"], "kind": out["probe"]["kind"],
                              "prompt": out["probe"]["prompt"], "options": out["probe"]["options"]}})


@router.post("/{word_id}/transfer-submit", response_model=BaseResponse[dict])
async def submit_word_transfer(word_id: uuid.UUID, db: DbDep, current_user: UserDep,
                               answer: str = Body(..., embed=True)):
    """R9.3 提交迁移题:判分 → 接收 BKT + 置 transfer_ok;verdict=transferred/memorized。"""
    await get_rls_db(db, str(current_user.id))
    res = await vocab_probe_service.submit_transfer(
        db, student_id=current_user.id, word_id=word_id, answer=answer)
    await db.commit()
    return make_ok(res)


@router.post("/{word_id}/probe", response_model=BaseResponse[dict])
async def submit_word_probe(word_id: uuid.UUID, db: DbDep, current_user: UserDep,
                            key: str = Body(...), answer: str = Body(...)):
    """R9 提交客观探针(cloze/多义/搭配):判分 → 接收或产出掌握度 BKT → 错词本。"""
    await get_rls_db(db, str(current_user.id))
    res = await vocab_probe_service.submit_probe(
        db, student_id=current_user.id, word_id=word_id, key=key, answer=answer)
    await db.commit()
    return make_ok(res)


@router.post("/{word_id}/produce", response_model=BaseResponse[dict])
async def submit_word_produce(word_id: uuid.UUID, db: DbDep, current_user: UserDep,
                              sentence: str = Body(..., embed=True)):
    """R9.2 提交造句(产出):LLM 维度 rubric 评分 → 产出掌握度 prod BKT。"""
    await get_rls_db(db, str(current_user.id))
    res = await vocab_probe_service.submit_produce(
        db, student_id=current_user.id, word_id=word_id, sentence=sentence)
    await db.commit()
    return make_ok(res)


@router.post("/group-recep/probes", response_model=BaseResponse[dict])
async def group_recep_probes(db: DbDep, current_user: UserDep, word_ids: list[uuid.UUID] = Body(..., embed=True)):
    """R9.5 成组混合接收检测题面:N 句挖空 + 共享词库(防经验主义,答案逐句不同)。"""
    await get_rls_db(db, str(current_user.id))
    out = await vocab_probe_service.group_recep_quiz(db, student_id=current_user.id, word_ids=word_ids)
    await db.commit()
    return make_ok(out)


@router.post("/group-recep/submit", response_model=BaseResponse[dict])
async def group_recep_submit(db: DbDep, current_user: UserDep, answers: dict[str, str] = Body(..., embed=True)):
    """R9.5 提交成组检测:逐词判分 → 接收掌握度 BKT。answers={word_id: 所选词}。"""
    await get_rls_db(db, str(current_user.id))
    res = await vocab_probe_service.submit_group_recep(db, student_id=current_user.id, answers=answers)
    await db.commit()
    return make_ok(res)


# ── R9.6 优先学清单 + 拍照加词 ──
@router.get("/pins", response_model=BaseResponse[dict])
async def list_pins(db: DbDep, current_user: UserDep):
    """优先学清单(学生主动 pin 的词,级别高的在前)。"""
    await get_rls_db(db, str(current_user.id))
    return make_ok({"pins": await vocab_pin_service.list_pins(db, student_id=current_user.id)})


@router.get("/pinnable", response_model=BaseResponse[dict])
async def pinnable(db: DbDep, current_user: UserDep):
    """可挑选加入优先学的词:本人候选(作业/试卷/错题)+ 当前学期教材词,标注是否已 pin。"""
    await get_rls_db(db, str(current_user.id))
    return make_ok({"words": await vocab_pin_service.pinnable_words(db, student_id=current_user.id)})


@router.get("/intensive/homework/batches", response_model=BaseResponse[dict])
async def hw_word_batches(db: DbDep, current_user: UserDep):
    """作业精讲·单词:按来源卷(批次)归组的词清单概览。"""
    from app.services import vocab_intensive_service
    return make_ok({"batches": await vocab_intensive_service.homework_batches(db, student_id=current_user.id)})


@router.get("/intensive/homework/words", response_model=BaseResponse[dict])
async def hw_word_list(db: DbDep, current_user: UserDep, paper_id: uuid.UUID = Query(...)):
    """作业精讲·单词:某批次(卷)里的词 + 词库详解。"""
    from app.services import vocab_intensive_service
    return make_ok({"words": await vocab_intensive_service.homework_words(
        db, student_id=current_user.id, paper_id=paper_id)})


@router.get("/intensive/course/units", response_model=BaseResponse[dict])
async def course_word_units(db: DbDep, current_user: UserDep,
                            grade: str | None = Query(None), semester: str | None = Query(None)):
    """课程精讲·单词:某学期单元(默认当前学期)+ 每单元词数/已学数 + 闯关解锁/学期通关。"""
    from app.services import vocab_intensive_service
    return make_ok(await vocab_intensive_service.course_units(
        db, student_id=current_user.id, grade=grade, semester=semester))


@router.get("/intensive/course/words", response_model=BaseResponse[dict])
async def course_word_list(db: DbDep, current_user: UserDep, unit_id: uuid.UUID = Query(...)):
    """课程精讲·单词:某教材单元的词 + 词库详解(带 studied)。"""
    from app.services import vocab_intensive_service
    return make_ok({"words": await vocab_intensive_service.course_words(
        db, unit_id=unit_id, student_id=current_user.id)})


@router.get("/intensive/course/task", response_model=BaseResponse[DailyTaskOut])
async def course_intensive_task(db: DbDep, current_user: UserDep, unit_id: uuid.UUID = Query(...)):
    """课程精讲·单词「完整词力通流程」:限定在该单元词范围内的一组任务(结构同 daily-task)。"""
    await get_rls_db(db, str(current_user.id))
    from app.services import vocab_intensive_service
    wids = await vocab_intensive_service.course_word_ids(db, unit_id=unit_id)
    return make_ok(await vocabulary_service.get_daily_task_scoped(
        db, student_id=current_user.id, word_ids=wids))


@router.get("/intensive/homework/task", response_model=BaseResponse[DailyTaskOut])
async def homework_intensive_task(db: DbDep, current_user: UserDep, paper_id: uuid.UUID = Query(...)):
    """作业精讲·单词「完整词力通流程」:限定在该批次(卷)词范围内的一组任务(结构同 daily-task)。"""
    await get_rls_db(db, str(current_user.id))
    from app.services import vocab_intensive_service
    wids = await vocab_intensive_service.homework_word_ids(
        db, student_id=current_user.id, paper_id=paper_id)
    return make_ok(await vocabulary_service.get_daily_task_scoped(
        db, student_id=current_user.id, word_ids=wids))


@router.post("/pins", response_model=BaseResponse[dict])
async def add_pins(db: DbDep, current_user: UserDep,
                   word_ids: list[uuid.UUID] = Body(..., embed=True), priority: int = Body(1),
                   paper_id: uuid.UUID | None = Body(None)):
    """从来源库挑选加入优先学(可设级别)。paper_id:来源卷(作业精讲按批次归组)。"""
    await get_rls_db(db, str(current_user.id))
    r = await vocab_pin_service.pin_words(db, student_id=current_user.id, word_ids=word_ids,
                                          priority=priority, source_paper_id=paper_id)
    await db.commit()
    return make_ok(r)


@router.post("/intensive/homework/add", response_model=BaseResponse[dict])
async def add_homework_candidates(db: DbDep, current_user: UserDep,
                                  word_ids: list[uuid.UUID] = Body(..., embed=True),
                                  paper_id: uuid.UUID = Body(...)):
    """把试卷生词加入「作业待学习」→ 作业精讲按批次归组(候选,不进词力通优先学)。"""
    await get_rls_db(db, str(current_user.id))
    r = await vocab_pin_service.add_paper_candidates(
        db, student_id=current_user.id, word_ids=word_ids, source_paper_id=paper_id)
    await db.commit()
    return make_ok(r)


@router.post("/{word_id}/ensure-media", response_model=BaseResponse[dict])
async def ensure_word_media_api(word_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """某词若无已发布媒体,即时生成配图/发音/英文释义/例句并发布(全学生共享、落词条缓存,
    同词不二次付费)。返回更新后的单词卡片数据。供长难句/作业「加入学习」对无媒体词即时补齐。"""
    from app.core.exceptions import AppError
    from app.services import vocab_media_service
    from app.services.vocab_intensive_service import _word_out
    w = await vocab_media_service.ensure_word_media(db, word_id=word_id)
    if w is None:
        raise AppError(code=404, message="单词不存在")
    return make_ok(_word_out(w))


@router.put("/pins/{word_id}", response_model=BaseResponse[dict])
async def update_pin(word_id: uuid.UUID, db: DbDep, current_user: UserDep, priority: int = Body(..., embed=True)):
    """调整某词优先级别(≤0 即移出优先学)。"""
    await get_rls_db(db, str(current_user.id))
    await vocab_pin_service.set_priority(db, student_id=current_user.id, word_id=word_id, priority=priority)
    await db.commit()
    return make_ok({"ok": True})


@router.delete("/pins/{word_id}", response_model=BaseResponse[dict])
async def remove_pin(word_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """移出优先学(保留为普通候选)。"""
    await get_rls_db(db, str(current_user.id))
    await vocab_pin_service.unpin(db, student_id=current_user.id, word_id=word_id)
    await db.commit()
    return make_ok({"ok": True})


@router.post("/pins/from-photo", response_model=BaseResponse[dict])
async def pin_from_photo(db: DbDep, current_user: UserDep,
                         image_url: str = Body(..., embed=True), priority: int = Body(1)):
    """拍照加词:图片 OCR 抽英文词 → 词典命中者加入优先学。返回 {recognized, pinned, not_found}。"""
    await get_rls_db(db, str(current_user.id))
    r = await vocab_pin_service.pin_from_photo(db, student_id=current_user.id, image_url=image_url, priority=priority)
    await db.commit()
    return make_ok(r)


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
            examples=w.examples, phrases=w.phrases,
            wrong_count=lr.wrong_count, level=str(lr.level),
            image_urls=(w.image_urls if _pub(w) else None),
            en_description=(w.en_description if _pub(w) else None),
            word_audio_url=(w.word_audio_url if _pub(w) else None),
            en_desc_audio_url=(w.en_desc_audio_url if _pub(w) else None),
        )
        for lr, w in rows
    ]
    return make_ok(WrongWordListOut(total=total, items=items))


class CheckinIn(BaseModel):
    wrong_count: int = Field(0, ge=0)


@router.post("/checkin", response_model=BaseResponse[CheckinResult])
async def checkin(db: DbDep, current_user: UserDep, body: CheckinIn | None = None):
    """词力通完成一组学习：记入当日（日历=学习日志）+ 累加当日错题数。"""
    await get_rls_db(db, str(current_user.id))
    wrong = body.wrong_count if body else 0
    row, progress = await checkin_service.record_checkin(
        db, student_id=current_user.id, wrong_delta=wrong)
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
