# V2 M8 Spec: relative/student-view 代付迁移至 V2 学期购买

## 问题
`frontend/miniprogram/src/pages/relative/student-view.vue` 的"为孩子代付"功能：
- 使用 V1 月付定价（¥9/¥19/¥39/月），线上已不再使用
- 调用 `createOrder({ duration_months: 1, ... })` — V1 接口
- 没有教材版本 / 年级 / 学期选择，无法生成正确 V2 学期订单

## 目标
将代付模块迁移至 V2 学期购买模式，与 `semester-purchase.vue` 保持一致的定价和接口。

## 需求

### 功能需求
1. **选学期**：展示教材版本、年级、学期选择器（与 semester-purchase.vue 相同选项）
2. **选套餐**：展示 3 档价格 — 基础版 ¥39、Pro ¥79、ProMax ¥159（/学期）
3. **代付参数**：`createOrder` 携带 `semesters: [{ textbook_version, grade, semester }]` 和 `target_student_id`
4. **不再传 `duration_months`**

### 选项范围（与 semester-purchase.vue 保持同步）
- 教材版本：译林版 / 人教版 / 北师大版
- 年级：小学3年级 … 小学6年级、初中7年级 … 初中9年级
- 学期：上 / 下

### UX
- 代付卡片标题改为"为孩子购买学期会员"
- 价格显示：¥XX /学期
- 代付按钮文字：`代付 ¥{price}`

## 影响范围
- `frontend/miniprogram/src/pages/relative/student-view.vue`（纯前端修改）
- 无后端变更
