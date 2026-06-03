# 词力通严格校验复习完成度 Implementation Plan（D-105）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 打卡从"进入完成页即发放"改为后端实算今日任务完成度（复习全完成 + 新词全学完），达标才发放。

**Architecture:** 新增 `vocabulary_service.compute_today_progress` 计算完成度；`checkin_service.record_checkin` 拆为"始终写入的 `_upsert_checkin`"+"严格校验闸门 `record_checkin`"；API 去 body、返回 `completed` + 缺口；前端按 `completed` 展示打卡或引导。

**Tech Stack:** FastAPI + SQLAlchemy 2.x asyncio + Pydantic v2 + PostgreSQL；uni-app Vue3 mini-program。零迁移、无花钱。

**运行约定：** 后端 python = `/opt/anaconda3/bin/python`，pytest 从 `backend/` 目录跑、路径用 `../tests/...`、加 `-p no:randomly`。前端从 `frontend/miniprogram/` 跑 `npm run build:mp-weixin`。

---

## File Structure

| 文件 | 职责 | 改动 |
|---|---|---|
| `backend/app/services/vocabulary_service.py` | 词汇业务逻辑 | +`_new_target`（纯函数）+`compute_today_progress`（DB） |
| `backend/app/services/checkin_service.py` | 打卡逻辑 | 拆 `_upsert_checkin`（始终写）+ `record_checkin`（严格闸门，改签名） |
| `backend/app/schemas/vocabulary.py` | schemas | `CheckinResult` 扩展；删 `CheckinIn` |
| `backend/app/api/v1/vocabulary.py` | API | `POST /checkin` 去 body，返回 completed/缺口；去 `CheckinIn` import |
| `tests/services/test_vocabulary_service.py` | service 测试 | +`compute_today_progress` / `_new_target` 测试 |
| `tests/services/test_checkin_service.py` | 打卡测试 | 迁移既有 5 例到 `_upsert_checkin` + 改 status 测试 + 新增 2 闸门例 |
| `tests/api/test_vocabulary.py` | API 测试 | 重写 checkin 流（completed/未达标），去旧 body 入参 |
| `frontend/miniprogram/src/api/vocabulary.ts` | 前端 API | `checkin()` 去参 |
| `frontend/miniprogram/src/types/api.ts` | 前端类型 | `VocabCheckinResult` 扩展 |
| `frontend/miniprogram/src/pages/vocabulary/index.vue` | 完成页 | finishSession 按 completed 展示/引导 |

---

## Task 1: `compute_today_progress`（后端完成度计算）

**Files:**
- Modify: `backend/app/services/vocabulary_service.py`
- Test: `tests/services/test_vocabulary_service.py`

- [ ] **Step 1: 写失败测试（纯函数 `_new_target` + DB 完成度）**

在 `tests/services/test_vocabulary_service.py` 末尾追加（文件已有 `db_session`/`_make_student`/`_seed_words` fixtures 与 `from datetime import datetime, timezone`；若缺 `timedelta` 则在该测试内 `from datetime import timedelta`）：

