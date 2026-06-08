# V2 M5: Admin Web 词力通媒体 实施计划

**日期：** 2026-06-08
**来源 Spec：** 2026-06-08-v2-m5-admin-vocab-media.md

## 执行顺序

### Step 1 — TDD 后端（RED → GREEN 验证）
写 `tests/api/test_admin_vocab_media.py`：
1. `test_list_vocab_requires_admin` — 未鉴权 → 401
2. `test_list_vocab_returns_structure` — admin → 200 + items/total 字段
3. `test_generate_vocab_media_404` — 不存在 word_id → 404
4. `test_generate_vocab_media_success` — 有效词 → 200 + media_status 字段
5. `test_review_vocab_media_approve` — approve=True → media_status='published'

验证：`python3 -c "import tests.api.test_admin_vocab_media"` ImportError（RED）。

### Step 2 — 查看后端 API 确认字段名
读 `backend/app/api/v1/admin.py` vocab 部分，确认：
- `/admin/vocab` 返回结构（items/total）
- `/admin/vocab/{id}/generate-media` 路径参数名
- review body 字段（approve: bool）

### Step 3 — Admin Web Types + API
- `frontend/admin/src/types.ts`：追加 `AdminVocabMediaItem`
- `frontend/admin/src/api/admin.ts`：追加 4 个函数

### Step 4 — VocabMedia.vue（新建）
- 筛选栏：状态 select + 搜索 input
- 列表表格：word / 状态徽标 / en_description 预览 / image 数量 / 操作
- 操作：🤖生成 / ✅通过 / ❌拒绝 / ✏️编辑（弹窗）
- 编辑弹窗：en_description textarea + image_urls text area（每行一条 URL）

### Step 5 — 路由 + 侧边栏
- `router/index.ts`：插入 `vocab-media` 路由
- `MainLayout.vue`：插入菜单项 `🔤 词力通媒体`

### Step 6 — 前端 Build 验证
`cd frontend/admin && npm run build`

### Step 7 — Commit
`git add` + commit message: feat(admin): V2 M5 词力通媒体生成审核
