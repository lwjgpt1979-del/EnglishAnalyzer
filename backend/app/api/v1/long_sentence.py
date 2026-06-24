"""长难句 学生端 API（L2）:列长难句 / 取解析(主干分层/译文/句法点跳 R6 资源)。"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends

from app.core.database import get_db
from app.core.exceptions import AppError
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.kp import (
    LongSentenceItem, LongSentenceListOut, LongSentenceDetailOut, LongSentenceNodeRef,
    VerifyTypesOut, VerifyQuestionOut, VerifySubmitIn, VerifySubmitOut,
)
from app.services import long_sentence_service as lss
from app.services import tts_service
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/long-sentences", tags=["long-sentences"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.get("", response_model=BaseResponse[LongSentenceListOut])
async def list_long_sentences(
    db: DbDep, current_user: UserDep, node_id: uuid.UUID | None = None, limit: int = 50,
):
    """已发布长难句:平台共享(可按句法 node 过滤)+ 本人个人长难句(student_long_sentence)。"""
    rows = await lss.list_published(db, node_id=node_id, owner_id=current_user.id, limit=limit)
    fav = await lss.favorited_ids(db, user_id=current_user.id, ls_ids=[r.id for r in rows])
    items = [LongSentenceItem(
        id=r.id, text=r.text, source_kind=r.source_kind,
        syntax_points=(r.analysis_json or {}).get("syntax_points", []),
        favorited=r.id in fav,
    ) for r in rows]
    if node_id is None:   # 个人长难句不挂句法 node,不参与 node 过滤
        for s in await lss.list_student_published(db, owner_id=current_user.id, limit=limit):
            items.append(LongSentenceItem(
                id=s.id, text=s.text, source_kind="uploaded",
                syntax_points=(s.analysis_json or {}).get("syntax_points", []), favorited=False))
    return make_ok(LongSentenceListOut(total=len(items), items=items))


@router.get("/next", response_model=BaseResponse[dict])
async def next_sentence(db: DbDep, current_user: UserDep, exclude: str = ""):
    """自适应推荐下一句:按学生水平 θ(年级估)选难度贴近的、优先薄弱句法点 + 课程对齐 + 个人材料。
    exclude: 逗号分隔的已学 id,避免重复。返回 {item, theta, target, weak_hit}。"""
    ex = []
    for x in (exclude or "").split(","):
        x = x.strip()
        if x:
            try:
                ex.append(uuid.UUID(x))
            except ValueError:
                pass
    r = await lss.recommend_next(db, user=current_user, exclude_ids=ex)
    best = r["best"]
    if best is None:
        return make_ok({"item": None, "theta": r["theta"], "target": r["target"], "weak_hit": False})
    kind, row = best
    item = LongSentenceItem(
        id=row.id, text=row.text,
        source_kind=row.source_kind if kind == "platform" else "uploaded",
        syntax_points=(row.analysis_json or {}).get("syntax_points", []),
        favorited=(row.id in await lss.favorited_ids(db, user_id=current_user.id, ls_ids=[row.id])) if kind == "platform" else False,
        difficulty=row.difficulty,
    )
    return make_ok({"item": item.model_dump(mode="json"), "theta": round(r["theta"]),
                    "target": round(r["target"]), "weak_hit": r["weak_hit"]})


@router.post("/feedback", response_model=BaseResponse[dict])
async def submit_feedback(db: DbDep, current_user: UserDep, rating: str = Body("", embed=True)):
    """难度反馈校准水平 θ(rating 从请求体取)。rating: easy(太简单)|ok(刚好)|hard(有点难)。"""
    if rating not in ("easy", "ok", "hard"):
        raise AppError(code=400, message="rating 须为 easy|ok|hard")
    theta = await lss.apply_feedback(db, current_user, rating=rating)
    return make_ok({"theta": round(theta), "target": round(min(95.0, theta + 5))})


async def _student_one(db, ls_id, owner_id):
    from app.models.d20_long_sentence import StudentLongSentence
    s = await db.get(StudentLongSentence, ls_id)
    if s is not None and s.status == "published" and s.owner_id == owner_id:
        return s
    return None


@router.get("/{ls_id}", response_model=BaseResponse[LongSentenceDetailOut])
async def get_long_sentence(ls_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """长难句解析详情。平台库优先;否则查本人个人长难句。"""
    ls, nodes = await lss.get_detail(db, ls_id=ls_id)
    if ls is not None and ls.status == "published":
        favorited = await lss.is_favorited(db, user_id=current_user.id, ls_id=ls_id)
        return make_ok(LongSentenceDetailOut(
            id=ls.id, text=ls.text, source_kind=ls.source_kind, analysis=ls.analysis_json,
            audio_url=ls.audio_url, favorited=favorited,
            nodes=[LongSentenceNodeRef(**n) for n in nodes]))
    s = await _student_one(db, ls_id, current_user.id)
    if s is not None:
        return make_ok(LongSentenceDetailOut(
            id=s.id, text=s.text, source_kind="uploaded", analysis=s.analysis_json,
            audio_url=None, favorited=False, nodes=[]))
    raise AppError(code=404, message="长难句不存在或未发布")


@router.post("/{ls_id}/favorite", response_model=BaseResponse[dict])
async def favorite(ls_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """收藏长难句(仅平台库支持收藏)。"""
    ls, _ = await lss.get_detail(db, ls_id=ls_id)
    if ls is None:
        return make_ok({"favorited": False})
    on = await lss.set_favorite(db, user_id=current_user.id, ls_id=ls_id, on=True)
    return make_ok({"favorited": on})


@router.delete("/{ls_id}/favorite", response_model=BaseResponse[dict])
async def unfavorite(ls_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """取消收藏长难句。"""
    on = await lss.set_favorite(db, user_id=current_user.id, ls_id=ls_id, on=False)
    return make_ok({"favorited": on})


@router.post("/{ls_id}/audio", response_model=BaseResponse[dict])
async def get_audio(ls_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """听原句:返回句子音频直链。平台句库里有 audio_url 直接返回,否则合成→存 COS→回填;
    个人长难句不回填库,直接返回空 url 让前端走 /tts/speak 流式。"""
    ls, _ = await lss.get_detail(db, ls_id=ls_id)
    if ls is not None and ls.status == "published":
        if ls.audio_url:
            return make_ok({"url": ls.audio_url})
        speed = await tts_service.speed_for_stage_db(db, "junior")
        url = await tts_service.get_or_create_audio_url(ls.text, speed=speed)
        if url:
            ls.audio_url = url
            await db.commit()
        return make_ok({"url": url or ""})
    s = await _student_one(db, ls_id, current_user.id)
    if s is not None:
        return make_ok({"url": ""})   # 前端回退流式
    raise AppError(code=404, message="长难句不存在或未发布")


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
