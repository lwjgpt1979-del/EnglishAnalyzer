# 亲人可见打卡日历 Implementation Plan（D-106）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 已绑定亲人在"查看孩子"页看到孩子当月打卡日历（哪些天打卡 + 连续/最高天数）。

**Architecture:** 新增可复用 `checkin_service.get_month_calendar`；亲人端 API 沿用 `assert_bound` 校验亲子绑定后查 study_checkins；前端在 student-view 页加月度网格卡片。

**Tech Stack:** FastAPI + SQLAlchemy 2.x asyncio + Pydantic v2 + PostgreSQL；uni-app Vue3。零迁移、无花钱。

**运行约定：** 后端 python = `/opt/anaconda3/bin/python`，pytest 从 `backend/` 跑、路径 `../tests/...`、加 `-p no:randomly`。前端从 `frontend/miniprogram/` 跑 `npm run build:mp-weixin`。

---

## File Structure

| 文件 | 职责 | 改动 |
|---|---|---|
| `backend/app/services/checkin_service.py` | 打卡逻辑 | +`get_month_calendar`（可复用） |
| `backend/app/schemas/relative.py` | 亲人端 schemas | +`CheckinDayItem`/`CheckinCalendarOut` |
| `backend/app/api/v1/relative.py` | 亲人端 API | +checkin-calendar endpoint |
| `tests/services/test_checkin_service.py` | 打卡测试 | +3 日历例 |
| `tests/api/test_relative.py` | 亲人端测试 | +2 例（403/200） |
| `frontend/miniprogram/src/api/relative.ts` | 前端 API | +getStudentCheckinCalendar |
| `frontend/miniprogram/src/types/api.ts` | 前端类型 | +RelativeCheckinDay/Calendar |
| `frontend/miniprogram/src/pages/relative/student-view.vue` | 查看孩子页 | +打卡日历卡片 |

---

## Task 1: `get_month_calendar`（后端日历查询）

**Files:**
- Modify: `backend/app/services/checkin_service.py`
- Test: `tests/services/test_checkin_service.py`

- [ ] **Step 1: 写失败测试**

在 `tests/services/test_checkin_service.py` 末尾追加（文件已有 `_student`/`_today`/`db_session` 与 `from datetime import datetime, timedelta, timezone`、`from app.models.d5_learning import StudyCheckin`）：

```python
# ─── D-106: 当月打卡日历 ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_calendar_two_days_this_month(db_session):
    """当月 2 天打卡 → days 长度 2、checked_count 2、按日期升序。"""
    sid = await _student(db_session)
    t = _today()
    d1 = t.replace(day=1)
    d2 = t.replace(day=2)
    db_session.add_all([
        StudyCheckin(id=uuid.uuid4(), student_id=sid, checkin_date=d1,
                     new_words_count=5, review_done=True, streak_days=1),
        StudyCheckin(id=uuid.uuid4(), student_id=sid, checkin_date=d2,
                     new_words_count=3, review_done=True, streak_days=2),
    ])
    await db_session.flush()
    cal = await checkin_service.get_month_calendar(
        db_session, student_id=sid, year=t.year, month=t.month)
    assert cal["year"] == t.year and cal["month"] == t.month
    assert cal["checked_count"] == 2
    assert [d["date"] for d in cal["days"]] == [d1.isoformat(), d2.isoformat()]
    assert cal["days"][0]["new_words_count"] == 5


@pytest.mark.asyncio
async def test_calendar_excludes_other_months(db_session):
    """上月/下月行不计入当月。"""
    from datetime import date
    sid = await _student(db_session)
    # 固定到一个安全月份（6月），避免月初/月末边界
    db_session.add_all([
        StudyCheckin(id=uuid.uuid4(), student_id=sid, checkin_date=date(2026, 6, 15),
                     new_words_count=5, review_done=True, streak_days=1),
        StudyCheckin(id=uuid.uuid4(), student_id=sid, checkin_date=date(2026, 5, 31),
                     new_words_count=5, review_done=True, streak_days=1),
        StudyCheckin(id=uuid.uuid4(), student_id=sid, checkin_date=date(2026, 7, 1),
                     new_words_count=5, review_done=True, streak_days=1),
    ])
    await db_session.flush()
    cal = await checkin_service.get_month_calendar(
        db_session, student_id=sid, year=2026, month=6)
    assert cal["checked_count"] == 1
    assert cal["days"][0]["date"] == "2026-06-15"


@pytest.mark.asyncio
async def test_calendar_empty_month(db_session):
    """空月 → days 空、checked_count 0。"""
    sid = await _student(db_session)
    cal = await checkin_service.get_month_calendar(
        db_session, student_id=sid, year=2099, month=1)
    assert cal["days"] == [] and cal["checked_count"] == 0
    assert cal["current_streak"] == 0 and cal["longest_streak"] == 0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_checkin_service.py -p no:randomly -q`
