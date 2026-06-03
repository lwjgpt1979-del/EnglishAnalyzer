# 词力通严格校验复习完成度 设计（D-105）

**日期：** 2026-06-03
**归属：** 词力通打卡激励 4 项后续之 ①（最轻、纯后端逻辑）。前序：D-100/101/102/103/104。

## 背景与目标

D-104 打卡为"进入完成页即发放"，前端 `finishSession` 硬传 `new_words_count=newCards.length`、`review_done=true`。问题：可被前端绕过、不反映真实完成度。

目标：打卡改为 **后端实算今日任务完成度，达标才发放**。口径（已确认）：**今日到期复习词全部完成 AND 今日新词全部学完**。

## 完成度口径

| 维度 | 判定 |
|---|---|
| 复习完成 `review_done` | 当前到期复习词数 `review_due == 0`。作答后（对/错）`next_review_at` 均被推到未来，自然移出到期集合（`next_review_at <= now`），故"到期清零"即复习完成。 |
| 今日已学新词数 `new_learned_today` | `COUNT(VocabularyLearning where student_id 且 created_at 的 UTC 日期 == today)`。`created_at` 为首次学新词建行时间。 |
| 今日新词目标 `new_target` | `min(new_limit, new_learned_today + new_words_remaining)`。`new_limit` = 档位每日新词上限；`new_words_remaining` = 词库中该生未学词数。词库新词足够→目标=档位上限；新词不足→学完所有可学的即达标（避免"无词可学却卡住打卡"）。 |
| 新词完成 `new_done` | `new_learned_today >= new_target` |
| 达标 `all_done` | `review_done AND new_done` |

## 架构与组件

### 后端

**1. `vocabulary_service.compute_today_progress(db, *, student_id) -> dict`**（新增）

返回：
```python
{
    "review_due": int,            # 当前到期复习词数（next_review_at <= now）
    "review_done": bool,          # review_due == 0
    "new_learned_today": int,     # 今日 created 的 learning 行数（UTC date == today）
    "new_target": int,            # min(new_limit, new_learned_today + new_words_remaining)
    "new_done": bool,             # new_learned_today >= new_target
    "all_done": bool,             # review_done and new_done
}
```

实现要点：
- `review_due`：`SELECT count(*) FROM vocabulary_learning WHERE student_id=:sid AND next_review_at <= now`。
- `new_learned_today`：`SELECT count(*) ... WHERE student_id=:sid AND func.date(created_at) == today_utc`。用 `func.date(VocabularyLearning.created_at) == _today()`（`_today()` 复用 checkin_service 口径：`datetime.now(timezone.utc).date()`）。
- `new_words_remaining`：`SELECT count(*) FROM vocabulary_words WHERE id NOT IN (该生已学 word_id 子查询)`。
- `new_limit`：复用 `vocabulary_service._daily_new_limit(db, student_id=...)`。

**2. `checkin_service.record_checkin` 接入严格校验**（改）

签名改为：
```python
async def record_checkin(db, *, student_id) -> tuple[StudyCheckin | None, dict]:
    progress = await vocabulary_service.compute_today_progress(db, student_id=student_id)
    if not progress["all_done"]:
        return None, progress
    # 达标：写打卡（new_words_count / review_done 由后端实算填充）
    row = await _upsert_checkin(
        db, student_id=student_id,
        new_words_count=progress["new_learned_today"],
        review_done=True,
    )
    return row, progress
```
- 去掉 `new_words_count` / `review_done` 入参（由 progress 实算）。
- 同日幂等保持：内部 `_upsert_checkin` 沿用 D-104 逻辑（今日行存在则更新计数、streak 不变；否则按昨日行推算 streak 后插入）。达标后当天再调用仍返回同一行、`completed=True`，不重复累加。
- 注意：避免 service 间循环 import——`checkin_service` import `vocabulary_service`（`vocabulary_service` 不反向 import `checkin_service`，现状即如此）。

**3. `schemas/vocabulary.py`**（改）
- `CheckinIn`：废弃 `new_words_count` / `review_done` 字段（保留空 body 兼容，或删除；本批直接删除入参，body 可为空）。改为无字段 body（或直接让 endpoint 不收 body）。
- `CheckinResult`：扩展
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

