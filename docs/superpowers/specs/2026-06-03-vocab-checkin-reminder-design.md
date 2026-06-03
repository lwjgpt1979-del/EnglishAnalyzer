# 打卡提醒双通道 设计（D-108）

**日期：** 2026-06-03
**归属：** 词力通打卡激励 4 项后续之 ④（收尾，依赖最重）。前序：D-100~D-107。

## 背景与目标

给"昨天打了卡、今天还没打"的学生发**打卡提醒**，防断签。双通道：**站内消息**（真发，复用消息中心）+ **微信订阅消息**（dev-mock 骨架，占位 key → 记日志）。项目无定时任务基础设施，故提醒触发做成 **CLI 脚本供外部 cron 调用**，不引入 apscheduler、不开公网端点。

## 关键决策（已确认）

- 提醒对象：**仅"昨日有打卡行、今日无打卡行"**的学生（精准防断签）。
- 触发入口：**CLI 脚本**（核心逻辑在 service），外部 crontab 每晚调用。
- 微信订阅消息：**后端 dev-mock 骨架先行**，前端 `requestSubscribeMessage` 授权留后续。
- 站内消息类型：新增 enum 值 `checkin_reminder`（**迁移 0018**，本系列唯一迁移）。
- **无前端改动**、无花钱（dev-mock）。

## 架构与组件

### 1. 配置（`backend/app/core/config.py`）
新增（沿用 SMS 的 `placeholder-*` dev-mock 判定）：
```python
wechat_subscribe_provider: str = "placeholder-dev"          # 'placeholder-*' 触发 dev mock
wechat_subscribe_template_checkin: str = "placeholder-template-checkin"
```
对应 `.env` 可加（gitignored，不提交真值）：`WECHAT_SUBSCRIBE_PROVIDER=`、`WECHAT_SUBSCRIBE_TEMPLATE_CHECKIN=`。

### 2. 迁移 0018（`alembic/versions/0018_checkin_reminder_enum.py`）
对标 0009 的 enum-add 写法：
```python
revision = "0018"
down_revision = "0017"

def upgrade() -> None:
    op.execute("COMMIT")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'checkin_reminder'")

def downgrade() -> None:
    pass  # PG 不支持 enum 值删除（会孤立已用该值的行）
```
**需应用到 DB**（`DATABASE_URL=... alembic upgrade head`），否则站内消息 emit 该类型会报错。

### 3. 微信订阅消息 service（`backend/app/services/wechat_subscribe_service.py`，新建）
```python
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)


def _is_dev() -> bool:
    return settings.wechat_subscribe_provider.startswith("placeholder")


async def send_checkin_reminder(*, openid: str, streak_days: int) -> bool:
    """发送打卡提醒订阅消息。dev-mock：记日志返回 True；prod 走真实微信 API（未接入）。"""
    if _is_dev():
        logger.info(
            "[WX SUBSCRIBE DEV MOCK] checkin reminder openid=%s streak=%s template=%s",
            openid, streak_days, settings.wechat_subscribe_template_checkin,
        )
        return True
    raise NotImplementedError("生产微信订阅消息 provider 未接入")
```

### 4. 站内消息（`backend/app/services/notification_service.py`）
- `TYPE_TO_CHANNEL` 增加 `"checkin_reminder": "study"`。
- 新增便捷函数：
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

### 5. 提醒编排 service（`backend/app/services/reminder_service.py`，新建）
```python
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d1_users import User
from app.models.d5_learning import StudyCheckin
from app.services import checkin_service, notification_service, wechat_subscribe_service


async def find_reminder_targets(db: AsyncSession) -> list[tuple[uuid.UUID, str | None]]:
    """昨日有打卡行、今日无打卡行的学生 → (student_id, openid)。"""
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

### 6. CLI 触发入口（`backend/app/tasks/send_checkin_reminders.py` + `__init__.py`，新建）
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
> 部署：服务器 crontab 例 `0 20 * * * cd /app/backend && DATABASE_URL=... python -m app.tasks.send_checkin_reminders`（写入归档/上线清单，不在本批落地真实 cron）。

## 数据流

外部 cron → CLI → `run_checkin_reminders` → `find_reminder_targets`（昨日有/今日无）→ 逐人 emit 站内消息（真发）+ wechat_subscribe dev-mock（记日志）→ 提交。

## 错误处理

- dev-mock 不真发、不抛错（占位 provider）。
- 单个学生发送失败不应中断整体（MVP 可不做 per-user try/catch；若 emit/订阅抛错则整批失败回滚——MVP 接受，后续可加容错）。实现保持简单：异常上抛由 CLI 体现退出码。

## 测试（TDD）

**`tests/services/test_reminder_service.py`（新建）**
1. `find_reminder_targets`：学生A 昨日有行+今日无行 → 在名单；学生B 今日已打 → 不在；学生C 仅前天有行 → 不在。
2. `run_checkin_reminders`：对学生A 执行后 `notified>=1`，且其站内出现 `type='checkin_reminder'`、`channel='study'` 的 Notification。

**`tests/services/test_wechat_subscribe_service.py`（新建）**
3. dev-mock：`send_checkin_reminder(openid=..., streak_days=3)` 返回 True、不抛错。

> 注：测试依赖迁移 0018 已应用（enum 值存在），故先 `alembic upgrade head`。

## 影响范围

- `backend/app/core/config.py`（2 配置）
- `backend/alembic/versions/0018_checkin_reminder_enum.py`（新，**迁移**）
- `backend/app/services/wechat_subscribe_service.py`（新，dev-mock）
- `backend/app/services/notification_service.py`（TYPE_TO_CHANNEL + emit_checkin_reminder）
- `backend/app/services/reminder_service.py`（新）
- `backend/app/tasks/send_checkin_reminders.py` + `__init__.py`（新，CLI）
- `tests/services/test_reminder_service.py`、`test_wechat_subscribe_service.py`（新）
- **无前端、无花钱**；**含迁移 0018**。

## 不做（后续）

- 前端 `requestSubscribeMessage` 授权入口 + 真实模板ID（需真实小程序订阅消息配置）
- 真实微信订阅消息 API 接入（prod provider）
- 真实定时调度（apscheduler/celery）——本批用外部 cron
- 提醒频率控制 / 免打扰时段 / 用户开关持久化
- per-user 发送容错与重试

## 相关

D-104~107（打卡系列）、D-074（消息中心）；需求 §6.4。