Expected: FAIL（`module ... has no attribute 'get_month_calendar'`）

- [ ] **Step 3: 实现 `get_month_calendar`**

在 `backend/app/services/checkin_service.py` 顶部 import 区把 `from datetime import date, datetime, timedelta, timezone` 确认含 `date`（现状已是）。在 `get_checkin_status` 之后追加：

```python
async def get_month_calendar(
    db: AsyncSession, *, student_id: uuid.UUID, year: int, month: int,
) -> dict:
    """当月打卡日历：已打卡日列表 + 连续/最高天数（复用 status 摘要）。"""
    month_start = date(year, month, 1)
    next_month_start = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    rows = (await db.execute(
        select(StudyCheckin).where(
            StudyCheckin.student_id == student_id,
            StudyCheckin.checkin_date >= month_start,
            StudyCheckin.checkin_date < next_month_start,
        ).order_by(StudyCheckin.checkin_date)
    )).scalars().all()
    days = [
        {
            "date": r.checkin_date.isoformat(),
            "new_words_count": r.new_words_count,
            "streak_days": r.streak_days,
        }
        for r in rows
    ]
    status = await get_checkin_status(db, student_id=student_id)
    return {
        "year": year,
        "month": month,
        "days": days,
        "checked_count": len(days),
        "current_streak": status["current_streak"],
        "longest_streak": status["longest_streak"],
    }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_checkin_service.py -p no:randomly -q`
Expected: PASS（新增 3 例）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/checkin_service.py tests/services/test_checkin_service.py
git commit -m "feat(backend): 词力通当月打卡日历 get_month_calendar"
```

---

## Task 2: schemas + 亲人端 API

**Files:**
- Modify: `backend/app/schemas/relative.py`
- Modify: `backend/app/api/v1/relative.py`
- Test: `tests/api/test_relative.py`

- [ ] **Step 1: 写失败测试（403 未绑定 / 200 已绑定）**

在 `tests/api/test_relative.py` 末尾追加（复用 `_setup_user` / `client`，新增 import StudyCheckin）：

```python
# ─── D-106: 亲人可见打卡日历 ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_checkin_calendar_requires_bound(client):
    """未绑定亲子 → 403。"""
    s_h, sid = await _setup_user(client, f"cs_{uuid.uuid4().hex[:6]}", 2010)
    p_h, _ = await _setup_user(client, f"cp_{uuid.uuid4().hex[:6]}", 1985)
    r = await client.get(f"/api/v1/relative/students/{sid}/checkin-calendar", headers=p_h)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_checkin_calendar_bound_ok(client):
    """已绑定 → 200，days 含已打卡日。"""
    from datetime import datetime, timezone
    from app.models.d5_learning import StudyCheckin
    s_h, sid = await _setup_user(client, f"cbs_{uuid.uuid4().hex[:6]}", 2010)
    p_h, _ = await _setup_user(client, f"cbp_{uuid.uuid4().hex[:6]}", 1985)
    iv = await client.post("/api/v1/relative/invite-code", headers=s_h)
    code = iv.json()["data"]["code"]
    await client.post("/api/v1/relative/bind",
                      json={"code": code, "relationship": "母亲"}, headers=p_h)
    # 给学生插一条今日打卡
    now = datetime.now(timezone.utc)
    async with _async_session_factory() as s:
        s.add(StudyCheckin(
            id=uuid.uuid4(), student_id=uuid.UUID(sid), checkin_date=now.date(),
            new_words_count=5, review_done=True, streak_days=1))
        await s.commit()
    r = await client.get(
        f"/api/v1/relative/students/{sid}/checkin-calendar",
        params={"year": now.year, "month": now.month}, headers=p_h)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["checked_count"] == 1
    assert data["days"][0]["date"] == now.date().isoformat()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/api/test_relative.py -p no:randomly -q`
Expected: FAIL（404 路由不存在 / 校验失败）

- [ ] **Step 3: 加 schemas**

在 `backend/app/schemas/relative.py` 末尾追加：

```python
class CheckinDayItem(BaseModel):
    date: str
    new_words_count: int
    streak_days: int


class CheckinCalendarOut(BaseModel):
    year: int
    month: int
    days: list[CheckinDayItem]
    checked_count: int
    current_streak: int
    longest_streak: int
