# 机构端切片八：机构会员到期预警通知（D-127）设计文档

> 零迁移、dev-mock 无花钱（站内通知，不接企业微信）。

## 目标

每日 cron 跑预警：对每个机构，名下学生有近 30 天到期的有效会员时，给该机构所有管理员发站内通知；机构管理员在 admin web 新增的「通知」中心查看。

## 背景与现状

- `notification_service.emit(db, *, user_id, type_, title, content, meta=None)`；`notification_type` 枚举含 `membership` / `system`（无需新枚举值）。
- `/notifications/*` API（list / unread-count / {id}/read / read-all / delete read）用 `get_current_user`，任何登录用户（含 institution_admin）可调。
- `reminder_service` + `tasks/send_checkin_reminders.py`（D-108）是 cron 预警范式。
- 机构体系 D-120~126 就绪：`students.institution_id`、`users.institution_id`（机构管理员）、`memberships(user_id/expires_at/is_active/tier)`。
- 缺口：机构管理员用 admin web，现有站内消息中心在小程序端，admin web 无通知入口 → 本切片补 admin web 通知中心。

## 架构

cron 每日执行 `run_expiry_alerts` → 遍历机构 → 统计名下学生近 30 天到期有效会员数 → >0 则给该机构每个管理员 `emit(type_="membership")` → 机构管理员在 admin web「通知」中心（复用现有 `/notifications/*`）查看。零迁移、无付费调用。

## 后端组件

### `institution_expiry_alert_service.py`（新建）

```
async def run_expiry_alerts(db: AsyncSession, *, days: int = 30) -> dict:
    # now = utcnow; cutoff = now + days 天
    # 找出所有机构管理员：select User where role=='institution_admin' and institution_id is not None
    #   按 institution_id 分组成 {inst_id: [admin_user_id, ...]}
    # 对每个 inst_id：
    #   expiring = count(distinct Membership.user_id) where
    #       user_id in (select Student.id where Student.institution_id == inst_id)
    #       and Membership.is_active and Membership.expires_at is not None
    #       and now <= Membership.expires_at <= cutoff
    #   若 expiring > 0：对每个 admin emit(
    #       type_="membership", title="会员到期预警",
    #       content=f"您机构有 {expiring} 名学生会员将在 {days} 天内到期，请及时续费")
    #       并 institutions_notified += 1（每机构计一次）、admins_notified += len(admins)
    # 返回 {"institutions_notified": int, "admins_notified": int}
```

实现要点：复用 `select`/`func` 聚合；emit 由调用方决定 commit（service 内只 flush，CLI/测试负责 commit，与 reminder_service 一致——以 reminder_service 实际行为为准，若其内部 commit 则照做）。

### `tasks/send_expiry_alerts.py`（新建，CLI cron）

镜像 `tasks/send_checkin_reminders.py`：建 async session → `await run_expiry_alerts(db)` → commit → print 摘要。供 cron 每日调用。

## 前端（admin web）

- `api/notifications.ts`（新）：
  - `listNotifications()` → GET `/notifications/`（取 items）
  - `markRead(id)` → PATCH `/notifications/{id}/read`
  - `unreadCount()` → GET `/notifications/unread-count`
  - 返回类型按现有后端响应结构（`NotificationListOut` items[]、`UnreadCountOut`）适配。
- `views/Notifications.vue`：通知列表（标题 / 内容 / 时间 / 已读态），每条未读可「标为已读」；顶部显示未读数。
- router 加 `/notifications`；MainLayout 两个角色分支都加「通知」菜单项（platform_admin 与 institution_admin 均可用）。

## 测试

**service**（`tests/services/test_institution_expiry_alert.py`）：
- 名下学生有近 30 天到期 active 会员 → 该机构管理员收到 1 条 membership 通知（查 Notification 表）。
- 无近 30 天到期 → 不发。
- 跨机构隔离：A、B 各有到期会员，A 管理员只收到关于 A 的通知（按 user_id 校验）。
- 多管理员：同机构 2 个管理员都收到。

**dev-mock**：纯 DB，无企业微信/LLM/媒体。CLI 仅需可 import + 运行（不强制单测）。

## 不做（后续切片）

企业微信真实推送、去重/合并跨日（每日一条聚合已是当日合并）、可配置阈值天数、老师账号变更通知、邮件/短信、admin web 未读红点轮询。

## 影响范围

- 新增：`institution_expiry_alert_service.py`、`tasks/send_expiry_alerts.py`；admin web `api/notifications.ts`、`views/Notifications.vue`。
- 修改：admin web `router/index.ts`、`layouts/MainLayout.vue`（两角色加「通知」菜单）。
- 无数据库迁移，无新依赖，无付费调用。
