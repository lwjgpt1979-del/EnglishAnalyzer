# 补签 + 打卡热力图 + 连续里程碑徽章 设计（D-107）

**日期：** 2026-06-03
**归属：** 词力通打卡激励 4 项后续之 ③。前序：D-100~D-106。

## 背景与目标

在已有打卡（D-104）+ 严格校验（D-105）+ 亲人日历（D-106）基础上，补齐学生端激励三件套：
1. **补签**：补回漏签日，**恢复连续天数**（对标百词斩补签卡）。
2. **打卡热力图**：学生端在词力通页看到本月打卡热力图。
3. **连续里程碑徽章**：连续天数解锁铜/银/金徽章（纯展示）。

## 关键设计决策（已确认）

- 补签**恢复连续** → streak 从"打卡时存储 `streak_days`"改为**按实际打卡日期集合动态计算**。
- 补签**不限次数**（只限当月内、早于今天、未打卡日）。
- 徽章**由 longest_streak 现算**（零表、零迁移）。
- 热力图 + 徽章放**词力通 index 页** `empty`/`done` 两态顶部。
- **零迁移**（复用 study_checkins）。

## 架构与组件

### 后端 `checkin_service.py`

**1. streak 动态计算（重构核心）**

新增纯函数：
```python
def _compute_streaks(dates: set[date], today: date) -> tuple[int, int]:
    """从打卡日期集合算 (current_streak, longest_streak)。
    current：今日在集合→从今日往回数连续；否则昨日在集合→从昨日往回数；否则 0。
    longest：集合中最长连续日期段长度。
    """
    if not dates:
        return 0, 0
    # current
    if today in dates:
        anchor = today
    elif (today - timedelta(days=1)) in dates:
        anchor = today - timedelta(days=1)
    else:
        anchor = None
    current = 0
    if anchor is not None:
        d = anchor
        while d in dates:
            current += 1
            d -= timedelta(days=1)
    # longest
    longest = 0
    for d in dates:
        if (d - timedelta(days=1)) not in dates:  # 段起点
            run = 0
            x = d
            while x in dates:
                run += 1
                x += timedelta(days=1)
            longest = max(longest, run)
    return current, longest
```

`get_checkin_status` 改为：
```python
async def get_checkin_status(db, *, student_id) -> dict:
    today = _today()
    rows = (await db.execute(
        select(StudyCheckin.checkin_date, StudyCheckin.new_words_count, StudyCheckin.review_done)
        .where(StudyCheckin.student_id == student_id)
    )).all()
    dates = {r[0] for r in rows}
    current, longest = _compute_streaks(dates, today)
    today_row = next((r for r in rows if r[0] == today), None)
    return {
        "checked_in_today": today in dates,
        "current_streak": current,
        "longest_streak": longest,
        "today_new_words": today_row[1] if today_row else 0,
        "today_review_done": today_row[2] if today_row else False,
    }
```

**2. `_upsert_checkin` 写动态 streak_days**

`_upsert_checkin` 在写/更新某日行后，把该行 `streak_days` 置为"以该日结尾的连续段长度"（基于含该日的日期集合）。保持列有意义（非权威；权威为动态计算）。
```python
async def _upsert_checkin(db, *, student_id, checkin_date, new_words_count, review_done) -> StudyCheckin:
    # 取该生全部日期（含将写入日）
    existing = {r[0] for r in (await db.execute(
        select(StudyCheckin.checkin_date).where(StudyCheckin.student_id == student_id)
    )).all()}
    existing.add(checkin_date)
    run = _run_ending_at(existing, checkin_date)
    row = await _row_for(db, student_id, checkin_date)
    if row is not None:
        row.new_words_count = new_words_count
        row.review_done = review_done
        row.streak_days = run
        await db.flush()
        return row
    row = StudyCheckin(id=uuid.uuid4(), student_id=student_id, checkin_date=checkin_date,
                       new_words_count=new_words_count, review_done=review_done, streak_days=run)
    db.add(row)
    await db.flush()
    return row


def _run_ending_at(dates: set[date], d: date) -> int:
    n = 0
    while d in dates:
        n += 1
        d -= timedelta(days=1)
    return n
```
> `record_checkin`（D-105）改为传 `checkin_date=_today()`；返回 `(row, progress)` 不变，`row.streak_days` 即今日动态连续。

**3. 补签 `make_up_checkin`**
```python
async def make_up_checkin(db, *, student_id, d: date) -> dict:
    """补签某漏签日（当月内、早于今天、未打卡）。恢复连续。返回 {date, current_streak, longest_streak}。"""
    today = _today()
    month_start = today.replace(day=1)
    if d >= today:
        raise AppError(code=400, message="只能补签今天之前的日期")
    if d < month_start:
        raise AppError(code=400, message="只能补签本月内的日期")
    existing = await _row_for(db, student_id, d)
    if existing is not None:
        raise AppError(code=400, message="该日已打卡")
    await _upsert_checkin(db, student_id=student_id, checkin_date=d,
                          new_words_count=0, review_done=False)
    status = await get_checkin_status(db, student_id=student_id)
    return {"date": d.isoformat(),
            "current_streak": status["current_streak"],
            "longest_streak": status["longest_streak"]}
```
> import `from app.core.exceptions import AppError`（项目现有路径，relative_service.py 同款）。

