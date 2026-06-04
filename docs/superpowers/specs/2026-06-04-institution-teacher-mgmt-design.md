# 机构端切片二：名下老师账号管理（D-121）设计文档

> 机构端 MVP 第二切片。零迁移、dev-mock 无花钱。

## 目标

机构管理员可在 admin web 生成机构加入邀请码、查看名下老师列表、把老师移出机构；老师在小程序输 6 位码加入机构。

## 背景与现状

- `InviteCode` 模型已存在：`code(6)`/`type`/`issuer_id`/`target_id`/`expires_at`/`used_at`，`invite_code_type` 枚举含 `institution_join`。
- `relative_service.generate_invite_code` 已有 6 位码生成 + 查重范式可复用。
- `teachers.institution_id`（nullable，FK→institutions）已存在；`users.institution_id`（D-120 新增）记录机构管理员归属。
- `institution_service`（D-120）已有 get_profile/update_profile/get_overview；`/institution/*` 路由 + `InstAdminDep` 已就绪。
- 老师为微信登录用户，role=teacher，有 `teachers` 行（PK=users.id）。

## 架构

复用 `InviteCode`（`institution_join`）打通：机构管理员（admin web）生成邀请码 → 老师（小程序）输码加入（设 `teachers.institution_id`）→ 管理员后台看名下老师、移出机构（解绑 = `teachers.institution_id=None`）。机构归属：邀请码消费时机构来自 `issuer.institution_id`。全程零迁移、无付费调用。

## 后端组件

### 1. `institution_service.py`（新增函数）

```
generate_join_code(db, *, institution_id, issuer_id) -> InviteCode
    # type="institution_join"，6 位码查重，expires_at = now + 7 天，issuer_id=管理员
list_teachers(db, *, institution_id) -> list[Teacher]   # join User 取展示字段
remove_teacher(db, *, institution_id, teacher_id) -> None
    # 校验 teacher.institution_id == institution_id，否则 AppError(404)；置 None
```

### 2. `teacher_service.py`（新增函数）

```
join_institution(db, *, teacher_user_id, code) -> Teacher
    # 校验码：type=institution_join, used_at IS NULL, expires_at > now，否则 AppError(400)
    # 机构 = issuer(User).institution_id；issuer 无机构 → AppError(400)
    # teacher 已属某机构 → AppError(409)
    # 设 teacher.institution_id = 机构；code.used_at = now；code.target_id = teacher_user_id
```

### 3. API

机构管理员（`InstAdminDep = require_role("institution_admin")`，机构来自 `current_user.institution_id`）：

- `POST /institution/teachers/invite-code` → `InviteCodeOut`
- `GET /institution/teachers` → `list[InstitutionTeacherOut]`
- `DELETE /institution/teachers/{teacher_id}` → `BaseResponse[dict]`（移出机构）

老师（`require_role("teacher")`）：

- `POST /teacher/join-institution`（body `JoinInstitutionRequest`）→ `InstitutionTeacherOut`（加入后的本人信息）

### 4. `schemas/institution.py`（新增）

- `InviteCodeOut`：code: str / expires_at: datetime
- `InstitutionTeacherOut`：id: uuid / nickname: str|None / phone: str|None / subject: str|None / cert_status: str
- `JoinInstitutionRequest`：code: str

## 前端

### admin web

- `views/InstitutionTeachers.vue`：「生成邀请码」按钮（弹窗显示 code + 有效期，可复制）、老师列表表格（昵称/电话/科目/认证状态）、每行「移出机构」按钮（二次确认）。
- `api/institution.ts`：`generateTeacherInviteCode / listTeachers / removeTeacher`。
- router：加 `institution/teachers` 路由（meta.roles=['institution_admin']）。
- MainLayout：institution_admin 菜单加「老师管理」第三项。

### 小程序老师端

- `pages/teacher/join-institution.vue`：输 6 位码 → 调 join → 成功 toast + 返回。
- `api/teacher.ts`：`joinInstitution(code)`。
- 老师端入口（老师页或个人中心）加「加入机构」按钮。

## 测试

**service**：
- `generate_join_code` 生成 institution_join 码、可查到。
- `join_institution` 成功设 institution_id + used_at；已属机构 → 409；过期/已用码 → 400。
- `list_teachers` 按机构隔离（不含他机构老师）。
- `remove_teacher` 解绑成功；移除他机构老师 → 404。

**api**：
- 管理员生成码 → 老师 join → 管理员列表可见该老师 → 移除后列表不含。
- A 机构管理员 DELETE B 机构老师 → 404。
- platform_admin 访问 `/institution/teachers` → 403（沿用 D-120 鉴权）。

**dev-mock**：纯 DB，无 LLM/媒体/支付。

## 不做（后续切片）

企业微信通知（老师账号变更）、老师资源额度配置、branch_admin 分级、老师资料编辑、邀请码撤销/历史列表。

## 影响范围

- 新增：admin web `InstitutionTeachers.vue`；小程序 `pages/teacher/join-institution.vue`。
- 修改：`institution_service.py`、`teacher_service.py`、`schemas/institution.py`、`api/v1/institution.py`、`api/v1/teacher.py`；admin web `api/institution.ts`、`router/index.ts`、`MainLayout.vue`；小程序 `api/teacher.ts`、老师端入口、`pages.json`。
- 无数据库迁移，无新依赖，无付费调用。
