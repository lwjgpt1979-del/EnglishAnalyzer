# 作文 AI 精修 MVP Implementation Plan（D-109）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 学生提交作文 → AI 多维度批改（评分+逐处问题+优化版）→ 对比展示 + 历史，Pro/ProMax 专属。

**Architecture:** 复用 essays 表（零迁移）+ LLM dev-mock 模式（`is_llm_dev_mode`）；essay_service 做会员闸门+批改+落库；前端两页（输入/详情）。

**Tech Stack:** FastAPI + SQLAlchemy 2.x asyncio + Pydantic v2 + PostgreSQL；uni-app Vue3。零迁移、dev-mock 无花钱。

**运行约定：** 后端 python = `/opt/anaconda3/bin/python`，pytest 从 `backend/` 跑、路径 `../tests/...`、`-p no:randomly`。前端 `frontend/miniprogram/` 跑 `npm run build:mp-weixin`。

---

## File Structure

| 文件 | 改动 |
|---|---|
| `backend/app/services/essay_service.py` | 新：polish_essay/_grade/_monthly_count/get/list |
| `backend/app/schemas/essay.py` | 新：EssayCreate/EssayScoreItem/EssayIssueItem/EssayOut/EssayListItem/EssayListOut |
| `backend/app/api/v1/essay.py` | 新：POST/GET/GET endpoints |
| `backend/app/api/v1/router.py` | 注册 essay_router |
| `tests/services/test_essay_service.py` | 新 |
| `tests/api/test_essay.py` | 新 |
| `frontend/miniprogram/src/types/api.ts` | +Essay 类型 |
| `frontend/miniprogram/src/api/essay.ts` | 新 |
| `frontend/miniprogram/src/pages/essay/index.vue`、`detail.vue` | 新 |
| `frontend/miniprogram/src/pages.json` | 注册两页 |
| `frontend/miniprogram/src/pages/index/index.vue` | +作文精修宫格入口 |

---

## Task 1: essay_service（会员闸门 + dev-mock 批改）

**Files:**
- Create: `backend/app/services/essay_service.py`
- Test: `tests/services/test_essay_service.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/services/test_essay_service.py`：
```python
"""作文 AI 精修 service 测试（D-109）。"""
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.core.exceptions import AppError
from app.models.d2_payments import Membership
from app.services import essay_service


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _student(s, tier: str | None) -> uuid.UUID:
    from app.services.auth_service import upsert_user
    u = await upsert_user(s, openid=f"essay_{uuid.uuid4().hex[:8]}")
    await s.flush()
    if tier:
        s.add(Membership(id=uuid.uuid4(), user_id=u.id, tier=tier,
                         started_at=datetime.now(timezone.utc), is_active=True))
        await s.flush()
    return u.id


@pytest.mark.asyncio
async def test_polish_pro_devmock(db_session):
    sid = await _student(db_session, "pro")
    essay = await essay_service.polish_essay(
        db_session, student_id=sid, original_text="I am very good at English.", essay_type="话题作文")
    assert str(essay.status) == "completed"
    assert essay.polished_text
    assert len(essay.dimensions["scores"]) == 4
    assert "total" in essay.dimensions
    assert isinstance(essay.dimensions["issues"], list)


@pytest.mark.asyncio
async def test_polish_free_forbidden(db_session):
    sid = await _student(db_session, None)  # 无会员 = free
    with pytest.raises(AppError):
        await essay_service.polish_essay(db_session, student_id=sid, original_text="hello")


@pytest.mark.asyncio
async def test_pro_monthly_limit(db_session):
    sid = await _student(db_session, "pro")
    for _ in range(3):
        await essay_service.polish_essay(db_session, student_id=sid, original_text="essay text")
    with pytest.raises(AppError):
        await essay_service.polish_essay(db_session, student_id=sid, original_text="essay text 4")


@pytest.mark.asyncio
async def test_promax_unlimited(db_session):
    sid = await _student(db_session, "promax")
    for _ in range(5):
        e = await essay_service.polish_essay(db_session, student_id=sid, original_text="essay text")
    assert str(e.status) == "completed"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_essay_service.py -p no:randomly -q`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 建 essay_service**

