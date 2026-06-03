# 补签 + 打卡热力图 + 里程碑徽章 Implementation Plan（D-107）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 学生端补签（恢复连续）+ 本月打卡热力图 + 连续里程碑徽章（纯展示）。

**Architecture:** streak 从"存储值"重构为"按打卡日期集合动态计算"以支撑补签恢复连续；补签/热力图/徽章全部基于 study_checkins，零迁移；徽章由 longest_streak 现算。

**Tech Stack:** FastAPI + SQLAlchemy 2.x asyncio + Pydantic v2 + PostgreSQL；uni-app Vue3。零迁移、无花钱。

**运行约定：** 后端 python = `/opt/anaconda3/bin/python`，pytest 从 `backend/` 跑、路径 `../tests/...`、加 `-p no:randomly`。前端从 `frontend/miniprogram/` 跑 `npm run build:mp-weixin`。

---

## File Structure

| 文件 | 改动 |
|---|---|
| `backend/app/services/checkin_service.py` | +`_compute_streaks`/`_run_ending_at`/`_badges`/`make_up_checkin`；改 `_upsert_checkin`（加 checkin_date + 动态 streak_days）/`get_checkin_status`（动态）/`record_checkin`（传 checkin_date） |
| `backend/app/schemas/vocabulary.py` | +`CheckinBadge`/`StudentCalendarOut`/`MakeUpIn`/`MakeUpResult` |
| `backend/app/api/v1/vocabulary.py` | +`/checkin/calendar`、`/checkin/make-up` |
| `tests/services/test_checkin_service.py` | +新增例；改写 `test_consecutive_day_streak_increments`/`test_status` |
| `tests/api/test_vocabulary.py` | +3 例 |
| `frontend/miniprogram/src/types/api.ts` | +徽章/日历/补签类型 |
| `frontend/miniprogram/src/api/vocabulary.ts` | +`getCheckinCalendar`/`makeUpCheckin` |
| `frontend/miniprogram/src/pages/vocabulary/index.vue` | empty/done 顶部「本月打卡」面板 |

---

## Task 1: streak 动态化 + 徽章

**Files:**
- Modify: `backend/app/services/checkin_service.py`
- Test: `tests/services/test_checkin_service.py`

- [ ] **Step 1: 写失败测试 + 改写受影响的两例**

(a) 在 `tests/services/test_checkin_service.py` 末尾追加：
```python
# ─── D-107: 动态 streak + 徽章 ────────────────────────────────────────

def test_compute_streaks_pure():
    from datetime import date as _d
    from app.services.checkin_service import _compute_streaks
    today = _d(2026, 6, 10)
    # 连续 3 天到今天
    assert _compute_streaks({_d(2026,6,8), _d(2026,6,9), _d(2026,6,10)}, today) == (3, 3)
    # 今日未打，昨日起连续 2 天
    assert _compute_streaks({_d(2026,6,8), _d(2026,6,9)}, today) == (2, 2)
    # 断签（仅前天）→ current 0，longest 1
    assert _compute_streaks({_d(2026,6,8)}, today) == (0, 1)
    # 空集
    assert _compute_streaks(set(), today) == (0, 0)
    # 补签填补：6/7,6/8 间补 → longest 增长
    assert _compute_streaks({_d(2026,6,7), _d(2026,6,8), _d(2026,6,9), _d(2026,6,10)}, today) == (4, 4)


def test_badges_thresholds():
    from app.services.checkin_service import _badges
    b0 = _badges(0)
    assert all(x["unlocked"] is False for x in b0)
    b7 = _badges(7)
    assert b7[0]["unlocked"] is True and b7[1]["unlocked"] is False
    b100 = _badges(100)
    assert all(x["unlocked"] is True for x in b100)
    assert [x["level"] for x in b0] == ["bronze", "silver", "gold"]
```

(b) 改写既有 `test_consecutive_day_streak_increments` 为播种真实连续 3 天：
```python
@pytest.mark.asyncio
async def test_consecutive_day_streak_increments(db_session):
    sid = await _student(db_session)
    for n in (3, 2, 1):  # today-3, today-2, today-1
        db_session.add(StudyCheckin(
            id=uuid.uuid4(), student_id=sid, checkin_date=_today() - timedelta(days=n),
            new_words_count=1, review_done=True, streak_days=0))
    await db_session.flush()
    row = await checkin_service._upsert_checkin(db_session, student_id=sid, new_words_count=2, review_done=True)
    assert row.streak_days == 4
```

