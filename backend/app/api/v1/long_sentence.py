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
)
from app.services import long_sentence_service as lss
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


@router.get("/{ls_id}", response_model=BaseResponse[LongSentenceDetailOut])
async def get_long_sentence(ls_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """长难句解析详情:主干/分层/译文/难点 + 句法点(跳 /curriculum/nodes/{node_id}/resources 看讲解)。"""
    ls, nodes = await lss.get_detail(db, ls_id=ls_id)
    if ls is None or ls.status != "published":
        raise AppError(code=404, message="长难句不存在或未发布")
    return make_ok(LongSentenceDetailOut(
        id=ls.id, text=ls.text, source_kind=ls.source_kind, analysis=ls.analysis_json,
        nodes=[LongSentenceNodeRef(**n) for n in nodes],
    ))