创建 `backend/app/services/essay_service.py`：
```python
"""作文 AI 精修 service（D-109）。复用 LLM dev-mock；会员闸门 Pro月3次/ProMax不限。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, time, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d5_learning import Essay
from app.services import membership_service
from app.services.llm_provider import chat_completion, is_llm_dev_mode

_DIMENSIONS = [("内容", 25), ("语言", 25), ("结构", 25), ("词汇", 25)]
_PRO_MONTHLY_LIMIT = 3

_SYSTEM_PROMPT = (
    "你是专业英语作文批改老师。请对学生作文从内容/语言/结构/词汇四个维度各 25 分打分，"
    "逐处指出问题（原文片段、修改建议、类型[语法/表达/词汇]、说明），并给出整体优化版本。"
    "只返回 JSON，键：scores(list of {dimension,score,full})、total(int)、"
    "issues(list of {original,suggestion,type,color,explanation})、polished_text(str)。"
    "颜色规则：语法=red，表达=yellow，词汇=blue。"
)


async def _monthly_count(db: AsyncSession, student_id: uuid.UUID) -> int:
    now = datetime.now(timezone.utc)
    month_start = datetime.combine(now.date().replace(day=1), time.min, tzinfo=timezone.utc)
    return (await db.execute(
        select(func.count()).select_from(Essay).where(
            Essay.student_id == student_id,
            Essay.created_at >= month_start,
        )
    )).scalar_one()


async def _grade(*, original_text: str, essay_type: str | None) -> dict:
    if is_llm_dev_mode():
        return {
            "scores": [{"dimension": d, "score": s - 3, "full": s} for d, s in _DIMENSIONS],
            "total": sum(s - 3 for _, s in _DIMENSIONS),
            "issues": [{
                "original": "very good", "suggestion": "excellent", "type": "词汇",
                "color": "blue", "explanation": "将 'very good' 替换为 'excellent' 更符合书面表达。",
            }],
            "polished_text": original_text + "\n\n[AI 优化版 - dev mock]",
        }
    prompt = f"作文题型：{essay_type or '未指定'}\n作文原文：\n{original_text}"
    try:
        resp = await chat_completion(
            system_prompt=_SYSTEM_PROMPT, user_prompt=prompt, max_tokens=2048)
    except Exception as exc:
        raise AppError(code=502, message=f"AI服务暂时不可用，请稍后重试（{exc}）") from exc
    try:
        return json.loads((resp.choices[0].message.content or "").strip())
    except json.JSONDecodeError as exc:
        raise AppError(code=500, message="AI作文批改返回格式异常") from exc


async def polish_essay(
    db: AsyncSession, *, student_id: uuid.UUID, original_text: str,
    title: str | None = None, essay_type: str | None = None,
    wrong_question_id: uuid.UUID | None = None,
) -> Essay:
    m = await membership_service.get_active_membership(db, user_id=student_id)
    tier = str(m.tier) if m else "free"
    if tier in ("free", "basic"):
        raise AppError(code=403, message="作文精修为 Pro/ProMax 专属功能，请升级会员")
    if tier == "pro" and await _monthly_count(db, student_id) >= _PRO_MONTHLY_LIMIT:
        raise AppError(code=403, message="本月作文精修次数已用完（Pro 每月3次）")
    result = await _grade(original_text=original_text, essay_type=essay_type)
    essay = Essay(
        id=uuid.uuid4(), student_id=student_id, wrong_question_id=wrong_question_id,
        original_text=original_text, polished_text=result["polished_text"],
        dimensions={
            "scores": result["scores"], "total": result["total"],
            "issues": result["issues"], "title": title, "essay_type": essay_type,
        },
        round_count=1, status="completed",
    )
    db.add(essay)
    await db.flush()
    return essay


async def get_essay(db: AsyncSession, *, student_id: uuid.UUID, essay_id: uuid.UUID) -> Essay | None:
    return (await db.execute(
        select(Essay).where(Essay.id == essay_id, Essay.student_id == student_id)
    )).scalar_one_or_none()


async def list_essays(db: AsyncSession, *, student_id: uuid.UUID) -> list[Essay]:
    return list((await db.execute(
        select(Essay).where(Essay.student_id == student_id).order_by(Essay.created_at.desc())
    )).scalars().all())
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_essay_service.py -p no:randomly -q`
Expected: PASS（4 例）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/essay_service.py tests/services/test_essay_service.py
git commit -m "feat(backend): 作文精修 service（会员闸门 + LLM dev-mock 批改）"
```

---

## Task 2: schemas + API + router

**Files:**
- Create: `backend/app/schemas/essay.py`
- Create: `backend/app/api/v1/essay.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `tests/api/test_essay.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/api/test_essay.py`：
```python
"""作文精修 API 测试（D-109）。"""
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch

from app.core.database import _async_session_factory
from app.main import app
from app.models.d2_payments import Membership


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _login_pro(client: AsyncClient, suffix: str) -> dict:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as mock_wx:
        mock_wx.return_value = {"openid": f"essayapi_{suffix}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}
    me = (await client.get("/api/v1/users/me", headers=headers)).json()["data"]
    async with _async_session_factory() as s:
        s.add(Membership(id=uuid.uuid4(), user_id=uuid.UUID(me["id"]), tier="pro",
                         started_at=datetime.now(timezone.utc), is_active=True))
        await s.commit()
    return headers


@pytest.mark.asyncio
async def test_essay_requires_auth(client):
    r = await client.post("/api/v1/essays", json={"original_text": "hi"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_essay_flow(client):
    headers = await _login_pro(client, uuid.uuid4().hex[:6])
    r = await client.post("/api/v1/essays",
                          json={"original_text": "I am very good.", "essay_type": "话题作文"},
                          headers=headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["polished_text"] and len(data["scores"]) == 4 and data["status"] == "completed"
    eid = data["id"]
    lst = (await client.get("/api/v1/essays", headers=headers)).json()["data"]
    assert lst["total"] >= 1 and any(it["id"] == eid for it in lst["items"])
    detail = (await client.get(f"/api/v1/essays/{eid}", headers=headers)).json()["data"]
    assert detail["id"] == eid and len(detail["issues"]) >= 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/api/test_essay.py -p no:randomly -q`
