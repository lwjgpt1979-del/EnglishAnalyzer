"""客服与用户支持（§13）：工单 / FAQ / 意见反馈（用户侧）。

后台受理/维护在 admin.py。
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import make_ok
from app.services import (announcement_service, faq_service, support_service,
                          user_feedback_service)

router = APIRouter(tags=["support"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


# ── 平台公告（§5.6）──────────────────────────────────────────────────────────
@router.get("/announcements", response_model=None)
async def list_announcements(db: DbDep, current_user: UserDep):
    """当前用户可见的生效公告（全平台 + 命中其机构/年级）。"""
    await get_rls_db(db, str(current_user.id))
    return make_ok(await announcement_service.public_list(db, user_id=current_user.id))


# ── FAQ 自助（§13.2）──────────────────────────────────────────────────────────
@router.get("/faq", response_model=None)
async def list_faq(db: DbDep, audience: str = Query("c", description="c|b|all")):
    """公开 FAQ（按分类分组）。无需鉴权语义上可放开，这里仍走登录用户。"""
    return make_ok(await faq_service.public_list(db, audience=audience))


# ── 客服工单（§13.1）──────────────────────────────────────────────────────────
@router.post("/support/tickets", response_model=None)
async def create_ticket(body: dict, db: DbDep, current_user: UserDep):
    """提交工单。body={category, subject, content, order_id?}。"""
    await get_rls_db(db, str(current_user.id))
    oid = body.get("order_id")
    t = await support_service.create_ticket(
        db, user_id=current_user.id, category=(body or {}).get("category", "other"),
        subject=(body or {}).get("subject", ""), content=(body or {}).get("content", ""),
        order_id=(uuid.UUID(oid) if oid else None))
    await db.commit()
    return make_ok({"id": str(t.id), "status": t.status})


@router.get("/support/tickets", response_model=None)
async def my_tickets(db: DbDep, current_user: UserDep,
                     skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    await get_rls_db(db, str(current_user.id))
    return make_ok(await support_service.list_mine(
        db, user_id=current_user.id, skip=skip, limit=limit))


@router.get("/support/tickets/{ticket_id}", response_model=None)
async def ticket_thread(ticket_id: uuid.UUID, db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    return make_ok(await support_service.get_thread(
        db, ticket_id=ticket_id, user_id=current_user.id))


@router.post("/support/tickets/{ticket_id}/reply", response_model=None)
async def reply_ticket(ticket_id: uuid.UUID, body: dict, db: DbDep, current_user: UserDep):
    """用户追加回复。body={content}。"""
    await get_rls_db(db, str(current_user.id))
    m = await support_service.reply(
        db, ticket_id=ticket_id, sender_role="user", sender_id=current_user.id,
        content=(body or {}).get("content", ""))
    await db.commit()
    return make_ok({"id": str(m.id)})


# ── 意见反馈 / BUG（§13.3）────────────────────────────────────────────────────
@router.post("/feedback/suggestions", response_model=None)
async def submit_feedback(body: dict, db: DbDep, current_user: UserDep):
    """提交功能建议/BUG。body={kind: suggestion|bug, content, images?[], contact?}。"""
    await get_rls_db(db, str(current_user.id))
    f = await user_feedback_service.submit(
        db, user_id=current_user.id, kind=(body or {}).get("kind", "suggestion"),
        content=(body or {}).get("content", ""), images=(body or {}).get("images"),
        contact=(body or {}).get("contact"))
    await db.commit()
    return make_ok({"id": str(f.id), "status": f.status})


@router.get("/feedback/suggestions", response_model=None)
async def my_feedback(db: DbDep, current_user: UserDep,
                      skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    await get_rls_db(db, str(current_user.id))
    return make_ok(await user_feedback_service.list_mine(
        db, user_id=current_user.id, skip=skip, limit=limit))
