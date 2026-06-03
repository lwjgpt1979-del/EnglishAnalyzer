# 打卡提醒双通道 Implementation Plan（D-108）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给"昨日打卡、今日未打"的学生发打卡提醒（站内消息真发 + 微信订阅消息 dev-mock），CLI 供外部 cron 触发。

**Architecture:** 配置占位 dev-mock；新增 `checkin_reminder` 通知类型（迁移 0018）；reminder_service 编排"昨日有/今日无"目标 → 双通道发送；CLI 入口供 crontab。

**Tech Stack:** FastAPI + SQLAlchemy 2.x asyncio + Pydantic v2 + PostgreSQL + Alembic。**含迁移 0018**、无前端、无花钱。

**运行约定：** 后端 python = `/opt/anaconda3/bin/python`，pytest 从 `backend/` 跑、路径 `../tests/...`、加 `-p no:randomly`。迁移：`cd backend && DATABASE_URL=$(grep -E '^DATABASE_URL=' .env | cut -d= -f2-) /opt/anaconda3/bin/python -m alembic upgrade head`。

---

## File Structure

| 文件 | 改动 |
|---|---|
| `backend/app/core/config.py` | +`wechat_subscribe_provider`/`wechat_subscribe_template_checkin` |
| `backend/alembic/versions/0018_checkin_reminder_enum.py` | 新：enum ADD VALUE |
| `backend/app/services/wechat_subscribe_service.py` | 新：dev-mock 订阅消息 |
| `backend/app/services/notification_service.py` | +TYPE_TO_CHANNEL + emit_checkin_reminder |
| `backend/app/services/reminder_service.py` | 新：find_targets + run |
| `backend/app/tasks/__init__.py` + `send_checkin_reminders.py` | 新：CLI |
| `tests/services/test_wechat_subscribe_service.py` | 新 |
| `tests/services/test_reminder_service.py` | 新 |

---

## Task 1: 配置 + 微信订阅消息 dev-mock service

**Files:**
- Modify: `backend/app/core/config.py`
- Create: `backend/app/services/wechat_subscribe_service.py`
- Test: `tests/services/test_wechat_subscribe_service.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/services/test_wechat_subscribe_service.py`：
```python
"""微信订阅消息 dev-mock 测试（D-108）。"""
import pytest

from app.services import wechat_subscribe_service


@pytest.mark.asyncio
async def test_send_checkin_reminder_dev_mock():
    # 默认 placeholder provider → dev mock，返回 True 不抛错
    ok = await wechat_subscribe_service.send_checkin_reminder(openid="ox_test", streak_days=3)
    assert ok is True


def test_is_dev_default():
    assert wechat_subscribe_service._is_dev() is True
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_wechat_subscribe_service.py -p no:randomly -q`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 加配置**

在 `backend/app/core/config.py` 的 Settings 类中，SMS 配置附近追加两行：
```python
    # 微信订阅消息（打卡提醒，D-108）
    wechat_subscribe_provider: str = "placeholder-dev"  # 'placeholder-*' 触发 dev mock
    wechat_subscribe_template_checkin: str = "placeholder-template-checkin"
```

- [ ] **Step 4: 建 service**

创建 `backend/app/services/wechat_subscribe_service.py`：
```python
"""微信订阅消息服务（D-108）。MVP dev-mock：占位 provider 仅记日志，不真发。"""
from __future__ import annotations

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


def _is_dev() -> bool:
    return settings.wechat_subscribe_provider.startswith("placeholder")


async def send_checkin_reminder(*, openid: str, streak_days: int) -> bool:
    """发送打卡提醒订阅消息。dev-mock 记日志返回 True；prod 走真实微信 API（未接入）。"""
    if _is_dev():
        logger.info(
            "[WX SUBSCRIBE DEV MOCK] checkin reminder openid=%s streak=%s template=%s",
            openid, streak_days, settings.wechat_subscribe_template_checkin,
        )
        return True
    raise NotImplementedError("生产微信订阅消息 provider 未接入")
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_wechat_subscribe_service.py -p no:randomly -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/core/config.py backend/app/services/wechat_subscribe_service.py tests/services/test_wechat_subscribe_service.py
git commit -m "feat(backend): 微信订阅消息 dev-mock service + 配置（打卡提醒）"
```

---

## Task 2: 迁移 0018 + 站内消息 checkin_reminder

**Files:**
- Create: `backend/alembic/versions/0018_checkin_reminder_enum.py`
- Modify: `backend/app/services/notification_service.py`
- Test: `tests/services/test_notification_checkin.py`（新建）

- [ ] **Step 1: 写迁移 0018**

创建 `backend/alembic/versions/0018_checkin_reminder_enum.py`（对标 0009）：
```python
"""add checkin_reminder to notification_type enum (D-108)

Revision ID: 0018
Revises: 0017
Create Date: 2026-06-03

PostgreSQL: ALTER TYPE ... ADD VALUE 必须在事务外执行，故先 COMMIT。
Downgrade 为 no-op（PG 不支持删除 enum 值）。
"""
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("COMMIT")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'checkin_reminder'")


def downgrade() -> None:
    pass
```

