# V2 M4b：整卷上传全链路打通 实施计划

> **For agentic workers:** Use `superpowers:test-driven-development` for all backend tasks.

**Goal:** 打通 M4 整卷上传的入口、错题本、诊断三条链路。

**Design Ref:** `docs/superpowers/specs/2026-06-07-v2-m4b-paper-upload-integration.md`

---

## 执行顺序

```
Task 1（wrong_question service paper source）
Task 2（diagnosis paper integration）← 依赖 Task 1
Task 3（前端首页双入口）← 独立
Task 4（前端错题本整卷 tab）← 依赖 Task 1
Task 5（归档 + 验证）← 依赖全部
```

---

## Task 1：后端 — wrong_question_service paper source（TDD）

**Files:**
- Create: `tests/services/test_wrong_question_paper_source.py`
- Modify: `backend/app/services/wrong_question_service.py`

### Step 1: 了解现有 service 结构

```bash
grep -n "def list_wrong_questions\|source\|WrongQuestion" \
  backend/app/services/wrong_question_service.py | head -20
```

### Step 2: 写测试（RED）

新建 `tests/services/test_wrong_question_paper_source.py`：

```python
"""wrong_question_service paper source TDD 测试。"""
from __future__ import annotations
import uuid
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import _async_session_factory
from app.models.d13_v2_user_papers import UserUploadedPaper, UserPaperQuestion


@pytest_asyncio.fixture
async def db():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


@pytest_asyncio.fixture
async def student_id():
    return uuid.uuid4()


@pytest_asyncio.fixture
async def seed_paper_questions(db, student_id):
    """植入 1 个整卷，3 道题：2 道错（is_wrong=True），1 道对。"""
    paper = UserUploadedPaper(
        id=uuid.uuid4(),
        student_id=student_id,
        source_image_urls=["https://example.com/p1.jpg"],
        ocr_status="completed",
    )
    db.add(paper)
    wrong1 = UserPaperQuestion(
        id=uuid.uuid4(), user_paper_id=paper.id, stem="题目A", is_wrong=True, question_type="单选",
    )
    wrong2 = UserPaperQuestion(
        id=uuid.uuid4(), user_paper_id=paper.id, stem="题目B", is_wrong=True, question_type="填空",
    )
    correct1 = UserPaperQuestion(
        id=uuid.uuid4(), user_paper_id=paper.id, stem="题目C", is_wrong=False, question_type="单选",
    )
    db.add_all([wrong1, wrong2, correct1])
    await db.flush()
    return {"paper": paper, "wrong1": wrong1, "wrong2": wrong2, "correct1": correct1}


@pytest.mark.asyncio
async def test_list_paper_source_returns_only_wrong(db, student_id, seed_paper_questions):
    """source='paper' 只返回 is_wrong=True 的题，不含答对的。"""
    from app.services.wrong_question_service import list_wrong_questions
    items = await list_wrong_questions(db, student_id=student_id, source="paper", skip=0, limit=20)
    assert len(items) == 2
    texts = [i.question_text for i in items]
    assert "题目A" in texts
    assert "题目B" in texts
    assert "题目C" not in texts


@pytest.mark.asyncio
async def test_list_paper_source_is_mastered_false(db, student_id, seed_paper_questions):
    """整卷错题适配体 is_mastered 始终为 False。"""
    from app.services.wrong_question_service import list_wrong_questions
    items = await list_wrong_questions(db, student_id=student_id, source="paper", skip=0, limit=20)
    for item in items:
        assert item.is_mastered is False


@pytest.mark.asyncio
async def test_list_paper_source_has_source_label(db, student_id, seed_paper_questions):
    """整卷错题适配体 source_label='整卷'。"""
    from app.services.wrong_question_service import list_wrong_questions
    items = await list_wrong_questions(db, student_id=student_id, source="paper", skip=0, limit=20)
    for item in items:
        assert getattr(item, "source_label", None) == "整卷"


@pytest.mark.asyncio
async def test_list_all_source_merges_v1_and_paper(db, student_id, seed_paper_questions):
    """source='all' 合并 V1 + paper 结果（paper 部分有 2 道错题）。"""
    from app.services.wrong_question_service import list_wrong_questions
    items = await list_wrong_questions(db, student_id=student_id, source="all", skip=0, limit=50)
    # 至少包含整卷的 2 道错题
    paper_items = [i for i in items if getattr(i, "source_label", None) == "整卷"]
    assert len(paper_items) == 2


@pytest.mark.asyncio
async def test_list_upload_source_unchanged(db, student_id, seed_paper_questions):
    """source='upload'（V1）不受影响，返回空（本 fixture 未插 V1 wrong_questions）。"""
    from app.services.wrong_question_service import list_wrong_questions
    items = await list_wrong_questions(db, student_id=student_id, source="upload", skip=0, limit=20)
    assert all(getattr(i, "source_label", "上传") != "整卷" for i in items)
```