```python
# ─── D-105: 完成度计算 ────────────────────────────────────────────────

def test_new_target_pure():
    from app.services.vocabulary_service import _new_target
    # 词库新词充足：取档位上限
    assert _new_target(5, 0, 100) == 5
    assert _new_target(5, 3, 100) == 5
    # 词库新词不足：学完所有可学即收缩（已学3+剩0=3）
    assert _new_target(5, 3, 0) == 3
    assert _new_target(5, 1, 2) == 3


@pytest.mark.asyncio
async def test_progress_fresh_student_not_done(db_session):
    """全新学生：无到期复习（review_done True），但今日未学新词 → all_done False。"""
    from app.services import vocabulary_service
    sid = await _make_student(db_session)
    await _seed_words(db_session, 10)  # 词库有未学新词
    p = await vocabulary_service.compute_today_progress(db_session, student_id=sid)
    assert p["review_due"] == 0 and p["review_done"] is True
    assert p["new_learned_today"] == 0
    assert p["new_target"] == 5  # free 档上限
    assert p["new_done"] is False and p["all_done"] is False


@pytest.mark.asyncio
async def test_progress_due_review_blocks(db_session):
    """有到期复习词 → review_done False、all_done False。"""
    from datetime import timedelta
    from app.models.d5_learning import VocabularyLearning
    from app.services import vocabulary_service
    sid = await _make_student(db_session)
    [wid] = await _seed_words(db_session, 1)
    now = datetime.now(timezone.utc)
    db_session.add(VocabularyLearning(
        id=uuid.uuid4(), student_id=sid, word_id=wid,
        interval_days=1, repetitions=1, easiness_factor=2.5,
        next_review_at=now - timedelta(days=1),  # 已到期
        level="learning",
    ))
    await db_session.flush()
    p = await vocabulary_service.compute_today_progress(db_session, student_id=sid)
    assert p["review_due"] >= 1 and p["review_done"] is False
    assert p["all_done"] is False


@pytest.mark.asyncio
async def test_progress_all_done_when_new_learned(db_session):
    """今日学满 free 上限(5)且无到期复习 → all_done True。"""
    from datetime import timedelta
    from app.models.d5_learning import VocabularyLearning
    from app.services import vocabulary_service
    sid = await _make_student(db_session)
    wids = await _seed_words(db_session, 5)
    now = datetime.now(timezone.utc)
    for wid in wids:
        db_session.add(VocabularyLearning(
            id=uuid.uuid4(), student_id=sid, word_id=wid,
            interval_days=1, repetitions=1, easiness_factor=2.5,
            next_review_at=now + timedelta(days=1),  # 未到期
            level="learning", created_at=now,
        ))
    await db_session.flush()
    p = await vocabulary_service.compute_today_progress(db_session, student_id=sid)
    assert p["review_due"] == 0
    assert p["new_learned_today"] == 5
    assert p["new_target"] == 5
    assert p["new_done"] is True and p["all_done"] is True
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_vocabulary_service.py -p no:randomly -q`
Expected: FAIL（`AttributeError: module ... has no attribute '_new_target'` / `compute_today_progress'`）

- [ ] **Step 3: 实现 `_new_target` + `compute_today_progress`**

在 `backend/app/services/vocabulary_service.py` 顶部 import 行补 `time`：
```python
from datetime import datetime, time, timedelta, timezone
```

在 `_daily_new_limit` 函数之后插入：
```python
def _new_target(new_limit: int, new_learned_today: int, new_words_remaining: int) -> int:
    """今日新词目标：词库新词足够取档位上限；不足则学完所有可学即达标。"""
    return min(new_limit, new_learned_today + new_words_remaining)


async def compute_today_progress(db: AsyncSession, *, student_id: uuid.UUID) -> dict:
    """计算今日任务完成度（复习全完成 + 新词全学完）。"""
    now = datetime.now(timezone.utc)
    today = now.date()
    day_start = datetime.combine(today, time.min, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    review_due = (await db.execute(
        select(func.count()).select_from(VocabularyLearning).where(
            VocabularyLearning.student_id == student_id,
            VocabularyLearning.next_review_at <= now,
        )
    )).scalar_one()

    new_learned_today = (await db.execute(
        select(func.count()).select_from(VocabularyLearning).where(
            VocabularyLearning.student_id == student_id,
            VocabularyLearning.created_at >= day_start,
            VocabularyLearning.created_at < day_end,
        )
    )).scalar_one()

    learned_subq = (
        select(VocabularyLearning.word_id)
        .where(VocabularyLearning.student_id == student_id)
        .scalar_subquery()
    )
    new_words_remaining = (await db.execute(
        select(func.count()).select_from(VocabularyWord).where(
            VocabularyWord.id.not_in(learned_subq),
        )
    )).scalar_one()

    new_limit = await _daily_new_limit(db, student_id=student_id)
    target = _new_target(new_limit, int(new_learned_today), int(new_words_remaining))
    review_done = int(review_due) == 0
    new_done = int(new_learned_today) >= target
    return {
        "review_due": int(review_due),
        "review_done": review_done,
        "new_learned_today": int(new_learned_today),
        "new_target": target,
        "new_done": new_done,
        "all_done": review_done and new_done,
    }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_vocabulary_service.py -p no:randomly -q`
