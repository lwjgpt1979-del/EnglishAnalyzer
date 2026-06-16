"""敏感词内容过滤（§5.6）。

超管在后台维护敏感词库（sensitive_words），本服务提供：
- find_hits：返回命中的敏感词
- assert_clean：命中 block 类敏感词则抛 AppError(400)，用于阻断学生/老师提交
- mask：把命中词替换为 ***（用于 AI 报告/作文展示等软处理）
- admin CRUD

含 30s 内存缓存，避免每次请求查库（词库变更后最多 30s 生效，与「次日生效」口径相容）。
"""
from __future__ import annotations

import datetime as dt
import time
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d9_system import SensitiveWord

_CATEGORIES = {"political", "porn", "violence", "ad", "other"}
_ACTIONS = {"block", "mask"}

# 进程内缓存： (loaded_at, [(word, action), ...])
_CACHE_TTL = 30.0
_cache: tuple[float, list[tuple[str, str]]] | None = None


def _invalidate() -> None:
    global _cache
    _cache = None


async def _load(db: AsyncSession) -> list[tuple[str, str]]:
    global _cache
    now = time.monotonic()
    if _cache and now - _cache[0] < _CACHE_TTL:
        return _cache[1]
    rows = (await db.execute(
        select(SensitiveWord.word, SensitiveWord.action)
        .where(SensitiveWord.is_active.is_(True)))).all()
    words = [(str(w).lower(), str(a)) for w, a in rows if w]
    _cache = (now, words)
    return words


async def find_hits(db: AsyncSession, text: str) -> list[str]:
    """返回 text 命中的敏感词（去重，保序）。"""
    if not text:
        return []
    low = text.lower()
    seen, hits = set(), []
    for w, _ in await _load(db):
        if w and w in low and w not in seen:
            seen.add(w)
            hits.append(w)
    return hits


async def assert_clean(db: AsyncSession, text: str) -> None:
    """命中任意 block 类敏感词 → 抛 400（阻断提交）。mask 类不阻断。"""
    if not text:
        return
    low = text.lower()
    for w, action in await _load(db):
        if action == "block" and w and w in low:
            raise AppError(code=400, message="内容包含违规词，请修改后重试")


async def mask(db: AsyncSession, text: str) -> str:
    """把命中词替换为等长 ***（软处理，用于展示）。"""
    if not text:
        return text
    out = text
    for w, _ in await _load(db):
        if not w:
            continue
        # 大小写不敏感替换
        idx = out.lower().find(w)
        while idx != -1:
            out = out[:idx] + ("*" * len(w)) + out[idx + len(w):]
            idx = out.lower().find(w, idx + len(w))
    return out


# ── admin CRUD ───────────────────────────────────────────────────────────────
def _item(s: SensitiveWord) -> dict:
    return {
        "id": str(s.id), "word": s.word, "category": s.category,
        "action": s.action, "is_active": s.is_active,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


async def admin_list(db: AsyncSession, *, category: str = "all", q: str | None = None,
                     skip: int = 0, limit: int = 200) -> dict:
    stmt = select(SensitiveWord)
    if category and category != "all":
        stmt = stmt.where(SensitiveWord.category == category)
    if q:
        stmt = stmt.where(SensitiveWord.word.ilike(f"%{q}%"))
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = (await db.execute(
        stmt.order_by(SensitiveWord.created_at.desc()).offset(skip).limit(limit))).scalars().all()
    return {"total": total, "items": [_item(s) for s in rows]}


async def admin_add(db: AsyncSession, *, admin_id: uuid.UUID, word: str,
                    category: str = "other", action: str = "block") -> SensitiveWord:
    word = (word or "").strip()
    if not word:
        raise AppError(code=400, message="敏感词不能为空")
    if category not in _CATEGORIES:
        raise AppError(code=400, message="无效分类")
    if action not in _ACTIONS:
        raise AppError(code=400, message="无效处理方式")
    exists = await db.scalar(select(SensitiveWord.id).where(
        func.lower(SensitiveWord.word) == word.lower()))
    if exists:
        raise AppError(code=400, message="该敏感词已存在")
    s = SensitiveWord(id=uuid.uuid4(), word=word, category=category,
                      action=action, is_active=True, created_by=admin_id)
    db.add(s)
    await db.flush()
    _invalidate()
    return s


async def admin_batch_add(db: AsyncSession, *, admin_id: uuid.UUID, words: list[str],
                          category: str = "other", action: str = "block") -> int:
    """批量导入（去重、跳过已存在）。返回新增数。"""
    if category not in _CATEGORIES or action not in _ACTIONS:
        raise AppError(code=400, message="无效分类或处理方式")
    existing = {str(w).lower() for w in (await db.execute(
        select(SensitiveWord.word))).scalars().all()}
    n = 0
    for raw in words:
        w = (raw or "").strip()
        if not w or w.lower() in existing:
            continue
        existing.add(w.lower())
        db.add(SensitiveWord(id=uuid.uuid4(), word=w, category=category,
                             action=action, is_active=True, created_by=admin_id))
        n += 1
    await db.flush()
    _invalidate()
    return n


async def admin_update(db: AsyncSession, *, word_id: uuid.UUID, fields: dict) -> SensitiveWord:
    s = await db.get(SensitiveWord, word_id)
    if s is None:
        raise AppError(code=404, message="敏感词不存在")
    if "category" in fields and fields["category"] in _CATEGORIES:
        s.category = fields["category"]
    if "action" in fields and fields["action"] in _ACTIONS:
        s.action = fields["action"]
    if "is_active" in fields and fields["is_active"] is not None:
        s.is_active = bool(fields["is_active"])
    await db.flush()
    _invalidate()
    return s


async def admin_delete(db: AsyncSession, *, word_id: uuid.UUID) -> None:
    s = await db.get(SensitiveWord, word_id)
    if s is None:
        raise AppError(code=404, message="敏感词不存在")
    await db.delete(s)
    await db.flush()
    _invalidate()
