# 词力通错词本联动 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现。Steps 用 checkbox (`- [ ]`) 跟踪。

**Goal:** 词力通内答错自动入错词本 + 熟练度重置 + 错词优先复习 + 掌握自动移出 + 错词本列表（含前端页）。

**Architecture:** 复用 `vocabulary_learning`（迁移 0017 加 `is_wrong`/`wrong_count`）。改造 `vocabulary_service.submit_answer`（答错置错词、答对升 mastered 移出）与 `get_daily_task`（错词优先复习排序）；新增 `list_wrong_words` + `GET /vocabulary/wrong-words`；前端加错词本入口 + 列表页。MVP 只做"词力通答错"一个来源；试卷/老师来源、学情报告联动留后续。零花钱。

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic；uni-app Vue3。

参考 spec：`docs/superpowers/specs/2026-06-03-vocab-wrong-book-design.md`。

---

### Task 1: DB 字段 + 迁移 0017

**Files:**
- Modify: `backend/app/models/d5_learning.py`（VocabularyLearning 加 2 字段）
- Create: `backend/alembic/versions/0017_vocab_wrong_book.py`
- Test: `tests/models/test_model_structure.py`

- [ ] **Step 1: 写失败测试**

```python
def test_vocabulary_learning_has_wrong_book_fields():
    from app.models.d5_learning import VocabularyLearning
    cols = set(VocabularyLearning.__table__.columns.keys())
    assert "is_wrong" in cols
    assert "wrong_count" in cols
```

- [ ] **Step 2: 跑测试确认失败** `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/models/test_model_structure.py -k wrong_book -v` → FAIL。

- [ ] **Step 3: 加模型字段**（`d5_learning.py` 的 `VocabularyLearning` 类内，`level` 字段附近）

```python
    is_wrong = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))
    wrong_count = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
```

- [ ] **Step 4: 写迁移 0017**

```python
"""vocab wrong book: is_wrong / wrong_count on vocabulary_learning (词力通错词本)

Revision ID: 0017
Revises: 0016
Create Date: 2026-06-03
"""
import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vocabulary_learning", sa.Column(
        "is_wrong", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("vocabulary_learning", sa.Column(
        "wrong_count", sa.Integer(), nullable=False, server_default=sa.text("0")))


def downgrade() -> None:
    op.drop_column("vocabulary_learning", "wrong_count")
    op.drop_column("vocabulary_learning", "is_wrong")
```

- [ ] **Step 5: 跑迁移 + 测试**

Run: `cd backend && set -a && . ./.env && set +a && /opt/anaconda3/bin/python -m alembic upgrade head`
Run: `/opt/anaconda3/bin/python -m pytest ../tests/models/test_model_structure.py -k wrong_book -v` → PASS。

- [ ] **Step 6: Commit** `feat(backend): vocabulary_learning 加 is_wrong/wrong_count + 迁移 0017`

### Task 2: submit_answer 错词逻辑 + get_daily_task 错词优先 + list_wrong_words

**Files:**
- Modify: `backend/app/services/vocabulary_service.py`
- Test: `tests/services/test_vocabulary_service.py`

**改造点：**

1. `submit_answer`：在按 SM-2 写回 reps/interval/level 后，加错词本逻辑：

```python
    # 错词本联动（D-103）
    new_level = _level_for(reps)
    if not correct:
        lr.is_wrong = True
        lr.wrong_count = (lr.wrong_count or 0) + 1
    elif new_level == "mastered":
        lr.is_wrong = False
```

> 新建行分支（lr is None 首学）：新建 VocabularyLearning 时，若 `correct=False` 则 `is_wrong=True, wrong_count=1`，否则默认 `is_wrong=False, wrong_count=0`。在构造 VocabularyLearning(...) 时按 correct 传入这两个字段。

2. `get_daily_task` 复习词排序：`.order_by(VocabularyLearning.is_wrong.desc(), VocabularyLearning.wrong_count.desc(), VocabularyLearning.next_review_at)`（原为 `next_review_at`）。

3. 新增 `list_wrong_words`：

