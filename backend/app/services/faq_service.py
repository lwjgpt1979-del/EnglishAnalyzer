"""FAQ 自助模块（§13.2）：后台维护，小程序「帮助与反馈」展示。"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d9_system import FaqEntry

_AUDIENCES = {"c", "b", "all"}


def _item(f: FaqEntry) -> dict:
    return {
        "id": str(f.id), "audience": f.audience, "category": f.category,
        "question": f.question, "answer": f.answer, "sort_order": f.sort_order,
        "is_active": f.is_active,
        "updated_at": f.updated_at.isoformat() if f.updated_at else None,
    }


# ── 公开（小程序）──────────────────────────────────────────────────────────
async def public_list(db: AsyncSession, *, audience: str = "c") -> dict:
    """返回启用的 FAQ，按分类分组。audience=c(学生/亲人)|b(机构)。"""
    if audience not in _AUDIENCES:
        audience = "c"
    stmt = (select(FaqEntry).where(
        FaqEntry.is_active.is_(True),
        FaqEntry.audience.in_([audience, "all"]))
        .order_by(FaqEntry.category.asc(), FaqEntry.sort_order.asc()))
    rows = (await db.execute(stmt)).scalars().all()
    groups: dict[str, list[dict]] = {}
    for f in rows:
        groups.setdefault(f.category, []).append(
            {"id": str(f.id), "question": f.question, "answer": f.answer})
    return {"categories": [{"category": k, "items": v} for k, v in groups.items()]}


# ── 管理 ────────────────────────────────────────────────────────────────────
async def admin_list(db: AsyncSession, *, audience: str = "all",
                     skip: int = 0, limit: int = 100) -> dict:
    stmt = select(FaqEntry)
    if audience and audience != "all":
        stmt = stmt.where(FaqEntry.audience == audience)
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (await db.execute(
        stmt.order_by(FaqEntry.audience.asc(), FaqEntry.category.asc(),
                      FaqEntry.sort_order.asc()).offset(skip).limit(limit))).scalars().all()
    return {"total": total, "items": [_item(f) for f in rows]}


async def create(db: AsyncSession, *, admin_id: uuid.UUID, audience: str, category: str,
                 question: str, answer: str, sort_order: int = 0) -> FaqEntry:
    if audience not in _AUDIENCES:
        raise AppError(code=400, message="无效受众")
    question = (question or "").strip()
    answer = (answer or "").strip()
    if not question or not answer:
        raise AppError(code=400, message="问题和答案不能为空")
    f = FaqEntry(
        id=uuid.uuid4(), audience=audience, category=(category or "通用").strip()[:40],
        question=question[:200], answer=answer, sort_order=int(sort_order or 0),
        is_active=True, updated_by=admin_id)
    db.add(f)
    await db.flush()
    return f


async def update(db: AsyncSession, *, faq_id: uuid.UUID, admin_id: uuid.UUID,
                 fields: dict) -> FaqEntry:
    f = await db.get(FaqEntry, faq_id)
    if f is None:
        raise AppError(code=404, message="FAQ 不存在")
    for k in ("audience", "category", "question", "answer", "sort_order", "is_active"):
        if k in fields and fields[k] is not None:
            if k == "audience" and fields[k] not in _AUDIENCES:
                raise AppError(code=400, message="无效受众")
            setattr(f, k, fields[k])
    f.updated_by = admin_id
    f.updated_at = dt.datetime.now(dt.timezone.utc)
    await db.flush()
    return f


async def delete(db: AsyncSession, *, faq_id: uuid.UUID) -> None:
    f = await db.get(FaqEntry, faq_id)
    if f is None:
        raise AppError(code=404, message="FAQ 不存在")
    await db.delete(f)
    await db.flush()
