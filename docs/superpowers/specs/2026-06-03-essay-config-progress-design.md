# 作文精修深化：模板后台可配 + 跨篇进步分析 设计（D-111）

**日期：** 2026-06-03
**归属：** 作文精修（D-109/D-110）深化。需求 Module 5A（模板运营可配，5.7）+ 学情扩展。

## 背景与目标

1. **模板/范文运营后台可配**：D-110 模板是 service 常量；改为运营在 admin 后台配置（存 `system_configs`），学生端按配置展示，未配则回落内置常量。
2. **跨篇进步分析**：学生在作文精修首页看到「我的进步」——总篇数 / 平均分 / 各维度均分 / 趋势。

均**零迁移**（复用 `SystemConfig` + `essays`），复用 pricing_service 的 config 读写范式 + admin GET/PUT 范式。dev 无花钱。

## 架构与组件

### Part A：模板后台可配

**1. `essay_service.py`**
- 保留 `get_templates(essay_type)`（内置常量，**sync**，D-110 用法/测试不变）作为回落。
- 新增：
```python
_ESSAY_TEMPLATES_KEY = "essay_templates"

async def get_configured_templates(db: AsyncSession, essay_type: str | None) -> dict:
    """读 system_configs.essay_templates；命中题型→用之，否则 _default，再否则回落内置常量。"""
    from app.models.d9_system import SystemConfig
    r = await db.execute(select(SystemConfig).where(SystemConfig.key == _ESSAY_TEMPLATES_KEY))
    cfg = r.scalar_one_or_none()
    if cfg is not None:
        data = cfg.value if isinstance(cfg.value, dict) else {}
        if essay_type and essay_type in data:
            return data[essay_type]
        if "_default" in data:
            return data["_default"]
    return get_templates(essay_type)


async def get_all_templates_config(db: AsyncSession) -> dict:
    """admin 读：返回当前完整配置；未配置则返回内置（含 _default）。"""
    from app.models.d9_system import SystemConfig
    r = await db.execute(select(SystemConfig).where(SystemConfig.key == _ESSAY_TEMPLATES_KEY))
    cfg = r.scalar_one_or_none()
    if cfg is not None and isinstance(cfg.value, dict):
        return cfg.value
    return {**_TEMPLATES_BY_TYPE, "_default": _DEFAULT_TEMPLATE}


async def set_all_templates_config(db: AsyncSession, *, value: dict, admin_id) -> dict:
    """admin 写：upsert system_configs.essay_templates。"""
    from app.models.d9_system import SystemConfig
    r = await db.execute(select(SystemConfig).where(SystemConfig.key == _ESSAY_TEMPLATES_KEY))
    cfg = r.scalar_one_or_none()
    if cfg is None:
        cfg = SystemConfig(id=uuid.uuid4(), key=_ESSAY_TEMPLATES_KEY, value=value,
                           description="作文精修模板/范文（Module 5A）", updated_by=admin_id)
        db.add(cfg)
    else:
        cfg.value = value
        cfg.updated_by = admin_id
    await db.flush()
    return cfg.value
```

**2. 学生端 `GET /essays/templates`（api/v1/essay.py）改造**
原调 `essay_service.get_templates(essay_type)`（sync）→ 改调 `await essay_service.get_configured_templates(db, essay_type)`。返回 schema 不变（EssayTemplatesOut）。

**3. admin API（api/v1/admin.py）**
```python
@router.get("/essay-templates", response_model=BaseResponse[dict])
async def get_essay_templates(db: DbDep, admin: AdminDep):
    return make_ok(await essay_service.get_all_templates_config(db))

@router.put("/essay-templates", response_model=BaseResponse[dict])
async def update_essay_templates(body: dict, db: DbDep, admin: AdminDep):
    v = await essay_service.set_all_templates_config(db, value=body, admin_id=admin.id)
    await db.commit()
    return make_ok(v)
```
> body 直接收 dict（题型→{template,samples}）。MVP 不做严格 schema 校验（运营受控环境）；可加最简校验：值为 dict。`AdminDep`/`make_ok`/`BaseResponse` 复用 admin.py 现有。`admin.id` 以 admin.py 现有 admin 对象字段为准（实现核对，可能是 admin.user_id 或 current admin）。

**4. admin web（frontend/admin）**
- `api/admin.ts`：`getEssayTemplates()` / `updateEssayTemplates(payload)`。
- `views/EssayTemplates.vue`：按题型分组编辑 template（textarea）+ samples（多行，每行一条）。加载 GET，保存 PUT。
- `router/index.ts`：加 `{ path: 'essay-templates', component: EssayTemplates.vue }`。
- `layouts/MainLayout.vue`：菜单加「作文模板」入口。

### Part B：跨篇进步分析

