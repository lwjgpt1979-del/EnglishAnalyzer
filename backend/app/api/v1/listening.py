"""听力练习 API（精听 + 答题/错题归集 + 跟读评测）。"""
from __future__ import annotations

import base64
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.exceptions import AppError
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.listening import ListeningBrief, ListeningDetail
from app.services import listening_service, pronunciation_service

router = APIRouter(prefix="/listening", tags=["listening"])

UserDep = Annotated[User, Depends(get_current_user)]
DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("/exercises", response_model=BaseResponse[list[ListeningBrief]])
async def list_exercises(current_user: UserDep):
    """听力素材列表（不含答案/原文）。"""
    return make_ok([ListeningBrief(**e) for e in listening_service.list_exercises()])


@router.get("/exercises/{exercise_id}", response_model=BaseResponse[ListeningDetail])
async def get_exercise(exercise_id: str, current_user: UserDep):
    """听力素材详情（含原文与答案，前端控制听前不展示）。"""
    return make_ok(ListeningDetail(**listening_service.get_exercise(exercise_id)))


@router.post("/exercises/{exercise_id}/submit", response_model=None)
async def submit(exercise_id: str, body: dict, db: DbDep, current_user: UserDep):
    """提交精听答案：判分 + 错题归集（§6.4）。body={answers:[int,...]}。"""
    await get_rls_db(db, str(current_user.id))
    answers = [int(x) for x in (body or {}).get("answers", [])]
    res = await listening_service.submit_answers(
        db, student_id=current_user.id, exercise_id=exercise_id, answers=answers)
    await db.commit()
    return make_ok(res)


@router.get("/wrong", response_model=None)
async def wrong_book(db: DbDep, current_user: UserDep):
    """听力错题库（§6.4），会员专享。"""
    from app.services import entitlement_service
    await entitlement_service.require_feature(
        db, user_id=current_user.id, key="listening.wrongbook", code=402,
        message="听力错题库为会员专享，开通会员后可用 🎧")
    await get_rls_db(db, str(current_user.id))
    return make_ok(await listening_service.list_wrong(db, student_id=current_user.id))


@router.post("/shadow", response_model=None)
async def shadow(body: dict, db: DbDep, current_user: UserDep):
    """听力句子跟读评测（§6.3），会员专享。body={reference_text, audio(base64), audio_format}。"""
    from app.services import entitlement_service
    await entitlement_service.require_feature(
        db, user_id=current_user.id, key="listening.shadow", code=402,
        message="跟读为会员专享功能，开通会员后即可使用 🎤")
    ref = ((body or {}).get("reference_text") or "").strip()
    if not ref:
        raise AppError(code=400, message="缺少跟读句子")
    audio_bytes = b""
    if (body or {}).get("audio"):
        try:
            audio_bytes = base64.b64decode(body["audio"])
        except Exception:  # noqa: BLE001
            audio_bytes = b""
    mode = "word" if len(ref.split()) <= 1 else "sentence"
    result = await pronunciation_service.assess(
        reference_text=ref, audio_bytes=audio_bytes or None,
        mode=mode, audio_format=(body or {}).get("audio_format") or "mp3")
    # 记录跟读分 → 薄弱句库（best-effort，§6.4）
    try:
        await get_rls_db(db, str(current_user.id))
        await listening_service.log_shadow(
            db, student_id=current_user.id, sentence=ref, score=int(result.get("overall", 0)))
        await db.commit()
    except Exception:  # noqa: BLE001
        pass
    return make_ok(result)


@router.get("/weak-sentences", response_model=None)
async def weak_sentences(db: DbDep, current_user: UserDep):
    """跟读薄弱句库（最高分<60，优先复练），会员专享。"""
    from app.services import entitlement_service
    await entitlement_service.require_feature(
        db, user_id=current_user.id, key="listening.shadow", code=402,
        message="跟读为会员专享功能，开通会员后即可使用 🎤")
    await get_rls_db(db, str(current_user.id))
    return make_ok(await listening_service.list_weak_sentences(db, student_id=current_user.id))
