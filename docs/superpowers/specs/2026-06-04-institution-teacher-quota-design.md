# 机构端切片九：老师资源额度配置（出卷月额度，D-128）设计文档

> 含迁移 0021；dev-mock 无花钱。

## 目标

机构管理员在 admin web 给名下各老师配置「每月出卷上限」；老师出卷（创建作业）时校验本月额度，超额拒绝，未配置 = 不限。

## 背景与现状

- 需求 §1166：机构管理员可在后台配置各老师资源分配上限（如每月最多出 30 份卷），未配置默认不限。
- `assignment_service.create_assignment(db, *, teacher_id, class_id, title, questions, due_at)` 当前**无额度闸门**。
- `assignments` 有 `teacher_id` + `created_at`，可统计本月出卷数。
- `teachers` 模型可加列（需迁移）。`institution_service.list_teachers` 返回 `list[(Teacher, User)]`，`InstitutionTeacherOut`（D-121）已有 id/nickname/phone/subject/cert_status。
- **AI 批改额度不在本切片**：`essay_service.polish_essay` 是学生自用（按学生 tier 限额）；作业判分用规则 `_grade`（非 AI）；`grade_submission` 是老师人工打分。当前无老师侧 AI 批改入口可挂额度，故留待后续。

## 架构

迁移 0021 给 `teachers` 加 `monthly_paper_quota`（nullable int，NULL=不限）。机构管理员经 admin web 配置；`create_assignment` 加闸门：本月出卷数 ≥ 额度则拒绝。含迁移、无付费调用。

## 数据模型（迁移 0021）

`teachers` 加列 `monthly_paper_quota`（`sa.Integer`, nullable=True，NULL=不限）。模型 `d1_users.py` 的 `Teacher` 同步加列。沿用迁移范式（0017/0019 加列）。

## 后端组件

### `institution_service.py`（新增 + 改 list_teachers 返回）

```
set_teacher_quota(db, *, institution_id, teacher_id, monthly_paper_quota: int | None) -> Teacher
    # 校验 teacher.institution_id == institution_id，否则 AppError(404)
    # teacher.monthly_paper_quota = monthly_paper_quota（None 清除限制）
    # flush, return teacher
```

`list_teachers` 已返回 `(Teacher, User)`，API 层从 Teacher 读 `monthly_paper_quota`，无需改 service 签名。

### `assignment_service.create_assignment`（加闸门）

在 `await class_service._get_owned_class(...)` 之后、创建 Assignment 之前插入：

```python
teacher = await db.get(Teacher, teacher_id)
if teacher is not None and teacher.monthly_paper_quota is not None:
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    used = (await db.execute(
        select(func.count()).select_from(Assignment).where(
            Assignment.teacher_id == teacher_id,
            Assignment.created_at >= month_start,
        )
    )).scalar_one()
    if used >= teacher.monthly_paper_quota:
        raise AppError(code=403, message="本月出卷额度已用尽，请联系机构管理员")
```

需 import `Teacher`（`app.models.d1_users`）、`func`（已 import select；补 func）。

### API

机构管理员（`InstAdminDep`，机构来自 `current_user.institution_id`）：
- `PATCH /institution/teachers/{teacher_id}/quota`（body `TeacherQuotaUpdate`）→ `InstitutionTeacherOut`
- `GET /institution/teachers` 的 `InstitutionTeacherOut` 加 `monthly_paper_quota: int | None`

### schemas（`schemas/institution.py`）

- `InstitutionTeacherOut` 加 `monthly_paper_quota: int | None = None`
- `TeacherQuotaUpdate`：`monthly_paper_quota: int | None`

## 前端（admin web 老师管理页 `InstitutionTeachers.vue`）

- 表格加「月出卷额度」列：显示数字或「不限」。
- 每行加「设额度」按钮 → ElMessageBox.prompt 输入数字（留空=不限）→ 调 `setTeacherQuota` → 刷新。
- `api/institution.ts`：`setTeacherQuota(teacherId, quota: number|null)`；`InstitutionTeacher` interface 加 `monthly_paper_quota`。

## 测试

**service**：
- `set_teacher_quota` 设数值 / 设 None 清除；跨机构 teacher → 404。

**assignment service**：
- 老师配额度=2，本月已出 2 → `create_assignment` 抛 403；本月出 1 → 可出卷。
- 额度=None → 不限（可连续出卷）。

**api**：
- 管理员 PATCH quota → `GET /institution/teachers` 回显 `monthly_paper_quota`。
- 跨机构设额度 → 404。

**dev-mock**：纯 DB，无付费/LLM/媒体。

## 不做（后续切片）

AI 批改额度（无老师侧 AI 入口）、机构套餐总额度池/先到先得、按周/天额度、出卷进度条可视化、超额申请、老师端额度提示页。

## 影响范围

- 新增：迁移 `0021_teacher_paper_quota.py`。
- 修改：`d1_users.py`（Teacher 加列）、`institution_service.py`（set_teacher_quota）、`assignment_service.py`（出卷闸门）、`schemas/institution.py`、`api/v1/institution.py`；admin web `api/institution.ts` + `InstitutionTeachers.vue`；测试更新 `test_model_structure`（表数不变，仅列变，无需改）。
- 一个迁移 0021（teachers 加 nullable 列），无新依赖，无付费调用。
