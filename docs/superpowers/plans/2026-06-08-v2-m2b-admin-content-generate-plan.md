# V2 M2b：Admin Web 课程内容 AI 生成触发器 实施计划

**Design Ref:** `docs/superpowers/specs/2026-06-08-v2-m2b-admin-content-generate.md`

## 执行顺序
```
Task 1（backend service: list_units_with_stats）
Task 2（backend API: 两个端点）← 依赖 Task 1
Task 3（TDD API 测试）← 依赖 Task 2
Task 4（前端 CurriculumUnits.vue + 路由）← 独立
Task 5（归档 + 验证）
```

---

## Task 1：backend service — list_units_with_stats

**Files:** `backend/app/services/curriculum_service.py`

新增函数，返回每个单元的 KP 数 + 内容数：

```python
from dataclasses import dataclass

@dataclass
class UnitContentStat:
    unit_id: uuid.UUID
    textbook_version: str
    grade: str
    semester: str
    unit_no: int
    unit_title: str
    kp_count: int
    content_count: int       # 已有内容条数（任意 status）
    content_rate: float      # content_count / (kp_count * 6)，0-1

async def list_units_with_stats(db: AsyncSession) -> list[UnitContentStat]:
    """列出所有单元及内容完成度，供 Admin 课程管理页使用。"""
    from app.models.d4_knowledge import KnowledgePointContent, UnitKnowledgePoint

    # 所有单元
    units = (await db.execute(
        select(CurriculumUnit).order_by(
            CurriculumUnit.textbook_version,
            CurriculumUnit.grade,
            CurriculumUnit.semester,
            CurriculumUnit.unit_no,
        )
    )).scalars().all()

    if not units:
        return []

    unit_ids = [u.id for u in units]

    # 每个单元的 KP 数
    kp_counts = dict((await db.execute(
        select(UnitKnowledgePoint.unit_id, func.count())
        .where(UnitKnowledgePoint.unit_id.in_(unit_ids))
        .group_by(UnitKnowledgePoint.unit_id)
    )).all())

    # 每个单元的内容数（via KP join）
    content_rows = (await db.execute(
        select(UnitKnowledgePoint.unit_id, func.count(KnowledgePointContent.id))
        .join(
            KnowledgePointContent,
            KnowledgePointContent.knowledge_point_id == UnitKnowledgePoint.knowledge_point_id,
            isouter=True,
        )
        .where(UnitKnowledgePoint.unit_id.in_(unit_ids))
        .group_by(UnitKnowledgePoint.unit_id)
    )).all()
    content_counts = dict(content_rows)

    result = []
    for u in units:
        kc = kp_counts.get(u.id, 0)
        cc = content_counts.get(u.id, 0)
        rate = round(cc / (kc * 6), 4) if kc > 0 else 0.0
        result.append(UnitContentStat(
            unit_id=u.id,
            textbook_version=u.textbook_version,
            grade=str(u.grade),
            semester=str(u.semester),
            unit_no=u.unit_no,
            unit_title=u.unit_title or "",
            kp_count=kc,
            content_count=cc,
            content_rate=min(rate, 1.0),
        ))
    return result
```

验证：
```bash
python3 -c "
from app.services.curriculum_service import list_units_with_stats, UnitContentStat
print('✅ list_units_with_stats OK')
"
```

---

## Task 2：backend API — 两个 admin 端点

**Files:** `backend/app/api/v1/admin.py`

在文件末尾追加：

```python
# ── V2 课程单元管理 ────────────────────────────────────────────────────

@router.get("/curriculum/units")
async def list_curriculum_units(db: DbDep, admin: AdminDep):
    """列出所有课程单元 + 内容完成度统计，供 Admin 内容生成触发。"""
    from app.services.curriculum_service import list_units_with_stats
    stats = await list_units_with_stats(db)
    return make_ok([
        {
            "unit_id": str(s.unit_id),
            "textbook_version": s.textbook_version,
            "grade": s.grade,
            "semester": s.semester,
            "unit_no": s.unit_no,
            "unit_title": s.unit_title,
            "kp_count": s.kp_count,
            "content_count": s.content_count,
            "content_rate": s.content_rate,
        }
        for s in stats
    ])


@router.post("/curriculum/units/{unit_id}/generate")
async def generate_unit_content(
    unit_id: uuid.UUID,
    db: DbDep,
    admin: AdminDep,
):
    """触发 AI 生成指定单元的课程内容（dev mock 即时返回；生产约 5-15s）。
    
    生成内容 status='draft'，需在 ContentsReview 页面审核发布。
    """
    from app.models.d4_knowledge import CurriculumUnit
    from app.services import curriculum_ai_service

    unit = (await db.execute(
        select(CurriculumUnit).where(CurriculumUnit.id == unit_id)
    )).scalar_one_or_none()
    if unit is None:
        raise AppError(code=404, message="单元不存在")

    ai_unit = await curriculum_ai_service.generate_unit(
        textbook_version=unit.textbook_version,
        grade=str(unit.grade),
        semester=str(unit.semester),
        unit_no=unit.unit_no,
    )
    await curriculum_service.persist_unit(db, ai_unit=ai_unit, content_status="draft")
    await db.commit()

    # 返回更新后统计
    from app.services.curriculum_service import list_units_with_stats
    stats = await list_units_with_stats(db)
    stat = next((s for s in stats if s.unit_id == unit_id), None)
    return make_ok({
        "unit_id": str(unit_id),
        "kp_count": stat.kp_count if stat else 0,
        "content_count": stat.content_count if stat else 0,
        "content_rate": stat.content_rate if stat else 0.0,
    })
```

