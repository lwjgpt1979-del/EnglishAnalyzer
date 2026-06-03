# 词力通打卡激励 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现。Steps 用 checkbox (`- [ ]`) 跟踪。

**Goal:** 词力通完成会话即记当日打卡，展示连续天数（断签归零）+ 历史最高。

**Architecture:** 复用既有 `study_checkins`（零迁移）。新增 `checkin_service`（record_checkin / get_checkin_status，streak 靠"昨天有无行"推算）+ 2 个 API + 前端完成页打卡展示。MVP 不做提醒推送 / 亲人可见。零花钱。

**Tech Stack:** FastAPI + SQLAlchemy async；uni-app Vue3。

参考 spec：`docs/superpowers/specs/2026-06-03-vocab-checkin-design.md`。

---

### Task 1: checkin_service（record + status）

**Files:**
- Create: `backend/app/services/checkin_service.py`
- Test: `tests/services/test_checkin_service.py`

实现：

```python
"""词力通每日打卡（P1 / D-104）。复用 study_checkins，零迁移。"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d5_learning import StudyCheckin


def _today() -> date:
    return datetime.now(timezone.utc).date()


async def _row_for(db: AsyncSession, student_id: uuid.UUID, d: date) -> StudyCheckin | None:
    return (await db.execute(
        select(StudyCheckin).where(
            StudyCheckin.student_id == student_id,
            StudyCheckin.checkin_date == d,
        )
    )).scalar_one_or_none()


async def record_checkin(
    db: AsyncSession, *, student_id: uuid.UUID,
    new_words_count: int = 0, review_done: bool = False,
) -> StudyCheckin:
    today = _today()
    row = await _row_for(db, student_id, today)
    if row is not None:
        # 同日重复：更新计数，streak 不变（幂等）
        row.new_words_count = new_words_count
        row.review_done = review_done
        await db.flush()
        return row
    yesterday = await _row_for(db, student_id, today - timedelta(days=1))
    streak = (yesterday.streak_days + 1) if yesterday is not None else 1
    row = StudyCheckin(
        id=uuid.uuid4(), student_id=student_id, checkin_date=today,
        new_words_count=new_words_count, review_done=review_done, streak_days=streak,
    )
    db.add(row)
    await db.flush()
    return row


async def get_checkin_status(db: AsyncSession, *, student_id: uuid.UUID) -> dict:
    today = _today()
    today_row = await _row_for(db, student_id, today)
    yest_row = await _row_for(db, student_id, today - timedelta(days=1))
    if today_row is not None:
        current = today_row.streak_days
    elif yest_row is not None:
        current = yest_row.streak_days  # 今日待打、连续仍保持
    else:
        current = 0
    longest = (await db.execute(
        select(func.coalesce(func.max(StudyCheckin.streak_days), 0))
        .where(StudyCheckin.student_id == student_id)
    )).scalar_one()
    return {
        "checked_in_today": today_row is not None,
        "current_streak": current,
        "longest_streak": int(longest),
        "today_new_words": today_row.new_words_count if today_row else 0,
        "today_review_done": today_row.review_done if today_row else False,
    }
```

- [ ] **Step 1: 写失败测试**（`tests/services/test_checkin_service.py`）