```python
async def list_wrong_words(
    db: AsyncSession, *, student_id: uuid.UUID, skip: int = 0, limit: int = 50,
) -> tuple[list[tuple[VocabularyLearning, VocabularyWord]], int]:
    base = (
        select(VocabularyLearning, VocabularyWord)
        .join(VocabularyWord, VocabularyWord.id == VocabularyLearning.word_id)
        .where(VocabularyLearning.student_id == student_id, VocabularyLearning.is_wrong.is_(True))
    )
    total = (await db.execute(
        select(func.count()).select_from(
            select(VocabularyLearning.id).where(
                VocabularyLearning.student_id == student_id, VocabularyLearning.is_wrong.is_(True)
            ).subquery()
        )
    )).scalar_one()
    rows = (await db.execute(
        base.order_by(VocabularyLearning.wrong_count.desc()).offset(skip).limit(limit)
    )).all()
    return list(rows), total
```

- [ ] **Step 1: 写失败测试**（`test_vocabulary_service.py` 末尾）

```python
@pytest.mark.asyncio
async def test_wrong_answer_marks_wrong_book(db_session):
    from app.services import vocabulary_service
    sid = await _make_student(db_session)
    [wid] = await _seed_words(db_session, 1)
    await vocabulary_service.submit_answer(db_session, student_id=sid, word_id=wid, correct=False)
    from sqlalchemy import select as _sel
    from app.models.d5_learning import VocabularyLearning
    lr = (await db_session.execute(_sel(VocabularyLearning).where(
        VocabularyLearning.student_id==sid, VocabularyLearning.word_id==wid))).scalar_one()
    assert lr.is_wrong is True and lr.wrong_count == 1

@pytest.mark.asyncio
async def test_mastered_removes_from_wrong_book(db_session):
    from sqlalchemy import select as _sel
    from app.models.d5_learning import VocabularyLearning
    from app.services import vocabulary_service
    sid = await _make_student(db_session)
    [wid] = await _seed_words(db_session, 1)
    await vocabulary_service.submit_answer(db_session, student_id=sid, word_id=wid, correct=False)  # 入错词本
    for _ in range(5):  # 连续答对升到 mastered
        await vocabulary_service.submit_answer(db_session, student_id=sid, word_id=wid, correct=True)
    lr = (await db_session.execute(_sel(VocabularyLearning).where(
        VocabularyLearning.student_id==sid, VocabularyLearning.word_id==wid))).scalar_one()
    assert lr.level == "mastered" and lr.is_wrong is False

@pytest.mark.asyncio
async def test_list_wrong_words(db_session):
    from app.services import vocabulary_service
    sid = await _make_student(db_session)
    ids = await _seed_words(db_session, 3)
    await vocabulary_service.submit_answer(db_session, student_id=sid, word_id=ids[0], correct=False)
    await vocabulary_service.submit_answer(db_session, student_id=sid, word_id=ids[1], correct=False)
    await vocabulary_service.submit_answer(db_session, student_id=sid, word_id=ids[1], correct=False)  # ids[1] 错 2 次
    await db_session.flush()
    rows, total = await vocabulary_service.list_wrong_words(db_session, student_id=sid)
    assert total == 2
    # wrong_count 降序：ids[1]（2 次）在前
    assert rows[0][1].id == ids[1]
```

- [ ] **Step 2: 跑测试确认失败**
- [ ] **Step 3: 实现 3 处改造**
- [ ] **Step 4: 跑测试确认通过** `/opt/anaconda3/bin/python -m pytest ../tests/services/test_vocabulary_service.py -v`
- [ ] **Step 5: Commit** `feat(backend): 词力通错词本逻辑（答错入本/掌握移出/错词优先复习/列表）`

### Task 3: schema + 错词本 API

**Files:**
- Modify: `backend/app/schemas/vocabulary.py`（WrongWordItem/WrongWordListOut）
- Modify: `backend/app/api/v1/vocabulary.py`（GET /wrong-words）
- Test: `tests/api/test_vocabulary.py`

schema：