Expected: PASS（含 4 个新例）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/vocabulary_service.py tests/services/test_vocabulary_service.py
git commit -m "feat(backend): 词力通今日完成度计算 compute_today_progress"
```

---

## Task 2: `checkin_service` 严格校验闸门

**Files:**
- Modify: `backend/app/services/checkin_service.py`
- Test: `tests/services/test_checkin_service.py`

- [ ] **Step 1: 迁移既有测试到 `_upsert_checkin` + 新增 2 闸门测试**

编辑 `tests/services/test_checkin_service.py`：把现有 5 个测试里所有 `checkin_service.record_checkin(db_session, student_id=sid, new_words_count=N, review_done=True)` 调用改为 `checkin_service._upsert_checkin(db_session, student_id=sid, new_words_count=N, review_done=True)`（共：`test_first_checkin_streak_1`、`test_consecutive_day_streak_increments`、`test_broken_streak_resets`、`test_same_day_idempotent` 各 1 处；`test_status` 内 2 处——`record_checkin(...)` 两次都改 `_upsert_checkin(...)`）。返回值与断言不变（仍返回单行）。

然后在文件末尾追加闸门测试（新增 import 见代码内）：

```python
# ─── D-105: record_checkin 严格校验闸门 ──────────────────────────────

async def _seed_words(s, n: int) -> list[uuid.UUID]:
    from app.models.d5_learning import VocabularyWord
    ids = []
    for i in range(n):
        w = VocabularyWord(
            id=uuid.uuid4(), word=f"ckwords_{uuid.uuid4().hex[:6]}",
            phonetic="ˈtest", definitions=[{"pos": "n.", "meaning": f"测试{i}"}],
            examples=None, difficulty=1,
        )
        s.add(w)
        ids.append(w.id)
    await s.flush()
    return ids


@pytest.mark.asyncio
async def test_record_checkin_blocked_when_incomplete(db_session):
    """今日未学新词 → all_done False，record_checkin 不写行、返回 (None, progress)。"""
    sid = await _student(db_session)
    await _seed_words(db_session, 10)  # 词库有未学新词、本人未学
    row, progress = await checkin_service.record_checkin(db_session, student_id=sid)
    assert row is None
    assert progress["all_done"] is False
    assert await checkin_service._row_for(db_session, sid, _today()) is None