### Step 3: 确认 RED

```bash
cd backend
python3 -c "
from app.services import wrong_question_service
import inspect
sig = inspect.signature(wrong_question_service.list_wrong_questions)
print('params:', list(sig.parameters.keys()))
# 预期：source 参数不存在 → AttributeError 或 缺少参数
"
```

### Step 4: 查看现有 service 实现

```bash
grep -n "def list_wrong_questions\|skip\|limit\|source\|WrongQuestion" \
  backend/app/services/wrong_question_service.py | head -30
```

### Step 5: 实现 paper source 支持

在 `wrong_question_service.py` 中：

**新增 adapter dataclass**（在 import 区域后）：
```python
from dataclasses import dataclass, field

@dataclass
class WrongQuestionAdapted:
    """统一视图：适配 UserPaperQuestion → WrongQuestionOut 接口。"""
    id: uuid.UUID
    question_text: str | None
    question_type: str | None
    is_mastered: bool
    source_label: str
    source_image_url: str | None = None
    difficulty: int | None = None
    created_at: datetime | None = None
```

**修改 `list_wrong_questions`**，增加 `source` 参数：
```python
async def list_wrong_questions(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    source: str = "all",   # "all" | "upload" | "assignment" | "paper"
    skip: int = 0,
    limit: int = 20,
) -> list:
    """返回错题列表。source='paper' 查整卷错题；其余走 V1 WrongQuestion 表。"""
    if source == "paper":
        return await _list_paper_wrongs(db, student_id=student_id, skip=skip, limit=limit)
    if source == "all":
        v1 = await _list_v1_wrongs(db, student_id=student_id, source=None, skip=0, limit=500)
        paper = await _list_paper_wrongs(db, student_id=student_id, skip=0, limit=500)
        merged = v1 + paper
        return merged[skip: skip + limit]
    return await _list_v1_wrongs(db, student_id=student_id, source=source, skip=skip, limit=limit)
```

**新增 helper**：
```python
async def _list_paper_wrongs(db, *, student_id, skip=0, limit=20):
    from app.models.d13_v2_user_papers import UserPaperQuestion, UserUploadedPaper
    rows = (await db.execute(
        select(UserPaperQuestion)
        .join(UserUploadedPaper, UserUploadedPaper.id == UserPaperQuestion.user_paper_id)
        .where(
            UserUploadedPaper.student_id == student_id,
            UserPaperQuestion.is_wrong == True,
        )
        .order_by(UserPaperQuestion.id)
        .offset(skip).limit(limit)
    )).scalars().all()
    return [
        WrongQuestionAdapted(
            id=r.id,
            question_text=r.stem,
            question_type=r.question_type,
            is_mastered=False,
            source_label="整卷",
        )
        for r in rows
    ]
```

**重构原有逻辑**为 `_list_v1_wrongs(db, *, student_id, source, skip, limit)`（把现有 if/where 逻辑提取进去）。

### Step 6: 确认 GREEN

```bash
python3 -c "
from app.services.wrong_question_service import list_wrong_questions, WrongQuestionAdapted
import inspect
sig = inspect.signature(list_wrong_questions)
assert 'source' in sig.parameters
print('✅ list_wrong_questions 有 source 参数')
print('✅ WrongQuestionAdapted 定义存在')
"
```

### Step 7: Commit

```bash
git add backend/app/services/wrong_question_service.py \
        tests/services/test_wrong_question_paper_source.py
git commit -m "feat(v2-m4b): wrong_question_service 支持 source=paper（整卷错题）TDD"
```

---

## Task 2：后端 — 诊断联动整卷错题 KP（TDD）

**Files:**
- Create: `tests/services/test_diagnosis_paper_integration.py`
- Modify: `backend/app/services/diagnosis_service.py`

### Step 1: 写测试（RED）

新建 `tests/services/test_diagnosis_paper_integration.py`：

