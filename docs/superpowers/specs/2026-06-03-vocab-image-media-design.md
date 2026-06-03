# 词力通「图背单词 + 英文描述 + 双音频」设计（P1 / 词力通深化）

**日期：** 2026-06-03
**状态：** 已与用户确认，待转 writing-plans

## 1. 目标

为词力通词卡增加"可理解性"媒体：每个单词配 **多张图**、一段 **英文可理解性描述**（用英语解释英语）、以及 **两段音频**（单词发音 + 英文描述朗读）。对标百词斩「图背单词」，并叠加听/读可理解性输入。

**第一刀范围（本设计）：** 仅做**展示层 + 运营生成/审核**。学生端词卡展示图集 + 英文描述 + 两个播放按钮。
**明确不做（后续切片）：** 看图选词题型（需 ≥4 词有图做干扰项、前端较重）；真·文生图 / 真 TTS 的厂商接入（本设计只留 config 接缝，dev-mock 占位）。

## 2. 成本与安全边界（关键）

- **本切片一分钱不花**：图片、音频均走 **dev-mock 占位 URL**；英文描述走现有 DeepSeek LLM 的 dev-mock。可完整跑通 + 可测试。
- **真·文生图 + 真 TTS 是两个独立 config 接缝**（provider 抽象），**等用户确认预算 + 通过安全渠道提供 key 后再开**；key 绝不进聊天/不进 git；`backend/.env` 不提交。
- 不在本切片实现真实厂商调用与真实 COS 上传逻辑（dev-mock 返回占位 URL；真实上传留接缝）。

## 3. 数据模型

`vocabulary_words` 新增 5 个 nullable 字段（迁移 0016，向后兼容；存量行全 NULL）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `image_urls` | JSONB | 多张配图 URL 数组（如 `["https://.../1.png", ...]`） |
| `en_description` | Text | 英文可理解性描述（用英语解释词义） |
| `word_audio_url` | String | 单词本身发音音频 URL |
| `en_desc_audio_url` | String | 英文描述朗读音频 URL |
| `media_status` | String，默认 `'draft'` | 媒体审核态：`draft`/`published`/`retired`；学生端只看 `published` |

> 沿用 D-095/096 的"半自动审核闸门"哲学：生成默认 `draft`，运营审核 → `published`，学生端只见 published。

## 4. 组件（单一职责、可独立测试）

### 4.1 `vocab_media_provider.py`（provider 抽象，类比 `llm_provider`）
- `is_image_dev_mode()` / `is_tts_dev_mode()` —— 统一 dev-mock 判定（key 为 placeholder 时 dev-mock）。
- `generate_images(prompt: str, n: int) -> list[str]` —— dev-mock 返回 n 个确定性占位 URL（如 `https://placehold.co/600x400?text=<word>-i`）；真 provider 接缝读 `IMAGE_PROVIDER`/`IMAGE_API_KEY`（dev 为 placeholder）。
- `generate_tts(text: str) -> str` —— dev-mock 返回确定性占位音频 URL；真 provider 接缝读 `TTS_PROVIDER`/`TTS_API_KEY`。
- 英文描述不在此模块——复用现有 `llm_provider.chat_completion`（已具 dev-mock）。

### 4.2 `vocab_media_service.py`
- `generate_for_word(db, *, word_id) -> VocabularyWord`：
  1. 取词；2. LLM 生成 `en_description`（dev-mock 出固定英文描述）；3. provider 生成 `image_urls`（n 张）、`word_audio_url`、`en_desc_audio_url`；4. 写库，`media_status='draft'`。
- `list_words_for_media_review(db, *, media_status='draft', skip, limit) -> (rows, total)`。
- `review_word_media(db, *, word_id, approve) -> VocabularyWord`：approve→`published` / reject→`retired`。
- `update_word_media(db, *, word_id, image_urls?, en_description?, word_audio_url?, en_desc_audio_url?)` —— 运营人工修订。

### 4.3 运营 admin API（复用 `admin.py` + `require_role("platform_admin")`）
- `POST /admin/vocab/{word_id}/generate-media` —— 触发生成（dev-mock）。
- `GET /admin/vocab?media_status=draft&skip=&limit=` —— 待审媒体列表（含全字段）。
- `POST /admin/vocab/{word_id}/media/review` body `{approve}` —— 通过/驳回。
- `PUT /admin/vocab/{word_id}/media` body `{image_urls?, en_description?, word_audio_url?, en_desc_audio_url?}` —— 编辑。

### 4.4 学生端（`vocabulary_service` + 小程序词力通页）
- `WordCardOut` 增 `image_urls` / `en_description` / `word_audio_url` / `en_desc_audio_url`（仅当该词 `media_status='published'` 时填充，否则为空/None）。
- `get_daily_task` 返回的词卡带上这些字段（published 才有）。
- 词力通页词卡：展示**图集**（横向滑动/网格）+ **英文描述** + **两个播放按钮**（🔊 单词 / 🔊 英文描述）。无媒体时回退到现有纯文本词卡（向后兼容）。

## 5. 数据流

```
运营后台点"生成媒体"
  → POST /admin/vocab/{id}/generate-media
  → vocab_media_service.generate_for_word
      → llm_provider.chat_completion  → en_description（dev-mock 文本）
      → vocab_media_provider.generate_images → image_urls（dev-mock 占位图）
      → vocab_media_provider.generate_tts ×2 → word_audio_url + en_desc_audio_url（dev-mock 占位音频）
      → 写库，media_status='draft'
  → 运营审核 POST .../media/review {approve:true} → media_status='published'
  → 学生 GET /vocabulary/daily-task → published 词带回 图+英文描述+双音频
  → 词力通词卡展示图集/英文描述/播放按钮
```

## 6. 错误处理
- 词不存在 → `AppError(404)`。
- 生成时 LLM/provider 异常 → 抛 `AppError(502/500)`（dev-mock 不会触发）。
- 学生端：词无 published 媒体 → 字段为空，前端回退纯文本词卡，不报错。

## 7. 测试策略
- provider dev-mock：`generate_images` 返回 n 个确定 URL；`generate_tts` 返回确定 URL；判定函数。
- service：`generate_for_word` 写满 5 字段且 `media_status='draft'`；review approve→published / reject→retired；update 改字段；不存在抛错。
- admin API：生成→列表(draft)→编辑→审核(published) 流；非管理员 403。
- 学生端：daily-task 仅返回 published 媒体（draft 词不带媒体字段）。
- 前端：`npm run build:mp-weixin` 编译通过。

## 8. 影响范围
- 后端：迁移 0016 + `models/d5_learning.py`(VocabularyWord 加字段) + `services/vocab_media_provider.py`(新) + `services/vocab_media_service.py`(新) + `services/vocabulary_service.py`(WordCardOut 带媒体) + `schemas/vocabulary.py`(字段) + `api/v1/admin.py`(4 端点) + `config.py`(IMAGE_*/TTS_* 占位配置) + 测试。
- 前端：`pages/vocabulary/index.vue`(词卡媒体展示) + `types/api.ts`。
- 无花钱（全 dev-mock）。

## 9. 后续切片（不在本设计）
- 看图选词题型（4 图选 1）。
- 真·文生图 provider 接入（预算 + key）。
- 真 TTS provider 接入（预算 + key）。
- 真实 COS 图片/音频上传与生命周期管理。
- 每日上限/词库范围按档位（已在 D-100 备注）。