Expected: FAIL（404 路由不存在）

- [ ] **Step 3: 建 schemas**

创建 `backend/app/schemas/essay.py`：
```python
"""作文精修 schemas（D-109）。"""
from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class EssayCreate(BaseModel):
    original_text: str = Field(..., min_length=1)
    title: str | None = None
    essay_type: str | None = None
    wrong_question_id: uuid.UUID | None = None


class EssayScoreItem(BaseModel):
    dimension: str
    score: int
    full: int


class EssayIssueItem(BaseModel):
    original: str
    suggestion: str
    type: str
    color: str
    explanation: str


class EssayOut(BaseModel):
    id: uuid.UUID
    original_text: str
    polished_text: str | None = None
    scores: list[EssayScoreItem]
    total: int
    issues: list[EssayIssueItem]
    title: str | None = None
    essay_type: str | None = None
    round_count: int
    status: str
    created_at: str


class EssayListItem(BaseModel):
    id: uuid.UUID
    title: str | None = None
    essay_type: str | None = None
    total: int
    status: str
    created_at: str


class EssayListOut(BaseModel):
    total: int
    items: list[EssayListItem]
```

- [ ] **Step 4: 建 API**

创建 `backend/app/api/v1/essay.py`：
```python
"""作文精修 API（D-109）。"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.exceptions import AppError
from app.core.security import get_current_user
from app.models.d1_users import User
from app.models.d5_learning import Essay
from app.schemas.base import BaseResponse, make_ok
from app.schemas.essay import (
    EssayCreate, EssayListItem, EssayListOut, EssayOut,
)
from app.services import essay_service

router = APIRouter(prefix="/essays", tags=["essays"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


def _to_out(e: Essay) -> EssayOut:
    dim = e.dimensions or {}
    return EssayOut(
        id=e.id, original_text=e.original_text, polished_text=e.polished_text,
        scores=dim.get("scores", []), total=dim.get("total", 0),
        issues=dim.get("issues", []), title=dim.get("title"),
        essay_type=dim.get("essay_type"), round_count=e.round_count,
        status=str(e.status), created_at=e.created_at.isoformat(),
    )


@router.post("", response_model=BaseResponse[EssayOut])
async def create_essay(body: EssayCreate, db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    essay = await essay_service.polish_essay(
        db, student_id=current_user.id, original_text=body.original_text,
        title=body.title, essay_type=body.essay_type, wrong_question_id=body.wrong_question_id)
    await db.commit()
    return make_ok(_to_out(essay))


@router.get("", response_model=BaseResponse[EssayListOut])
async def list_my_essays(db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    rows = await essay_service.list_essays(db, student_id=current_user.id)
    items = [
        EssayListItem(
            id=e.id, title=(e.dimensions or {}).get("title"),
            essay_type=(e.dimensions or {}).get("essay_type"),
            total=(e.dimensions or {}).get("total", 0),
            status=str(e.status), created_at=e.created_at.isoformat(),
        )
        for e in rows
    ]
    return make_ok(EssayListOut(total=len(items), items=items))


@router.get("/{essay_id}", response_model=BaseResponse[EssayOut])
async def get_my_essay(essay_id: uuid.UUID, db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    e = await essay_service.get_essay(db, student_id=current_user.id, essay_id=essay_id)
    if e is None:
        raise AppError(code=404, message="作文记录不存在")
    return make_ok(_to_out(e))
```

