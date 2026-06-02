# 站内消息中心实施计划（Plan J，Module 7B）

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps 使用 `- [ ]` checkbox。

**Goal:** 实现需求文档 §916-948 「功能模块 7B：站内消息中心」MVP——AI分析完成/老师批注/支付结果三类关键通知写入消息中心；前端首页右上角铃铛+未读数；消息中心页支持分频道筛选、已读未读、批量操作、保留期管理。

**Architecture:** 复用现有 `notifications` 表（D-059 / d9_system）+ 迁移 0006 加 3 列（channel/expires_at/meta）；新建 `notification_service` 提供 emit helpers；3 处业务调用点注入；前端新增 `pages/messages/index.vue` 列表页 + 首页铃铛组件。

**Tech Stack:** FastAPI · SQLAlchemy 2.x asyncio · Pydantic v2 · pytest-asyncio STRICT · uni-app Vue3

---

## File Structure

```
新增后端:
  backend/alembic/versions/0006_notifications_meta.py
  backend/app/schemas/notifications.py
  backend/app/services/notification_service.py
  backend/app/api/v1/notifications.py
  tests/api/test_notifications.py

修改后端:
  backend/app/models/d9_system.py                # Notification 加 3 列
  backend/app/services/ai_service.py             # analyze 末尾 emit 通知
  backend/app/services/teacher_service.py        # add_comment 末尾 emit 通知
  backend/app/services/order_service.py 或 webhook   # 支付成功 emit 会员通知
  backend/app/api/v1/router.py                   # +notifications_router

新增前端:
  frontend/miniprogram/src/api/notifications.ts
  frontend/miniprogram/src/pages/messages/index.vue

修改前端:
  frontend/miniprogram/src/types/api.ts          # +类型
  frontend/miniprogram/src/pages.json            # +1 页
  frontend/miniprogram/src/pages/index/index.vue # 加铃铛 + 未读数
```

**Key model facts:**
- 现有 `Notification` 字段：id, user_id, type(enum analysis_done/membership/system/assignment/report_ready/bind_*/ocr_failed), title, content, is_read, read_at, created_at
- 现有 `notification_type` enum 已含 9 个值，本次**不动 enum**（避免迁移加值的复杂度）
- 新增 `channel` 字段（String，5 个值：study/membership/system/relative/teacher）作为用户可见分类，从 type 推导写入
- 新增 `expires_at`（保留期：会员类 12 月 / 其他 3 月）
- 新增 `meta` JSONB（存联跳信息：wq_id/order_id/teacher_id 等，前端点击通知跳转用）

---

## Task 0: 迁移 0006 + Notification 模型扩展

**Files:**
- Create: `backend/alembic/versions/0006_notifications_meta.py`
- Modify: `backend/app/models/d9_system.py`

- [ ] **Step 1: 修改 `backend/app/models/d9_system.py`，在 `Notification` 类内（is_read 之前）追加 3 列**

```python
    channel = mapped_column(sa.String(20), nullable=False, server_default=sa.text("'system'"))
    expires_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    meta = mapped_column(JSONB, nullable=True)
```

确认顶部已 import JSONB（现有 `from sqlalchemy.dialects.postgresql import UUID, JSONB`）。

- [ ] **Step 2: 创建 `backend/alembic/versions/0006_notifications_meta.py`**

```python
"""notifications: add channel/expires_at/meta

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notifications", sa.Column("channel", sa.String(length=20), nullable=False, server_default=sa.text("'system'")))
    op.add_column("notifications", sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("notifications", sa.Column("meta", JSONB(), nullable=True))
    op.create_index("ix_notifications_user_unread", "notifications", ["user_id", "is_read"])


def downgrade() -> None:
    op.drop_index("ix_notifications_user_unread", table_name="notifications")
    op.drop_column("notifications", "meta")
    op.drop_column("notifications", "expires_at")
    op.drop_column("notifications", "channel")
```

- [ ] **Step 3: 跑迁移**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
DATABASE_URL="postgresql+psycopg://postgres:dev@localhost:5432/enggramer" alembic upgrade head
```
Expected: `Running upgrade 0005 -> 0006`

- [ ] **Step 4: 全量测试无回归**

```bash
python -m pytest ../tests/ -q
```
Expected: 之前 187 PASS

- [ ] **Step 5: 提交**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add backend/alembic/versions/0006_notifications_meta.py backend/app/models/d9_system.py
git commit -m "feat(db): migration 0006 — notifications add channel/expires_at/meta"
```

---

## Task 1: Schemas + Service + 占位测试

