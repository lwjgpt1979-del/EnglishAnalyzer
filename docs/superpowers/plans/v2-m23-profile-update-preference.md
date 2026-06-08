# V2 M23 Plan — 用户修改教材偏好

## 步骤

### 1. Backend
**a) `app/schemas/auth.py`**：新增 `UpdateProfileRequest`
```python
class UpdateProfileRequest(BaseModel):
    preferred_textbook_version: str | None = None
    preferred_grade: str | None = None
    preferred_semester: str | None = None
```

**b) `app/api/v1/auth.py`**：新增 `PATCH /profile`
```python
@router.patch("/profile", response_model=BaseResponse[dict])
async def update_profile(body: UpdateProfileRequest, db: DbDep, current_user: UserDep):
    if body.preferred_textbook_version is not None:
        current_user.preferred_textbook_version = body.preferred_textbook_version
    if body.preferred_grade is not None:
        current_user.preferred_grade = body.preferred_grade
    if body.preferred_semester is not None:
        current_user.preferred_semester = body.preferred_semester
    await db.flush()
    return make_ok({
        "preferred_textbook_version": current_user.preferred_textbook_version,
        "preferred_grade": current_user.preferred_grade,
        "preferred_semester": current_user.preferred_semester,
    })
```

### 2. Frontend
**a) `api/auth.ts`**：新增 `updateProfile(data)` → `PATCH /api/v1/auth/profile`

**b) `pages/profile/index.vue`**：
- 用户信息卡片下方显示当前教材偏好（教材版本 / 年级 / 学期）
- 「修改教材偏好」按钮 → 展示三个 picker
- 确认提交后更新 `auth.user` 本地状态

### 3. TDD
新建 `tests/api/test_update_profile.py`
- `test_can_update_preferred_textbook`
- `test_partial_update_preserves_other_fields`

## 文件修改清单
- `backend/app/schemas/auth.py`（新增 schema）
- `backend/app/api/v1/auth.py`（新增 PATCH 端点）
- `frontend/miniprogram/src/api/auth.ts`（新增函数）
- `frontend/miniprogram/src/pages/profile/index.vue`（添加编辑 UI）
- `tests/api/test_update_profile.py`（新建）