**4. 徽章 `_badges`**
```python
_BADGE_DEFS = [("bronze", "坚持铜章", 7), ("silver", "毅力银章", 30), ("gold", "登峰金章", 100)]

def _badges(longest_streak: int) -> list[dict]:
    return [{"level": lv, "name": nm, "threshold": th, "unlocked": longest_streak >= th}
            for lv, nm, th in _BADGE_DEFS]
```

### 后端 schemas（`schemas/vocabulary.py` 追加）
```python
class CheckinBadge(BaseModel):
    level: str
    name: str
    threshold: int
    unlocked: bool


class StudentCalendarOut(BaseModel):
    year: int
    month: int
    days: list[dict]            # {date, new_words_count, streak_days}
    checked_count: int
    current_streak: int
    longest_streak: int
    badges: list[CheckinBadge]


class MakeUpIn(BaseModel):
    date: str                   # YYYY-MM-DD


class MakeUpResult(BaseModel):
    date: str
    current_streak: int
    longest_streak: int
```

### 后端 API（`api/v1/vocabulary.py` 追加）
```python
@router.get("/checkin/calendar", response_model=BaseResponse[StudentCalendarOut])
async def checkin_calendar(db, current_user, year: int | None = None, month: int | None = None):
    await get_rls_db(...)
    now = datetime.now(timezone.utc)
    cal = await checkin_service.get_month_calendar(db, student_id=current_user.id,
            year=year or now.year, month=month or now.month)
    badges = checkin_service._badges(cal["longest_streak"])
    return make_ok(StudentCalendarOut(**cal, badges=[CheckinBadge(**b) for b in badges]))

@router.post("/checkin/make-up", response_model=BaseResponse[MakeUpResult])
async def checkin_make_up(body: MakeUpIn, db, current_user):
    await get_rls_db(...)
    from datetime import date as _date
    d = _date.fromisoformat(body.date)
    res = await checkin_service.make_up_checkin(db, student_id=current_user.id, d=d)
    await db.commit()
    return make_ok(MakeUpResult(**res))
```
> `_badges` 为模块私有但供 endpoint 调用，可接受（同模块内 import 使用）。或在 service 暴露 `get_badges`。实现时用 `checkin_service._badges` 或加公共别名均可。

### 前端

**`types/api.ts`**：`VocabCheckinBadge` / `VocabStudentCalendar` / `VocabMakeUpResult`。

**`api/vocabulary.ts`**：
```typescript
export function getCheckinCalendar(year?: number, month?: number): Promise<VocabStudentCalendar> {...}
export function makeUpCheckin(date: string): Promise<VocabMakeUpResult> {...}
```

**`pages/vocabulary/index.vue`**：`empty` 与 `done` 两态顶部插入「本月打卡」面板：
- 摘要：连续 {{ streak }} 天 · 最高 {{ longest }} 天
- 徽章条：铜/银/金，`unlocked` 亮、否则灰
- 热力图网格（复用 D-106 的 cells 计算思路）：已打卡 🔥；**过去未打卡日**可点 → `makeUpCheckin(date)` → 刷新面板
- onMounted（或进入 empty/done 时）拉 `getCheckinCalendar()`

## 数据流

完成/今日已学完 → 词力通页 empty/done 态拉 calendar → 渲染热力图+徽章+连续。点漏签日 → make-up → 后端校验+写 study_checkins+动态重算 streak → 返回新连续 → 前端刷新。

## 错误处理

- 补签非法（已打卡/未来/跨月）→ `AppError(400)`，前端 toast。
- calendar 拉取失败不阻塞页面。

## 测试（TDD）

**service（`tests/services/test_checkin_service.py`）**
1. `_compute_streaks`：连续 3 天→(3,3)；今日未打+昨日起连续 2→current=2；断签→重置；空→(0,0)；补签填补后 longest 增长。
2. `make_up_checkin`：补签昨日（今日已打、前日已打）→ current 恢复为连续；已打卡日补签→400；未来日→400；跨月→400。
3. `_badges`：longest=0→全未解锁；longest=7→铜解锁；longest=100→全解锁。
4. **改写**受 streak 动态化影响的 D-104/105 测试：`test_consecutive_day_streak_increments`、`test_status` 改为播种真实连续日期行（不再用单行假 streak_days）。

**API（`tests/api/test_vocabulary.py`）**
5. `GET /checkin/calendar` 返回 days + badges（鉴权）。
6. `POST /checkin/make-up` 成功补签并恢复连续。
7. `POST /checkin/make-up` 未来日 → 400。

## 影响范围

- `backend/app/services/checkin_service.py`（_compute_streaks/_run_ending_at/_upsert_checkin 改/get_checkin_status 改/make_up_checkin/_badges）
- `backend/app/schemas/vocabulary.py`（CheckinBadge/StudentCalendarOut/MakeUpIn/MakeUpResult）
- `backend/app/api/v1/vocabulary.py`（calendar/make-up 两 endpoint）
- `tests/services/test_checkin_service.py`（新增 + 改写若干 streak 例）、`tests/api/test_vocabulary.py`（+3）
- 前端 `types/api.ts`、`api/vocabulary.ts`、`pages/vocabulary/index.vue`
- **零迁移、无花钱。**

## 不做（后续）

- 补签消耗积分/补签卡
- 徽章解锁推送/动画/分享
- 跨月浏览热力图
- 打卡提醒双通道（D-108）

## 相关

D-104/105/106（打卡系列）；需求 §6.4。
