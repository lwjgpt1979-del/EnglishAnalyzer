# 作文 AI 精修 MVP 设计（D-109）

**日期：** 2026-06-03
**归属：** P1 新方向。需求文档 Module 5A「作文精修」。表 `essays` 已存在（域5），本切片从 service 层往上全建。

## 背景与目标

学生提交英文作文 → AI 多维度批改（评分 + 逐处问题标注 + 优化版本）→ 原文/优化版对比展示 → 存档 + 历史。复用现有 LLM dev-mock 模式（`is_llm_dev_mode()`：DEEPSEEK_API_KEY 占位 → 返回固定 mock；真实走 `chat_completion`），dev 不花钱。

## 范围裁定（MVP）

对标 Module 5A 步骤 1-3 + 5（提交 → AI 批改 → 改进说明 → 存档/历史）。

**做：** 提交作文 → 批改（维度评分 + polished_text + 逐处 issues）→ 列表/详情对比展示 → 会员闸门。
**不做（后续）：** 步骤4 模板/范文推荐；多轮精修迭代（表 `round_count` 已支持，MVP 单轮）；维度/颜色/分值后台可配（MVP 默认常量）；老师出卷（另立项）。

## 会员闸门

复用 `membership_service.get_active_membership(db, user_id=...)` 取 tier：
- `free` / `basic` → `AppError(403, "作文精修为 Pro/ProMax 专属功能，请升级会员")`
- `pro` → 本月已精修次数 `< 3` 才放行（查 `essays` 当月 `created_at` 计数）；超限 → `AppError(403, "本月作文精修次数已用完（Pro 每月3次）")`
- `promax` → 不限

> tier 值确认：`membership_tier_enum = free/basic/pro/promax`（与 vocabulary_service `_DAILY_NEW_LIMIT` 同款）。`is_llm_dev_mode` 在 `app.services.llm_provider`；`chat_completion` 同模块。`get_active_membership(db, *, user_id) -> Membership | None`，`.tier`。测试造档位：直接插 `Membership(user_id, tier, started_at=now, is_active=True)`（order_id nullable）。

## 默认批改维度（常量，后台可配留后续）

```python
_DIMENSIONS = [("内容", 25), ("语言", 25), ("结构", 25), ("词汇", 25)]
_COLOR_BY_TYPE = {"语法": "red", "表达": "yellow", "词汇": "blue"}  # 颜色标签
```

## 架构与组件

### 后端

**1. `essay_service.py`（新建）**

```python
async def _monthly_count(db, student_id) -> int:
    # 当月 essays 计数（UTC 月界）
    ...

async def polish_essay(
    db, *, student_id, original_text, title=None, essay_type=None, wrong_question_id=None,
) -> Essay:
    # 1) 档位闸门
    m = await membership_service.get_active_membership(db, user_id=student_id)
    tier = str(m.tier) if m else "free"
    if tier in ("free", "basic"):
        raise AppError(code=403, message="作文精修为 Pro/ProMax 专属功能，请升级会员")
    if tier == "pro" and await _monthly_count(db, student_id) >= 3:
        raise AppError(code=403, message="本月作文精修次数已用完（Pro 每月3次）")
    # 2) 批改（dev-mock / real）
    result = await _grade(original_text=original_text, essay_type=essay_type)
    # result: {"scores":[{dimension,score,full}], "total":int, "issues":[{original,suggestion,type,color,explanation}], "polished_text":str}
    # 3) 落库
    essay = Essay(
        id=uuid.uuid4(), student_id=student_id, wrong_question_id=wrong_question_id,
        original_text=original_text, polished_text=result["polished_text"],
        dimensions={"scores": result["scores"], "total": result["total"], "issues": result["issues"],
                    "title": title, "essay_type": essay_type},
        round_count=1, status="completed",
    )
    db.add(essay); await db.flush()
    return essay


async def _grade(*, original_text, essay_type) -> dict:
    if is_llm_dev_mode():
        return {
            "scores": [{"dimension": d, "score": s - 3, "full": s} for d, s in _DIMENSIONS],
            "total": sum(s - 3 for _, s in _DIMENSIONS),
            "issues": [
                {"original": "very good", "suggestion": "excellent", "type": "词汇",
                 "color": "blue", "explanation": "将 'very good' 替换为 'excellent' 更符合书面表达。"},
            ],
            "polished_text": original_text + "\n\n[AI 优化版 - dev mock]",
        }
    # real：chat_completion 结构化 JSON（system 提示要求返回 scores/issues/polished_text）
    ...解析 JSON，异常 → AppError(502/500)，对齐 ai_service 风格...


async def get_essay(db, *, student_id, essay_id) -> Essay | None: ...
async def list_essays(db, *, student_id) -> list[Essay]: ...
```