```python
import uuid
from datetime import datetime, timedelta, timezone
import pytest
import pytest_asyncio
from app.core.database import _async_session_factory
from app.models.d5_learning import StudyCheckin
from app.services import checkin_service


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _student(s) -> uuid.UUID:
    from app.services.auth_service import upsert_user
    u = await upsert_user(s, openid=f"checkin_{uuid.uuid4().hex[:8]}")
    await s.flush()
    return u.id


def _today():
    return datetime.now(timezone.utc).date()


@pytest.mark.asyncio
async def test_first_checkin_streak_1(db_session):
    sid = await _student(db_session)
    row = await checkin_service.record_checkin(db_session, student_id=sid, new_words_count=5, review_done=True)
    assert row.streak_days == 1 and row.new_words_count == 5


@pytest.mark.asyncio
async def test_consecutive_day_streak_increments(db_session):
    sid = await _student(db_session)
    # 造昨天的行 streak=3
    db_session.add(StudyCheckin(
        id=uuid.uuid4(), student_id=sid, checkin_date=_today() - timedelta(days=1),
        new_words_count=3, review_done=True, streak_days=3))
    await db_session.flush()
    row = await checkin_service.record_checkin(db_session, student_id=sid, new_words_count=2, review_done=True)
    assert row.streak_days == 4


@pytest.mark.asyncio
async def test_broken_streak_resets(db_session):
    sid = await _student(db_session)
    # 前天有行、昨天无行 → 今天 streak=1
    db_session.add(StudyCheckin(
        id=uuid.uuid4(), student_id=sid, checkin_date=_today() - timedelta(days=2),
        new_words_count=1, review_done=True, streak_days=9))
    await db_session.flush()
    row = await checkin_service.record_checkin(db_session, student_id=sid, new_words_count=1, review_done=True)
    assert row.streak_days == 1


@pytest.mark.asyncio
async def test_same_day_idempotent(db_session):
    sid = await _student(db_session)
    r1 = await checkin_service.record_checkin(db_session, student_id=sid, new_words_count=5, review_done=True)
    r2 = await checkin_service.record_checkin(db_session, student_id=sid, new_words_count=8, review_done=True)
    assert r1.id == r2.id and r2.streak_days == 1 and r2.new_words_count == 8


@pytest.mark.asyncio
async def test_status(db_session):
    sid = await _student(db_session)
    db_session.add(StudyCheckin(
        id=uuid.uuid4(), student_id=sid, checkin_date=_today() - timedelta(days=1),
        new_words_count=1, review_done=True, streak_days=7))
    await db_session.flush()
    st = await checkin_service.get_checkin_status(db_session, student_id=sid)
    assert st["checked_in_today"] is False
    assert st["current_streak"] == 7   # 今日待打、连续保持
    assert st["longest_streak"] == 7
    await checkin_service.record_checkin(db_session, student_id=sid, new_words_count=2, review_done=True)
    st2 = await checkin_service.get_checkin_status(db_session, student_id=sid)
    assert st2["checked_in_today"] is True and st2["current_streak"] == 8 and st2["longest_streak"] == 8
```

- [ ] **Step 2: 跑测试确认失败** `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_checkin_service.py -q` → FAIL（模块不存在）。
- [ ] **Step 3: 实现 checkin_service**
- [ ] **Step 4: 跑测试确认通过**
- [ ] **Step 5: Commit** `feat(backend): 词力通打卡 service（record + status，streak/断签）`

### Task 2: schema + 打卡 API

**Files:**
- Modify: `backend/app/schemas/vocabulary.py`（CheckinIn/CheckinResult/CheckinStatusOut）
- Modify: `backend/app/api/v1/vocabulary.py`（POST /checkin + GET /checkin/status）
- Test: `tests/api/test_vocabulary.py`

schema（`schemas/vocabulary.py` 末尾）：