**Files:**
- Create: `backend/app/schemas/notifications.py`
- Create: `backend/app/services/notification_service.py`
- Create: `tests/api/test_notifications.py`

- [ ] **Step 1: 创建 `backend/app/schemas/notifications.py`**

```python
"""站内消息中心 Schemas（Module 7B / D-074）。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class NotificationOut(BaseModel):
    id: uuid.UUID
    type: str
    channel: str  # study / membership / system / relative / teacher
    title: str
    content: str
    is_read: bool
    read_at: datetime | None
    created_at: datetime
    expires_at: datetime | None
    meta: dict[str, Any] | None

    model_config = {"from_attributes": True}


class NotificationListOut(BaseModel):
    items: list[NotificationOut]
    total: int
    unread_count: int


class UnreadCountOut(BaseModel):
    count: int
```

- [ ] **Step 2: 创建 `backend/app/services/notification_service.py`**

```python
"""消息通知服务（Module 7B / D-074）。

- emit_*: 业务侧调用，写入站内通知（type → channel 由本模块映射）
- list/mark/delete: API 端点调用
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d9_system import Notification

# type → channel 映射（5 个频道：study/membership/system/relative/teacher）
TYPE_TO_CHANNEL = {
    "analysis_done": "study",
    "ocr_failed": "study",
    "report_ready": "study",
    "assignment": "study",
    "membership": "membership",
    "system": "system",
    "bind_request": "relative",
    "bind_accepted": "relative",
    "bind_rejected": "relative",
}

# 保留期：会员类 12 月，其他 3 月（需求文档 §936）
RETENTION_DAYS_MEMBERSHIP = 365
RETENTION_DAYS_OTHER = 90


def _channel_for(type_: str) -> str:
    return TYPE_TO_CHANNEL.get(type_, "system")


def _expires_at_for(type_: str) -> datetime:
    days = RETENTION_DAYS_MEMBERSHIP if type_ == "membership" else RETENTION_DAYS_OTHER
    return datetime.now(timezone.utc) + timedelta(days=days)


async def emit(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    type_: str,
    title: str,
    content: str,
    meta: dict[str, Any] | None = None,
) -> Notification:
    """通用发通知。type_ 必须是 Notification.type enum 的合法值。"""
    notif = Notification(
        id=uuid.uuid4(),
        user_id=user_id,
        type=type_,
        channel=_channel_for(type_),
        title=title,
        content=content,
        meta=meta,
        expires_at=_expires_at_for(type_),
    )
    db.add(notif)
    await db.flush()
    return notif


# —— 业务封装：让调用方语义更清晰 ———————————————————
async def emit_analysis_done(
    db: AsyncSession, *, user_id: uuid.UUID, wq_id: uuid.UUID,
) -> Notification:
    return await emit(
        db, user_id=user_id, type_="analysis_done",
        title="AI 分析完成", content="你的错题已生成诊断报告，点击查看。",
        meta={"wq_id": str(wq_id)},
    )


async def emit_teacher_comment(
    db: AsyncSession, *, user_id: uuid.UUID, wq_id: uuid.UUID, teacher_id: uuid.UUID,
) -> Notification:
    return await emit(
        db, user_id=user_id, type_="assignment",
        title="老师为你批注了一道错题", content="点击查看老师的反馈。",
        meta={"wq_id": str(wq_id), "teacher_id": str(teacher_id)},
    )


async def emit_membership(
    db: AsyncSession, *, user_id: uuid.UUID, title: str, content: str,
    order_id: uuid.UUID | None = None,
) -> Notification:
    meta: dict[str, Any] | None = {"order_id": str(order_id)} if order_id else None
    return await emit(
        db, user_id=user_id, type_="membership",
        title=title, content=content, meta=meta,
    )


# —— 查询 / 操作 ————————————————————————————————
async def list_notifications(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    channel: str | None = None,
    unread_only: bool = False,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[Notification], int, int]:
    """返回 (items, total, unread_count)。"""
    base = select(Notification).where(Notification.user_id == user_id)
    if channel:
        base = base.where(Notification.channel == channel)
    if unread_only:
        base = base.where(Notification.is_read.is_(False))

    total_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(total_q)).scalar_one()

    unread_q = select(func.count(Notification.id)).where(
        Notification.user_id == user_id, Notification.is_read.is_(False),
    )
    unread_count = (await db.execute(unread_q)).scalar_one()

    items_q = base.order_by(Notification.created_at.desc()).offset(skip).limit(limit)
    items = list((await db.execute(items_q)).scalars().all())
    return items, total, unread_count


async def unread_count(db: AsyncSession, *, user_id: uuid.UUID) -> int:
    q = select(func.count(Notification.id)).where(
        Notification.user_id == user_id, Notification.is_read.is_(False),
    )
    return (await db.execute(q)).scalar_one()


async def mark_read(db: AsyncSession, *, user_id: uuid.UUID, notif_id: uuid.UUID) -> Notification:
    from app.core.exceptions import AppError
    r = await db.execute(
        select(Notification).where(
            Notification.id == notif_id, Notification.user_id == user_id,
        )
    )
    n = r.scalar_one_or_none()
    if n is None:
        raise AppError(code=404, message="消息不存在")
    if not n.is_read:
        n.is_read = True
        n.read_at = datetime.now(timezone.utc)
        await db.flush()
    return n


async def mark_all_read(db: AsyncSession, *, user_id: uuid.UUID) -> int:
    now = datetime.now(timezone.utc)
    r = await db.execute(
        select(Notification).where(
            Notification.user_id == user_id, Notification.is_read.is_(False),
        )
    )
    affected = 0
    for n in r.scalars().all():
        n.is_read = True
        n.read_at = now
        affected += 1
    await db.flush()
    return affected


async def delete_read(db: AsyncSession, *, user_id: uuid.UUID) -> int:
    r = await db.execute(
        delete(Notification).where(
            Notification.user_id == user_id, Notification.is_read.is_(True),
        )
    )
    await db.flush()
    return r.rowcount or 0
```

