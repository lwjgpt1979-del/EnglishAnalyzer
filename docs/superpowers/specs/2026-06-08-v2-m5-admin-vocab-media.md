# V2 M5: Admin Web 词力通媒体生成与审核 设计

**日期：** 2026-06-08
**状态：** 待实施
**参考：** 2026-06-03-vocab-image-media-design.md（后端已就绪）

## 1. 问题

词力通词卡支持「图背单词 + 英文描述 + 双音频」，后端 API 已全部就绪：
- `GET /admin/vocab` — 列出所有词（含 media_status 筛选）
- `POST /admin/vocab/{id}/generate-media` — AI 生成媒体（dev mock）
- `POST /admin/vocab/{id}/media/review` — 审核（approve/reject）
- `PUT /admin/vocab/{id}/media` — 编辑内容

但 Admin Web 没有对应页面，导致无法触发生成、无法审核，学生端词卡始终无图无音频无英文描述。

## 2. 目标

Admin Web 新增「词力通媒体」页面：
- 按 media_status 筛选（all / draft / published / retired）
- 按文本搜索（word 包含）
- 列表展示词、状态、预览 en_description、操作
- 🤖 一键生成媒体（dev mock）
- ✅ 审核通过 / ❌ 拒绝（draft → published / retired）
- ✏️ 编辑 en_description / image_urls
- 状态徽标色彩标识（draft=橙, published=绿, retired=灰）

## 3. 使用的后端 API

```
GET    /api/v1/admin/vocab?status=draft&search=happy&skip=0&limit=50
POST   /api/v1/admin/vocab/{id}/generate-media
POST   /api/v1/admin/vocab/{id}/media/review   body: {approve: bool}
PUT    /api/v1/admin/vocab/{id}/media           body: {en_description?, image_urls?, word_audio_url?, en_desc_audio_url?}
```

返回 `AdminVocabMediaItem`:
```ts
{
  id: string
  word: string
  phonetic?: string
  definitions: string[]
  image_urls: string[] | null
  en_description: string | null
  word_audio_url: string | null
  en_desc_audio_url: string | null
  media_status: 'draft' | 'published' | 'retired'
}
```

## 4. 前端组件

**`frontend/admin/src/views/VocabMedia.vue`**（新建）
- `el-select` 筛选状态 + `el-input` 搜索词
- `el-table` 展示词列表：word / 状态徽标 / en_description（truncated） / image数量 / 操作列
- 操作列：🤖生成 / ✅通过 / ❌拒绝 / ✏️编辑
- `el-dialog` 编辑弹窗：textarea en_description + el-input image_urls（每行一条 URL）

**`frontend/admin/src/api/admin.ts`** 追加：
```ts
export interface AdminVocabMediaItem { ... }
export function listVocabMedia(params): Promise<{items: AdminVocabMediaItem[], total: number}>
export function generateVocabMedia(id: string): Promise<AdminVocabMediaItem>
export function reviewVocabMedia(id: string, approve: boolean): Promise<AdminVocabMediaItem>
export function updateVocabMedia(id: string, body: {...}): Promise<AdminVocabMediaItem>
```

**`frontend/admin/src/types.ts`** 追加 `AdminVocabMediaItem` interface。

**路由 + 侧边栏**：
- router: `{ path: 'vocab-media', component: VocabMedia.vue }`
- MainLayout: `<el-menu-item index="/vocab-media">🔤 词力通媒体</el-menu-item>`（在 curriculum-units 后面）

## 5. 测试策略

**后端**（已有后端测试，本切片聚焦 API 鉴权 + 结构）：
- `GET /admin/vocab` 无鉴权 → 401
- `GET /admin/vocab` admin 鉴权 → 200 + `{items: [], total: 0}` 结构
- `POST /admin/vocab/{bad-id}/generate-media` admin → 404
- `POST /admin/vocab/{id}/generate-media` admin → 200 + 字段完整
- `POST /admin/vocab/{id}/media/review` admin approve=True → media_status='published'

**前端**：`cd frontend/admin && npm run build` 通过。

## 6. 影响范围

- 新增：`frontend/admin/src/views/VocabMedia.vue`
- 修改：`frontend/admin/src/api/admin.ts`、`types.ts`、`router/index.ts`、`layouts/MainLayout.vue`
- 新增：`tests/api/test_admin_vocab_media.py`（5 个 TDD 测试）
- 零迁移、零 LLM 花费（dev mock）

## 7. 不做

- 真实文生图 / TTS 接入（NotImplementedError 留接缝）
- 批量生成（单条即可，批量留后续）
- 图片直传 COS（dev mock URL 占位）
