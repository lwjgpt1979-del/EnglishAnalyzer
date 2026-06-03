# 亲人可见打卡日历 设计（D-106）

**日期：** 2026-06-03
**归属：** 词力通打卡激励 4 项后续之 ②。前序：D-100~D-105。复用现成亲人账号体系（D-076）。

## 背景与目标

D-104/105 已建立学生打卡（`study_checkins` + streak + 严格校验）。本切片让**已绑定的亲人**在"查看孩子"页看到孩子的**当月打卡日历**，强化家庭监督与激励。复用现成亲人体系：`relative_service.assert_bound` 校验亲子绑定后读学生数据（与 `relative_view_student_diagnosis` / `_wrong_questions` 同款模式）。

## 范围裁定

- **仅当月只读**：MVP 不做切换上下月（留后续）。
- **只做亲人端**：学生端打卡热力图归 D-107（`get_month_calendar` 服务设计为可复用，D-107 直接复用）。

## 架构与组件

### 后端

**1. `checkin_service.get_month_calendar(db, *, student_id, year, month) -> dict`**（新增）

返回：
```python
{
    "year": int,
    "month": int,
    "days": [   # 仅当月已打卡的日子，按日期升序
        {"date": "2026-06-01", "new_words_count": 5, "streak_days": 3},
        ...
    ],
    "checked_count": int,    # 本月打卡天数 = len(days)
    "current_streak": int,   # 复用 get_checkin_status
    "longest_streak": int,
}
```

实现要点：
- 当月范围：`month_start = date(year, month, 1)`；`next_month_start = date(year+1, 1, 1) if month == 12 else date(year, month+1, 1)`。
- 查询：`SELECT * FROM study_checkins WHERE student_id=:sid AND checkin_date >= month_start AND checkin_date < next_month_start ORDER BY checkin_date`。
- `days`：每行映射 `{date: checkin_date.isoformat(), new_words_count, streak_days}`。
- `current_streak` / `longest_streak`：复用 `get_checkin_status(db, student_id=...)` 的 `current_streak` / `longest_streak`（避免重复逻辑）。

**2. `schemas/relative.py`**（新增两个）
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

**3. `api/v1/relative.py`**（新增 endpoint，置于现有 `relative_view_student_wqs` 之后）
```python
from datetime import datetime, timezone
from app.schemas.relative import CheckinCalendarOut, CheckinDayItem
from app.services import checkin_service

@router.get(
    "/students/{student_id}/checkin-calendar",
    response_model=BaseResponse[CheckinCalendarOut],
)
async def relative_view_student_checkin_calendar(
    student_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
    year: int | None = None,
    month: int | None = None,
):
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
> import 风格沿用文件现状（局部 import 亦可，参照既有 `relative_view_student_wqs`）。

### 前端

**1. `api/relative.ts`**（新增）
```typescript
export function getStudentCheckinCalendar(studentId: string, year?: number, month?: number) {
  const q: Record<string, number> = {}
  if (year) q.year = year
  if (month) q.month = month
  return request<RelativeCheckinCalendar>(
    `/api/v1/relative/students/${studentId}/checkin-calendar`,
    { method: 'GET', data: q },
  )
}
```

**2. `types/api.ts`**（新增）
```typescript
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

**3. `pages/relative/student-view.vue`**（新增「本月打卡日历」卡片）
- onMounted 同时拉 `getStudentCheckinCalendar(studentId)`。
- 卡片头部摘要：`本月打卡 {{ cal.checked_count }} 天 · 当前连续 {{ cal.current_streak }} 天 · 历史最高 {{ cal.longest_streak }} 天`。
- 月度网格：7 列；用 `cal.year/month` 计算当月天数与首日星期偏移；已打卡日（date 在 `checkedSet` 中）高亮 + 🔥。
- 计算逻辑（前端 computed）：
  ```typescript
  const checkedSet = computed(() => new Set(cal.value?.days.map(d => d.date) ?? []))
  const cells = computed(() => {
    if (!cal.value) return []
    const { year, month } = cal.value
    const first = new Date(year, month - 1, 1).getDay() // 0=周日
    const daysIn = new Date(year, month, 0).getDate()
    const arr: { day: number; date: string; checked: boolean }[] = []
    for (let i = 0; i < first; i++) arr.push({ day: 0, date: '', checked: false }) // 占位
    for (let d = 1; d <= daysIn; d++) {
      const date = `${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`
      arr.push({ day: d, date, checked: checkedSet.value.has(date) })
    }
    return arr
  })
  ```

## 数据流

亲人在 center 页点孩子 → student-view 页 onMounted 拉学情 + 打卡日历 → 调 `GET /relative/students/{id}/checkin-calendar` → 后端 `assert_bound` 校验 → `get_month_calendar` 查当月 study_checkins + 复用 status 摘要 → 前端渲染网格。

## 错误处理

- 未绑定亲子 → `assert_bound` 抛 `AppError(403)`（现成）。
- 日历拉取失败不阻塞学情卡展示（前端 try/catch，日历卡显示空态）。
- `year`/`month` 缺省 → 用当前 UTC 年月。

## 测试（TDD）

**service（`tests/services/test_checkin_service.py` 扩展）**
1. 当月 2 天打卡 → `days` 长度 2、`checked_count==2`、按日期升序。
2. 跨月行（上月/下月各 1 行）不计入当月 `days`。
3. 空月 → `days==[]`、`checked_count==0`；同时 `current_streak`/`longest_streak` 反映既有打卡。

**API（`tests/api/test_relative.py` 扩展，复用其登录/绑定 helper）**
4. 未绑定亲子 → `GET checkin-calendar` 返回 403。
5. 已绑定 → 200，`data.days` 含已打卡日、`data.checked_count` 正确。

## 影响范围

- `backend/app/services/checkin_service.py`（+`get_month_calendar`）
- `backend/app/schemas/relative.py`（+`CheckinDayItem`/`CheckinCalendarOut`）
- `backend/app/api/v1/relative.py`（+endpoint）
- `frontend/miniprogram/src/api/relative.ts`、`types/api.ts`、`pages/relative/student-view.vue`
- **零迁移**（复用 study_checkins）、**无花钱**。

## 不做（后续）

- 切换上下月 / 跨月浏览
- 学生端打卡热力图（D-107）
- 补签 / 里程碑徽章（D-107）
- 打卡提醒双通道（D-108）

## 相关

D-104（打卡激励）、D-105（严格校验）、D-076（亲人端）；需求 §6.4、§四D。
