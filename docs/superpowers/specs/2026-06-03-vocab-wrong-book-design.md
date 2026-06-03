# 词力通错词本联动 设计（P1 / 词力通深化）

**日期：** 2026-06-03
**状态：** 已与用户确认，待转 writing-plans
**参考：** 需求文档 §6.4.6 错词本（与错题系统深度联动）

## 1. 目标

词力通内单词答错自动进错词本、熟练度重置、错词优先复习、掌握后自动移出；并提供错词本列表给学生查看。对标百词斩错词本。

**第一刀范围：** 仅"词力通内答错"这一错词来源 + 错词优先复习 + 掌握移出 + 错词本列表（含前端页）。
**明确不做（后续切片）：** 试卷 AI 错因"词汇不熟"自动入错词本、老师手动标注（§6.4.6 另两源，需跨系统接线）；学情报告"词汇薄弱点"接错词本（留后续）；错词本按词性/频率筛选。

## 2. 数据模型

`vocabulary_learning` 新增 2 字段（迁移 0017，向后兼容；存量行默认 false/0）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `is_wrong` | Boolean，默认 false | 是否在错词本中 |
| `wrong_count` | Integer，默认 0 | 累计答错次数（错得越多复习越靠前） |

## 3. 核心逻辑（改造 `vocabulary_service.submit_answer`）

现有 `submit_answer` 已按 SM-2 更新 repetitions/interval/level。在其基础上：
- **答错**（`correct=False`）：`is_wrong=True`，`wrong_count += 1`。（熟练度重置由现有 SM-2 完成：reps=0、level→new）
- **答对且升到 mastered**（更新后 `level == "mastered"`，即现有 `_level_for(reps)` 判定）：`is_wrong=False`（自动移出错词本）。
- 其它情况：`is_wrong`/`wrong_count` 不变。

> 用 `level == "mastered"` 判定移出，自动与现有 `_level_for`（reps≥4→mastered）对齐，不硬编码 reps 阈值。

## 4. 错词优先复习（改造 `get_daily_task`）

复习词查询排序由 `next_review_at ASC` 改为 **`is_wrong DESC, wrong_count DESC, next_review_at ASC`**（错词最前、错得多的更靠前）。新词逻辑不变。

## 5. 错词本接口

新增 `GET /vocabulary/wrong-words`（`get_current_user`）：
- 返回该生 `is_wrong=True` 的词，join `vocabulary_words`，按 `wrong_count DESC` 排序。
- 每项含：word、phonetic、definitions、wrong_count、level、以及 published 媒体（image_urls/en_description/word_audio_url/en_desc_audio_url，复用 D-101 `_to_card` 的 published 规则）。
- service：`list_wrong_words(db, *, student_id, skip, limit) -> (items, total)`。
- schema：`WrongWordItem` + `WrongWordListOut`。

## 6. 前端

- 词力通页（`pages/vocabulary/index.vue`）顶部/完成页加「错词本」入口（navigateTo 新页）。
- 新页 `pages/vocabulary/wrong-book.vue`：拉 `GET /vocabulary/wrong-words`，列表展示错词（单词 + 释义 + 错误次数徽标 + 熟练度），空态文案。

## 7. 错误处理
- 错词本接口无错词 → 返回空列表（前端空态）。
- submit_answer 改造不改变其既有错误语义（词不存在等）。

## 8. 测试策略
- service：答错置 is_wrong=True 且 wrong_count 累加；答对升 mastered 移出（is_wrong=False）；中间态不误改；错词优先复习排序（错词排在普通到期复习词前）；list_wrong_words 只返回 is_wrong=True 且按 wrong_count 降序。
- API：`GET /vocabulary/wrong-words` 鉴权 + 返回结构 + 只含错词；未登录 401。
- 前端：`npm run build:mp-weixin` 通过。

## 9. 影响范围
- 后端：迁移 0017 + `d5_learning.py`(VocabularyLearning 加 2 字段) + `vocabulary_service.py`(submit_answer/get_daily_task 改造 + list_wrong_words) + `schemas/vocabulary.py`(WrongWordItem/WrongWordListOut) + `api/v1/vocabulary.py`(新端点) + 测试。
- 前端：`pages/vocabulary/index.vue`(入口) + `pages/vocabulary/wrong-book.vue`(新) + `pages.json` + `api/vocabulary.ts` + `types/api.ts`。
- 无花钱。

## 10. 后续切片（不在本设计）
- 试卷 AI 错因 / 老师标注 两个错词来源。
- 学情报告"词汇薄弱点"接错词本。
- 错词本筛选/分类、错词专项练习入口。
