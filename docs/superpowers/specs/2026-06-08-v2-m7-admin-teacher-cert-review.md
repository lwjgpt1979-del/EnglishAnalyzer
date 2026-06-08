# V2 M7: Admin Web 教师认证审核 设计

**日期：** 2026-06-08
**状态：** 待实施

## 1. 问题

- `auto_approve_teacher_cert = True`（dev 默认）
- 生产置 `False` → 老师提交认证后 cert_status=pending，但**平台管理员无处审核**：
  - 后端只有 `POST /admin/teachers/{id}/review`，**没有列表接口**
  - Admin Web **没有教师认证审核页面**
  - 数据大盘**没有 pending_teachers 指标**
- 生产等价于认证功能完全失效

## 2. 目标

1. **后端**新增 `GET /admin/teachers?cert_status=pending` 列表接口
2. **后端**数据大盘 `AdminOverviewOut` 新增 `pending_teachers: int`
3. **Admin Web** 新增「👨‍🏫 教师认证审核」页面：按状态筛选老师、查看证书、通过/拒绝
4. **Admin Web** 数据大盘展示 pending_teachers 数量（醒目提示）

## 3. 后端组件

### 3.1 `teacher_service.py` 新增 `list_teachers_for_admin`

```python
async def list_teachers_for_admin(
    db: AsyncSession,
    *,
    cert_status: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[tuple[Teacher, User]], int]:
    """平台管理员查看所有老师，可按 cert_status 筛选。"""
```

- `join(User)` 取 nickname/phone
- `cert_status` 非空时 `.where(Teacher.cert_status == cert_status)`
- 返回 `(rows, total)`

### 3.2 新增 schema `AdminTeacherItem`（`schemas/teacher.py`）

```python
class AdminTeacherItem(BaseModel):
    teacher_id: uuid.UUID   # = users.id
    nickname: str | None
    phone: str | None
    subject: str | None
    cert_status: str        # uncertified/pending/certified/rejected
    cert_doc_url: str | None
    max_students: int
    institution_id: uuid.UUID | None  # 所属机构（可空）
    monthly_paper_quota: int | None
    created_at: str         # ISO datetime

class AdminTeacherListOut(BaseModel):
    total: int
    items: list[AdminTeacherItem]
```

### 3.3 `GET /admin/teachers` 路由（`admin.py`）

```python
@router.get("/teachers", response_model=BaseResponse[AdminTeacherListOut])
async def list_teachers(
    db: DbDep, admin: AdminDep,
    cert_status: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
```

### 3.4 `AdminOverviewOut` 新增 `pending_teachers: int`

`admin_stats_service.get_overview()` 追加：
```python
from app.models.d1_users import Teacher
pending_teachers = (await db.execute(
    select(func.count()).select_from(Teacher).where(Teacher.cert_status == "pending")
)).scalar_one()
```

## 4. Admin Web 组件

### 4.1 `frontend/admin/src/views/TeacherCertReview.vue`（新建）

- **筛选**：cert_status select（pending/certified/rejected/全部）
- **表格**：nickname / phone / subject / cert_status 徽标 / 认证材料链接 / 操作
- **操作**：✅ 通过（approve=true）/ ❌ 拒绝（approve=false，optional reason）
- **状态徽标**：pending=橙、certified=绿、rejected=红、uncertified=灰
- 通过/拒绝后该行 cert_status 实时更新

### 4.2 `admin.ts` API 函数
```ts
listTeachersForAdmin(params): Promise<AdminTeacherListOut>
reviewTeacherCert(teacherId, approve, reason?): Promise<AdminTeacherItem>
```

### 4.3 `types.ts` 新增 `AdminTeacherItem` / `AdminTeacherListOut`

### 4.4 路由 + 侧边栏
- router: `{ path: 'teacher-cert', component: TeacherCertReview.vue }`
- MainLayout: `<el-menu-item index="/teacher-cert">👨‍🏫 教师认证审核</el-menu-item>`

### 4.5 Overview.vue 追加 pending_teachers 卡片

## 5. 测试策略（TDD）

`tests/api/test_admin_teacher_cert_review.py`：
1. `test_list_teachers_requires_admin` — 未鉴权 → 401
2. `test_list_all_teachers` — admin → 200 + items/total 结构
3. `test_filter_by_cert_status_pending` — 植入 pending 老师 → cert_status=pending 过滤有结果
4. `test_review_teacher_approve` — approve=True → cert_status='certified'
5. `test_review_teacher_reject` — approve=False → cert_status='rejected'
6. `test_overview_has_pending_teachers` — pending_teachers 字段存在且 ≥ 0

## 6. 影响范围

- 后端：`teacher_service.py`(+list_teachers_for_admin) + `schemas/teacher.py`(+2) + `admin.py`(+GET /teachers) + `admin_stats_service.py`(+pending_teachers) + `schemas/admin.py`(+pending_teachers)
- 前端：`TeacherCertReview.vue`(新建) + `admin.ts` + `types.ts` + `router` + `MainLayout.vue` + `Overview.vue`
- 测试：`tests/api/test_admin_teacher_cert_review.py`
- 零迁移、零花钱