```

- [ ] **Step 4: 加 API endpoint**

在 `backend/app/api/v1/relative.py` 的 `relative_view_student_wqs` 之后追加（import 用局部，与既有风格一致）：

```python
@router.get(
    "/students/{student_id}/checkin-calendar",
    response_model=BaseResponse["CheckinCalendarOut"],
)
async def relative_view_student_checkin_calendar(
    student_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
    year: int | None = None,
    month: int | None = None,
):
    from datetime import datetime, timezone
    from app.schemas.relative import CheckinCalendarOut, CheckinDayItem
    from app.services import checkin_service
    await get_rls_db(db, str(current_user.id))
    await relative_service.assert_bound(
        db, relative_id=current_user.id, student_id=student_id,
    )
    now = datetime.now(timezone.utc)
    cal = await checkin_service.get_month_calendar(
        db, student_id=student_id,
        year=year or now.year, month=month or now.month,
    )
    return make_ok(CheckinCalendarOut(
        year=cal["year"], month=cal["month"],
        days=[CheckinDayItem(**d) for d in cal["days"]],
        checked_count=cal["checked_count"],
        current_streak=cal["current_streak"],
        longest_streak=cal["longest_streak"],
    ))
```

> `response_model=BaseResponse["CheckinCalendarOut"]` 用前向引用字符串，避免顶部 import；FastAPI 解析时已加载该 schema。若 FastAPI 报无法解析前向引用，则改为在文件顶部 `from app.schemas.relative import (... , CheckinCalendarOut)` 并去掉引号。实现时以能 import app 为准（Step 5 验证）。

- [ ] **Step 5: 跑测试确认通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/api/test_relative.py -p no:randomly -q`
Expected: PASS

> 若 Step 5 因前向引用报错，改 endpoint 的 `response_model=BaseResponse[CheckinCalendarOut]` 并把 `CheckinCalendarOut` 加进文件顶部已有的 `from app.schemas.relative import (...)` 块（同时保留局部 import 的 `CheckinDayItem` 或一并提到顶部），再重跑。

- [ ] **Step 6: 提交**

```bash
git add backend/app/schemas/relative.py backend/app/api/v1/relative.py tests/api/test_relative.py
git commit -m "feat(backend): 亲人可见打卡日历 API（assert_bound + 月历）"
```

---

## Task 3: 前端 student-view 打卡日历卡片

**Files:**
- Modify: `frontend/miniprogram/src/types/api.ts`
- Modify: `frontend/miniprogram/src/api/relative.ts`
- Modify: `frontend/miniprogram/src/pages/relative/student-view.vue`

- [ ] **Step 1: 加类型**

在 `frontend/miniprogram/src/types/api.ts` 末尾追加：

```typescript
// 亲人可见打卡日历（D-106）
export interface RelativeCheckinDay {
  date: string
  new_words_count: number
  streak_days: number
}
export interface RelativeCheckinCalendar {
  year: number
  month: number
  days: RelativeCheckinDay[]
  checked_count: number
  current_streak: number
  longest_streak: number
}
```

- [ ] **Step 2: 加前端 API**

在 `frontend/miniprogram/src/api/relative.ts` 顶部 import 处补类型（若该文件用 `import type {...} from '@/types/api'` 则加入；若无类型 import 则新增一行），并在文件末尾追加：

```typescript
import type { RelativeCheckinCalendar } from '@/types/api'

export function getStudentCheckinCalendar(studentId: string, year?: number, month?: number) {
  const data: Record<string, number> = {}
  if (year) data.year = year
  if (month) data.month = month
  return request<RelativeCheckinCalendar>(
    `/api/v1/relative/students/${studentId}/checkin-calendar`,
    { method: 'GET', data },
  )
}
```
> 若文件顶部已有 `import { request } from ...` 与其它 import，保持不动；`import type` 行放到现有 import 区即可（重复 import 同模块不影响构建，但优先合并到已有 type import）。

- [ ] **Step 3: student-view 加日历卡片**

编辑 `frontend/miniprogram/src/pages/relative/student-view.vue`：

(a) 在 `<view v-else>` 内、"为孩子续费"卡片之前插入日历卡片：
```html
      <view class="card">
        <view class="card-title">本月打卡日历</view>
        <view v-if="cal" class="cal-summary">
          本月打卡 {{ cal.checked_count }} 天 · 当前连续 {{ cal.current_streak }} 天 · 历史最高 {{ cal.longest_streak }} 天
        </view>
        <view class="cal-grid">
          <view v-for="(c, i) in cells" :key="i" class="cal-cell" :class="{ checked: c.checked, blank: !c.day }">
            <text v-if="c.day">{{ c.checked ? '🔥' : c.day }}</text>
          </view>
        </view>
      </view>
```