- [ ] **Step 3: 创建 `tests/api/test_notifications.py`（schema + service 测试）**

```python
"""消息中心测试（Module 7B / D-074）。"""
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.schemas.notifications import NotificationOut, NotificationListOut, UnreadCountOut
from app.services.auth_service import upsert_user
from app.services.notification_service import (
    emit,
    emit_analysis_done,
    emit_teacher_comment,
    emit_membership,
    list_notifications,
    unread_count,
    mark_read,
    mark_all_read,
    delete_read,
    _channel_for,
)


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def user(db_session):
    u = await upsert_user(db_session, openid=f"notif_{uuid.uuid4().hex[:8]}")
    await db_session.flush()
    return u


def test_channel_mapping():
    assert _channel_for("analysis_done") == "study"
    assert _channel_for("membership") == "membership"
    assert _channel_for("bind_request") == "relative"
    assert _channel_for("system") == "system"
    assert _channel_for("unknown_xxx") == "system"


def test_notification_out_schema():
    out = NotificationOut(
        id=uuid.uuid4(), type="system", channel="system",
        title="t", content="c", is_read=False, read_at=None,
        created_at=datetime.now(timezone.utc), expires_at=None, meta=None,
    )
    assert out.channel == "system"


@pytest.mark.asyncio
async def test_emit_and_list(db_session, user):
    await emit_analysis_done(db_session, user_id=user.id, wq_id=uuid.uuid4())
    await emit_teacher_comment(db_session, user_id=user.id, wq_id=uuid.uuid4(), teacher_id=uuid.uuid4())
    await db_session.flush()

    items, total, unread = await list_notifications(db_session, user_id=user.id)
    assert total == 2
    assert unread == 2
    assert items[0].meta is not None


@pytest.mark.asyncio
async def test_filter_by_channel(db_session, user):
    await emit_analysis_done(db_session, user_id=user.id, wq_id=uuid.uuid4())
    await emit_membership(db_session, user_id=user.id, title="到期", content="即将到期")
    await db_session.flush()

    items, total, _ = await list_notifications(db_session, user_id=user.id, channel="membership")
    assert total == 1
    assert items[0].channel == "membership"


@pytest.mark.asyncio
async def test_mark_read(db_session, user):
    n = await emit_analysis_done(db_session, user_id=user.id, wq_id=uuid.uuid4())
    await db_session.flush()

    updated = await mark_read(db_session, user_id=user.id, notif_id=n.id)
    assert updated.is_read is True
    assert updated.read_at is not None


@pytest.mark.asyncio
async def test_mark_all_read(db_session, user):
    for _ in range(3):
        await emit_analysis_done(db_session, user_id=user.id, wq_id=uuid.uuid4())
    await db_session.flush()

    affected = await mark_all_read(db_session, user_id=user.id)
    assert affected == 3
    assert await unread_count(db_session, user_id=user.id) == 0


@pytest.mark.asyncio
async def test_delete_read(db_session, user):
    n1 = await emit_analysis_done(db_session, user_id=user.id, wq_id=uuid.uuid4())
    await emit_analysis_done(db_session, user_id=user.id, wq_id=uuid.uuid4())  # 保留未读
    await db_session.flush()
    await mark_read(db_session, user_id=user.id, notif_id=n1.id)

    deleted = await delete_read(db_session, user_id=user.id)
    assert deleted == 1
    items, total, _ = await list_notifications(db_session, user_id=user.id)
    assert total == 1


@pytest.mark.asyncio
async def test_emit_membership_with_order(db_session, user):
    oid = uuid.uuid4()
    n = await emit_membership(db_session, user_id=user.id, title="支付成功", content="感谢", order_id=oid)
    await db_session.flush()
    assert n.meta == {"order_id": str(oid)}
    assert n.channel == "membership"
```