(c) 改写既有 `test_status` 为播种真实连续 7 天（截至昨日）：
```python
@pytest.mark.asyncio
async def test_status(db_session):
    sid = await _student(db_session)
    for n in range(7, 0, -1):  # today-7 .. today-1
        db_session.add(StudyCheckin(
            id=uuid.uuid4(), student_id=sid, checkin_date=_today() - timedelta(days=n),
            new_words_count=1, review_done=True, streak_days=0))
    await db_session.flush()
    st = await checkin_service.get_checkin_status(db_session, student_id=sid)
    assert st["checked_in_today"] is False
    assert st["current_streak"] == 7
    assert st["longest_streak"] == 7
    await checkin_service._upsert_checkin(db_session, student_id=sid, new_words_count=2, review_done=True)
    st2 = await checkin_service.get_checkin_status(db_session, student_id=sid)
    assert st2["checked_in_today"] is True and st2["current_streak"] == 8 and st2["longest_streak"] == 8
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_checkin_service.py -p no:randomly -q`
Expected: FAIL（`_compute_streaks`/`_badges` 不存在；改写的两例因旧逻辑断言不符而 FAIL）

- [ ] **Step 3: 重构 checkin_service.py**

(a) 在 `_row_for` 之后新增纯函数：
```python
def _run_ending_at(dates: set[date], d: date) -> int:
    n = 0
    while d in dates:
        n += 1
        d -= timedelta(days=1)
    return n


def _compute_streaks(dates: set[date], today: date) -> tuple[int, int]:
    if not dates:
        return 0, 0
    if today in dates:
        anchor = today
    elif (today - timedelta(days=1)) in dates:
        anchor = today - timedelta(days=1)
    else:
        anchor = None
    current = _run_ending_at(dates, anchor) if anchor is not None else 0
    longest = 0
    for d in dates:
        if (d - timedelta(days=1)) not in dates:  # 连续段起点
            run = 0
            x = d
            while x in dates:
                run += 1
                x += timedelta(days=1)
            longest = max(longest, run)
    return current, longest


_BADGE_DEFS = [("bronze", "坚持铜章", 7), ("silver", "毅力银章", 30), ("gold", "登峰金章", 100)]


def _badges(longest_streak: int) -> list[dict]:
    return [{"level": lv, "name": nm, "threshold": th, "unlocked": longest_streak >= th}
            for lv, nm, th in _BADGE_DEFS]


async def _all_dates(db: AsyncSession, student_id: uuid.UUID) -> set[date]:
    rows = (await db.execute(
        select(StudyCheckin.checkin_date).where(StudyCheckin.student_id == student_id)
    )).all()
    return {r[0] for r in rows}
```

(b) 把 `_upsert_checkin` 整体替换为（加 `checkin_date` 参数、动态 streak_days）：
```python
async def _upsert_checkin(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    new_words_count: int,
    review_done: bool,
    checkin_date: date | None = None,
) -> StudyCheckin:
    """写入/更新某日打卡行；streak_days = 以该日结尾的连续段长度（动态）。"""
    d = checkin_date or _today()
    dates = await _all_dates(db, student_id)
    dates.add(d)
    run = _run_ending_at(dates, d)
    row = await _row_for(db, student_id, d)
    if row is not None:
        row.new_words_count = new_words_count
        row.review_done = review_done
        row.streak_days = run
        await db.flush()
        return row
    row = StudyCheckin(
        id=uuid.uuid4(), student_id=student_id, checkin_date=d,
        new_words_count=new_words_count, review_done=review_done, streak_days=run,
    )
    db.add(row)
    await db.flush()
    return row
```

