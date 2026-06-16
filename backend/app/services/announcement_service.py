"""平台公告（§5.6）：全平台或定向（机构/年级）发布 + 用户侧拉取。"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d1_users import Student, User
from app.models.d9_system import Announcement

_AUDIENCES = {"all", "institution", "grade"}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _aware(d):
    if d is None:
        return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def _item(a: Announcement) -> dict:
    return {
        "id": str(a.id), "title": a.title, "content": a.content,
        "audience": a.audience, "target_values": a.target_values or [],
        "pinned": a.pinned, "is_active": a.is_active,
        "starts_at": a.starts_at.isoformat() if a.starts_at else None,
        "ends_at": a.ends_at.isoformat() if a.ends_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _pub_item(a: Announcement) -> dict:
    return {
        "id": str(a.id), "title": a.title, "content": a.content, "pinned": a.pinned,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


async def _user_targets(db: AsyncSession, user_id: uuid.UUID) -> tuple[str | None, str | None]:
    """解析用户的机构 id 与年级（学生优先取 students 表，回落 users）。"""
    inst, grade = None, None
    s = await db.get(Student, user_id)
    if s is not None:
        inst = str(s.institution_id) if s.institution_id else None
        grade = s.grade
    u = await db.get(User, user_id)
    if u is not None:
        inst = inst or (str(u.institution_id) if u.institution_id else None)
        grade = grade or u.preferred_grade
    return inst, grade


# ── 用户侧 ──────────────────────────────────────────────────────────────────
async def public_list(db: AsyncSession, *, user_id: uuid.UUID, limit: int = 30) -> dict:
    """当前用户可见的生效公告（全平台 + 命中其机构/年级），置顶优先、按时间倒序。"""
    now = _now()
    inst, grade = await _user_targets(db, user_id)
    conds = [Announcement.audience == "all"]
    if inst:
        conds.append(and_(Announcement.audience == "institution",
                          Announcement.target_values.contains([inst])))
    if grade:
        conds.append(and_(Announcement.audience == "grade",
                          Announcement.target_values.contains([grade])))
    stmt = (select(Announcement).where(and_(
        Announcement.is_active.is_(True),
        or_(Announcement.starts_at.is_(None), Announcement.starts_at <= now),
        or_(Announcement.ends_at.is_(None), Announcement.ends_at >= now),
        or_(*conds)))
        .order_by(Announcement.pinned.desc(), Announcement.created_at.desc())
        .limit(limit))
    rows = (await db.execute(stmt)).scalars().all()
    return {"items": [_pub_item(a) for a in rows]}


# ── 管理 ────────────────────────────────────────────────────────────────────
async def admin_list(db: AsyncSession, *, skip: int = 0, limit: int = 50) -> dict:
    total = int(await db.scalar(select(func.count()).select_from(Announcement)) or 0)
    rows = (await db.execute(
        select(Announcement).order_by(Announcement.created_at.desc())
        .offset(skip).limit(limit))).scalars().all()
    return {"total": total, "items": [_item(a) for a in rows]}


async def admin_create(db: AsyncSession, *, admin_id: uuid.UUID, title: str, content: str,
                       audience: str = "all", target_values: list[str] | None = None,
                       pinned: bool = False, starts_at: dt.datetime | None = None,
                       ends_at: dt.datetime | None = None) -> Announcement:
    title = (title or "").strip()
    content = (content or "").strip()
    if not title or not content:
        raise AppError(code=400, message="标题和内容不能为空")
    if audience not in _AUDIENCES:
        raise AppError(code=400, message="无效受众")
    tv = [str(v).strip() for v in (target_values or []) if str(v).strip()]
    if audience != "all" and not tv:
        raise AppError(code=400, message="定向公告需指定目标（机构/年级）")
    if starts_at and ends_at and _aware(ends_at) <= _aware(starts_at):
        raise AppError(code=400, message="结束时间须晚于开始时间")
    a = Announcement(
        id=uuid.uuid4(), title=title[:120], content=content, audience=audience,
        target_values=(tv if audience != "all" else None), pinned=bool(pinned),
        starts_at=starts_at, ends_at=ends_at, is_active=True, created_by=admin_id)
    db.add(a)
    await db.flush()
    return a


async def admin_update(db: AsyncSession, *, ann_id: uuid.UUID, fields: dict) -> Announcement:
    a = await db.get(Announcement, ann_id)
    if a is None:
        raise AppError(code=404, message="公告不存在")
    for k in ("title", "content", "pinned", "is_active"):
        if k in fields and fields[k] is not None:
            setattr(a, k, fields[k])
    await db.flush()
    return a


async def admin_delete(db: AsyncSession, *, ann_id: uuid.UUID) -> None:
    a = await db.get(Announcement, ann_id)
    if a is None:
        raise AppError(code=404, message="公告不存在")
    await db.delete(a)
    await db.flush()