> 注意路由前缀：router `prefix="/essays"`，故 POST 用 `@router.post("")`、列表 `@router.get("")`、详情 `@router.get("/{essay_id}")`。完整路径即 `/api/v1/essays`。

- [ ] **Step 5: 注册 router**

编辑 `backend/app/api/v1/router.py`：
1. import 区加 `from app.api.v1.essay import router as essay_router`。
2. 在其它 `v1_router.include_router(...)` 处追加 `v1_router.include_router(essay_router)`。

- [ ] **Step 6: 跑测试确认通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/api/test_essay.py -p no:randomly -q`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add backend/app/schemas/essay.py backend/app/api/v1/essay.py backend/app/api/v1/router.py tests/api/test_essay.py
git commit -m "feat(backend): 作文精修 API（提交/列表/详情）+ router 注册"
```

---

## Task 3: 前端作文精修两页 + 入口

**Files:**
- Modify: `frontend/miniprogram/src/types/api.ts`
- Create: `frontend/miniprogram/src/api/essay.ts`
- Create: `frontend/miniprogram/src/pages/essay/index.vue`, `detail.vue`
- Modify: `frontend/miniprogram/src/pages.json`, `frontend/miniprogram/src/pages/index/index.vue`

- [ ] **Step 1: 加类型**

`types/api.ts` 末尾追加：
```typescript
// 作文精修（D-109）
export interface EssayScoreItem { dimension: string; score: number; full: number }
export interface EssayIssueItem { original: string; suggestion: string; type: string; color: string; explanation: string }
export interface EssayDetail {
  id: string
  original_text: string
  polished_text: string | null
  scores: EssayScoreItem[]
  total: number
  issues: EssayIssueItem[]
  title: string | null
  essay_type: string | null
  round_count: number
  status: string
  created_at: string
}
export interface EssayListItem {
  id: string; title: string | null; essay_type: string | null
  total: number; status: string; created_at: string
}
export interface EssayList { total: number; items: EssayListItem[] }
```

- [ ] **Step 2: 加 api**

创建 `frontend/miniprogram/src/api/essay.ts`：
```typescript
import { request } from '@/utils/request'
import type { EssayDetail, EssayList } from '@/types/api'

export function createEssay(payload: { original_text: string; title?: string; essay_type?: string }): Promise<EssayDetail> {
  return request<EssayDetail>('/api/v1/essays', { method: 'POST', data: payload })
}
export function getEssays(): Promise<EssayList> {
  return request<EssayList>('/api/v1/essays', { method: 'GET' })
}
export function getEssay(id: string): Promise<EssayDetail> {
  return request<EssayDetail>(`/api/v1/essays/${id}`, { method: 'GET' })
}
```

- [ ] **Step 3: 建 index.vue**