- [ ] **Step 2: 应用迁移到 DB**

Run: `cd backend && DATABASE_URL=$(grep -E '^DATABASE_URL=' .env | cut -d= -f2-) /opt/anaconda3/bin/python -m alembic upgrade head`
Expected: 升级到 0018，无报错。可 `... alembic current` 确认 `0018 (head)`。

- [ ] **Step 3: 写失败测试**

创建 `tests/services/test_notification_checkin.py`：
```python
"""打卡提醒站内消息测试（D-108）。"""
import uuid

import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.services import notification_service


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _student(s) -> uuid.UUID:
    from app.services.auth_service import upsert_user
    u = await upsert_user(s, openid=f"notif_{uuid.uuid4().hex[:8]}")
    await s.flush()
    return u.id


@pytest.mark.asyncio
async def test_emit_checkin_reminder(db_session):
    sid = await _student(db_session)
    n = await notification_service.emit_checkin_reminder(
        db_session, user_id=sid, streak_days=5)
    assert str(n.type) == "checkin_reminder"
    assert n.channel == "study"
    assert "5" in n.content
```

- [ ] **Step 4: 跑测试确认失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_notification_checkin.py -p no:randomly -q`
Expected: FAIL（`emit_checkin_reminder` 不存在）

- [ ] **Step 5: 改 notification_service**

在 `backend/app/services/notification_service.py` 的 `TYPE_TO_CHANNEL` 字典追加一项：
```python
    "checkin_reminder": "study",
```
在 `emit_membership` 之后追加：
```python
async def emit_checkin_reminder(
    db: AsyncSession, *, user_id: uuid.UUID, streak_days: int,
) -> Notification:
    return await emit(
        db, user_id=user_id, type_="checkin_reminder",
        title="别让连续中断啦",
        content=f"你已连续打卡 {streak_days} 天，今天还没学，快来词力通保持记录！",
        meta={"streak_days": streak_days},
    )
```

- [ ] **Step 6: 跑测试确认通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_notification_checkin.py -p no:randomly -q`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add backend/alembic/versions/0018_checkin_reminder_enum.py backend/app/services/notification_service.py tests/services/test_notification_checkin.py
git commit -m "feat(backend): 站内打卡提醒消息 checkin_reminder（迁移0018）"
```

---

## Task 3: reminder_service + CLI 入口

**Files:**
- Create: `backend/app/services/reminder_service.py`
- Create: `backend/app/tasks/__init__.py`, `backend/app/tasks/send_checkin_reminders.py`
- Test: `tests/services/test_reminder_service.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/services/test_reminder_service.py`：
```python
"""打卡提醒编排测试（D-108）。"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.database import _async_session_factory
from app.models.d5_learning import StudyCheckin
from app.models.d9_system import Notification
from app.services import reminder_service


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _student(s) -> uuid.UUID:
    from app.services.auth_service import upsert_user
    u = await upsert_user(s, openid=f"rem_{uuid.uuid4().hex[:8]}")
    await s.flush()
    return u.id


def _today():
    return datetime.now(timezone.utc).date()


def _add(s, sid, d):
    s.add(StudyCheckin(id=uuid.uuid4(), student_id=sid, checkin_date=d,
                       new_words_count=1, review_done=True, streak_days=1))


@pytest.mark.asyncio
async def test_find_targets(db_session):
    a = await _student(db_session)  # 昨日有、今日无 → 命中
    b = await _student(db_session)  # 今日已打 → 不命中
    c = await _student(db_session)  # 仅前天 → 不命中
    _add(db_session, a, _today() - timedelta(days=1))
    _add(db_session, b, _today() - timedelta(days=1))
    _add(db_session, b, _today())
    _add(db_session, c, _today() - timedelta(days=2))
    await db_session.flush()
    targets = await reminder_service.find_reminder_targets(db_session)
    ids = {t[0] for t in targets}
    assert a in ids
    assert b not in ids
    assert c not in ids


@pytest.mark.asyncio
async def test_run_reminders_emits_notification(db_session):
    a = await _student(db_session)
    _add(db_session, a, _today() - timedelta(days=1))
    await db_session.flush()
    res = await reminder_service.run_checkin_reminders(db_session)
    assert res["notified"] >= 1
    rows = (await db_session.execute(
        select(Notification).where(
            Notification.user_id == a, Notification.type == "checkin_reminder")
    )).scalars().all()
    assert len(rows) == 1 and rows[0].channel == "study"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_reminder_service.py -p no:randomly -q`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 建 reminder_service**

创建 `backend/app/services/reminder_service.py`：
```python
"""打卡提醒编排（D-108）。找出"昨日有/今日无"的学生，双通道发送。"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d1_users import User
from app.models.d5_learning import StudyCheckin
from app.services import checkin_service, notification_service, wechat_subscribe_service