@pytest.mark.asyncio
async def test_record_checkin_writes_when_complete(db_session):
    """今日学满 free 上限(5)且无到期复习 → 写打卡、streak=1。"""
    from app.models.d5_learning import VocabularyLearning
    sid = await _student(db_session)
    wids = await _seed_words(db_session, 5)
    now = datetime.now(timezone.utc)
    for wid in wids:
        db_session.add(VocabularyLearning(
            id=uuid.uuid4(), student_id=sid, word_id=wid,
            interval_days=1, repetitions=1, easiness_factor=2.5,
            next_review_at=now + timedelta(days=1),
            level="learning", created_at=now,
        ))
    await db_session.flush()
    row, progress = await checkin_service.record_checkin(db_session, student_id=sid)
    assert progress["all_done"] is True
    assert row is not None and row.streak_days == 1
    assert row.new_words_count == 5 and row.review_done is True
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_checkin_service.py -p no:randomly -q`
Expected: FAIL（`_upsert_checkin` 不存在 / `record_checkin` 旧签名报 `unexpected keyword`/返回非 tuple）

- [ ] **Step 3: 重构 `checkin_service.py`**

把 `backend/app/services/checkin_service.py` 中现有 `record_checkin` 函数整体替换为下面两个函数（`_today`/`_row_for`/`get_checkin_status` 保持不变），并在顶部 import 区补 `from app.services import vocabulary_service`：

```python
async def _upsert_checkin(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    new_words_count: int,
    review_done: bool,
) -> StudyCheckin:
    """写入/更新当日打卡行（streak 推算）。同日重复调用幂等（更新计数、streak 不变）。"""
    today = _today()
    row = await _row_for(db, student_id, today)
    if row is not None:
        row.new_words_count = new_words_count
        row.review_done = review_done
        await db.flush()
        return row
    yesterday = await _row_for(db, student_id, today - timedelta(days=1))
    streak = (yesterday.streak_days + 1) if yesterday is not None else 1
    row = StudyCheckin(
        id=uuid.uuid4(),
        student_id=student_id,
        checkin_date=today,
        new_words_count=new_words_count,
        review_done=review_done,
        streak_days=streak,
    )
    db.add(row)
    await db.flush()
    return row


async def record_checkin(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
) -> tuple[StudyCheckin | None, dict]:
    """严格校验今日任务完成度，达标才写打卡。返回 (打卡行 or None, progress)。"""
    progress = await vocabulary_service.compute_today_progress(db, student_id=student_id)
    if not progress["all_done"]:
        return None, progress
    row = await _upsert_checkin(
        db,
        student_id=student_id,
        new_words_count=progress["new_learned_today"],
        review_done=True,
    )
    return row, progress