(c) 把 `get_checkin_status` 整体替换为动态版：
```python
async def get_checkin_status(db: AsyncSession, *, student_id: uuid.UUID) -> dict:
    """返回打卡状态：今日是否已打、当前连续、历史最高、今日计数（按日期集合动态算）。"""
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

> `func` 若不再被使用，保留 import 无妨（不强制删）。`record_checkin` 无需改（其 `_upsert_checkin(...)` 调用不传 checkin_date，默认今日）。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_checkin_service.py -p no:randomly -q`
Expected: PASS（含新增 2 例 + 改写 2 例 + 既有例）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/checkin_service.py tests/services/test_checkin_service.py
git commit -m "feat(backend): 词力通 streak 动态化 + 里程碑徽章现算"
```

---

## Task 2: 补签 service

**Files:**
- Modify: `backend/app/services/checkin_service.py`
- Test: `tests/services/test_checkin_service.py`

- [ ] **Step 1: 写失败测试**

末尾追加：
```python
# ─── D-107: 补签 ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_make_up_restores_streak(db_session):
    """今日已打 + 前日已打、昨日漏 → 补昨日后连续应为 3。"""
    sid = await _student(db_session)
    for n in (2, 0):  # 前天、今天
        db_session.add(StudyCheckin(
            id=uuid.uuid4(), student_id=sid, checkin_date=_today() - timedelta(days=n),
            new_words_count=1, review_done=True, streak_days=0))
    await db_session.flush()
    res = await checkin_service.make_up_checkin(
        db_session, student_id=sid, d=_today() - timedelta(days=1))
    assert res["current_streak"] == 3
    assert res["date"] == (_today() - timedelta(days=1)).isoformat()


@pytest.mark.asyncio
async def test_make_up_already_checked_rejected(db_session):
    from app.core.exceptions import AppError
    sid = await _student(db_session)
    db_session.add(StudyCheckin(
        id=uuid.uuid4(), student_id=sid, checkin_date=_today() - timedelta(days=1),
        new_words_count=1, review_done=True, streak_days=1))
    await db_session.flush()
    with pytest.raises(AppError):
        await checkin_service.make_up_checkin(db_session, student_id=sid, d=_today() - timedelta(days=1))


@pytest.mark.asyncio
async def test_make_up_future_rejected(db_session):
    from app.core.exceptions import AppError
    sid = await _student(db_session)
    with pytest.raises(AppError):
        await checkin_service.make_up_checkin(db_session, student_id=sid, d=_today() + timedelta(days=1))
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_checkin_service.py -k make_up -p no:randomly -q`
Expected: FAIL（`make_up_checkin` 不存在）

- [ ] **Step 3: 实现 `make_up_checkin`**

顶部 import 区加：
```python
from app.core.exceptions import AppError
```
在 `make_up` 之处（`get_month_calendar` 之后）追加：
```python
async def make_up_checkin(db: AsyncSession, *, student_id: uuid.UUID, d: date) -> dict:
    """补签某漏签日（当月内、早于今天、未打卡）。恢复连续。返回 {date, current_streak, longest_streak}。"""
    today = _today()
    if d >= today:
        raise AppError(code=400, message="只能补签今天之前的日期")
    if d < today.replace(day=1):
        raise AppError(code=400, message="只能补签本月内的日期")
    if await _row_for(db, student_id, d) is not None:
        raise AppError(code=400, message="该日已打卡")
    await _upsert_checkin(db, student_id=student_id, new_words_count=0,
                          review_done=False, checkin_date=d)
    status = await get_checkin_status(db, student_id=student_id)
    return {
        "date": d.isoformat(),
        "current_streak": status["current_streak"],
        "longest_streak": status["longest_streak"],
    }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_checkin_service.py -p no:randomly -q`
Expected: PASS（全部，含补签 3 例）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/checkin_service.py tests/services/test_checkin_service.py
git commit -m "feat(backend): 词力通补签 make_up_checkin（恢复连续）"
```

---

## Task 3: schemas + 学生端 API

**Files:**
- Modify: `backend/app/schemas/vocabulary.py`
- Modify: `backend/app/api/v1/vocabulary.py`
- Test: `tests/api/test_vocabulary.py`

- [ ] **Step 1: 写失败测试**