- [ ] **Step 4: 跑测试 → 应通过**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_notifications.py -v
```
Expected: 9 PASS

- [ ] **Step 5: 全量不回归**

```bash
python -m pytest ../tests/ -q
```

- [ ] **Step 6: 提交**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add backend/app/schemas/notifications.py backend/app/services/notification_service.py tests/api/test_notifications.py
git commit -m "feat(notifications): schemas + service + 9 tests"
```

---

## Task 2: API endpoints + Router 注册

**Files:**
- Create: `backend/app/api/v1/notifications.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `tests/api/test_notifications.py`（追加 API 测试）

- [ ] **Step 1: 创建 `backend/app/api/v1/notifications.py`**

```python
"""站内消息中心 API（Module 7B / D-074）。"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.notifications import (
    NotificationOut,
    NotificationListOut,
    UnreadCountOut,
)
from app.services import notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.get("/", response_model=BaseResponse[NotificationListOut])
async def list_notifications_api(
    db: DbDep,
    current_user: UserDep,
    channel: str | None = Query(None, description="study/membership/system/relative/teacher"),
    unread_only: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    await get_rls_db(db, str(current_user.id))
    items, total, unread = await notification_service.list_notifications(
        db, user_id=current_user.id, channel=channel,
        unread_only=unread_only, skip=skip, limit=limit,
    )
    return make_ok(NotificationListOut(
        items=[NotificationOut.model_validate(n) for n in items],
        total=total,
        unread_count=unread,
    ))


@router.get("/unread-count", response_model=BaseResponse[UnreadCountOut])
async def unread_count_api(db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    c = await notification_service.unread_count(db, user_id=current_user.id)
    return make_ok(UnreadCountOut(count=c))


@router.patch("/{notif_id}/read", response_model=BaseResponse[NotificationOut])
async def mark_read_api(notif_id: uuid.UUID, db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    n = await notification_service.mark_read(db, user_id=current_user.id, notif_id=notif_id)
    await db.commit()
    return make_ok(NotificationOut.model_validate(n))


@router.post("/read-all", response_model=BaseResponse[dict])
async def mark_all_read_api(db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    n = await notification_service.mark_all_read(db, user_id=current_user.id)
    await db.commit()
    return make_ok({"affected": n})


@router.delete("/read", response_model=BaseResponse[dict])
async def delete_read_api(db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    n = await notification_service.delete_read(db, user_id=current_user.id)
    await db.commit()
    return make_ok({"deleted": n})
```

- [ ] **Step 2: 改 `backend/app/api/v1/router.py` 加 notifications_router**

```python
from app.api.v1.notifications import router as notifications_router
# ...
v1_router.include_router(notifications_router)
```

- [ ] **Step 3: 追加 API 测试到 `tests/api/test_notifications.py`**

```python


# ── API 测试 ──────────────────────────────────────────────────────────────────
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from app.main import app


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _login(client: AsyncClient, suffix: str) -> dict:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as mock_wx:
        mock_wx.return_value = {"openid": f"notif_api_{suffix}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


@pytest.mark.asyncio
async def test_list_empty_then_emit(client):
    headers = await _login(client, uuid.uuid4().hex[:6])

    # 完善 profile（避免 is_active gate）
    await client.post(
        "/api/v1/auth/complete-profile",
        json={"birth_year": 1990, "agreement_version": "v1.0"}, headers=headers,
    )

    r1 = await client.get("/api/v1/notifications/", headers=headers)
    assert r1.status_code == 200
    assert r1.json()["data"]["total"] == 0
    assert r1.json()["data"]["unread_count"] == 0

    r2 = await client.get("/api/v1/notifications/unread-count", headers=headers)
    assert r2.json()["data"]["count"] == 0


@pytest.mark.asyncio
async def test_full_flow_mark_and_delete(client):
    headers = await _login(client, uuid.uuid4().hex[:6])
    await client.post(
        "/api/v1/auth/complete-profile",
        json={"birth_year": 1990, "agreement_version": "v1.0"}, headers=headers,
    )

    # 通过 emit 直插 3 条通知（绕过 API，模拟业务侧）
    from app.core.database import _async_session_factory
    from app.services.notification_service import emit_analysis_done
    from sqlalchemy import select
    from app.models.d1_users import User as UserModel
    async with _async_session_factory() as s:
        user = (await s.execute(select(UserModel).where(UserModel.openid.like("notif_api_%")).order_by(UserModel.created_at.desc()).limit(1))).scalar_one()
        for _ in range(3):
            await emit_analysis_done(s, user_id=user.id, wq_id=uuid.uuid4())
        await s.commit()

    r1 = await client.get("/api/v1/notifications/", headers=headers)
    assert r1.json()["data"]["total"] == 3
    assert r1.json()["data"]["unread_count"] == 3

    # mark first as read
    first_id = r1.json()["data"]["items"][0]["id"]
    r2 = await client.patch(f"/api/v1/notifications/{first_id}/read", headers=headers)
    assert r2.status_code == 200
    assert r2.json()["data"]["is_read"] is True

    # mark all read
    r3 = await client.post("/api/v1/notifications/read-all", headers=headers)
    assert r3.json()["data"]["affected"] == 2  # 剩余 2 条未读

    # delete read
    r4 = await client.delete("/api/v1/notifications/read", headers=headers)
    assert r4.json()["data"]["deleted"] == 3
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest ../tests/api/test_notifications.py -v
python -m pytest ../tests/ -q
```
Expected: notifications 11 PASS（9+2）；全量无回归

- [ ] **Step 5: 提交**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add backend/app/api/v1/notifications.py backend/app/api/v1/router.py tests/api/test_notifications.py
git commit -m "feat(notifications): API endpoints + 2 integration tests"
```

---

## Task 3: 业务侧 emit 集成（AI分析完成 + 老师批注 + 支付成功）

**Files:**
- Modify: `backend/app/services/ai_service.py`
- Modify: `backend/app/services/teacher_service.py`
- Modify: `backend/app/services/order_service.py` 或 webhook（看支付确认在哪）

- [ ] **Step 1: ai_service.py — analyze 末尾发"AI分析完成"通知**

READ `app/services/ai_service.py` 末尾，找 `analyze_wrong_question` 函数 return 前，加：
```python
from app.services.notification_service import emit_analysis_done
await emit_analysis_done(db, user_id=student_id, wq_id=wq.id)
```
注意 emit 后不调用 commit（调用方控事务）。

- [ ] **Step 2: teacher_service.py — add_comment 末尾发"老师批注"通知**

READ `app/services/teacher_service.py` 的 `add_comment`，在 return 前加：
```python
from app.services.notification_service import emit_teacher_comment
await emit_teacher_comment(db, user_id=wq.student_id, wq_id=wq.id, teacher_id=teacher_id)
```

- [ ] **Step 3: 支付成功 emit 会员通知**

READ `app/api/v1/orders.py` 或 `webhooks.py`，找支付成功的位置（会员激活点）。在 membership 创建/激活后加：
```python
from app.services.notification_service import emit_membership
await emit_membership(
    db, user_id=order.user_id,
    title="会员开通成功",
    content=f"您的{order.tier}会员已激活，到期 {membership.expires_at:%Y-%m-%d}。",
    order_id=order.id,
)
```
位置自定（webhook 处理 success 那段最合适）。

- [ ] **Step 4: 跑全量测试，确认无回归**

```bash
python -m pytest ../tests/ -q
```

如有 test_wrong_questions / test_teacher 因新增 notification 写入断言失败，**只读不改**那些测试——它们插入的 WQ/comment 现在会顺带写 notification，但断言 wq/comment 本身的字段应仍 PASS。若失败需具体修复，BLOCKED + 报告。

- [ ] **Step 5: 提交**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add backend/app/services/ai_service.py backend/app/services/teacher_service.py
git add backend/app/services/order_service.py 2>/dev/null
git add backend/app/api/v1/orders.py backend/app/api/v1/webhooks.py 2>/dev/null
git commit -m "feat(notifications): emit on analyze done / teacher comment / payment success"
```

---

## Task 4: 前端 — 铃铛入口 + 消息中心页

**Files:**
- Modify: `frontend/miniprogram/src/types/api.ts`
- Create: `frontend/miniprogram/src/api/notifications.ts`
- Modify: `frontend/miniprogram/src/pages.json`
- Create: `frontend/miniprogram/src/pages/messages/index.vue`
- Modify: `frontend/miniprogram/src/pages/index/index.vue`

- [ ] **Step 1: types/api.ts 加类型**

```typescript
export interface NotificationOut {
  id: string
  type: string
  channel: 'study' | 'membership' | 'system' | 'relative' | 'teacher'
  title: string
  content: string
  is_read: boolean
  read_at: string | null
  created_at: string
  expires_at: string | null
  meta: Record<string, any> | null
}

export interface NotificationListOut {
  items: NotificationOut[]
  total: number
  unread_count: number
}
```

- [ ] **Step 2: 创建 api/notifications.ts**

```typescript
import { request } from '@/utils/request'
import type { BaseResponse, NotificationListOut, NotificationOut } from '../types/api'

export function listNotifications(params: { channel?: string; unread_only?: boolean; skip?: number; limit?: number } = {}): Promise<BaseResponse<NotificationListOut>> {
  return request('/notifications/', { method: 'GET', data: params })
}

export function getUnreadCount(): Promise<BaseResponse<{ count: number }>> {
  return request('/notifications/unread-count', { method: 'GET' })
}

export function markRead(id: string): Promise<BaseResponse<NotificationOut>> {
  return request(`/notifications/${id}/read`, { method: 'PATCH' })
}

export function markAllRead(): Promise<BaseResponse<{ affected: number }>> {
  return request('/notifications/read-all', { method: 'POST' })
}

export function deleteRead(): Promise<BaseResponse<{ deleted: number }>> {
  return request('/notifications/read', { method: 'DELETE' })
}
```

（注：用项目实际的 request 路径，可能是 `@/utils/request` 或 `./request`，照其他 api/*.ts 现有用法。）

- [ ] **Step 3: pages.json 加 1 页**

```json
{ "path": "pages/messages/index", "style": { "navigationBarTitleText": "消息中心" } }
```

- [ ] **Step 4: 创建 pages/messages/index.vue**

```vue
<template>
  <view class="page">
    <!-- 频道筛选 -->
    <view class="channels">
      <text
        v-for="c in channels"
        :key="c.key"
        class="ch"
        :class="{ active: activeChannel === c.key }"
        @tap="switchChannel(c.key)"
      >{{ c.label }}</text>
    </view>

    <!-- 操作栏 -->
    <view v-if="items.length > 0" class="actions">
      <text class="action-btn" @tap="onMarkAll">全部已读</text>
      <text class="action-btn" @tap="onDeleteRead">删除已读</text>
    </view>

    <!-- 列表 -->
    <view v-if="loading" class="tip">加载中…</view>
    <view v-else-if="items.length === 0" class="tip">暂无消息</view>
    <view
      v-for="n in items"
      :key="n.id"
      class="msg"
      :class="{ unread: !n.is_read }"
      @tap="onTap(n)"
    >
      <view v-if="!n.is_read" class="dot" />
      <view class="msg-body">
        <view class="msg-head">
          <text class="msg-title">{{ n.title }}</text>
          <text class="msg-time">{{ n.created_at.slice(5, 16).replace('T', ' ') }}</text>
        </view>
        <text class="msg-content">{{ n.content }}</text>
        <text class="msg-channel">{{ channelLabel(n.channel) }}</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listNotifications, markRead, markAllRead, deleteRead } from '@/api/notifications'
import type { NotificationOut } from '@/types/api'

const channels = [
  { key: '', label: '全部' },
  { key: 'study', label: '📚 学习' },
  { key: 'membership', label: '💳 会员' },
  { key: 'system', label: '🔔 系统' },
  { key: 'teacher', label: '👩‍🏫 老师' },
  { key: 'relative', label: '👨‍👩‍👧 亲人' },
]
const activeChannel = ref('')
const items = ref<NotificationOut[]>([])
const loading = ref(false)

function channelLabel(c: string): string {
  const m: Record<string, string> = { study: '学习', membership: '会员', system: '系统', teacher: '老师', relative: '亲人' }
  return m[c] || c
}

async function load() {
  loading.value = true
  try {
    const r = await listNotifications({ channel: activeChannel.value || undefined, limit: 50 })
    items.value = r.data?.items || []
  } finally { loading.value = false }
}

async function switchChannel(c: string) {
  activeChannel.value = c
  await load()
}

async function onTap(n: NotificationOut) {
  if (!n.is_read) {
    try { await markRead(n.id); n.is_read = true } catch { /* ignore */ }
  }
  // 联跳：根据 meta.wq_id 跳错题详情
  if (n.meta?.wq_id) {
    uni.navigateTo({ url: `/pages/wrong-questions/detail?id=${n.meta.wq_id}` })
  } else if (n.channel === 'membership') {
    uni.switchTab({ url: '/pages/profile/index' })
  }
}

async function onMarkAll() {
  try { await markAllRead(); await load(); uni.showToast({ title: '已全部标已读', icon: 'success' }) }
  catch (e: any) { uni.showToast({ title: e?.message || '操作失败', icon: 'none' }) }
}

async function onDeleteRead() {
  try { await deleteRead(); await load(); uni.showToast({ title: '已清空已读', icon: 'success' }) }
  catch (e: any) { uni.showToast({ title: e?.message || '操作失败', icon: 'none' }) }
}

onMounted(load)
</script>

<style scoped>
.page { padding: 16rpx; background: var(--c-bg-page); min-height: 100vh; }
.channels { display: flex; gap: 8rpx; padding: 8rpx 4rpx 16rpx; overflow-x: auto; }
.ch { padding: 8rpx 18rpx; background: var(--c-bg-card); border-radius: var(--r-pill); font-size: 24rpx; color: var(--c-text-second); white-space: nowrap; }
.ch.active { background: var(--c-primary); color: var(--c-ink); font-weight: 700; }
.actions { display: flex; gap: 16rpx; padding: 8rpx 8rpx 16rpx; }
.action-btn { font-size: 24rpx; color: var(--c-gold); font-weight: 600; padding: 4rpx 12rpx; }
.tip { text-align: center; padding: 80rpx 0; color: var(--c-text-hint); font-size: 26rpx; }
.msg { display: flex; gap: 12rpx; background: var(--c-bg-card); border-radius: var(--r-lg); padding: 24rpx; margin-bottom: 12rpx; box-shadow: 0 2rpx 12rpx rgba(0,0,0,.03); }
.msg.unread { background: var(--c-primary-faint); border-left: 4rpx solid var(--c-gold); }
.dot { width: 12rpx; height: 12rpx; background: var(--c-orange); border-radius: 50%; margin-top: 12rpx; flex-shrink: 0; }
.msg-body { flex: 1; }
.msg-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6rpx; }
.msg-title { font-size: 28rpx; font-weight: 700; color: var(--c-ink); }
.msg-time { font-size: 22rpx; color: var(--c-text-hint); }
.msg-content { font-size: 26rpx; color: var(--c-text-body); line-height: 1.5; display: block; margin-bottom: 6rpx; }
.msg-channel { font-size: 22rpx; color: var(--c-text-hint); }
</style>
```

- [ ] **Step 5: 改 pages/index/index.vue 加铃铛 + 未读数**

READ 现有内容（已有 onMounted + profile 拦截）。在 template 的 `<view class="home-page">` 内最顶部加铃铛：

```vue
    <view class="topbar">
      <view class="bell-wrap" @tap="goMessages">
        <text class="bell">🔔</text>
        <text v-if="unreadCount > 0" class="badge">{{ unreadCount > 99 ? '99+' : unreadCount }}</text>
      </view>
    </view>
```

script 加：
```typescript
import { getUnreadCount } from '@/api/notifications'
const unreadCount = ref(0)
async function loadUnread() {
  if (!auth.isLoggedIn()) return
  try { const r = await getUnreadCount(); unreadCount.value = r.data?.count || 0 } catch { /* ignore */ }
}
function goMessages() { uni.navigateTo({ url: '/pages/messages/index' }) }
```
现有 onMounted 末尾追加 `await loadUnread()`，并加一个 onShow 刷新（uni-app 用 `onShow` from `@dcloudio/uni-app`）：
```typescript
import { onShow } from '@dcloudio/uni-app'
onShow(loadUnread)
```

样式：
```css
.topbar { display: flex; justify-content: flex-end; padding: 8rpx 0 16rpx; }
.bell-wrap { position: relative; padding: 8rpx; }
.bell { font-size: 40rpx; }
.badge { position: absolute; top: 0; right: 0; background: var(--c-danger); color: #fff; font-size: 20rpx; min-width: 28rpx; height: 28rpx; line-height: 28rpx; padding: 0 6rpx; border-radius: 999rpx; text-align: center; font-weight: 700; }
```

- [ ] **Step 6: 提交前端**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add frontend/miniprogram/src/types/api.ts \
        frontend/miniprogram/src/api/notifications.ts \
        frontend/miniprogram/src/pages.json \
        frontend/miniprogram/src/pages/messages/ \
        frontend/miniprogram/src/pages/index/index.vue
git commit -m "feat(notifications): frontend — bell + message center page"
```

---

## Task 5: 集成验证 + 归档 D-074 + Push

- [ ] **Step 1: 全量后端测试**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/ -q
```
Expected: 187 + 11 = 198 PASS

- [ ] **Step 2: live server 冒烟**

```bash
uvicorn app.main:app --port 8024 --log-level warning &
UVICORN_PID=$!
sleep 3
curl -s http://localhost:8024/openapi.json | python3 -c "
import json,sys
spec = json.load(sys.stdin)
paths = sorted([p for p in spec['paths'].keys() if '/notifications' in p])
print('通知端点:')
for p in paths: print('  ', p)
print('count:', len(paths))
"
kill $UVICORN_PID 2>/dev/null || true
sleep 1
```
Expected: 5 个端点

- [ ] **Step 3: 归档 D-074 到 `docs/决策归档.md`（插入在 D-073 之前）**

```markdown
## D-074｜站内消息中心 MVP（Module 7B）

**日期：** 2026-05-27
**背景：** P0 学生端最后一个缺口——老师批注/AI分析完成/支付结果等关键节点用户错过实时推送后无任何回看入口；微信小程序 subscribeMessage 授权率低，站内消息中心是兜底的"看得到"通道。
**结论：**
1. **数据层（迁移 0006）：** 复用既有 `notifications` 表（D-059 d9_system 已建），加 3 列 `channel/expires_at/meta` 和 `(user_id, is_read)` 复合索引；不动 `notification_type` enum（保留原 9 值）。
2. **频道分类（§916）：** 服务侧从 type 推导 channel（study/membership/system/relative/teacher 五频道）作用户可见分组；type 仍用于精确语义。
3. **保留期（§936）：** 会员类 365 天、其他 90 天，写入 `expires_at` 作过期标记（实际清理交后续 cron，本批不做物理删除）。
4. **业务集成点（3 处）：** `ai_service.analyze_wrong_question` 末尾 emit_analysis_done；`teacher_service.add_comment` 末尾 emit_teacher_comment；支付成功（webhook/order）emit_membership。emit 不 commit，由调用方控事务。
5. **API（5 个）：** GET `/notifications` 列表（channel 筛选 + unread_only + 分页 + 总未读数）、GET `/notifications/unread-count`（铃铛角标专用快端点）、PATCH `/notifications/{id}/read`、POST `/notifications/read-all`、DELETE `/notifications/read`。
6. **前端：** 首页右上角 🔔 铃铛 + 未读数 badge（onShow 刷新，避免离开页面回来失效）；新页 `pages/messages/index.vue` 横向频道筛选 chips + 全部已读/删除已读 + 未读高亮 + 联跳（meta.wq_id 跳错题详情、membership 跳 profile）。
7. **测试：** 11 个测试（2 schema/sync + 7 service + 2 API），全量 198 PASS。
8. **未做（遗留）：** 推送（subscribeMessage）与站内消息同步写——前端授权流程未做；会员到期提醒（需 cron 扫描 membership.expires_at）；老师端额外通知（学生交卷待批改、周班级报告——待班级模块就绪）；过期通知物理清理 cron；推送渠道（小程序模板/企业微信）。
**影响范围：** 迁移 0006（notifications 表 3 列 + 1 索引）；5 个新 API 端点；1 个新前端页 + 首页铃铛；测试 +11；已推送 GitHub main 分支。

---

```

- [ ] **Step 4: 提交 + push**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add "docs/决策归档.md"
git commit -m "docs: archive D-074 — message center MVP (Module 7B)"
git push
```

---

## Self-Review

### Spec 覆盖
| §7B 需求条目 | 实现位置 |
|------|------|
| 5 频道分类 | service TYPE_TO_CHANNEL + 前端 chips |
| 已读/未读区分 + 高亮 | message 列表 unread class + dot |
| 全部已读 / 删除已读 | mark_all_read + delete_read 端点 |
| 保留期 12月/3月 | _expires_at_for + expires_at 字段（cron 物理清理待做） |
| 推送同步写消息中心 | 业务侧 emit hooks（推送本身未做） |
| 首页铃铛角标 | index.vue topbar + unreadCount + onShow |
| B 端额外消息 | 未做，归档明列遗留（待班级/作业模块） |

### 类型一致性
- `channel` 字段在 model / schema / 前端 chip 一致使用 5 个 key
- `meta.wq_id` 在 emit_analysis_done/emit_teacher_comment 写入 + 前端 onTap 读取联跳
- `unread_count` 在 list 端点和 unread-count 专门端点返回一致 int

### Placeholder 扫描
无 TBD/TODO；过期清理/推送授权/B 端通知已在归档明列遗留。