```python
"""诊断报告整卷错题 KP 联动 TDD 测试。"""
from __future__ import annotations
import uuid
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import _async_session_factory
from app.models.d13_v2_user_papers import (
    UserUploadedPaper, UserPaperQuestion, UserPaperQuestionKnowledgePoint
)
from app.models.d4_knowledge import KnowledgePoint


@pytest_asyncio.fixture
async def db():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


@pytest_asyncio.fixture
async def student_id():
    return uuid.uuid4()


@pytest_asyncio.fixture
async def seed_paper_kp(db, student_id):
    """整卷错题 + KP 关联。"""
    kp = KnowledgePoint(id=uuid.uuid4(), name="被动语态", category="grammar")
    db.add(kp)
    paper = UserUploadedPaper(
        id=uuid.uuid4(), student_id=student_id,
        source_image_urls=["https://x.com/p.jpg"], ocr_status="completed",
    )
    db.add(paper)
    q = UserPaperQuestion(
        id=uuid.uuid4(), user_paper_id=paper.id, stem="X", is_wrong=True, question_type="单选",
    )
    db.add(q)
    await db.flush()
    link = UserPaperQuestionKnowledgePoint(
        user_paper_question_id=q.id, knowledge_point_id=kp.id
    )
    db.add(link)
    await db.flush()
    return {"kp": kp, "question": q}


@pytest.mark.asyncio
async def test_diagnosis_includes_paper_kp(db, student_id, seed_paper_kp):
    """整卷错题的 KP 出现在诊断 kp_dimension，accuracy=0（全错）。"""
    from app.services.diagnosis_service import _aggregate_structured_dimensions
    kp_dim, _ = await _aggregate_structured_dimensions(db, student_id=student_id)
    kp_ids = [str(item.knowledge_point_id) for item in kp_dim]
    assert str(seed_paper_kp["kp"].id) in kp_ids

    item = next(i for i in kp_dim if i.knowledge_point_id == seed_paper_kp["kp"].id)
    assert item.accuracy == 0.0
    assert item.attempts >= 1


@pytest.mark.asyncio
async def test_diagnosis_no_paper_kp_without_wrong(db, student_id):
    """没有整卷错题时，kp_dimension 来源为 sim_practice_records（为空列表）。"""
    from app.services.diagnosis_service import _aggregate_structured_dimensions
    kp_dim, _ = await _aggregate_structured_dimensions(db, student_id=student_id)
    assert kp_dim == []
```

### Step 2: 确认 RED（整卷 KP 不在诊断中）

```bash
python3 -c "
from app.services.diagnosis_service import _aggregate_structured_dimensions
print('function exists, not yet paper-aware')
"
```

### Step 3: 修改 diagnosis_service

在 `_aggregate_structured_dimensions` 函数末尾，在 `return kp_dimension, semester_dimension` 之前，增加整卷错题 KP 合并：

```python
    # ── 整卷错题 KP（来自 user_paper_question_knowledge_points）──
    from app.models.d13_v2_user_papers import (
        UserPaperQuestion, UserPaperQuestionKnowledgePoint, UserUploadedPaper
    )
    paper_recs = (await db.execute(
        select(UserPaperQuestionKnowledgePoint.knowledge_point_id)
        .join(UserPaperQuestion, UserPaperQuestion.id ==
              UserPaperQuestionKnowledgePoint.user_paper_question_id)
        .join(UserUploadedPaper, UserUploadedPaper.id == UserPaperQuestion.user_paper_id)
        .where(
            UserUploadedPaper.student_id == student_id,
            UserPaperQuestion.is_wrong == True,
        )
    )).scalars().all()

    for kp_id in paper_recs:
        slot = kp_agg.setdefault(kp_id, [0, 0])
        slot[0] += 1   # attempt
        # is_correct = False（is_wrong=True → 全部错误）

    # 补充 kp_ids（用于 kp_meta 查询，在已有 kp_ids 之后追加新 KP）
    new_kp_ids = [kid for kid in kp_agg if kid not in set(kp_ids)]
    if new_kp_ids:
        extra_meta = {
            kid: (name, str(cat) if cat else None)
            for kid, name, cat in (await db.execute(
                select(KnowledgePoint.id, KnowledgePoint.name, KnowledgePoint.category)
                .where(KnowledgePoint.id.in_(new_kp_ids))
            )).all()
        }
        kp_meta.update(extra_meta)
```

**注意**：上述代码块需插入在 `kp_ids = list(kp_agg.keys())` 之后、`kp_dimension = [...]` 列表推导之前。需要重构一下：先 build kp_agg，再加入 paper，最后查 kp_meta，最后 build kp_dimension。

**完整重构后的函数结构**：
```
1. 查 sim_practice_records → kp_agg
2. 查 paper wrong KPs → merge into kp_agg  ← 新增
3. 查 kp_meta (name, category) for all kp_ids in kp_agg  ← 统一查
4. build kp_dimension list
5. build semester_dimension (同前)
```