创建 `frontend/miniprogram/src/pages/essay/index.vue`：
```vue
<template>
  <view class="page">
    <view class="card">
      <view class="card-title">作文 AI 精修</view>
      <textarea v-model="text" class="essay-input" placeholder="粘贴或输入你的英文作文…" :maxlength="-1" />
      <input v-model="essayType" class="type-input" placeholder="作文题型（选填，如 话题作文）" />
      <button class="btn-primary" :disabled="loading || !text.trim()" @tap="onSubmit">
        {{ loading ? 'AI 批改中…' : 'AI 精修' }}
      </button>
      <view class="tip">Pro/ProMax 专属 · Pro 每月 3 次</view>
    </view>

    <view class="card">
      <view class="card-title">历史精修</view>
      <view v-if="!list.length" class="empty">还没有精修记录</view>
      <view v-for="it in list" :key="it.id" class="row" @tap="goDetail(it.id)">
        <text class="row-title">{{ it.title || it.essay_type || '作文' }}</text>
        <text class="row-score">{{ it.total }} 分</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { createEssay, getEssays } from '@/api/essay'
import type { EssayListItem } from '@/types/api'

const text = ref('')
const essayType = ref('')
const loading = ref(false)
const list = ref<EssayListItem[]>([])

async function loadList() {
  try { list.value = (await getEssays()).items } catch { /* 忽略 */ }
}
onShow(loadList)

async function onSubmit() {
  loading.value = true
  try {
    const r = await createEssay({ original_text: text.value, essay_type: essayType.value || undefined })
    text.value = ''
    uni.navigateTo({ url: `/pages/essay/detail?id=${r.id}` })
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'none' })
  } finally {
    loading.value = false
  }
}
function goDetail(id: string) { uni.navigateTo({ url: `/pages/essay/detail?id=${id}` }) }
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 20rpx; }
.card-title { font-size: var(--fs-h2); font-weight: 700; color: var(--c-ink); margin-bottom: 16rpx; }
.essay-input { width: 100%; height: 320rpx; font-size: 28rpx; color: var(--c-text-body); line-height: 1.6; }
.type-input { width: 100%; height: 72rpx; font-size: 26rpx; border-top: 1rpx solid var(--c-border); margin-top: 12rpx; }
.btn-primary { background: var(--c-primary); color: var(--c-ink); border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; margin-top: 16rpx; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #b9a94e; }
.tip { font-size: 22rpx; color: var(--c-text-hint); margin-top: 12rpx; text-align: center; }
.empty { font-size: 26rpx; color: var(--c-text-hint); padding: 24rpx 0; text-align: center; }
.row { display: flex; justify-content: space-between; padding: 16rpx 0; border-bottom: 1rpx solid var(--c-border); }
.row-title { font-size: 28rpx; color: var(--c-text-body); }
.row-score { font-size: 28rpx; font-weight: 700; color: var(--c-gold); }
</style>
```

- [ ] **Step 4: 建 detail.vue**

创建 `frontend/miniprogram/src/pages/essay/detail.vue`：
```vue
<template>
  <view class="page">
    <view v-if="!essay" class="tip">加载中…</view>
    <view v-else>
      <view class="card">
        <view class="card-title">总分 {{ essay.total }}</view>
        <view v-for="s in essay.scores" :key="s.dimension" class="score-row">
          <text class="dim">{{ s.dimension }}</text>
          <text class="sc">{{ s.score }} / {{ s.full }}</text>
        </view>
      </view>

      <view class="card">
        <view class="card-title">原文</view>
        <text class="para">{{ essay.original_text }}</text>
      </view>

      <view class="card">
        <view class="card-title">AI 优化版</view>
        <text class="para">{{ essay.polished_text }}</text>
      </view>

      <view v-if="essay.issues.length" class="card">
        <view class="card-title">逐处建议</view>
        <view v-for="(it, i) in essay.issues" :key="i" class="issue" :class="it.color">
          <text class="issue-head">{{ it.original }} → {{ it.suggestion }}（{{ it.type }}）</text>
          <text class="issue-exp">{{ it.explanation }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getEssay } from '@/api/essay'
import type { EssayDetail } from '@/types/api'

const essay = ref<EssayDetail | null>(null)

onLoad((q) => {
  const id = (q as { id?: string })?.id
  if (id) getEssay(id).then((e) => { essay.value = e }).catch((e) => {
    uni.showToast({ title: (e as Error).message, icon: 'none' })
  })
})
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.tip { text-align: center; padding: 120rpx 0; color: var(--c-text-hint); }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 20rpx; }
.card-title { font-size: var(--fs-h2); font-weight: 700; color: var(--c-ink); margin-bottom: 16rpx; }
.score-row { display: flex; justify-content: space-between; padding: 8rpx 0; font-size: 28rpx; color: var(--c-text-body); }
.sc { font-weight: 700; color: var(--c-gold); }
.para { font-size: 28rpx; color: var(--c-text-body); line-height: 1.7; white-space: pre-wrap; }
.issue { padding: 12rpx; border-radius: 12rpx; margin-bottom: 12rpx; background: var(--c-bg-page); border-left: 6rpx solid var(--c-border); }
.issue.red { border-left-color: #e54d42; }
.issue.yellow { border-left-color: #f0ad4e; }
.issue.blue { border-left-color: #3b82f6; }
.issue-head { display: block; font-size: 26rpx; font-weight: 700; color: var(--c-ink); }
.issue-exp { display: block; font-size: 24rpx; color: var(--c-text-second); margin-top: 6rpx; line-height: 1.6; }
</style>
```

