# V2 M30 Spec：学情周报推送（家长端）

**日期**：2026-06-09  
**状态**：设计中

---

## 一、背景与目标

家长绑定孩子后，希望每周了解孩子的学习情况，而不必手动查看小程序。

**目标**：每周一早 8 点，自动给每个绑定了孩子的家长（relative）发送上周学情摘要：
- 打卡天数（7 天中打了几天）
- 做题数（仿真题 + 整卷错题数）
- 连续打卡最高天数
- 最需加强的知识点（top-2 薄弱点）

**双通道推送**：
1. **站内通知**（`notifications` 表）：复用现有 `notification_service.emit`，家长在小程序"消息中心"可见
2. **微信订阅消息**（可选）：复用 `wechat_subscribe_service`，需家长提前授权（单独 template_id）

**MVP 范围**：站内通知必做，微信订阅消息预留接口但 dev-mock（需额外申请模板）。

---

## 二、数据模型（零迁移）

复用现有表：

| 表 | 用途 |
|---|---|
| `student_relatives` | 找到每个学生绑定的家长列表 |
| `study_checkins` | 本周打卡记录（checkin_date, streak_days） |
| `sim_practice_records` | 本周仿真题做题数 |
| `user_paper_questions` | 本周整卷错题数（is_wrong=True） |
| `ai_analyses` | 薄弱知识点（knowledge_points 字段按频次统计） |
| `notifications` | 输出：家长侧站内通知 |

---

## 三、服务设计

### `weekly_report_service.py`

#### `generate_student_weekly_report(db, *, student_id, week_start) -> WeeklyReportData`

```python
@dataclass
class WeeklyReportData:
    student_id: uuid.UUID
    student_nickname: str
    week_start: date        # ISO，如 2026-06-02
    week_end: date          # week_start + 6 天
    checkin_days: int       # 本周打卡天数（0-7）
    practice_count: int     # 仿真题做题数
    wrong_paper_count: int  # 整卷错题数
    max_streak: int         # 本周最高连续打卡天数
    weak_kp_names: list[str]  # top-2 薄弱知识点名
```

查询逻辑：
- `checkin_days`: `COUNT(*)` WHERE `checkin_date BETWEEN week_start AND week_end AND student_id=...`
- `max_streak`: `MAX(streak_days)` 同上
- `practice_count`: `COUNT(*)` FROM `sim_practice_records` WHERE `created_at` in 本周
- `wrong_paper_count`: `COUNT(*)` FROM `user_paper_questions` WHERE `is_wrong=True AND created_at` in 本周
- `weak_kp_names`: 从 `ai_analyses.knowledge_points` 取近 30 天数据，按频次 top-2

#### `run_weekly_reports(db) -> dict`

```python
async def run_weekly_reports(db: AsyncSession) -> dict:
    """供 cron 每周一 08:00 调用。
    遍历所有有家长绑定的学生，生成周报并给每个家长发通知。
    返回 {students_processed, relatives_notified}。
    """
```

逻辑：
1. 查询上周的 `week_start`（上周一），`week_end`（上周日）
2. 查 `student_relatives` 得到 [(student_id, relative_id), ...]
3. 去重 student_id，批量生成周报
4. 对每个 relative，发站内通知（type=`weekly_report`）
5. （可选）调 `wechat_subscribe_service.send_weekly_report` dev-mock

---

## 四、通知格式

### 站内通知（`notifications`）

```
type: "weekly_report"
channel: "study"
title: "📊 {nickname}本周学情周报"
body: "打卡 {checkin_days}/7 天，做题 {practice_count} 道{weak_kp_str}"
```

其中 `weak_kp_str`：
- 无薄弱点：`""` 
- 有：`，薄弱点：{kp1}、{kp2}`

### 微信订阅消息（预留，dev-mock）

```python
async def send_weekly_report_wx(*, openid: str, nickname: str, checkin_days: int, practice_count: int) -> bool:
    # 生产需申请对应模板，dev-mock 只记日志
```

---

## 五、API（可选，供前端拉取最近一条周报详情）

暂不新增 API，家长通过"消息中心"查看站内通知即可（通知 body 已含摘要）。

---

## 六、Config

```python
# 已有，无需新增字段
WECHAT_SUBSCRIBE_TEMPLATE_WEEKLY_REPORT=  # 留空 = dev-mock
```

---

## 七、测试策略

`tests/services/test_weekly_report_service.py`：

1. `test_generate_report_counts_checkins` — 有打卡记录时正确统计天数
2. `test_generate_report_no_data_returns_zeros` — 无记录时全部 0
3. `test_run_weekly_reports_notifies_relatives` — 有绑定家长时发站内通知
4. `test_run_weekly_reports_no_relatives_skips` — 无家长绑定时 notified=0
5. `test_run_weekly_reports_dedup_student` — 同一学生多个家长时每个家长都收到

---

## 八、CLI + cron

`backend/app/tasks/send_weekly_reports.py`：

```python
"""学情周报 CLI：服务器 crontab 每周一 08:00 调用。
用法：DATABASE_URL=... python -m app.tasks.send_weekly_reports
"""
```

Cron 条目：
```
0 8 * * 1 cd /opt/enggramer/backend && DATABASE_URL=... /path/python -m app.tasks.send_weekly_reports
```

---

## 九、文件修改清单

| 文件 | 变更 |
|---|---|
| `backend/app/services/weekly_report_service.py` | 新建，核心逻辑 |
| `backend/app/tasks/send_weekly_reports.py` | 新建，CLI 入口 |
| `backend/app/services/notification_service.py` | 新增 `weekly_report` type 到 `TYPE_TO_CHANNEL` |
| `backend/app/services/wechat_subscribe_service.py` | 新增 `send_weekly_report_wx`（dev-mock） |
| `tests/services/test_weekly_report_service.py` | 新建，5 个测试 |
| `docs/上线前清单.md` | 新增 cron 配置说明 |