```python
class WrongWordItem(BaseModel):
    word_id: uuid.UUID
    word: str
    phonetic: str | None = None
    definitions: list[dict] | dict
    wrong_count: int
    level: str
    image_urls: list[str] | None = None
    en_description: str | None = None
    word_audio_url: str | None = None
    en_desc_audio_url: str | None = None

class WrongWordListOut(BaseModel):
    total: int
    items: list[WrongWordItem]
```

API（`api/v1/vocabulary.py`，复用 DbDep/UserDep + get_rls_db）：

```python
@router.get("/wrong-words", response_model=BaseResponse[WrongWordListOut])
async def wrong_words(db: DbDep, current_user: UserDep, skip: int = 0, limit: int = 50):
    await get_rls_db(db, str(current_user.id))
    rows, total = await vocabulary_service.list_wrong_words(
        db, student_id=current_user.id, skip=skip, limit=limit)
    def _pub(w):
        return str(getattr(w, "media_status", "draft")) == "published"
    items = [WrongWordItem(
        word_id=w.id, word=w.word, phonetic=w.phonetic, definitions=w.definitions,
        wrong_count=lr.wrong_count, level=str(lr.level),
        image_urls=(w.image_urls if _pub(w) else None),
        en_description=(w.en_description if _pub(w) else None),
        word_audio_url=(w.word_audio_url if _pub(w) else None),
        en_desc_audio_url=(w.en_desc_audio_url if _pub(w) else None),
    ) for lr, w in rows]
    return make_ok(WrongWordListOut(total=total, items=items))
```

> `BaseResponse`/`make_ok` 已在 vocabulary.py 导入；`WrongWordItem`/`WrongWordListOut` 加入 from app.schemas.vocabulary import。

- [ ] **Step 1: 写失败测试**（`test_vocabulary.py`：登录学生 → 直接建 1 词 + submit wrong → GET /wrong-words 200 含该词 wrong_count≥1；未登录 401）。可复用 `_seed_word` + `submitVocabAnswer` 经 API：先 `POST /vocabulary/answer {correct:false}` 再 `GET /wrong-words`。
- [ ] **Step 2: 跑测试确认失败**
- [ ] **Step 3: 实现 schema + 端点**
- [ ] **Step 4: 跑测试确认通过 + 后端全量回归** `/opt/anaconda3/bin/python -m pytest ../tests -q -p no:randomly`
- [ ] **Step 5: Commit** `feat(backend): 错词本 API（GET /vocabulary/wrong-words）`

### Task 4: 前端错词本入口 + 列表页

**Files:**
- Modify: `frontend/miniprogram/src/api/vocabulary.ts`（getWrongWords）
- Modify: `frontend/miniprogram/src/types/api.ts`（WrongWordItem/WrongWordList）
- Create: `frontend/miniprogram/src/pages/vocabulary/wrong-book.vue`
- Modify: `frontend/miniprogram/src/pages.json`（注册）
- Modify: `frontend/miniprogram/src/pages/vocabulary/index.vue`（完成页加「错词本」入口）

- [ ] **Step 1: api + 类型**

`api/vocabulary.ts`：
```typescript
export function getWrongWords(): Promise<VocabWrongList> {
  return request<VocabWrongList>('/api/v1/vocabulary/wrong-words', { method: 'GET' })
}
```
`types/api.ts`：
```typescript
export interface VocabWrongItem {
  word_id: string; word: string; phonetic?: string | null
  definitions: Array<{ pos?: string; meaning: string }> | Record<string, unknown>
  wrong_count: number; level: string
  image_urls?: string[] | null; en_description?: string | null
  word_audio_url?: string | null; en_desc_audio_url?: string | null
}
export interface VocabWrongList { total: number; items: VocabWrongItem[] }
```

- [ ] **Step 2: 错词本页** `pages/vocabulary/wrong-book.vue`：onMounted 拉 getWrongWords；列表每项展示 单词 + 音标 + 释义 + 「错 N 次」徽标 + 熟练度；空态"还没有错词，继续加油 🎉"。