在 `tests/api/test_vocabulary.py` 末尾追加（复用 `_login`/`_seed_word`/`_async_session_factory`，新增 import）：
```python
# ─── D-107: 学生端日历 + 补签 ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_checkin_calendar_with_badges(client):
    from datetime import datetime, timezone
    from app.models.d5_learning import StudyCheckin
    headers = await _login(client, uuid.uuid4().hex[:6])
    me = (await client.get("/api/v1/users/me", headers=headers)).json()["data"]
    now = datetime.now(timezone.utc)
    async with _async_session_factory() as s:
        s.add(StudyCheckin(
            id=uuid.uuid4(), student_id=uuid.UUID(me["id"]), checkin_date=now.date(),
            new_words_count=5, review_done=True, streak_days=1))
        await s.commit()
    r = await client.get("/api/v1/vocabulary/checkin/calendar",
                         params={"year": now.year, "month": now.month}, headers=headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["checked_count"] == 1
    assert len(data["badges"]) == 3
    assert data["badges"][0]["level"] == "bronze"


@pytest.mark.asyncio
async def test_make_up_via_api(client):
    from datetime import datetime, timedelta, timezone
    from app.models.d5_learning import StudyCheckin
    headers = await _login(client, uuid.uuid4().hex[:6])
    me = (await client.get("/api/v1/users/me", headers=headers)).json()["data"]
    now = datetime.now(timezone.utc)
    # 仅当今天不是 1 号时可补签昨天（避免月初边界）
    if now.day < 2:
        return
    yest = (now - timedelta(days=1)).date()
    r = await client.post("/api/v1/vocabulary/checkin/make-up",
                          json={"date": yest.isoformat()}, headers=headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["date"] == yest.isoformat()
    assert data["current_streak"] >= 1


@pytest.mark.asyncio
async def test_make_up_future_via_api(client):
    from datetime import datetime, timedelta, timezone
    headers = await _login(client, uuid.uuid4().hex[:6])
    now = datetime.now(timezone.utc)
    fut = (now + timedelta(days=1)).date()
    r = await client.post("/api/v1/vocabulary/checkin/make-up",
                          json={"date": fut.isoformat()}, headers=headers)
    assert r.status_code == 400
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/api/test_vocabulary.py -k "calendar or make_up" -p no:randomly -q`
Expected: FAIL（404 路由不存在）

- [ ] **Step 3: 加 schemas**

在 `backend/app/schemas/vocabulary.py` 末尾追加：
```python
class CheckinBadge(BaseModel):
    level: str
    name: str
    threshold: int
    unlocked: bool


class StudentCalendarOut(BaseModel):
    year: int
    month: int
    days: list[dict]
    checked_count: int
    current_streak: int
    longest_streak: int
    badges: list[CheckinBadge]


class MakeUpIn(BaseModel):
    date: str


class MakeUpResult(BaseModel):
    date: str
    current_streak: int
    longest_streak: int
```

- [ ] **Step 4: 加 API endpoints**

在 `backend/app/api/v1/vocabulary.py` import 区把 schemas 补上：
```python
from app.schemas.vocabulary import (
    CheckinBadge,
    CheckinResult,
    CheckinStatusOut,
    DailyTaskOut,
    MakeUpIn,
    MakeUpResult,
    StudentCalendarOut,
    VocabAnswerIn,
    VocabAnswerResult,
    WrongWordItem,
    WrongWordListOut,
)
```
在 `checkin_status` endpoint 之后追加：
```python
@router.get("/checkin/calendar", response_model=BaseResponse[StudentCalendarOut])
async def checkin_calendar(
    db: DbDep, current_user: UserDep, year: int | None = None, month: int | None = None,
):
    """学生本月打卡热力图 + 里程碑徽章。"""
    from datetime import datetime, timezone
    await get_rls_db(db, str(current_user.id))
    now = datetime.now(timezone.utc)
    cal = await checkin_service.get_month_calendar(
        db, student_id=current_user.id, year=year or now.year, month=month or now.month,
    )
    badges = checkin_service._badges(cal["longest_streak"])
    return make_ok(StudentCalendarOut(
        **cal, badges=[CheckinBadge(**b) for b in badges],
    ))


@router.post("/checkin/make-up", response_model=BaseResponse[MakeUpResult])
async def checkin_make_up(body: MakeUpIn, db: DbDep, current_user: UserDep):
    """补签某漏签日（恢复连续）。"""
    from datetime import date as _date
    await get_rls_db(db, str(current_user.id))
    d = _date.fromisoformat(body.date)
    res = await checkin_service.make_up_checkin(db, student_id=current_user.id, d=d)
    await db.commit()
    return make_ok(MakeUpResult(**res))
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/api/test_vocabulary.py -p no:randomly -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/schemas/vocabulary.py backend/app/api/v1/vocabulary.py tests/api/test_vocabulary.py
git commit -m "feat(backend): 词力通学生端打卡日历(含徽章)+补签 API"
```

---

## Task 4: 前端词力通页打卡面板

**Files:**
- Modify: `frontend/miniprogram/src/types/api.ts`
- Modify: `frontend/miniprogram/src/api/vocabulary.ts`
- Modify: `frontend/miniprogram/src/pages/vocabulary/index.vue`

- [ ] **Step 1: 加类型**