- [ ] **Step 5: 注册 pages.json**

在 `frontend/miniprogram/src/pages.json` 的 `pages` 数组中追加两项（紧随其它二级页风格）：
```json
    { "path": "pages/essay/index", "style": { "navigationBarTitleText": "作文精修" } },
    { "path": "pages/essay/detail", "style": { "navigationBarTitleText": "精修详情" } }
```

- [ ] **Step 6: 首页入口**

编辑 `frontend/miniprogram/src/pages/index/index.vue`，在词力通宫格之后、个人中心之前插入：
```html
      <view
        class="quick-card"
        @tap="() => uni.navigateTo({ url: '/pages/essay/index' })"
      >
        <text class="quick-icon">✍️</text>
        <text class="quick-label">作文精修</text>
      </view>
```

- [ ] **Step 7: 构建验证**

Run: `cd frontend/miniprogram && npm run build:mp-weixin`
Expected: `Build complete.`

- [ ] **Step 8: 提交**

```bash
git add frontend/miniprogram/src/types/api.ts frontend/miniprogram/src/api/essay.ts frontend/miniprogram/src/pages/essay/ frontend/miniprogram/src/pages.json frontend/miniprogram/src/pages/index/index.vue
git commit -m "feat(frontend): 作文精修 输入页 + 详情页 + 首页入口"
```

---

## Task 4: 全量回归 + 归档 D-109

**Files:**
- Modify: `docs/决策归档.md`

- [ ] **Step 1: 后端全量回归**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests -p no:randomly -q`
Expected: PASS（约 412 passed，净增 6 例。已知 flaky `test_get_wrong_question_api` 若失败，隔离重跑确认通过）

- [ ] **Step 2: 前端构建确认**

Run: `cd frontend/miniprogram && npm run build:mp-weixin`
Expected: `Build complete.`

- [ ] **Step 3: 归档 D-109**

在 `docs/决策归档.md` 顶部（`## D-108` 之前）插入 D-109 条目：日期、背景、结论（essay_service 会员闸门 Pro月3次/ProMax不限 + LLM dev-mock 批改 / schemas / API 提交列表详情 / 前端两页+入口）、测试（后端全量 passed + 前端 build）、影响范围、未做（模板范文/多轮迭代/维度后台可配/真实LLM预算/老师出卷）、相关（Module 5A、ai_service dev-mock、membership_service）。

- [ ] **Step 4: 提交**

```bash
git add docs/决策归档.md
git commit -m "docs: 归档 D-109 作文 AI 精修 MVP"
```

- [ ] **Step 5: 询问用户是否 push**

报告 commit 列表 + 测试/构建结果，征求明确同意后 `git push`。

---

## Self-Review

**1. Spec 覆盖：**
- 会员闸门（free/basic 403、Pro 月3次、ProMax 不限）→ Task 1 polish_essay ✓
- LLM dev-mock 批改（维度评分+issues+polished）→ Task 1 _grade ✓
- schemas + API（提交/列表/详情）+ router → Task 2 ✓
- 前端两页 + 入口 + pages.json → Task 3 ✓
- 零迁移、dev-mock 无花钱 → 全程 ✓

**2. 占位符扫描：** 无 TBD/TODO；每步含完整代码与命令。

**3. 类型一致：** `polish_essay` 写 `dimensions={scores,total,issues,title,essay_type}` 与 `_to_out`/`EssayListItem` 读取键一致；`EssayOut` 字段与前端 `EssayDetail` 对齐；router prefix `/essays` + `@router.post("")` 得 `/api/v1/essays`；tier 值 free/basic/pro/promax 与 membership_tier_enum 一致；`Membership(user_id,tier,started_at,is_active)` 与模型字段一致（order_id nullable 省略）。
