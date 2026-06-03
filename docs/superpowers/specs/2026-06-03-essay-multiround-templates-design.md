# 作文精修：多轮迭代 + 模板/范文 设计（D-110）

**日期：** 2026-06-03
**归属：** 作文精修（D-109）后续。需求 Module 5A：ProMax 多轮迭代精修 + 步骤4 模板/范文推荐。

## 背景与目标

在 D-109 单轮精修基础上补两块：
1. **多轮迭代精修**（ProMax 专属）：对同一作文反复修订重批，追踪进步轨迹（轮次上限默认 5）。
2. **模板/范文推荐**（步骤4）：按作文题型推荐高分模板 + 3-5 篇范文。

均**零迁移**（多轮存 `essays.dimensions` JSONB；模板用常量）、复用 D-109 dev-mock 批改、dev 无花钱。

## 关键决策（已确认）

- 多轮迭代 **ProMax 专属**（Pro 只能单轮 D-109）；轮次上限 **默认 5**（常量）。
- 多轮存储：同一 Essay 行 `dimensions["rounds"]` 列表（零迁移）；顶层 scores/total/issues/polished_text 反映**最新轮**（D-109 详情页不受影响）。
- 模板/范文：service 内置常量按题型 + 通用兜底（零迁移，运营可配留后续）。

## 架构与组件

### 后端 `essay_service.py`

**1. 多轮迭代 `repolish_essay`**
```python
_MAX_ROUNDS = 5

async def repolish_essay(
    db, *, student_id, essay_id, revised_text,
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
        # 用现有单轮结果回填 round 1（D-109 仅存顶层）
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
    # 顶层反映最新轮
    dim["rounds"] = rounds
    dim["scores"] = result["scores"]
    dim["total"] = result["total"]
    dim["issues"] = result["issues"]
    essay.dimensions = dim
    essay.polished_text = result["polished_text"]
    essay.round_count = len(rounds)
    # JSONB 原地修改需显式标记
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(essay, "dimensions")
    await db.flush()
    return essay
```
> **注意**：SQLAlchemy 对 JSONB 字段「原地 mutate」不会自动检测，必须重新赋值 `essay.dimensions = dim`（新 dict）或 `flag_modified`。本设计两者都做（赋新 dict + flag_modified）以确保持久化。

**2. 模板/范文 `get_templates`**
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

### 后端 schemas（`schemas/essay.py` 追加）
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
`EssayOut` 追加可选字段 `rounds: list[EssayRoundItem] = []`（仅回传 round 序号 + total，不回传全文，轻量趋势）。`_to_out` 从 `dimensions["rounds"]` 组装：`[{round:i+1, total:r["total"]} for i,r in enumerate(rounds)]`（无 rounds 则空列表）。

### 后端 API（`api/v1/essay.py` 追加）
```python
@router.post("/{essay_id}/repolish", response_model=BaseResponse[EssayOut])
async def repolish(essay_id: uuid.UUID, body: RepolishIn, db, current_user):
    await get_rls_db(...)
    essay = await essay_service.repolish_essay(
        db, student_id=current_user.id, essay_id=essay_id, revised_text=body.revised_text)
    await db.commit()
    return make_ok(_to_out(essay))

@router.get("/templates", response_model=BaseResponse[EssayTemplatesOut])
async def essay_templates(db, current_user, essay_type: str | None = None):
    await get_rls_db(...)
    t = essay_service.get_templates(essay_type)
    return make_ok(EssayTemplatesOut(essay_type=essay_type, template=t["template"], samples=t["samples"]))
```
> **路由顺序坑**：`/templates` 必须在 `/{essay_id}` **之前**注册，否则 `templates` 会被当成 essay_id 路径参数匹配（uuid 解析失败 422）。实现时把 `GET /templates` 放在 `GET /{essay_id}` 定义之前。

### 前端

**`types/api.ts`**：`EssayRoundItem`、`EssayTemplates`；`EssayDetail` 加 `rounds: EssayRoundItem[]`。
**`api/essay.ts`**：`repolishEssay(id, revisedText)`、`getEssayTemplates(essayType?)`。
**`pages/essay/detail.vue`**：
- 「模板与范文」卡片：onLoad 拉 `getEssayTemplates(essay.essay_type)` 展示模板 + 范文列表。
- 多轮：若 `essay.rounds.length > 1` 展示各轮总分趋势（round N: total）；「再改一版」按钮（ProMax 才有意义——非 ProMax 点了后端返回 403，前端 toast）→ 弹输入修订稿（简单用一个 textarea 区域 + 提交）→ `repolishEssay` → 刷新详情。
  - MVP 交互：详情页底部加可展开的「再改一版」textarea + 提交按钮，提交后重新 `getEssay(id)` 刷新。

## 数据流

详情页拉 essay + templates。点「再改一版」→ 输入修订稿 → POST /essays/{id}/repolish → ProMax+轮次校验 → 重新批改 → dimensions.rounds 追加 + 顶层更新 → 返回 → 前端刷新（趋势 +1 轮）。

## 错误处理

- 非 ProMax repolish → 403；超 5 轮 → 403；essay 非本人/不存在 → 404。
- 真实 LLM 失败 → 502/500（_grade 复用 D-109）。

## 测试（TDD，强制 dev-mock）

service+API 测试均 autouse `monkeypatch essay_service.is_llm_dev_mode=True`（同 D-109，绝不真打付费 LLM）。

**service（`tests/services/test_essay_service.py` 扩展）**
1. ProMax repolish：先 polish（round1）→ repolish（round2）→ `round_count==2`、`dimensions["rounds"]` 长度 2、顶层 total = 最新轮。
2. Pro repolish → AppError(403)。
3. 超 5 轮：构造 dimensions.rounds 已 5 条 → repolish → AppError(403)。
4. `get_templates("书信作文")` 返回该题型；`get_templates(None)` 返回兜底。

**API（`tests/api/test_essay.py` 扩展）**
5. ProMax 用户 repolish → 200，rounds 长度 2。
6. `GET /essays/templates?essay_type=话题作文` → 200 含 template + samples。

> 测试造 ProMax：插 `Membership(tier="promax", is_active=True)`（同 D-109 helper）。

## 影响范围

- `backend/app/services/essay_service.py`（+repolish_essay/_MAX_ROUNDS/get_templates/_TEMPLATES_BY_TYPE）
- `backend/app/schemas/essay.py`（+EssayRoundItem/RepolishIn/EssayTemplatesOut；EssayOut +rounds）
- `backend/app/api/v1/essay.py`（+repolish + templates；注意 /templates 在 /{essay_id} 前）
- `backend/app/api/v1/essay.py` `_to_out` 组装 rounds
- `tests/services/test_essay_service.py`、`tests/api/test_essay.py`（扩展）
- 前端 `types/api.ts`、`api/essay.ts`、`pages/essay/detail.vue`
- **零迁移**；**dev-mock 无花钱**。

## 不做（后续）

- 模板/范文运营后台可配（需建表）
- 范文真实 AI 生成（用内置静态范文）
- 跨篇作文进步分析 / 题型分布
- 轮次上限后台可配（常量 5）

## 相关

D-109（作文精修 MVP）；需求 Module 5A（ProMax 多轮 + 步骤4 模板）。