`types/api.ts` 末尾追加：
```typescript
// 打卡热力图 + 徽章 + 补签（D-107）
export interface VocabCheckinBadge {
  level: string
  name: string
  threshold: number
  unlocked: boolean
}
export interface VocabStudentCalendar {
  year: number
  month: number
  days: { date: string; new_words_count: number; streak_days: number }[]
  checked_count: number
  current_streak: number
  longest_streak: number
  badges: VocabCheckinBadge[]
}
export interface VocabMakeUpResult {
  date: string
  current_streak: number
  longest_streak: number
}
```

- [ ] **Step 2: 加前端 API**

`api/vocabulary.ts`：import 类型补 `VocabStudentCalendar, VocabMakeUpResult`，文件末尾追加：
```typescript
export function getCheckinCalendar(year?: number, month?: number): Promise<VocabStudentCalendar> {
  const data: Record<string, number> = {}
  if (year) data.year = year
  if (month) data.month = month
  return request<VocabStudentCalendar>('/api/v1/vocabulary/checkin/calendar', { method: 'GET', data })
}

export function makeUpCheckin(date: string): Promise<VocabMakeUpResult> {
  return request<VocabMakeUpResult>('/api/v1/vocabulary/checkin/make-up', {
    method: 'POST', data: { date },
  })
}
```

- [ ] **Step 3: index.vue 打卡面板**

编辑 `frontend/miniprogram/src/pages/vocabulary/index.vue`：

(a) `<script setup>` import 增加：
```typescript
import { getDailyTask, submitVocabAnswer, checkin, getCheckinCalendar, makeUpCheckin } from '@/api/vocabulary'
import type { VocabStudentCalendar } from '@/types/api'
```

