# V2 M6: Markdown 渲染 实施计划

**日期：** 2026-06-08
**来源 Spec：** 2026-06-08-v2-m6-markdown-render.md

## 执行顺序

### Step 1 — TDD：测试 md2html 工具函数
写 `tests/frontend/test_md2html.ts`（或直接在 Node 环境验证）。
由于 pytest 环境无 Node，用 python3 字符串验证规则后实现。

### Step 2 — 实现 `src/utils/md.ts`
规则（按优先顺序处理）：
1. h2: `^## (.+)$` → `<h2>$1</h2>`
2. h3: `^### (.+)$` → `<h3>$1</h3>`
3. 列表行: `^- (.+)$` → 收集成 `<ul><li>...</li></ul>`
4. 粗体: `**(.+?)**` → `<strong>$1</strong>`
5. 段落: 连续非空行分段
6. 空行: `\n\n+` → 段间分隔

### Step 3 — kp-content.vue
- import md2html
- `<text class="md">{{ currentContent.content_md }}</text>` → `<rich-text :nodes="md2html(currentContent.content_md)" />`
- 删除或调整 `.md` CSS（可保留容器样式）

### Step 4 — essay/detail.vue
- 检查 polished_text 格式（确认有 markdown 再改）
- 同样改为 rich-text

### Step 5 — Build 验证
`cd frontend/miniprogram && npm run build:mp-weixin`

### Step 6 — Commit
`feat(miniprogram): V2 M6 KP内容 Markdown 渲染（rich-text）`