验证：
```bash
python3 -c "
from app.api.v1.admin import router
routes = [r.path for r in router.routes]
assert '/admin/curriculum/units' in routes
assert '/admin/curriculum/units/{unit_id}/generate' in routes
print('✅ admin curriculum 端点 GREEN')
"
```

---

## Task 3：TDD — API 测试

**Files:** `tests/api/test_admin_curriculum_generate.py`

```python
"""Admin 课程内容生成端点 TDD 测试。"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_curriculum_units_requires_admin(client: AsyncClient):
    """未鉴权 → 401。"""
    r = await client.get("/api/v1/admin/curriculum/units")
    assert r.status_code == 401


@pytest.mark.asyncio  
async def test_list_curriculum_units_returns_list(admin_client: AsyncClient):
    """Admin 鉴权 → 200 + list。"""
    r = await admin_client.get("/api/v1/admin/curriculum/units")
    assert r.status_code == 200
    assert isinstance(r.json()["data"], list)


@pytest.mark.asyncio
async def test_generate_unit_content_invalid_id(admin_client: AsyncClient):
    """不存在的 unit_id → 404。"""
    import uuid
    r = await admin_client.post(f"/api/v1/admin/curriculum/units/{uuid.uuid4()}/generate")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_generate_unit_content_success(admin_client: AsyncClient, seeded_unit_id: str):
    """有效 unit_id → 200 + content_count > 0（dev mock 生成）。"""
    r = await admin_client.post(f"/api/v1/admin/curriculum/units/{seeded_unit_id}/generate")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["kp_count"] > 0
    assert data["content_count"] > 0
    assert data["content_rate"] > 0


@pytest.mark.asyncio
async def test_generate_unit_requires_admin(client: AsyncClient, seeded_unit_id: str):
    """非 admin → 401。"""
    r = await client.post(f"/api/v1/admin/curriculum/units/{seeded_unit_id}/generate")
    assert r.status_code == 401
```

---

## Task 4：前端 — CurriculumUnits.vue + 路由 + 菜单

### Step 1: 追加 types.ts

```typescript
export interface AdminCurriculumUnit {
  unit_id: string
  textbook_version: string
  grade: string
  semester: string
  unit_no: number
  unit_title: string
  kp_count: number
  content_count: number
  content_rate: number   // 0-1
}
```

### Step 2: 追加 api/admin.ts

```typescript
export function listCurriculumUnits(): Promise<AdminCurriculumUnit[]> {
  return unwrap<AdminCurriculumUnit[]>(request.get('/admin/curriculum/units'))
}

export function generateUnitContent(unitId: string): Promise<{
  unit_id: string; kp_count: number; content_count: number; content_rate: number
}> {
  return unwrap(request.post(`/admin/curriculum/units/${unitId}/generate`))
}
```

### Step 3: 新建 views/CurriculumUnits.vue（完整代码见 Task 4 实施）

### Step 4: 注册路由

```typescript
{ path: 'curriculum-units', name: 'curriculum-units',
  component: () => import('../views/CurriculumUnits.vue') },
```

### Step 5: 侧边栏加菜单

在 MainLayout.vue 的 el-menu 中加：
```html
<el-menu-item index="/curriculum-units">📚 课程内容生成</el-menu-item>
```

---

## Task 5：归档 + 验证

```bash
# 后端
python3 -c "
from app.services.curriculum_service import list_units_with_stats
from app.api.v1.admin import router
routes = [r.path for r in router.routes]
assert '/admin/curriculum/units' in routes
assert '/admin/curriculum/units/{unit_id}/generate' in routes
print('✅ 全部 OK')
"

# 前端
grep -c "curriculum-units" frontend/admin/src/router/index.ts
grep -c "generateUnitContent" frontend/admin/src/api/admin.ts

git add ... && git commit -m "feat(admin): 课程内容 AI 生成触发器（单元列表 + 生成按钮）"
```
