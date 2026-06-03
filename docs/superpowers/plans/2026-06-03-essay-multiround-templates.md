# 作文精修：多轮迭代 + 模板/范文 Implementation Plan（D-110）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ProMax 多轮迭代精修（追踪进步）+ 按题型模板/范文推荐。

**Architecture:** 多轮存 `essays.dimensions["rounds"]`（零迁移，顶层反映最新轮）；模板用 service 常量；复用 D-109 dev-mock 批改。

**Tech Stack:** FastAPI + SQLAlchemy 2.x asyncio + Pydantic v2 + PostgreSQL；uni-app Vue3。零迁移、dev-mock 无花钱。

**运行约定：** 后端 python = `/opt/anaconda3/bin/python`，pytest 从 `backend/` 跑、`../tests/...`、`-p no:randomly`。前端 `frontend/miniprogram/` 跑 `npm run build:mp-weixin`。所有 essay 测试沿用 D-109 的 autouse `monkeypatch essay_service.is_llm_dev_mode=True`（绝不真打付费 LLM）。

---

## File Structure

| 文件 | 改动 |
|---|---|
| `backend/app/services/essay_service.py` | +`repolish_essay`/`_MAX_ROUNDS`/`get_templates`/`_TEMPLATES_BY_TYPE`/`_DEFAULT_TEMPLATE` |
| `backend/app/schemas/essay.py` | +`EssayRoundItem`/`RepolishIn`/`EssayTemplatesOut`；`EssayOut` +`rounds` |
| `backend/app/api/v1/essay.py` | +`POST /{id}/repolish`、`GET /templates`（在 `/{essay_id}` 前）；`_to_out` 组装 rounds |
| `tests/services/test_essay_service.py` | +4 例 |
| `tests/api/test_essay.py` | +2 例 |
| `frontend/miniprogram/src/types/api.ts` | +EssayRoundItem/EssayTemplates；EssayDetail +rounds |
| `frontend/miniprogram/src/api/essay.ts` | +repolishEssay/getEssayTemplates |
| `frontend/miniprogram/src/pages/essay/detail.vue` | 模板卡片 + 多轮趋势 + 再改一版 |

---

## Task 1: service 多轮 + 模板 + schemas

**Files:**
- Modify: `backend/app/services/essay_service.py`、`backend/app/schemas/essay.py`
- Test: `tests/services/test_essay_service.py`

- [ ] **Step 1: 写失败测试**

在 `tests/services/test_essay_service.py` 末尾追加：
```python
# ─── D-110: 多轮迭代 + 模板 ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_repolish_promax(db_session):
    sid = await _student(db_session, "promax")
    e1 = await essay_service.polish_essay(db_session, student_id=sid, original_text="round1 text", essay_type="话题作文")
    e2 = await essay_service.repolish_essay(db_session, student_id=sid, essay_id=e1.id, revised_text="round2 better text")
    assert e2.round_count == 2
    assert len(e2.dimensions["rounds"]) == 2
    assert e2.dimensions["total"] == e2.dimensions["rounds"][-1]["total"]


@pytest.mark.asyncio
async def test_repolish_pro_forbidden(db_session):
    from app.core.exceptions import AppError
    sid = await _student(db_session, "pro")
    e1 = await essay_service.polish_essay(db_session, student_id=sid, original_text="text")
    with pytest.raises(AppError):
        await essay_service.repolish_essay(db_session, student_id=sid, essay_id=e1.id, revised_text="v2")


@pytest.mark.asyncio
async def test_repolish_max_rounds(db_session):
    from app.core.exceptions import AppError
    sid = await _student(db_session, "promax")
    e1 = await essay_service.polish_essay(db_session, student_id=sid, original_text="text", essay_type="话题作文")
    # 直接把 rounds 撑到 5 条
    e1.dimensions = {**e1.dimensions, "rounds": [{"text": "t", "scores": [], "total": 80, "issues": [], "polished_text": "p"} for _ in range(5)]}
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(e1, "dimensions")
    e1.round_count = 5
    await db_session.flush()
    with pytest.raises(AppError):
        await essay_service.repolish_essay(db_session, student_id=sid, essay_id=e1.id, revised_text="v6")


def test_get_templates():
    t = essay_service.get_templates("书信作文")
    assert "Dear" in t["template"] or "称呼" in t["template"]
    assert len(t["samples"]) >= 3
    d = essay_service.get_templates(None)
    assert d["template"] and len(d["samples"]) >= 3
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_essay_service.py -p no:randomly -q`
Expected: FAIL（`repolish_essay`/`get_templates` 不存在）