**1. `essay_service.get_progress(db, student_id) -> dict`**
```python
async def get_progress(db: AsyncSession, *, student_id) -> dict:
    rows = await list_essays(db, student_id=student_id)  # 倒序
    essays = list(reversed(rows))  # 按时间正序
    total_essays = len(essays)
    totals = [(e.dimensions or {}).get("total", 0) for e in essays]
    avg_total = round(sum(totals) / total_essays, 1) if total_essays else 0
    trend = [{"date": e.created_at.date().isoformat(), "total": (e.dimensions or {}).get("total", 0)} for e in essays]
    # 各维度平均
    dim_sum: dict[str, list[int]] = {}
    for e in essays:
        for s in (e.dimensions or {}).get("scores", []):
            dim_sum.setdefault(s["dimension"], []).append(s["score"])
    dimension_avg = [{"dimension": d, "avg": round(sum(v) / len(v), 1)} for d, v in dim_sum.items()]
    return {
        "total_essays": total_essays,
        "avg_total": avg_total,
        "trend": trend,
        "dimension_avg": dimension_avg,
    }
```

**2. 学生 API `GET /essays/progress`（api/v1/essay.py）**
```python
@router.get("/progress", response_model=BaseResponse[EssayProgressOut])
async def my_progress(db: DbDep, current_user: UserDep):
    await get_rls_db(...)
    return make_ok(EssayProgressOut(**await essay_service.get_progress(db, student_id=current_user.id)))
```
> **路由顺序**：`/progress` 与 `/templates` 均须在 `/{essay_id}` **之前**注册（避免被当 essay_id → 422）。本设计与 D-110 templates 一并置前。

**3. schemas（schemas/essay.py）**
```python
class EssayTrendItem(BaseModel):
    date: str
    total: int

class EssayDimensionAvg(BaseModel):
    dimension: str
    avg: float

class EssayProgressOut(BaseModel):
    total_essays: int
    avg_total: float
    trend: list[EssayTrendItem]
    dimension_avg: list[EssayDimensionAvg]
```

**4. 前端 `pages/essay/index.vue`**
- onShow 拉 `getEssayProgress()`；顶部「我的进步」卡片：总篇数 / 平均分 / 各维度均分（条）/ 趋势（最近若干篇总分）。
- `api/essay.ts`：`getEssayProgress()`；`types/api.ts`：`EssayProgress`。

## 数据流

- 模板：运营 admin 编辑 → PUT /admin/essay-templates（system_configs）→ 学生 GET /essays/templates 读配置（回落内置）。
- 进步：学生进作文精修首页 → GET /essays/progress → 聚合所有 essays → 卡片展示。

## 错误处理

- admin 鉴权失败 → 401/403（AdminDep 现成）。
- 无 essays → progress 返回 total_essays=0、avg 0、空数组（前端空态）。
- 配置缺失/格式异常 → 回落内置常量。

## 测试（TDD，essay 测试沿用 autouse dev-mock）

**service（test_essay_service.py 扩展）**
1. `get_configured_templates`：未配置 → 回落内置（话题作文）；写入配置后命中自定义；题型不存在 → _default。
2. `get_progress`：3 篇（promax dev-mock，total 各 88）→ total_essays=3、avg_total=88.0、trend 长度 3、dimension_avg 4 维各 22.0。

**admin API（test_admin.py 或 test_essay_admin.py 新）**
3. `PUT /admin/essay-templates` 后 `GET` 返回新配置（管理员登录复用现有 admin 测试 helper）。

**学生 API（test_essay.py 扩展）**
4. `GET /essays/progress`：Pro 用户提交 2 篇后返回 total_essays=2。
5. 配置生效：admin PUT 自定义模板 → 学生 GET /essays/templates 返回自定义（同测试内造数据）。

## 影响范围

- `backend/app/services/essay_service.py`（+get_configured_templates/get_all_templates_config/set_all_templates_config/get_progress/_ESSAY_TEMPLATES_KEY）
- `backend/app/schemas/essay.py`（+EssayTrendItem/EssayDimensionAvg/EssayProgressOut）
- `backend/app/api/v1/essay.py`（templates 改异步配置版 + progress endpoint，路由置前）
- `backend/app/api/v1/admin.py`（essay-templates GET/PUT）
- `tests/services/test_essay_service.py`、`tests/api/test_essay.py`、admin 测试（扩展/新增）
- 前端 `pages/essay/index.vue`、`api/essay.ts`、`types/api.ts`
- admin web `views/EssayTemplates.vue`、`api/admin.ts`、`router/index.ts`、`layouts/MainLayout.vue`
- **零迁移**；**dev-mock 无花钱**。

## 不做（后续）

- 模板富文本/配图；范文 AI 批量生成
- 进步分析图表（折线/同比环比）——MVP 仅返回数据 + 简单条/列表
- 模板按会员档位差异化展示（Pro 可见子集，留后续）
- 老师出卷（Module 5B 另立项）

## 相关

D-109/D-110（作文精修）；pricing_service（config 范式）；需求 Module 5A、5.7。
