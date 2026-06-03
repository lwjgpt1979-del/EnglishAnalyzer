# 词力通打卡激励 设计（P1 / 词力通深化）

**日期：** 2026-06-03
**状态：** 已与用户确认，待转 writing-plans
**参考：** 需求文档 §6.4.5 每日打卡与连续学习激励

## 1. 目标

词力通完成本次会话即记当日打卡；展示连续打卡天数（断签归零）+ 历史最高。提升留存。

**第一刀范围：** 打卡记录 + 连续天数/断签归零/历史最高 + 完成页展示。
**明确不做（后续切片）：** 晚 8 点未完成提醒推送（需定时任务/订阅消息）；亲人可见打卡（家庭监督）；"全部到期复习词"严格校验（MVP 用本次会话计数近似）。

## 2. 数据模型（零迁移）

复用既有 `study_checkins`（每生每天唯一，字段齐全）：

| 字段 | 说明 |
|------|------|
| `student_id` | 学生 |
| `checkin_date` | 打卡日（Date，与 student_id 组合唯一） |
| `new_words_count` | 当日新学词数 |
| `review_done` | 当日复习是否完成 |
| `streak_days` | 截至当日的连续打卡天数 |

## 3. 核心逻辑（新 `checkin_service`）

### `record_checkin(db, *, student_id, new_words_count, review_done) -> StudyCheckin`
- 取今日（UTC date）该生 `study_checkins` 行。
- **已存在**（同日重复打卡）：更新 `new_words_count`/`review_done`（取较大值/或就以传入值更新；MVP 用传入值覆盖），`streak_days` 不变（幂等，不重复累加）。
- **不存在**：查昨天该生行；`streak_days = (昨天行存在 ? 昨天.streak_days + 1 : 1)`；插入新行。
- 返回该行。

### `get_checkin_status(db, *, student_id) -> dict`
- `checked_in_today`：今日是否有行。
- `current_streak`：今日行的 streak_days；若今日无行但昨天有行，则 current_streak = 昨天.streak_days（连续仍保持、今日待打）；若昨天也无，0。
- `longest_streak`：该生历史 `max(streak_days)`（无记录则 0）。
- `today_new_words` / `today_review_done`：今日行的计数（无则 0/false）。

> 断签归零：靠"昨天有无行"决定新一天 streak 从昨天+1 还是从 1 起。

## 4. 接口（`api/v1/vocabulary.py`，复用 DbDep/UserDep + get_rls_db）

- `POST /vocabulary/checkin` body `CheckinIn{new_words_count:int, review_done:bool}` → `BaseResponse[CheckinResult]`（commit）。
- `GET /vocabulary/checkin/status` → `BaseResponse[CheckinStatusOut]`。

schema（`schemas/vocabulary.py`）：
```
class CheckinIn(BaseModel):
    new_words_count: int = 0
    review_done: bool = False

class CheckinResult(BaseModel):
    checkin_date: str        # ISO date
    streak_days: int
    new_words_count: int
    review_done: bool

class CheckinStatusOut(BaseModel):
    checked_in_today: bool
    current_streak: int
    longest_streak: int
    today_new_words: int
    today_review_done: bool
```

## 5. 前端

词力通完成页（`pages/vocabulary/index.vue` phase==='done'）：
- 进入完成阶段时调 `POST /vocabulary/checkin`（new_words_count = 本次新学词数 = `newCards.length`，review_done = 测试做完即 true）。
- 展示「已连续打卡 {{streak}} 天 🔥」（用返回的 streak_days）。
- 可选：完成页/词力通首屏展示历史最高（调 status）。MVP 完成页展示当前连续即可。

## 6. 错误处理
- checkin 幂等：同日多次调用不报错、不重复累加 streak。
- status 无任何记录 → current/longest=0、checked_in_today=false。

## 7. 测试策略
- service：
  - 首次打卡 streak=1；
  - 连续两天（mock 昨天行）→ 今天 streak=2；
  - 断签（昨天无行、前天有行）→ 今天 streak=1；
  - 同日重复 record_checkin 幂等（streak 不变、计数更新）；
  - get_checkin_status：checked_in_today、current_streak、longest_streak 正确。
- API：POST checkin 200 + streak；GET status 结构；未登录 401。
- 前端：`npm run build:mp-weixin` 通过。

> 测试"昨天/前天"行通过直接 insert `study_checkins`（指定 checkin_date）构造，不依赖真实日期推进。

## 8. 影响范围
- 后端：新增 `services/checkin_service.py` + `schemas/vocabulary.py`(3 schema) + `api/v1/vocabulary.py`(2 端点) + 测试。零迁移。
- 前端：`pages/vocabulary/index.vue`（完成阶段调 checkin + 展示连续天数）+ `api/vocabulary.ts` + `types/api.ts`。
- 无花钱。

## 9. 后续切片（不在本设计）
- 晚 8 点未完成提醒（定时任务 + 微信订阅消息）。
- 亲人可见打卡。
- 打卡日历热力图、连续 3 天未打卡提醒。
- 严格"全部到期复习词完成"判定。
