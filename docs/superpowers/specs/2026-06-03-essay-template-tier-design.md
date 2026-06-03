# 作文模板/范文 按会员档位差异化 设计（D-112）

**日期：** 2026-06-03
**归属：** 作文精修（D-109~111）小切片。需求 5.7：Pro 可见为 ProMax 子集。

## 目标

模板文本两档都看；**范文 samples 按档位裁剪**：ProMax 看全部，Pro 看前 `_PRO_SAMPLE_LIMIT`（默认 2）篇。

## 架构

**`essay_service.get_configured_templates(db, essay_type, tier=None)`** 加 `tier` 参数：
- 取得 `data = {template, samples}`（配置或内置，逻辑不变）。
- 若 `tier` 不是 `promax` 且不是 `None`（None=admin/未指定→全部）→ 返回 `{**data, "samples": data["samples"][:_PRO_SAMPLE_LIMIT]}`。
- 否则原样返回。
```python
_PRO_SAMPLE_LIMIT = 2

async def get_configured_templates(db, essay_type, tier=None) -> dict:
    ...原有读取逻辑得到 data...
    if tier is not None and tier != "promax":
        return {**data, "samples": list(data.get("samples", []))[:_PRO_SAMPLE_LIMIT]}
    return data
```
> `get_all_templates_config`（admin 全量）不受影响。

**`api/v1/essay.py` `GET /essays/templates`**：取当前用户 membership tier 传入。
```python
from app.services import essay_service, membership_service
m = await membership_service.get_active_membership(db, user_id=current_user.id)
tier = str(m.tier) if m else "free"
t = await essay_service.get_configured_templates(db, essay_type, tier=tier)
```

**前端**：详情页「模板与范文」卡片，Pro（samples 被裁剪时）可显示一行提示「升级 ProMax 查看更多范文」。MVP 简单：若 `tpl.samples.length <= 2` 且用户非 promax 时提示——但前端不易判 tier，**简化为不加提示**（后端裁剪已生效）；或加静态提示「ProMax 可见更多范文」。本切片前端**仅加一行静态提示**，不依赖 tier 判断。

## 测试（dev-mock）

**service（test_essay_service.py 扩展）**
1. `get_configured_templates(db, "话题作文", tier="pro")` → `len(samples) <= 2`。
2. `tier="promax"` → 全部 samples（内置话题作文 3 篇）。
3. `tier=None` → 全部（admin 预览）。

**API（test_essay.py 扩展）**
4. Pro 用户 `GET /essays/templates?essay_type=话题作文` → `len(samples) <= 2`。
5. ProMax 用户 → 全部（3 篇）。

## 影响范围

- `backend/app/services/essay_service.py`（get_configured_templates +tier、_PRO_SAMPLE_LIMIT）
- `backend/app/api/v1/essay.py`（templates endpoint 传 tier）
- `tests/services/test_essay_service.py`、`tests/api/test_essay.py`（扩展）
- 前端 `pages/essay/detail.vue`（静态提示，可选）
- **零迁移、无花钱。**

## 兼容

`get_configured_templates` 既有调用（D-111 不传 tier）→ tier=None → 全部，行为不变；D-111 测试不受影响。

## 不做（后续）

- 批改维度 Pro 子集（4 维固定，留后续）
- `_PRO_SAMPLE_LIMIT` 运营后台可配（MVP 常量）
- 前端按 tier 动态提示

## 相关

D-109~111；需求 5.7。
