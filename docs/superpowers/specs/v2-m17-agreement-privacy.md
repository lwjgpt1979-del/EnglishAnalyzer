# V2 M17 — 用户协议与隐私政策页面

## 背景
`account/settings.vue` 的「用户协议」和「隐私政策」入口当前只显示
`'协议占位（MVP）'` toast，从未跳转真实页面。

## 目标
1. 创建 `pages/account/agreement.vue` — 用户协议静态页面
2. 创建 `pages/account/privacy.vue` — 隐私政策静态页面
3. 注册到 `pages.json`
4. `settings.vue` 改为 `uni.navigateTo` 跳转

## 验收标准
- 点击「用户协议」/「隐私政策」能正常跳转
- 页面显示标题 + 基本条款内容（MVP 级别）