```python
class CheckinIn(BaseModel):
    new_words_count: int = 0
    review_done: bool = False

class CheckinResult(BaseModel):
    checkin_date: str
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

API（`api/v1/vocabulary.py`，import 上述 schema + `from app.services import checkin_service`）：

```python
@router.post("/checkin", response_model=BaseResponse[CheckinResult])
async def checkin(body: CheckinIn, db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    row = await checkin_service.record_checkin(
        db, student_id=current_user.id,
        new_words_count=body.new_words_count, review_done=body.review_done)
    await db.commit()
    return make_ok(CheckinResult(
        checkin_date=row.checkin_date.isoformat(), streak_days=row.streak_days,
        new_words_count=row.new_words_count, review_done=row.review_done))

@router.get("/checkin/status", response_model=BaseResponse[CheckinStatusOut])
async def checkin_status(db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    st = await checkin_service.get_checkin_status(db, student_id=current_user.id)
    return make_ok(CheckinStatusOut(**st))
```

- [ ] **Step 1: 写失败测试**（`test_vocabulary.py`：登录 → POST /checkin {new_words_count:5,review_done:true} → 200 streak_days==1；GET /checkin/status → checked_in_today true, current_streak 1；未登录 GET 401）。
- [ ] **Step 2: 跑测试确认失败**
- [ ] **Step 3: 实现 schema + 2 端点**
- [ ] **Step 4: 跑测试确认通过 + 后端全量回归** `/opt/anaconda3/bin/python -m pytest ../tests -q -p no:randomly`
- [ ] **Step 5: Commit** `feat(backend): 词力通打卡 API（checkin + status）`

### Task 3: 前端完成页打卡展示

**Files:**
- Modify: `frontend/miniprogram/src/api/vocabulary.ts`（checkin/checkinStatus）
- Modify: `frontend/miniprogram/src/types/api.ts`（CheckinResult/CheckinStatus）
- Modify: `frontend/miniprogram/src/pages/vocabulary/index.vue`（进完成阶段调 checkin + 展示连续天数）

- [ ] **Step 1: api + 类型**

`api/vocabulary.ts`：
```typescript
export function checkin(newWordsCount: number, reviewDone: boolean): Promise<VocabCheckinResult> {
  return request<VocabCheckinResult>('/api/v1/vocabulary/checkin', {
    method: 'POST', data: { new_words_count: newWordsCount, review_done: reviewDone },
  })
}
```
`types/api.ts`：
```typescript
export interface VocabCheckinResult {
  checkin_date: string; streak_days: number; new_words_count: number; review_done: boolean
}
```

- [ ] **Step 2: 完成页调打卡 + 展示**（`pages/vocabulary/index.vue`）
  - `<script setup>` 加 `import { checkin } from '@/api/vocabulary'` + `const streakDays = ref(0)`。
  - 在进入完成阶段处（`phase.value = 'done'` 的两处：`startQuiz` 当 quizQueue 空、`nextQuiz` 末尾）抽一个 `finishSession()` 调用：

```typescript
async function finishSession() {
  phase.value = 'done'
  try {
    const r = await checkin(newCards.value.length, true)
    streakDays.value = r.streak_days
  } catch { /* 打卡失败不阻断 */ }
}
```
  把原先 `phase.value = 'done'`（startQuiz 中 quizQueue 为空时、nextQuiz 末尾）替换为 `finishSession()`。
  - 完成卡内展示：`<view class="done-streak">已连续打卡 {{ streakDays }} 天 🔥</view>`（在答对率下方）。

- [ ] **Step 3: 构建验证** `cd frontend/miniprogram && npm run build:mp-weixin` → DONE。
- [ ] **Step 4: Commit** `feat(frontend): 词力通完成页打卡 + 连续天数展示`

### Task 4: 集成验证 + 归档 D-104

- [ ] **Step 1: 后端全量** `cd backend && /opt/anaconda3/bin/python -m pytest ../tests -q -p no:randomly` 全绿（374 + 本次新增）。
- [ ] **Step 2: 前端 build** 通过。
- [ ] **Step 3: 归档 D-104**（docs/决策归档.md 顶部）：打卡 service（record/status、streak 断签归零、历史最高）+ 2 API + 前端完成页打卡展示；明确提醒推送/亲人可见/严格复习校验留后续；零迁移。
- [ ] **Step 4: Commit +（征得同意后）push**

---

## 备注
- **streak 推算**：只看"昨天有无行"决定从昨天+1 还是从 1；不扫全历史，O(1)。
- **幂等**：同日重复打卡更新计数、streak 不变。
- **向后兼容**：study_checkins 此前无写入方（仅建表），本切片是首个写入者，不影响他处。