**4. `api/v1/vocabulary.py` `POST /vocabulary/checkin`**（改）
```python
@router.post("/checkin", response_model=BaseResponse[CheckinResult])
async def checkin(db: DbDep, current_user: UserDep):
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
- 不再收 `body: CheckinIn`。
- `GET /vocabulary/checkin/status` 不变。

### 前端

**`pages/vocabulary/index.vue` `finishSession`**（改）
```ts
async function finishSession() {
  phase.value = 'done'
  try {
    const r = await checkin()
    if (r.completed) {
      checkinDone.value = true
      streakDays.value = r.streak_days
    } else {
      checkinDone.value = false
      gapHint.value = buildGapHint(r) // 还差 X 个复习 / Y 个新词
    }
  } catch { /* 不阻塞完成页 */ }
}
```
- `api/vocabulary.ts`：`checkin()` 改为无参（`POST` 空 body）。
- `types/api.ts`：`VocabCheckinResult` 扩展 `completed` + 缺口字段。
- 完成卡：`completed` 真→「已连续打卡 N 天 🔥」；假→「还差 {review_due} 个复习 / {new_target - new_learned_today} 个新词，完成后才能打卡」。

## 数据流

完成会话 → 前端 `checkin()`（空 body）→ API → `record_checkin` → `compute_today_progress`（实算到期复习 + 今日新词）→ 达标则 upsert 打卡行返回 streak / 未达标返回缺口 → 前端按 `completed` 展示打卡或引导。

## 错误处理

- 打卡接口异常不阻塞完成页（前端 try/catch）。
- 未达标不是错误，正常返回 `completed=False`（HTTP 200）。
- 鉴权失败仍 401。

## 测试（TDD）

**service（`tests/services/test_checkin_service.py` 扩展 + `compute_today_progress`）**
1. 复习未清空（有 `next_review_at <= now` 的词）→ `review_done=False`、`all_done=False`，`record_checkin` 返回 `(None, progress)` 不写行。
2. 复习清空 + 今日新词学满 `new_limit`（词库新词充足）→ `all_done=True`，`record_checkin` 写行、streak=1。
3. 复习清空 + 新词没学够（`new_learned_today < new_limit` 且词库仍有未学词）→ `new_done=False`、`all_done=False` 不写行。
4. 复习清空 + 词库未学新词不足 `new_limit`（学完所有可学）→ `new_target` 收缩=已学数 → `new_done=True`、`all_done=True` 写行。
5. 达标后同日再调用 `record_checkin` → 幂等：返回同一行、streak 不变。

**API（`tests/api/test_vocabulary.py` 扩展）**
6. 未完成（复习未清空）→ `POST /checkin` 返回 `completed=False`、缺口字段、DB 无打卡行。
7. 完成 → `POST /checkin` 返回 `completed=True`、`streak_days==1`。

## 影响范围

- `backend/app/services/vocabulary_service.py`（+`compute_today_progress`）
- `backend/app/services/checkin_service.py`（`record_checkin` 接校验、改签名）
- `backend/app/schemas/vocabulary.py`（`CheckinResult` 扩展、`CheckinIn` 废弃入参）
- `backend/app/api/v1/vocabulary.py`（`checkin` endpoint 去 body）
- `frontend/miniprogram/src/api/vocabulary.ts`、`types/api.ts`、`pages/vocabulary/index.vue`
- **零迁移**（`created_at` 已存在）、**无花钱**。

## 兼容性

D-104 刚发布、`checkin` 仅词力通完成页一处调用，直接改接口签名（去 body）风险可控，前端同批更新。

## 不做（后续）

- 亲人可见打卡日历（D-106）
- 补签 / 热力图 / 里程碑徽章（D-107）
- 打卡提醒双通道（D-108）
- "犹豫"作答是否计入完成（当前 hesitant 不升级但已作答 → 已移出到期，计完成）

## 相关

D-104（打卡激励）；需求 §6.4。
