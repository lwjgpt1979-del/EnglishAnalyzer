"""长难句 学生端 API（L2）:列长难句 / 取解析(主干分层/译文/句法点跳 R6 资源)。"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.database import get_db
from app.core.exceptions import AppError
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.kp import (
    LongSentenceItem, LongSentenceListOut, LongSentenceDetailOut, LongSentenceNodeRef,
    VerifyTypesOut, VerifyQuestionOut, VerifySubmitIn, VerifySubmitOut,
)
from app.schemas.vocabulary import ShadowScoreIn
from app.services import long_sentence_service as lss
from app.services import pronunciation_service
from app.services import tts_service
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/long-sentences", tags=["long-sentences"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.get("", response_model=BaseResponse[LongSentenceListOut])
async def list_long_sentences(
    db: DbDep, current_user: UserDep, node_id: uuid.UUID | None = None, limit: int = 50,
):
    """已发布长难句(平台共享+个人);可按句法 node 过滤。"""
    rows = await lss.list_published(db, node_id=node_id, owner_id=current_user.id, limit=limit)
    items = [LongSentenceItem(
        id=r.id, text=r.text, source_kind=r.source_kind,
        syntax_points=(r.analysis_json or {}).get("syntax_points", []),
    ) for r in rows]
    return make_ok(LongSentenceListOut(total=len(items), items=items))


@router.post("/shadow-score", response_model=BaseResponse[dict])
async def shadow_score(body: ShadowScoreIn, db: DbDep, current_user: UserDep):
    """长难句跟读发音评测:整句录音(base64)→ SOE 评分,返回 {overall, level, words, tip…}。
    dev-mock 或无音频时返回 mock 评分。"""
    import base64 as _b64
    audio_bytes = b""
    if body.audio:
        try:
            audio_bytes = _b64.b64decode(body.audio)
        except Exception:  # noqa: BLE001
            audio_bytes = b""
    result = await pronunciation_service.assess(
        reference_text=body.reference_text, audio_bytes=audio_bytes or None,
        mode="sentence", audio_format=body.audio_format or "mp3")
    return make_ok(result)


@router.get("/{ls_id}", response_model=BaseResponse[LongSentenceDetailOut])
async def get_long_sentence(ls_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """长难句解析详情:主干/分层/译文/难点 + 句法点(跳 /curriculum/nodes/{node_id}/resources 看讲解)。"""
    ls, nodes = await lss.get_detail(db, ls_id=ls_id)
    if ls is None or ls.status != "published":
        raise AppError(code=404, message="长难句不存在或未发布")
    return make_ok(LongSentenceDetailOut(
        id=ls.id, text=ls.text, source_kind=ls.source_kind, analysis=ls.analysis_json,
        audio_url=ls.audio_url,
        nodes=[LongSentenceNodeRef(**n) for n in nodes],
    ))


@router.post("/{ls_id}/audio", response_model=BaseResponse[dict])
async def get_audio(ls_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """听原句:返回句子音频直链。库里已有 audio_url 直接返回;否则首次合成→存 COS→回填库。
    COS 未配置(dev)时返回空 url,前端回退 /tts/speak 流式播放。"""
    ls, _ = await lss.get_detail(db, ls_id=ls_id)
    if ls is None or ls.status != "published":
        raise AppError(code=404, message="长难句不存在或未发布")
    if ls.audio_url:
        return make_ok({"url": ls.audio_url})
    speed = await tts_service.speed_for_stage_db(db, "junior")
    url = await tts_service.get_or_create_audio_url(ls.text, speed=speed)
    if url:
        ls.audio_url = url
        await db.commit()
    return make_ok({"url": url or ""})


@router.get("/{ls_id}/verify-types", response_model=BaseResponse[VerifyTypesOut])
async def get_verify_types(ls_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """该长难句可用的验证题型(后台开放且本期可用),学生自选其一作答。"""
    types = await lss.enabled_verify_types(db)
    return make_ok(VerifyTypesOut(types=types))


@router.get("/{ls_id}/verify", response_model=BaseResponse[VerifyQuestionOut])
async def get_verify_question(ls_id: uuid.UUID, type: str, db: DbDep, current_user: UserDep):
    """取一道验证题(不含答案)。type 须在已开放题型内。"""
    if type not in await lss.enabled_verify_types(db):
        raise AppError(code=400, message="该验证题型未开放")
    ls, _ = await lss.get_detail(db, ls_id=ls_id)
    if ls is None or ls.status != "published":
        raise AppError(code=404, message="长难句不存在或未发布")
    q = lss.build_verify(ls, type)
    if q is None:
        raise AppError(code=400, message="该句无法生成此题型")
    return make_ok(VerifyQuestionOut(type=q["type"], prompt=q["prompt"], options=q["options"]))


@router.post("/{ls_id}/verify", response_model=BaseResponse[VerifySubmitOut])
async def submit_verify_answer(ls_id: uuid.UUID, body: VerifySubmitIn, db: DbDep, current_user: UserDep):
    """提交验证答案:判分 + 回写句法 node + 错题收口 + 达标判掌握。"""
    res = await lss.submit_verify(
        db, student_id=current_user.id, ls_id=ls_id, verify_type=body.type, answer=body.answer)
    await db.commit()
    return make_ok(VerifySubmitOut(**res))
