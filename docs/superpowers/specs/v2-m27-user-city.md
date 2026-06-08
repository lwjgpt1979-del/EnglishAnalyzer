# V2 M27 — 用户城市归属

## 背景
需求文档（Section 二.4）规定所有用户和机构在系统中均记录**归属城市**（city_code）。
`users` 表已有 `city_code` 和 `city_source` 字段，但：
- `complete-profile.vue` 注册流程没有城市选择器
- `GET /auth/profile` 不返回 `city_code`
- 无法在注册后修改城市

## 目标
1. `complete-profile.vue` 添加省/市两级城市选择器（注册时填写，可选）
2. `PATCH /auth/profile`（M23 新增）支持更新 `city_code`
3. profile.vue 展示城市归属（可修改）

## 技术方案
- 省市数据：静态 JSON 文件（省 + 34 个省级行政区的主要城市，约 3-4 KB）
- `city_code` 格式：`CN-GD-广州` 或简单 `广州市` 字符串（MVP 阶段用城市名即可）
- `city_source = 'self_selected'`（注册时填写）

## 验收标准
- 注册完善资料时可选城市（可跳过）
- 已注册用户可在 profile 页修改城市
- city_code 写入 users 表
