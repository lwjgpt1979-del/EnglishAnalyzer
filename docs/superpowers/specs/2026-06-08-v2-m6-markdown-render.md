# V2 M6: 小程序 Markdown 渲染 设计

**日期：** 2026-06-08
**状态：** 待实施

## 1. 问题

AI 生成的内容（kp-content.vue 的 content_md、essay/detail.vue 的 polished_text）包含 Markdown 标记，
但小程序用 `<text>` 原样展示，学生看到 `## 标题`、`**加粗**`、`- 列表` 等裸文本。

## 2. 解决方案

写一个轻量 `md2html(md: string): string` 工具函数，将 Markdown 转为 WeChat miniprogram `rich-text` 支持的 HTML 片段。

支持的格式（足以覆盖 AI 输出）：
- `## 标题` → `<h2>`
- `### 小标题` → `<h3>`  
- `**粗体**` → `<strong>`
- `- 列表项` → `<li>`（自动包裹 `<ul>`）
- `\n\n` 段落分隔 → `<p>`
- 其他普通行 → 保持换行（`<br>`）

## 3. 实现范围

### 新建 `frontend/miniprogram/src/utils/md.ts`
纯函数 `md2html(md: string): string`

### 修改 `frontend/miniprogram/src/pages/curriculum/kp-content.vue`
```html
<!-- 旧 -->
<text class="md">{{ currentContent.content_md }}</text>
<!-- 新 -->
<rich-text :nodes="md2html(currentContent.content_md)" />
```

### 修改 `frontend/miniprogram/src/pages/essay/detail.vue`（可选）
如果 polished_text 含 Markdown，同样用 rich-text 渲染。
先检查实际 polished_text 格式再决定。

## 4. rich-text 限制（WeChat miniprogram）

- `<a>`、`<script>` 等不支持
- 内联 style 中 `rpx` 不支持（需用 `px` 或 `em`）
- 不能绑定事件
- 使用 HTML string 格式（`nodes` = string）

## 5. 测试

- `md2html('## 标题')` → 含 `<h2>`
- `md2html('**加粗**')` → 含 `<strong>`
- `md2html('- 列表')` → 含 `<li>`
- `md2html('')` → `''`
- `npm run build:mp-weixin` 通过

## 6. 影响范围

- 新增：`frontend/miniprogram/src/utils/md.ts`
- 修改：`kp-content.vue`（import md2html + rich-text）
- 修改：`essay/detail.vue`（按需）
- 零迁移、零花钱
