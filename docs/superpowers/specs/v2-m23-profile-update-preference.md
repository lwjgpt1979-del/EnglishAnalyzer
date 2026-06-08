# V2 M23 — 用户修改教材偏好

## 背景
`complete-profile` 接口在注册时设置了 `preferred_textbook_version/grade/semester`，
但用户注册后无任何入口更改这些偏好。首页「开始学习」卡片、学期购买页都依赖这三个字段。
如果用户升年级或换教材版本，无法更新。

## 目标
1. backend：新增 `PATCH /auth/profile` 端点，支持更新 `preferred_textbook_version`、`preferred_grade`、`preferred_semester`（三字段可选）
2. frontend：`profile/index.vue` 用户信息卡片下方显示当前教材偏好，并提供「修改」入口
3. 点击「修改」展示三个 picker（教材版本 / 年级 / 学期），确认后提交

## 响应
```
PATCH /api/v1/auth/profile
body: { preferred_textbook_version?, preferred_grade?, preferred_semester? }
response: { preferred_textbook_version, preferred_grade, preferred_semester }
```

## 验收标准
- 修改后首页「开始学习」卡片文案立即更新
- auth.user 本地缓存同步更新
- 三个字段均可选，只传需要修改的字段