async def find_reminder_targets(db: AsyncSession) -> list[tuple[uuid.UUID, str | None]]:
    """昨日有打卡行、今日无打卡行的学生 → [(student_id, openid)]。"""
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    yest_ids = {r[0] for r in (await db.execute(
        select(StudyCheckin.student_id).where(StudyCheckin.checkin_date == yesterday)
    )).all()}
    today_ids = {r[0] for r in (await db.execute(
        select(StudyCheckin.student_id).where(StudyCheckin.checkin_date == today)
    )).all()}
    targets = yest_ids - today_ids
    if not targets:
        return []
    rows = (await db.execute(
        select(User.id, User.openid).where(User.id.in_(targets))
    )).all()
    return [(r[0], r[1]) for r in rows]


async def run_checkin_reminders(db: AsyncSession) -> dict:
    """对所有待提醒学生发送站内 + 微信订阅消息（dev-mock）。返回 {notified}。"""
    targets = await find_reminder_targets(db)
    notified = 0
    for student_id, openid in targets:
        status = await checkin_service.get_checkin_status(db, student_id=student_id)
        await notification_service.emit_checkin_reminder(
            db, user_id=student_id, streak_days=status["current_streak"])
        if openid:
            await wechat_subscribe_service.send_checkin_reminder(
                openid=openid, streak_days=status["current_streak"])
        notified += 1
    return {"notified": notified}
```

- [ ] **Step 4: 建 CLI 入口**

创建 `backend/app/tasks/__init__.py`（空文件）。
创建 `backend/app/tasks/send_checkin_reminders.py`：
```python
"""打卡提醒 CLI：供服务器 crontab 每晚调用。
用法：DATABASE_URL=... python -m app.tasks.send_checkin_reminders
"""
import asyncio

from app.core.database import _async_session_factory
from app.services import reminder_service


async def _main() -> None:
    async with _async_session_factory() as s:
        res = await reminder_service.run_checkin_reminders(s)
        await s.commit()
        print(f"[checkin-reminders] notified={res['notified']}")


if __name__ == "__main__":
    asyncio.run(_main())
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_reminder_service.py -p no:randomly -q`
Expected: PASS

- [ ] **Step 6: CLI 冒烟（可选，确认可导入运行）**

Run: `cd backend && /opt/anaconda3/bin/python -c "import app.tasks.send_checkin_reminders as m; print('import ok')"`
Expected: `import ok`

- [ ] **Step 7: 提交**

```bash
git add backend/app/services/reminder_service.py backend/app/tasks/ tests/services/test_reminder_service.py
git commit -m "feat(backend): 打卡提醒编排 reminder_service + CLI 入口"
```

---

## Task 4: 全量回归 + 归档 D-108

**Files:**
- Modify: `docs/决策归档.md`

- [ ] **Step 1: 后端全量回归**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests -p no:randomly -q`
Expected: PASS（约 405 passed；净增约 5 例。已知 flaky `test_get_wrong_question_api` 若失败，隔离重跑确认通过）

- [ ] **Step 2: 归档 D-108**

在 `docs/决策归档.md` 顶部（`## D-107` 之前）插入 D-108 条目：日期、背景、结论（配置 dev-mock / 迁移0018 checkin_reminder / wechat_subscribe_service dev-mock / reminder_service 昨日有今日无 / CLI 供 cron）、测试（后端全量 passed）、影响范围、部署提示（crontab 示例）、未做（前端授权/真实 provider/真实调度/频控）、相关（D-104~107、D-074，§6.4）。同时可在末尾标注"词力通打卡激励 4 项后续（D-105~108）全部完成"。

- [ ] **Step 3: 提交**

```bash
git add docs/决策归档.md
git commit -m "docs: 归档 D-108 打卡提醒双通道（打卡激励4项收尾）"
```

- [ ] **Step 4: 询问用户是否 push**

报告 commit 列表 + 测试结果 + "打卡激励 4 项全部完成"，征求明确同意后 `git push`。

---

## Self-Review

**1. Spec 覆盖：**
- 配置 dev-mock + wechat_subscribe_service → Task 1 ✓
- 迁移 0018 + 应用 + emit_checkin_reminder + 渠道映射 → Task 2 ✓
- reminder_service（昨日有/今日无 + 双通道）+ CLI → Task 3 ✓
- 仅"明天断签"口径 → Task 3 find_reminder_targets ✓
- 无前端、含迁移、无花钱 → 符合 ✓

**2. 占位符扫描：** 无 TBD/TODO；每步含完整代码与命令。

**3. 类型一致：** `find_reminder_targets` 返回 `list[tuple[uuid, str|None]]`，`run_checkin_reminders` 解包 `(student_id, openid)` 一致；`emit_checkin_reminder(db, *, user_id, streak_days)` 签名与调用一致；`send_checkin_reminder(*, openid, streak_days)` 签名与调用一致；通知类型字符串 `"checkin_reminder"` 与迁移 enum 值一致；`get_checkin_status` 返回 `current_streak` 键被复用一致。