`is_llm_dev_mode` 从现有处 import（与 ai_service 同源；实现时核对其定义位置，如 `app.services.llm_client` 或 `ai_service`）。

**2. `schemas/essay.py`（新建）**
```python
class EssayCreate(BaseModel):
    original_text: str = Field(..., min_length=1)
    title: str | None = None
    essay_type: str | None = None        # 图片作文/话题作文/书信作文等
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
    polished_text: str | None
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
    title: str | None
    essay_type: str | None
    total: int
    status: str
    created_at: str

class EssayListOut(BaseModel):
    total: int
    items: list[EssayListItem]
```
`EssayOut` 由 Essay ORM 组装（dimensions JSONB 拆出 scores/total/issues/title/essay_type）。

**3. `api/v1/essay.py`（新建）+ router 注册**
```python
@router.post("/essays", response_model=BaseResponse[EssayOut])
async def create_essay(body: EssayCreate, db, current_user):
    await get_rls_db(...)
    essay = await essay_service.polish_essay(db, student_id=current_user.id,
        original_text=body.original_text, title=body.title,
        essay_type=body.essay_type, wrong_question_id=body.wrong_question_id)
    await db.commit()
    return make_ok(_to_out(essay))

@router.get("/essays", response_model=BaseResponse[EssayListOut])
async def list_my_essays(db, current_user): ...

@router.get("/essays/{essay_id}", response_model=BaseResponse[EssayOut])
async def get_my_essay(essay_id, db, current_user):
    # 取本人 essay，不存在/非本人 → 404
```
在 `app/api/v1/router.py` 注册 essay router（prefix `/essays` 已在 router 内则按现有风格）。

### 前端

**1. `types/api.ts`**：`EssayScoreItem` / `EssayIssueItem` / `EssayDetail` / `EssayListItem`。
**2. `api/essay.ts`**：`createEssay(payload)` / `getEssays()` / `getEssay(id)`。
**3. `pages/essay/index.vue`**：textarea 输入作文 + 题型选择 + 「AI 精修」按钮 → 调 createEssay → 跳详情；下方历史列表（标题/题型/总分/时间，点进详情）。
**4. `pages/essay/detail.vue`**：维度评分条（各维度 score/full）+ 总分；原文 / 优化版对比；逐处问题列表（original→suggestion + 颜色 + 说明）。
**5. `pages.json`**：注册两页。
**6. 入口**：首页/学习中心「作文精修」宫格 → `pages/essay/index`。

## 数据流

学生输入作文 → POST /essays → 档位/次数闸门 → `_grade`（dev-mock 固定 / 真实 LLM）→ 写 essays(completed) → 返回 EssayOut → 前端跳详情展示评分+对比+问题。历史走 GET /essays。

## 错误处理

- 档位不足 / 次数超限 → 403（前端 toast，引导升级）。
- 真实 LLM 失败 → 502；JSON 解析失败 → 500（对齐 ai_service）。
- 详情非本人/不存在 → 404。

## 测试（TDD）

**service（`tests/services/test_essay_service.py`）**
1. dev-mock 精修：Pro 学生提交 → 返回 Essay status=completed、dimensions 含 scores(4)/total/issues、polished_text 非空。
2. free 档 → `polish_essay` 抛 AppError(403)。
3. Pro 当月已 3 篇 → 第 4 篇抛 AppError(403)。
4. ProMax → 多篇不受 3 次限制。

**API（`tests/api/test_essay.py`）**
5. 未登录 → 401。
6. Pro 提交 → 200 返回评分+优化版；GET /essays 列表含该篇；GET /essays/{id} 详情。

> 测试需构造会员档位：用 membership_service 给测试学生置 pro/promax（参照现有支付/会员测试的造数方式）。

## 影响范围

- `backend/app/services/essay_service.py`（新）
- `backend/app/schemas/essay.py`（新）
- `backend/app/api/v1/essay.py`（新）+ `router.py`(注册)
- `tests/services/test_essay_service.py`、`tests/api/test_essay.py`（新）
- 前端 `types/api.ts`、`api/essay.ts`、`pages/essay/index.vue`、`pages/essay/detail.vue`、`pages.json`、首页入口
- **零迁移**（essays 表已存在）；**dev-mock 无花钱**（真实精修需预算另确认）。

## 不做（后续）

- 模板/范文推荐（Module 5A 步骤4）
- 多轮精修迭代（ProMax，round_count 已支持）
- 批改维度/颜色/分值后台可配（5.7）
- 老师出卷闭环（Module 5B，另立项）
- 真实 LLM provider 接入（需预算）

## 相关

需求 Module 5A、5.7；复用 ai_service dev-mock 模式、membership_service。
