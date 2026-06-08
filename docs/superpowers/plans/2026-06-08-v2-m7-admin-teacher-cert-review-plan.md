# V2 M7: Admin 教师认证审核 实施计划

**日期：** 2026-06-08
**来源 Spec：** 2026-06-08-v2-m7-admin-teacher-cert-review.md

## 执行顺序

### Step 1 — TDD 写测试（RED）
写 `tests/api/test_admin_teacher_cert_review.py`，6 个测试。
用 `python3 -c "import tests.api.test_admin_teacher_cert_review"` 验证 ImportError（RED）。

### Step 2 — 后端 schemas
- `schemas/teacher.py`：追加 `AdminTeacherItem` + `AdminTeacherListOut`
- `schemas/admin.py`：`AdminOverviewOut` 加 `pending_teachers: int`

### Step 3 — 后端 service
- `teacher_service.py`：新增 `list_teachers_for_admin(db, *, cert_status, skip, limit)`
- `admin_stats_service.py`：`get_overview()` 追加 pending_teachers 查询

### Step 4 — 后端路由
- `admin.py`：`GET /admin/teachers` + import AdminTeacherListOut

### Step 5 — 验证 GREEN
`python3 -c "from tests.api.test_admin_teacher_cert_review import *; print('import ok')"` 通过。

### Step 6 — Admin Web Frontend
- `types.ts`：追加 `AdminTeacherItem` + `AdminTeacherListOut`
- `api/admin.ts`：追加 `listTeachersForAdmin()` + `reviewTeacherCert()`
- `views/TeacherCertReview.vue`：新建（筛选+表格+审核操作）
- `router/index.ts`：插入 `teacher-cert` 路由
- `layouts/MainLayout.vue`：插入菜单项
- `views/Overview.vue`：追加 pending_teachers 卡片

### Step 7 — Build 验证
`cd frontend/admin && npm run build` 通过

### Step 8 — Commit
`feat(admin): V2 M7 教师认证审核页面（列表+审核+大盘计数）`