- [ ] **Step 3: 实现 service**

在 `backend/app/services/essay_service.py` 顶部 import 区加：
```python
from sqlalchemy.orm.attributes import flag_modified
```
在 `_PRO_MONTHLY_LIMIT = 3` 之后加常量：
```python
_MAX_ROUNDS = 5
```
在 `polish_essay` 之后追加 `repolish_essay`：
```python
async def repolish_essay(
    db: AsyncSession, *, student_id: uuid.UUID, essay_id: uuid.UUID, revised_text: str,
) -> Essay:
    essay = await get_essay(db, student_id=student_id, essay_id=essay_id)
    if essay is None:
        raise AppError(code=404, message="作文记录不存在")
    m = await membership_service.get_active_membership(db, user_id=student_id)
    tier = str(m.tier) if m else "free"
    if tier != "promax":
        raise AppError(code=403, message="多轮迭代精修为 ProMax 专属功能")
    dim = dict(essay.dimensions or {})
    rounds = list(dim.get("rounds") or [])
    if not rounds:
        rounds = [{
            "text": essay.original_text,
            "scores": dim.get("scores", []), "total": dim.get("total", 0),
            "issues": dim.get("issues", []), "polished_text": essay.polished_text,
        }]
    if len(rounds) >= _MAX_ROUNDS:
        raise AppError(code=403, message=f"已达最多 {_MAX_ROUNDS} 轮精修上限")
    result = await _grade(original_text=revised_text, essay_type=dim.get("essay_type"))
    rounds.append({
        "text": revised_text, "scores": result["scores"], "total": result["total"],
        "issues": result["issues"], "polished_text": result["polished_text"],
    })
    dim["rounds"] = rounds
    dim["scores"] = result["scores"]
    dim["total"] = result["total"]
    dim["issues"] = result["issues"]
    essay.dimensions = dim
    essay.polished_text = result["polished_text"]
    essay.round_count = len(rounds)
    flag_modified(essay, "dimensions")
    await db.flush()
    return essay
```
在文件末尾追加模板常量 + `get_templates`：
```python
_TEMPLATES_BY_TYPE = {
    "话题作文": {
        "template": "开头：亮明观点（In my opinion, ...）。中间：2-3 个理由 + 例证（Firstly... Secondly... For example...）。结尾：总结升华（In conclusion, ...）。",
        "samples": [
            "Many students think... I believe... Firstly,... Secondly,... In conclusion,...",
            "With the development of technology,... On the one hand,... On the other hand,...",
            "It is often said that... From my perspective,... Therefore,...",
        ],
    },
    "书信作文": {
        "template": "称呼（Dear ...）→ 自我介绍/写信目的 → 主体（分点说明）→ 结尾礼貌用语（Looking forward to your reply）→ 落款（Yours, XXX）。",
        "samples": [
            "Dear Tom, I'm writing to tell you about... Looking forward to your reply. Yours, Li Hua",
            "Dear Sir or Madam, I am writing to apply for... I would appreciate it if... Yours sincerely, ...",
            "Dear friend, How is everything going? I'd like to share... Best wishes, ...",
        ],
    },
    "图片作文": {
        "template": "描述图片内容（The picture shows...）→ 分析现象/原因 → 表达观点或建议（We should...）。",
        "samples": [
            "The picture shows... This reminds us that... We should...",
            "As is shown in the picture,... The reason is that... Therefore,...",
            "Looking at the picture, we can see... It tells us... In my view,...",
        ],
    },
}

_DEFAULT_TEMPLATE = {
    "template": "三段式：开头点题 → 主体分点论述 + 例证 → 结尾总结。多用连接词（Firstly/However/In conclusion），避免中式表达。",
    "samples": [
        "In my opinion,... Firstly,... Secondly,... In conclusion,...",
        "There is no doubt that... For one thing,... For another,... Therefore,...",
        "As far as I am concerned,... On the one hand,... On the other hand,...",
    ],
}


def get_templates(essay_type: str | None) -> dict:
    return _TEMPLATES_BY_TYPE.get(essay_type or "", _DEFAULT_TEMPLATE)
```
在 `backend/app/schemas/essay.py` 追加：
```python
class EssayRoundItem(BaseModel):
    round: int
    total: int


class RepolishIn(BaseModel):
    revised_text: str = Field(..., min_length=1)


class EssayTemplatesOut(BaseModel):
    essay_type: str | None = None
    template: str
    samples: list[str]
```
并给 `EssayOut` 追加字段（在 `created_at` 前/后均可）：
```python
    rounds: list[EssayRoundItem] = []
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_essay_service.py -p no:randomly -q`
Expected: PASS（D-109 4 例 + D-110 4 例）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/essay_service.py backend/app/schemas/essay.py tests/services/test_essay_service.py
git commit -m "feat(backend): 作文多轮迭代 repolish + 模板范文 get_templates"
```

---

## Task 2: API repolish + templates

**Files:**
- Modify: `backend/app/api/v1/essay.py`
- Test: `tests/api/test_essay.py`

- [ ] **Step 1: 写失败测试**

在 `tests/api/test_essay.py` 末尾追加（复用既有 `client`/`_login_pro` + autouse dev-mock；新增 ProMax 登录 helper）：
```python
async def _login_promax(client: AsyncClient, suffix: str) -> dict:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as mock_wx:
        mock_wx.return_value = {"openid": f"essaymax_{suffix}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}
    me = (await client.get("/api/v1/users/me", headers=headers)).json()["data"]
    async with _async_session_factory() as s:
        s.add(Membership(id=uuid.uuid4(), user_id=uuid.UUID(me["id"]), tier="promax",
                         started_at=datetime.now(timezone.utc), is_active=True))
        await s.commit()
    return headers


@pytest.mark.asyncio
async def test_repolish_via_api(client):
    headers = await _login_promax(client, uuid.uuid4().hex[:6])
    r = await client.post("/api/v1/essays",
                          json={"original_text": "round1", "essay_type": "话题作文"}, headers=headers)
    eid = r.json()["data"]["id"]
    r2 = await client.post(f"/api/v1/essays/{eid}/repolish",
                           json={"revised_text": "round2 better"}, headers=headers)
    assert r2.status_code == 200
    data = r2.json()["data"]
    assert data["round_count"] == 2 and len(data["rounds"]) == 2


@pytest.mark.asyncio
async def test_templates_via_api(client):
    headers = await _login_pro(client, uuid.uuid4().hex[:6])
    r = await client.get("/api/v1/essays/templates", params={"essay_type": "话题作文"}, headers=headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["template"] and len(data["samples"]) >= 3
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/api/test_essay.py -p no:randomly -q`
Expected: FAIL（404 / 路由不存在）

- [ ] **Step 3: 改 API**

编辑 `backend/app/api/v1/essay.py`：
1. import 区补：
```python
from app.schemas.essay import (
    EssayCreate, EssayListItem, EssayListOut, EssayOut,
    EssayRoundItem, EssayTemplatesOut, RepolishIn,
)
```
2. `_to_out` 内 `EssayOut(...)` 追加 rounds 组装：
```python
def _to_out(e: Essay) -> EssayOut:
    dim = e.dimensions or {}
    rounds = dim.get("rounds") or []
    return EssayOut(
        id=e.id, original_text=e.original_text, polished_text=e.polished_text,
        scores=dim.get("scores", []), total=dim.get("total", 0),
        issues=dim.get("issues", []), title=dim.get("title"),
        essay_type=dim.get("essay_type"), round_count=e.round_count,
        status=str(e.status), created_at=e.created_at.isoformat(),
        rounds=[EssayRoundItem(round=i + 1, total=r.get("total", 0)) for i, r in enumerate(rounds)],
    )
```
3. 在 `@router.get("/{essay_id}", ...)` 定义**之前**插入 templates + repolish 两个路由（templates 必须在 `/{essay_id}` 前，避免被当 essay_id）：
```python
@router.get("/templates", response_model=BaseResponse[EssayTemplatesOut])
async def essay_templates(db: DbDep, current_user: UserDep, essay_type: str | None = None):
    await get_rls_db(db, str(current_user.id))
    t = essay_service.get_templates(essay_type)
    return make_ok(EssayTemplatesOut(essay_type=essay_type, template=t["template"], samples=t["samples"]))


@router.post("/{essay_id}/repolish", response_model=BaseResponse[EssayOut])
async def repolish(essay_id: uuid.UUID, body: RepolishIn, db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    essay = await essay_service.repolish_essay(
        db, student_id=current_user.id, essay_id=essay_id, revised_text=body.revised_text)
    await db.commit()
    return make_ok(_to_out(essay))
```
> `POST /{essay_id}/repolish` 与 `GET /{essay_id}` 方法不同、且 `/templates` 是 GET 在前，无冲突；但仍把 `/templates` 物理上写在 `/{essay_id}` 之前以策安全。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/api/test_essay.py -p no:randomly -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/api/v1/essay.py tests/api/test_essay.py
git commit -m "feat(backend): 作文 repolish + templates API（rounds 趋势回传）"
```

---

## Task 3: 前端详情页 多轮 + 模板

**Files:**
- Modify: `frontend/miniprogram/src/types/api.ts`、`api/essay.ts`、`pages/essay/detail.vue`

- [ ] **Step 1: 加类型**

`types/api.ts`：在 `EssayDetail` 接口中 `created_at` 后加 `rounds: EssayRoundItem[]`，并在 essay 类型区追加：
```typescript
export interface EssayRoundItem { round: number; total: number }
export interface EssayTemplates { essay_type: string | null; template: string; samples: string[] }
```
（`EssayDetail` 内加 `rounds: EssayRoundItem[]`）

- [ ] **Step 2: 加 api**

`api/essay.ts`：import 类型补 `EssayTemplates`，文件末尾追加：
```typescript
export function repolishEssay(id: string, revisedText: string): Promise<EssayDetail> {
  return request<EssayDetail>(`/api/v1/essays/${id}/repolish`, { method: 'POST', data: { revised_text: revisedText } })
}
export function getEssayTemplates(essayType?: string): Promise<EssayTemplates> {
  const data: Record<string, string> = {}
  if (essayType) data.essay_type = essayType
  return request<EssayTemplates>('/api/v1/essays/templates', { method: 'GET', data })
}
```

- [ ] **Step 3: 改 detail.vue**

编辑 `frontend/miniprogram/src/pages/essay/detail.vue`：

(a) 模板引入 import：
```typescript
import { getEssay, repolishEssay, getEssayTemplates } from '@/api/essay'
import type { EssayDetail, EssayTemplates } from '@/types/api'
```
(b) ref + 加载：
```typescript
const tpl = ref<EssayTemplates | null>(null)
const revised = ref('')
const showRevise = ref(false)
const repolishing = ref(false)

function loadEssay(id: string) {
  getEssay(id).then((e) => {
    essay.value = e
    getEssayTemplates(e.essay_type || undefined).then((t) => { tpl.value = t }).catch(() => {})
  }).catch((e) => uni.showToast({ title: (e as Error).message, icon: 'none' }))
}

async function onRepolish() {
  if (!essay.value || !revised.value.trim()) return
  repolishing.value = true
  try {
    essay.value = await repolishEssay(essay.value.id, revised.value)
    revised.value = ''
    showRevise.value = false
    uni.showToast({ title: '已生成新一轮', icon: 'success' })
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'none' })
  } finally {
    repolishing.value = false
  }
}
```
把原 `onLoad` 改为调用 `loadEssay(id)`：
```typescript
onLoad((q) => {
  const id = (q as { id?: string })?.id
  if (id) loadEssay(id)
})
```
(c) 模板（在 issues 卡片之后追加多轮趋势 + 模板卡片 + 再改一版）：
```html
      <view v-if="essay.rounds && essay.rounds.length > 1" class="card">
        <view class="card-title">进步轨迹</view>
        <view v-for="r in essay.rounds" :key="r.round" class="score-row">
          <text class="dim">第 {{ r.round }} 轮</text>
          <text class="sc">{{ r.total }} 分</text>
        </view>
      </view>

      <view v-if="tpl" class="card">
        <view class="card-title">模板与范文</view>
        <text class="para">{{ tpl.template }}</text>
        <view v-for="(s, i) in tpl.samples" :key="i" class="sample">{{ i + 1 }}. {{ s }}</view>
      </view>

      <view class="card">
        <button v-if="!showRevise" class="btn-ghost" @tap="showRevise = true">再改一版（ProMax）</button>
        <view v-else>
          <textarea v-model="revised" class="essay-input" placeholder="粘贴你修改后的作文…" />
          <button class="btn-primary" :disabled="repolishing || !revised.trim()" @tap="onRepolish">
            {{ repolishing ? '批改中…' : '提交新一轮' }}
          </button>
        </view>
      </view>
```
(d) 样式追加：
```css
.sample { font-size: 24rpx; color: var(--c-text-second); line-height: 1.7; margin-top: 8rpx; }
.essay-input { width: 100%; height: 240rpx; font-size: 28rpx; color: var(--c-text-body); line-height: 1.6; }
.btn-primary { background: var(--c-primary); color: var(--c-ink); border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; margin-top: 12rpx; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #b9a94e; }
.btn-ghost { background: var(--c-bg-page); color: var(--c-text-body); border-radius: var(--r-btn); padding: 18rpx; font-size: 28rpx; }
```

- [ ] **Step 4: 构建验证**

Run: `cd frontend/miniprogram && npm run build:mp-weixin`
Expected: `Build complete.`

- [ ] **Step 5: 提交**

```bash
git add frontend/miniprogram/src/types/api.ts frontend/miniprogram/src/api/essay.ts frontend/miniprogram/src/pages/essay/detail.vue
git commit -m "feat(frontend): 作文详情页 多轮进步轨迹 + 模板范文 + 再改一版"
```

---

## Task 4: 全量回归 + 归档 D-110

**Files:**
- Modify: `docs/决策归档.md`

- [ ] **Step 1: 后端全量回归**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests -p no:randomly -q`
Expected: PASS（约 418 passed；净增 6 例。已知 flaky `test_get_wrong_question_api` 若失败隔离重跑确认）

- [ ] **Step 2: 前端构建确认**

Run: `cd frontend/miniprogram && npm run build:mp-weixin`
Expected: `Build complete.`

- [ ] **Step 3: 归档 D-110**

在 `docs/决策归档.md` 顶部（`## D-109` 之前）插入 D-110 条目：日期、背景、结论（repolish ProMax 专属/5轮上限/dimensions.rounds 零迁移/顶层最新轮 + get_templates 常量按题型 + API repolish/templates(路由顺序) + 前端进步轨迹/模板/再改一版）、测试（强制 dev-mock；后端全量 passed + 前端 build）、影响范围、未做（模板后台可配/范文AI生成/跨篇分析）、相关（D-109、Module 5A）。

- [ ] **Step 4: 提交**

```bash
git add docs/决策归档.md
git commit -m "docs: 归档 D-110 作文多轮迭代 + 模板范文"
```

- [ ] **Step 5: 询问用户是否 push**

报告 commit 列表 + 测试/构建结果，征求明确同意后 `git push`。

---

## Self-Review

**1. Spec 覆盖：**
- 多轮 repolish（ProMax 专属/5轮上限/rounds 历史/顶层最新轮/JSONB flag_modified）→ Task 1 ✓
- 模板 get_templates（按题型 + 兜底）→ Task 1 ✓
- API repolish + templates（/templates 在 /{essay_id} 前）+ rounds 回传 → Task 2 ✓
- 前端进步轨迹 + 模板 + 再改一版 → Task 3 ✓
- 零迁移、dev-mock 强制（autouse 沿用 D-109）→ 全程 ✓

**2. 占位符扫描：** 无 TBD/TODO；每步含完整代码与命令。

**3. 类型一致：** `repolish_essay` 写 `dimensions["rounds"]`（list of {text,scores,total,issues,polished_text}），`_to_out` 读 rounds 组装 `EssayRoundItem{round,total}`；`EssayOut.rounds` 默认 `[]` 与 D-109 单轮（无 rounds 键）兼容（D-109 详情 rounds 返回空数组，前端 `rounds.length > 1` 不展示趋势，符合预期）；前端 `EssayDetail.rounds` 与后端对齐；tier "promax" 与 membership_tier_enum 一致。