### Step 4: 确认 GREEN

```bash
python3 -c "
import ast
with open('backend/app/services/diagnosis_service.py') as f:
    src = f.read()
assert 'UserPaperQuestionKnowledgePoint' in src
assert 'is_wrong == True' in src
print('✅ diagnosis_service 包含整卷错题联动逻辑')
"
```

### Step 5: Commit

```bash
git add backend/app/services/diagnosis_service.py \
        tests/services/test_diagnosis_paper_integration.py
git commit -m "feat(v2-m4b): 诊断报告纳入整卷错题 KP（paper wrong questions 联动）"
```

---

## Task 3：前端 — 首页双入口

**Files:**
- Modify: `frontend/miniprogram/src/pages/index/index.vue`

### Step 1: 修改快捷宫格

将首页 8 格改为：
- `📷 单题上传` → `/pages/upload/index`
- `📄 上传整卷` → `/pages/user-papers/upload`
- 移除"👤 个人中心"（通过底部 TabBar 进入）

```vue
<!-- 新增整卷入口，单题上传保留 -->
<view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/upload/index' })">
  <text class="quick-icon">📷</text>
  <text class="quick-label">单题上传</text>
</view>
<view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/user-papers/upload' })">
  <text class="quick-icon">📄</text>
  <text class="quick-label">上传整卷</text>
</view>
```

去掉"👤 个人中心"快捷卡（底部 TabBar 已有）。

### Step 2: 验证

```bash
grep -c "user-papers/upload\|upload/index" \
  frontend/miniprogram/src/pages/index/index.vue
# 预期：两行，各有一个
```

### Step 3: Commit

```bash
git add frontend/miniprogram/src/pages/index/index.vue
git commit -m "feat(miniprogram): 首页增加'上传整卷'快捷入口，单题/整卷双通道"
```

---

## Task 4：前端 — 错题本增加"整卷"tab

**Files:**
- Modify: `frontend/miniprogram/src/pages/wrong-questions/list.vue`
- Modify: `frontend/miniprogram/src/api/wrongQuestions.ts`

### Step 1: 查看现有 API 函数

```bash
grep -n "listWrongQuestions\|source" \
  frontend/miniprogram/src/api/wrongQuestions.ts | head -10
```

### Step 2: 更新 API 函数

确认 `listWrongQuestions(skip, limit, source)` 已有 source 参数，如没有则添加。

### Step 3: 更新错题本 list.vue

在 `SRC_TABS` 数组增加：
```typescript
{ label: '整卷', value: 'paper' },
```

整个 tabs 变为：
```typescript
const SRC_TABS = [
  { label: '全部', value: '' },
  { label: '上传', value: 'upload' },
  { label: '作业', value: 'assignment' },
  { label: '整卷', value: 'paper' },   // ← 新增
]
```

### Step 4: 验证无破坏

```bash
grep "SRC_TABS\|source" frontend/miniprogram/src/pages/wrong-questions/list.vue | head -10
```

### Step 5: Commit

```bash
git add frontend/miniprogram/src/pages/wrong-questions/list.vue \
        frontend/miniprogram/src/api/wrongQuestions.ts
git commit -m "feat(miniprogram): 错题本增加'整卷'来源 tab"
```

---

## Task 5：归档 + 整体验证

### Step 1: 后端导入链全验证

```bash
cd backend
python3 -c "
from app.services.wrong_question_service import list_wrong_questions, WrongQuestionAdapted
from app.services.diagnosis_service import _aggregate_structured_dimensions
import inspect

sig = inspect.signature(list_wrong_questions)
assert 'source' in sig.parameters

import ast
with open('app/services/diagnosis_service.py') as f:
    src = f.read()
assert 'UserPaperQuestionKnowledgePoint' in src

print('✅ wrong_question_service.list_wrong_questions(source) OK')
print('✅ diagnosis_service 整卷 KP 联动 OK')
"
```

### Step 2: 前端入口验证

```bash
grep -c "user-papers/upload" frontend/miniprogram/src/pages/index/index.vue
grep -c "'paper'" frontend/miniprogram/src/pages/wrong-questions/list.vue
# 预期：两个均 >= 1
```

### Step 3: 提交文档

```bash
git add docs/superpowers/specs/2026-06-07-v2-m4b-paper-upload-integration.md \
        docs/superpowers/plans/2026-06-07-v2-m4b-paper-upload-integration-plan.md
git commit -m "docs: V2 M4b 整卷上传全链路集成设计文档 + 实施计划"
```

### Step 4: 最终日志

```bash
git log --oneline -6
```