(b) 在 `<script setup>` 中：
- import 增加 `getStudentCheckinCalendar`：
```typescript
import { getStudentDiagnosisAsRelative, getStudentCheckinCalendar } from '@/api/relative'
import type { RelativeCheckinCalendar } from '@/types/api'
```
- 加 ref 与 computed：
```typescript
const cal = ref<RelativeCheckinCalendar | null>(null)
const checkedSet = computed(() => new Set(cal.value?.days.map(d => d.date) ?? []))
const cells = computed(() => {
  if (!cal.value) return [] as { day: number; date: string; checked: boolean }[]
  const { year, month } = cal.value
  const first = new Date(year, month - 1, 1).getDay()
  const daysIn = new Date(year, month, 0).getDate()
  const arr: { day: number; date: string; checked: boolean }[] = []
  for (let i = 0; i < first; i++) arr.push({ day: 0, date: '', checked: false })
  for (let d = 1; d <= daysIn; d++) {
    const date = `${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`
    arr.push({ day: d, date, checked: checkedSet.value.has(date) })
  }
  return arr
})
```
- 在 `onMounted` 拉学情后追加（在 `report.value = ...` 之后、`finally` 之前的 try 内）：
```typescript
    try { cal.value = await getStudentCheckinCalendar(studentId.value) } catch { /* 日历失败不阻塞 */ }
```

(c) 样式区追加：
```css
.cal-summary { font-size: 24rpx; color: var(--c-text-hint); margin-bottom: 16rpx; }
.cal-grid { display: flex; flex-wrap: wrap; }
.cal-cell { width: 14.28%; height: 64rpx; display: flex; align-items: center; justify-content: center; font-size: 24rpx; color: var(--c-text-body); }
.cal-cell.checked { color: var(--c-gold); font-weight: 700; }
.cal-cell.blank { visibility: hidden; }
```

- [ ] **Step 4: 构建验证**

Run: `cd frontend/miniprogram && npm run build:mp-weixin`
Expected: `Build complete.`

- [ ] **Step 5: 提交**

```bash
git add frontend/miniprogram/src/api/relative.ts frontend/miniprogram/src/types/api.ts frontend/miniprogram/src/pages/relative/student-view.vue
git commit -m "feat(frontend): 亲人端查看孩子页打卡日历卡片"
```

---

## Task 4: 全量回归 + 归档 D-106

**Files:**
- Modify: `docs/决策归档.md`

- [ ] **Step 1: 后端全量回归**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests -p no:randomly -q`
Expected: PASS（约 393 passed，净增 5 例：service 3 + API 2）

- [ ] **Step 2: 前端构建确认**

Run: `cd frontend/miniprogram && npm run build:mp-weixin`
Expected: `Build complete.`

- [ ] **Step 3: 归档 D-106**

在 `docs/决策归档.md` 顶部（`## D-105` 之前）插入 D-106 条目，格式对齐既有：日期、背景、结论（get_month_calendar 可复用 / assert_bound 亲人端 API / 前端月历卡片 / 仅当月只读）、测试（后端全量 passed + 前端 build）、影响范围、未做（切月 / D-107 / D-108）、相关（D-104/105/076，§6.4 §四D）。

- [ ] **Step 4: 提交**

```bash
git add docs/决策归档.md
git commit -m "docs: 归档 D-106 亲人可见打卡日历"
```

- [ ] **Step 5: 询问用户是否 push**

报告 commit 列表 + 测试/构建结果，征求明确同意后 `git push`。

---

## Self-Review

**1. Spec 覆盖：**
- `get_month_calendar`（当月行 / 跨月排除 / 空月 / 复用 status 摘要）→ Task 1 ✓
- schemas CheckinDayItem/CheckinCalendarOut → Task 2 ✓
- 亲人端 endpoint + assert_bound + 缺省年月 → Task 2 ✓
- 前端 api/types/student-view 月历卡片 → Task 3 ✓
- 零迁移、无花钱 → 全程无 alembic/付费 ✓

**2. 占位符扫描：** 无 TBD/TODO；每步含完整代码与命令。前向引用兜底方案已写明确切替代步骤（非占位）。

**3. 类型一致：** `get_month_calendar` 返回键 `year/month/days/checked_count/current_streak/longest_streak`（Task 1 定义 / Task 2 endpoint 使用一致）；`days` 元素键 `date/new_words_count/streak_days`（与 `CheckinDayItem` 字段一致）；前端 `RelativeCheckinCalendar` 字段与后端 `CheckinCalendarOut` 对齐；`cells`/`checkedSet` computed 与模板引用一致。
