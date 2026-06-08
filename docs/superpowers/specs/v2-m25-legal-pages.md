# V2 M25 — 协议/隐私政策正式文案

## 背景
`pages/account/agreement.vue` 和 `pages/account/privacy.vue` 当前为手写占位内容，
真实法务模板已在 `docs/legal/用户协议-模板.md` 和 `docs/legal/隐私政策-模板.md`。
微信小程序审核会逐条核对隐私政策与「用户隐私保护指引」是否一致。
`docs/上线前清单.md` H 项明确标注为软阻塞。

## 目标
1. 用 `docs/legal/隐私政策-模板.md` 完整内容替换 `pages/account/privacy.vue` 的占位文本
2. 用 `docs/legal/用户协议-模板.md` 完整内容替换 `pages/account/agreement.vue` 的占位文本
3. 两个模板中含 `{{...}}` 占位符的部分保留提醒标注（等法务填充真实信息）

## 验收标准
- 协议页显示完整条款（不再是 7 条笼统占位）
- 保留所有 `{{公司全称}}` 等待填充的占位符（用红色或加粗标注）
- `complete-profile.vue` 中协议勾选链接正确指向这两个页面