```

顶部 import 区调整为（补 vocabulary_service）：
```python
from app.models.d5_learning import StudyCheckin
from app.services import vocabulary_service
```

> 无循环 import：`vocabulary_service` 不 import `checkin_service`。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_checkin_service.py -p no:randomly -q`
Expected: PASS（5 迁移例 + 2 闸门例）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/checkin_service.py tests/services/test_checkin_service.py
git commit -m "feat(backend): 词力通打卡严格校验闸门（达标才发放）"
```

---

## Task 3: schemas + API 改造

**Files:**
- Modify: `backend/app/schemas/vocabulary.py`
- Modify: `backend/app/api/v1/vocabulary.py`
- Test: `tests/api/test_vocabulary.py`

- [ ] **Step 1: 重写 checkin API 测试**

编辑 `tests/api/test_vocabulary.py`：把现有 `test_checkin_flow`（约 111-122 行）整体替换为下面两个测试（`test_checkin_status_requires_auth` 保留不动）：

```python
@pytest.mark.asyncio
async def test_checkin_blocked_when_incomplete(client):
    """未学满今日新词 → completed False、不写打卡。"""
    await _seed_word()
    headers = await _login(client, uuid.uuid4().hex[:6])
    r = await client.post("/api/v1/vocabulary/checkin", headers=headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["completed"] is False
    st = await client.get("/api/v1/vocabulary/checkin/status", headers=headers)
    assert st.json()["data"]["checked_in_today"] is False


@pytest.mark.asyncio
async def test_checkin_completed_flow(client):
    """学满今日新词后打卡 → completed True、streak=1。"""
    for _ in range(5):
        await _seed_word()
    headers = await _login(client, uuid.uuid4().hex[:6])
    task = (await client.get("/api/v1/vocabulary/daily-task", headers=headers)).json()["data"]
    assert len(task["new_words"]) == 5  # free 档上限
    for w in task["new_words"]:
        await client.post("/api/v1/vocabulary/answer", headers=headers,
                          json={"word_id": w["word_id"], "correct": True})
    r = await client.post("/api/v1/vocabulary/checkin", headers=headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["completed"] is True and data["streak_days"] == 1
    st = (await client.get("/api/v1/vocabulary/checkin/status", headers=headers)).json()["data"]
    assert st["checked_in_today"] is True and st["current_streak"] == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/api/test_vocabulary.py -p no:randomly -q`
Expected: FAIL（返回体无 `completed` 字段 / endpoint 仍要求 body）

- [ ] **Step 3: 改 schemas**

编辑 `backend/app/schemas/vocabulary.py` 的 D-104 区块：删除 `CheckinIn` 类，把 `CheckinResult` 替换为：

```python
class CheckinResult(BaseModel):
    completed: bool                  # 今日任务是否达标（打卡是否发放）
    checkin_date: str | None = None  # 未达标时为 None
    streak_days: int = 0
    new_words_count: int = 0
    review_done: bool = False
    # 缺口（未完成时引导）
    review_due: int = 0
    new_learned_today: int = 0
    new_target: int = 0
```

`CheckinStatusOut` 保持不变。

- [ ] **Step 4: 改 API endpoint**

编辑 `backend/app/api/v1/vocabulary.py`：
1. import 区把 `CheckinIn,` 删除（保留 `CheckinResult, CheckinStatusOut`）。
2. 把 `checkin` endpoint 整体替换为：

```python
@router.post("/checkin", response_model=BaseResponse[CheckinResult])
async def checkin(db: DbDep, current_user: UserDep):
    """词力通完成会话打卡：后端实算今日完成度，达标才发放。"""
    await get_rls_db(db, str(current_user.id))
    row, progress = await checkin_service.record_checkin(db, student_id=current_user.id)
    if row is None:
        return make_ok(CheckinResult(
            completed=False,
            review_due=progress["review_due"],
            new_learned_today=progress["new_learned_today"],
            new_target=progress["new_target"],
        ))
    await db.commit()
    return make_ok(CheckinResult(
        completed=True,
        checkin_date=row.checkin_date.isoformat(),
        streak_days=row.streak_days,
        new_words_count=row.new_words_count,
        review_done=row.review_done,
        review_due=progress["review_due"],
        new_learned_today=progress["new_learned_today"],
        new_target=progress["new_target"],
    ))
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/api/test_vocabulary.py -p no:randomly -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/schemas/vocabulary.py backend/app/api/v1/vocabulary.py tests/api/test_vocabulary.py
git commit -m "feat(backend): 词力通打卡 API 去 body + 返回 completed/缺口"
```

---

## Task 4: 前端完成页按 completed 展示/引导

**Files:**
- Modify: `frontend/miniprogram/src/api/vocabulary.ts`
- Modify: `frontend/miniprogram/src/types/api.ts`
- Modify: `frontend/miniprogram/src/pages/vocabulary/index.vue`

- [ ] **Step 1: 改前端类型**

编辑 `frontend/miniprogram/src/types/api.ts`，把 `VocabCheckinResult` 替换为：

```typescript
// 打卡（D-104 / D-105 严格校验）
export interface VocabCheckinResult {
  completed: boolean
  checkin_date: string | null
  streak_days: number
  new_words_count: number
  review_done: boolean
  review_due: number
  new_learned_today: number
  new_target: number
}
```

- [ ] **Step 2: 改前端 API**

编辑 `frontend/miniprogram/src/api/vocabulary.ts`，把 `checkin` 函数替换为无参版本：

```typescript
export function checkin(): Promise<VocabCheckinResult> {
  return request<VocabCheckinResult>('/api/v1/vocabulary/checkin', { method: 'POST' })
}
```

- [ ] **Step 3: 改完成页逻辑 + 展示**

编辑 `frontend/miniprogram/src/pages/vocabulary/index.vue`：

(a) 在 `const streakDays = ref(0)` 之后补两个 ref：
```typescript
const checkinDone = ref(false)
const gapHint = ref('')
```

(b) 把 `finishSession` 函数体替换为：
```typescript
async function finishSession() {
  phase.value = 'done'
  try {
    const r = await checkin()
    checkinDone.value = r.completed
    if (r.completed) {
      streakDays.value = r.streak_days
    } else {
      const newGap = Math.max(0, r.new_target - r.new_learned_today)
      gapHint.value = `还差 ${r.review_due} 个复习 / ${newGap} 个新词，完成后才能打卡`
    }
  } catch {
    // 打卡失败不阻塞完成页展示
  }
}
```

(c) 把完成卡里的 `<view class="done-streak">已连续打卡 {{ streakDays }} 天 🔥</view>` 替换为：
```html
<view v-if="checkinDone" class="done-streak">已连续打卡 {{ streakDays }} 天 🔥</view>
<view v-else class="done-gap">{{ gapHint }}</view>
```

(d) 在样式区 `.done-streak { ... }` 之后补：
```css
.done-gap { margin-top: 20rpx; font-size: 28rpx; color: var(--c-text-second); }
```

- [ ] **Step 4: 构建验证**

Run: `cd frontend/miniprogram && npm run build:mp-weixin`
Expected: `Build complete.`

- [ ] **Step 5: 提交**

```bash
git add frontend/miniprogram/src/api/vocabulary.ts frontend/miniprogram/src/types/api.ts frontend/miniprogram/src/pages/vocabulary/index.vue
git commit -m "feat(frontend): 词力通完成页按达标展示打卡/未完成引导"
```

---

## Task 5: 全量回归 + 归档 D-105

**Files:**
- Modify: `docs/决策归档.md`

- [ ] **Step 1: 后端全量回归**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests -p no:randomly -q`
Expected: PASS（全绿；预期 383 passed 左右——D-104 的 7 例打卡相关被改写，净增约 2 例）

- [ ] **Step 2: 前端构建确认**

Run: `cd frontend/miniprogram && npm run build:mp-weixin`
Expected: `Build complete.`

- [ ] **Step 3: 归档 D-105**

在 `docs/决策归档.md` 顶部（`## D-104` 之前）插入 D-105 归档条目，格式对齐既有条目：日期、背景、结论（compute_today_progress 口径 / record_checkin 闸门 / API 去 body / 前端引导）、测试（后端全量 passed + 前端 build）、影响范围、未做（D-106/107/108）、相关（D-104，§6.4）。

- [ ] **Step 4: 提交**

```bash
git add docs/决策归档.md
git commit -m "docs: 归档 D-105 词力通严格校验复习完成度"
```

- [ ] **Step 5: 询问用户是否 push**

向用户报告：本切片 commit 列表 + 全量测试/构建结果，征求明确同意后再 `git push`。

---

## Self-Review

**1. Spec 覆盖：**
- 完成度口径（review_done/new_learned_today/new_target/new_done/all_done）→ Task 1 ✓
- record_checkin 接闸门、去入参、后端实算填充 → Task 2 ✓
- 同日幂等保持 → Task 2 `_upsert_checkin` 保留原逻辑，`test_same_day_idempotent` 迁移覆盖 ✓
- CheckinResult 扩展 / CheckinIn 废弃 → Task 3 ✓
- API 去 body、未达标返回缺口 → Task 3 ✓
- 前端按 completed 展示/引导、checkin() 去参 → Task 4 ✓
- 零迁移、无花钱 → 全程无 alembic/付费调用 ✓

**2. 占位符扫描：** 无 TBD/TODO；每个代码步骤含完整代码与确切命令。

**3. 类型一致：** `record_checkin` 返回 `tuple[StudyCheckin | None, dict]`（Task 2 定义 / Task 3 API 解包 `row, progress` 一致）；`compute_today_progress` 返回键 `review_due/review_done/new_learned_today/new_target/new_done/all_done`（Task 1 定义 / Task 2、Task 3 使用一致）；`VocabCheckinResult` 字段与后端 `CheckinResult` 对齐（completed/checkin_date/streak_days/new_words_count/review_done/review_due/new_learned_today/new_target）。
