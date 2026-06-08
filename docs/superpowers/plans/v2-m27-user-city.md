# V2 M27 Plan — 用户城市归属

## 步骤

### 1. 静态城市数据
新建 `frontend/miniprogram/src/data/cities.ts`：
```ts
export const PROVINCES = ['北京市', '上海市', '广东省', '江苏省', ...]
export const CITIES: Record<string, string[]> = {
  '北京市': ['北京市'],
  '广东省': ['广州市', '深圳市', '珠海市', ...],
  ...
}
```
约 30 个省 + 主要城市，文件 < 10 KB。

### 2. Backend `PATCH /auth/profile` 支持 city_code
在 M23 的 `UpdateProfileRequest` 新增 `city_code: str | None = None`，写入 `users.city_code`、`city_source = 'self_selected'`。

### 3. `complete-profile.vue` 添加城市选择
- 省级 picker → 市级 picker（两级联动）
- 可跳过（nullable）
- 提交时带 `city_code`

### 4. `profile/index.vue` 展示城市
- 用户信息行显示 `city_code`（可点击修改）

### 5. TDD
`tests/api/test_user_city.py`
- `test_can_set_city_in_complete_profile`
- `test_can_update_city_via_patch`

## 文件修改清单
- `frontend/miniprogram/src/data/cities.ts`（新建）
- `frontend/miniprogram/src/pages/auth/complete-profile.vue`（添加城市 picker）
- `frontend/miniprogram/src/pages/profile/index.vue`（展示 + 编辑城市）
- `backend/app/schemas/auth.py`（UpdateProfileRequest 加 city_code）
- `backend/app/api/v1/auth.py`（PATCH /profile 写 city_code + city_source）
- `tests/api/test_user_city.py`（新建）