(b) 加 ref 与计算（在 `streakDays` 等 ref 附近）：
```typescript
const cal = ref<VocabStudentCalendar | null>(null)
const calCells = computed(() => {
  if (!cal.value) return [] as { day: number; date: string; checked: boolean; missable: boolean }[]
  const { year, month } = cal.value
  const checkedSet = new Set(cal.value.days.map(d => d.date))
  const first = new Date(year, month - 1, 1).getDay()
  const daysIn = new Date(year, month, 0).getDate()
  const todayStr = new Date().toISOString().slice(0, 10)
  const arr: { day: number; date: string; checked: boolean; missable: boolean }[] = []
  for (let i = 0; i < first; i++) arr.push({ day: 0, date: '', checked: false, missable: false })
  for (let d = 1; d <= daysIn; d++) {
    const date = `${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`
    const checked = checkedSet.has(date)
    arr.push({ day: d, date, checked, missable: !checked && date < todayStr })
  }
  return arr
})
async function loadCalendar() {
  try { cal.value = await getCheckinCalendar() } catch { /* 不阻塞 */ }
}
async function onMakeUp(date: string) {
  try {
    await makeUpCheckin(date)
    await loadCalendar()
    uni.showToast({ title: '补签成功', icon: 'success' })
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'none' })
  }
}
```

(c) `finishSession` 末尾、以及 `load()` 中 `phase.value='empty'` 分支后，调用 `loadCalendar()`：
- 在 `finishSession` 的 `try` 块末尾追加 `await loadCalendar()`。
- 在 `load()` 里设置 `phase.value = 'empty'` 之后追加 `loadCalendar()`。

(d) 模板：在 `phase === 'empty'` 与 `phase === 'done'` 两个 `<view>` 内顶部插入打卡面板（抽同一段，分别粘贴）：
```html
      <view v-if="cal" class="checkin-panel">
        <view class="cp-summary">连续 {{ cal.current_streak }} 天 · 最高 {{ cal.longest_streak }} 天</view>
        <view class="cp-badges">
          <text v-for="b in cal.badges" :key="b.level" class="cp-badge" :class="{ on: b.unlocked }">
            {{ b.level === 'bronze' ? '🥉' : b.level === 'silver' ? '🥈' : '🥇' }}{{ b.name }}
          </text>
        </view>
        <view class="cp-grid">
          <view v-for="(c, i) in calCells" :key="i" class="cp-cell"
                :class="{ checked: c.checked, missable: c.missable, blank: !c.day }"
                @tap="c.missable ? onMakeUp(c.date) : null">
            <text v-if="c.day">{{ c.checked ? '🔥' : c.day }}</text>
          </view>
        </view>
        <view class="cp-hint">点亮灰色日期可补签</view>
      </view>
```

(e) 样式区追加：
```css
.checkin-panel { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 20rpx; }
.cp-summary { font-size: 28rpx; font-weight: 700; color: var(--c-ink); }
.cp-badges { display: flex; gap: 12rpx; margin: 12rpx 0; flex-wrap: wrap; }
.cp-badge { font-size: 22rpx; color: var(--c-text-hint); opacity: .45; }
.cp-badge.on { color: var(--c-gold); opacity: 1; font-weight: 700; }
.cp-grid { display: flex; flex-wrap: wrap; }
.cp-cell { width: 14.28%; height: 60rpx; display: flex; align-items: center; justify-content: center; font-size: 22rpx; color: var(--c-text-body); }
.cp-cell.checked { color: var(--c-gold); font-weight: 700; }
.cp-cell.missable { color: var(--c-text-hint); border: 1rpx dashed var(--c-border); border-radius: 8rpx; }
.cp-cell.blank { visibility: hidden; }
.cp-hint { font-size: 22rpx; color: var(--c-text-hint); margin-top: 8rpx; }
```

> 若 `empty` 分支当前是 `<view ... class="center-tip">` 纯文本，需把它改为可容纳面板的容器：在该 `center-tip` 文本之上套一层并插入面板，或在文本前加面板。实现时保持 `phase==='empty'` 文案不丢。

- [ ] **Step 4: 构建验证**

Run: `cd frontend/miniprogram && npm run build:mp-weixin`
Expected: `Build complete.`

- [ ] **Step 5: 提交**

```bash
git add frontend/miniprogram/src/types/api.ts frontend/miniprogram/src/api/vocabulary.ts frontend/miniprogram/src/pages/vocabulary/index.vue
git commit -m "feat(frontend): 词力通页打卡热力图+徽章+补签面板"
```

---

## Task 5: 全量回归 + 归档 D-107

**Files:**
- Modify: `docs/决策归档.md`

- [ ] **Step 1: 后端全量回归**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests -p no:randomly -q`
Expected: PASS（约 400 passed；净增 service+API 约 8 例，改写 2 例）

- [ ] **Step 2: 前端构建确认**

Run: `cd frontend/miniprogram && npm run build:mp-weixin`
Expected: `Build complete.`

- [ ] **Step 3: 归档 D-107**

在 `docs/决策归档.md` 顶部（`## D-106` 之前）插入 D-107 条目：日期、背景、结论（streak 动态化 / 补签恢复连续不限次 / 徽章 longest_streak 现算 / 学生端 calendar+make-up API / 前端面板）、测试（后端全量 passed + 前端 build）、影响范围、未做（补签消耗/徽章推送/跨月/ D-108）、相关（D-104/105/106，§6.4）。

- [ ] **Step 4: 提交**

```bash
git add docs/决策归档.md
git commit -m "docs: 归档 D-107 补签+热力图+里程碑徽章"
```

- [ ] **Step 5: 询问用户是否 push**

报告 commit 列表 + 测试/构建结果，征求明确同意后 `git push`。

---

## Self-Review

**1. Spec 覆盖：**
- streak 动态化（_compute_streaks/_run_ending_at/get_checkin_status/_upsert_checkin）→ Task 1 ✓
- 徽章 longest_streak 现算 → Task 1 ✓
- 补签恢复连续、不限次、当月/早于今天/未打卡校验 → Task 2 ✓
- 学生端 calendar(含 badges)+make-up API → Task 3 ✓
- 前端 empty/done 面板 + 补签交互 → Task 4 ✓
- 零迁移、无花钱 → 全程无 alembic/付费 ✓
- 受影响 D-104/105 streak 测试改写 → Task 1 Step 1(b)(c) ✓

**2. 占位符扫描：** 无 TBD/TODO；每步含完整代码与命令。前端 empty 容器调整给了明确指引（保留文案）。

**3. 类型一致：** `get_checkin_status` 返回键不变（callers 无破坏）；`_upsert_checkin` 新增 `checkin_date` 默认 None→today（既有调用兼容）；`make_up_checkin` 返回键 `date/current_streak/longest_streak` 与 `MakeUpResult` 一致；`StudentCalendarOut(**cal, badges=...)` —— `get_month_calendar` 返回键 `year/month/days/checked_count/current_streak/longest_streak` 恰好匹配 schema 其余字段；前端 `VocabStudentCalendar`/`VocabMakeUpResult` 与后端对齐；`calCells` 与模板引用一致。