```html
<template>
  <view class="wb-page">
    <view v-if="loading" class="center-tip">加载中…</view>
    <view v-else-if="!items.length" class="center-tip">还没有错词，继续加油 🎉</view>
    <view v-else>
      <view v-for="it in items" :key="it.word_id" class="wb-item">
        <view class="wb-head">
          <text class="wb-word">{{ it.word }}</text>
          <text class="wb-badge">错 {{ it.wrong_count }} 次</text>
        </view>
        <text v-if="it.phonetic" class="wb-ph">/{{ it.phonetic }}/</text>
        <text class="wb-def">{{ defText(it) }}</text>
        <text class="wb-level">熟练度：{{ it.level }}</text>
      </view>
    </view>
  </view>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getWrongWords } from '@/api/vocabulary'
import { useAuthStore } from '@/stores/auth'
import type { VocabWrongItem } from '@/types/api'
const auth = useAuthStore()
const loading = ref(true)
const items = ref<VocabWrongItem[]>([])
function defText(it: VocabWrongItem): string {
  const d = it.definitions
  return Array.isArray(d) ? d.map((x: any) => `${x.pos ? x.pos + ' ' : ''}${x.meaning}`).join('；') : ''
}
async function load() {
  if (!auth.isLoggedIn()) await auth.login()
  loading.value = true
  try { items.value = (await getWrongWords()).items } finally { loading.value = false }
}
onMounted(load)
</script>
<style scoped>
.wb-page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.center-tip { text-align: center; padding: 160rpx 40rpx; color: var(--c-text-hint); }
.wb-item { background: var(--c-bg-card); border-radius: var(--r-lg); padding: 24rpx; margin-bottom: 16rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,0.04); }
.wb-head { display: flex; justify-content: space-between; align-items: baseline; }
.wb-word { font-size: 36rpx; font-weight: 800; color: var(--c-ink); }
.wb-badge { font-size: 24rpx; color: var(--c-danger); font-weight: 600; }
.wb-ph { display: block; font-size: 26rpx; color: var(--c-text-second); margin-top: 4rpx; }
.wb-def { display: block; font-size: 28rpx; color: var(--c-text-body); margin-top: 10rpx; }
.wb-level { display: block; font-size: 22rpx; color: var(--c-text-hint); margin-top: 8rpx; }
</style>
```

- [ ] **Step 3: 注册路由** `pages.json` 加 `{ "path": "pages/vocabulary/wrong-book", "style": { "navigationBarTitleText": "错词本" } }`。

- [ ] **Step 4: 入口** `pages/vocabulary/index.vue` 完成页（phase==='done' 卡）「再来一组」按钮旁加：
```html
<button class="btn-secondary" @tap="() => uni.navigateTo({ url: '/pages/vocabulary/wrong-book' })">错词本</button>
```
（若无 .btn-secondary 样式则复用 .btn-primary 或加一个浅色样式）

- [ ] **Step 5: 构建验证** `cd frontend/miniprogram && npm run build:mp-weixin` → DONE。

- [ ] **Step 6: Commit** `feat(frontend): 词力通错词本列表页 + 入口`

### Task 5: 集成验证 + 归档 D-103

- [ ] **Step 1: 后端全量** `cd backend && /opt/anaconda3/bin/python -m pytest ../tests -q -p no:randomly` 全绿（368 + 本次新增）。
- [ ] **Step 2: 前端 build** 通过。
- [ ] **Step 3: 归档 D-103**（docs/决策归档.md 顶部）：错词本字段 + submit_answer 答错入本/掌握移出 + 错词优先复习 + list/API + 前端错词本页；明确只做"词力通答错"来源、试卷/老师来源 & 学情报告联动留后续；迁移 0017。
- [ ] **Step 4: Commit +（征得同意后）push**

---

## 备注
- **移出判定**用 `level == "mastered"`（与现有 `_level_for` 一致，reps≥4），不硬编码阈值。
- **向后兼容**：存量 learning 行 is_wrong=false/wrong_count=0，不影响 D-100/101/102 流程。
- **错词优先复习**只改排序，不改"到期才复习"口径（next_review_at <= now 仍是过滤条件）。
