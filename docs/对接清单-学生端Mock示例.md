# 学生端 API 请求/响应 Mock 示例(小程序前端 mock 用)

> 配套 [对接清单](对接清单-KP-First新API.md)。统一前缀 `/api/v1`,需带 `Authorization: Bearer <学生JWT>`。
> 所有响应统一包:`{ "code": 200, "message": "ok", "data": <载体>, "timestamp": 1718700000 }`;
> 失败为 `{ "code": <非200>, "message": "<原因>", "data": null, "timestamp": ... }`。
> 下文每条只示 **请求** 与 **data** 内容(省略外层 code/message/timestamp,挂载到 data 即可)。
> 示例里的 uuid / 时间均为占位,字段名与后端 schema 一一对应。

---

## 1. 个人知识图谱(R4)

### GET `/student-kp/graph?include_all=false`
请求:query `include_all`(bool,默认 false)
```json
{
  "summary": { "in_scope": 42, "practiced": 18, "weak": 5, "mastered": 9 },
  "items": [
    {
      "node_id": "7b1c0a2e-1111-4a00-9c10-000000000001",
      "name": "定语从句",
      "axis": "knowledge",
      "node_kind": "句法",
      "mastery": null,
      "practice_count": 6,
      "wrong_count": 4,
      "source_tags": ["practice", "wrong_hit"],
      "in_scope": true,
      "status": "weak"
    },
    {
      "node_id": "7b1c0a2e-1111-4a00-9c10-000000000002",
      "name": "一般现在时",
      "axis": "knowledge",
      "node_kind": "语法",
      "mastery": 1.0,
      "practice_count": 8,
      "wrong_count": 0,
      "source_tags": ["practice"],
      "in_scope": true,
      "status": "mastered"
    }
  ]
}
```
> `status` ∈ `mastered|weak|practiced|unlearned`;`include_all=true` 时还会返回 `practice_count=0` 的 `unlearned` 项。

### POST `/student-kp/enroll`
请求:无 body(用用户教材偏好)。未设教材偏好 → `code 400 "请先设置教材版本/年级/学期"`。
```json
{ "enrolled": 42 }
```

### GET `/student-kp/trend?node_id=<uuid>&days=30`
请求:query `node_id`(必), `days`(默认 30)
```json
{
  "node_id": "7b1c0a2e-1111-4a00-9c10-000000000001",
  "points": [
    { "date": "2026-06-16", "accuracy": 0.5,  "correct": 1, "wrong": 1 },
    { "date": "2026-06-17", "accuracy": 0.75, "correct": 3, "wrong": 1 },
    { "date": "2026-06-18", "accuracy": 1.0,  "correct": 2, "wrong": 0 }
  ]
}
```

---

## 2. 错题中心 / 复习(R3,wrong_record)

### GET `/wrong-center/review-queue`
请求:无
```json
{
  "due_count": 2,
  "items": [
    {
      "id": "9a2b0000-0000-4000-8000-00000000aa01",
      "q_scope": "uploaded",
      "question_id": "9a2b0000-0000-4000-8000-00000000bb01",
      "node_id": "7b1c0a2e-1111-4a00-9c10-000000000001",
      "review_count": 2,
      "next_review_at": "2026-06-18"
    },
    {
      "id": "9a2b0000-0000-4000-8000-00000000aa02",
      "q_scope": "platform",
      "question_id": "9a2b0000-0000-4000-8000-00000000bb02",
      "node_id": null,
      "review_count": 0,
      "next_review_at": "2026-06-18"
    }
  ]
}
```

### POST `/wrong-center/review`
请求 body:
```json
{ "wrong_record_id": "9a2b0000-0000-4000-8000-00000000aa01", "quality": 4 }
```
响应 data:
```json
{ "status": "open", "review_count": 3, "next_review_at": "2026-06-24" }
```
> `quality` 0–5;达标后 `status` 变 `mastered`。

---

## 3. 知识节点学习资源(R6)

### GET `/curriculum/nodes/{node_id}/resources?resource_type=lecture`
请求:path `node_id`;query `resource_type`(可选:lecture/video/example/essay/mindmap,缺省返回全部已发布)
```json
{
  "total": 2,
  "items": [
    {
      "id": "c0de0000-0000-4000-8000-00000000d001",
      "node_id": "7b1c0a2e-1111-4a00-9c10-000000000001",
      "resource_type": "lecture",
      "dimension": "grammar",
      "title": null,
      "content_md": "## 定语从句\n关系词 that/which/who 引导...",
      "media_url": null,
      "resource_json": null,
      "status": "published"
    },
    {
      "id": "c0de0000-0000-4000-8000-00000000d002",
      "node_id": "7b1c0a2e-1111-4a00-9c10-000000000001",
      "resource_type": "video",
      "dimension": null,
      "title": "定语从句精讲",
      "content_md": null,
      "media_url": "https://cdn.example.com/v/dingyu.mp4",
      "resource_json": null,
      "status": "published"
    }
  ]
}
```

---

## 4. 知识点讲解 / 掌握(已切 node_resource,路径不变)

### GET `/curriculum/knowledge-points/{kp_id}/contents`
请求:path `kp_id`。受单元 paywall:未购该单元 → `code 403`。无命中 node / 无已发布 lecture → `[]`。
```json
[
  { "dimension": "listening",   "content_md": "## 听力要点\n...", "audio_url": "https://cdn.example.com/a/u1.mp3" },
  { "dimension": "grammar",     "content_md": "## 语法解析\n...", "audio_url": null },
  { "dimension": "reading",     "content_md": "## 阅读策略\n...", "audio_url": null }
]
```

### GET `/curriculum/knowledge-points/{kp_id}/mastery`
请求:path `kp_id`。无记录时各计数为 0、`accuracy=null`。
```json
{
  "kp_name": "定语从句",
  "correct_count": 6,
  "wrong_count": 4,
  "total": 10,
  "accuracy": 0.6,
  "last_activity_at": "2026-06-18T07:30:00+00:00"
}
```

### GET `/curriculum/units/{unit_id}/mastery-summary`
请求:path `unit_id`
```json
[
  {
    "kp_id": "11110000-0000-4000-8000-0000000000a1",
    "kp_name": "定语从句",
    "kp_category": "grammar",
    "correct_count": 6,
    "wrong_count": 4,
    "total": 10,
    "accuracy": 0.6,
    "last_activity_at": "2026-06-18T07:30:00+00:00"
  },
  {
    "kp_id": "11110000-0000-4000-8000-0000000000a2",
    "kp_name": "一般现在时",
    "kp_category": "grammar",
    "correct_count": 0,
    "wrong_count": 0,
    "total": 0,
    "accuracy": null,
    "last_activity_at": null
  }
]
```

---

## 5. 长难句(L1–L7)

### GET `/long-sentences?node_id=<uuid>&limit=50`
请求:query `node_id`(可选,句法 node), `limit`(默认 50)
```json
{
  "total": 1,
  "items": [
    {
      "id": "12340000-0000-4000-8000-0000000000f1",
      "text": "The student who studies hard every day will surely pass the final exam.",
      "source_kind": "platform_real",
      "syntax_points": ["定语从句"]
    }
  ]
}
```
> `source_kind` ∈ `platform_real|textbook|uploaded`。

### GET `/long-sentences/{ls_id}`
请求:path `ls_id`。未发布/不存在 → `code 404`。
```json
{
  "id": "12340000-0000-4000-8000-0000000000f1",
  "text": "The student who studies hard every day will surely pass the final exam.",
  "source_kind": "platform_real",
  "analysis": {
    "main_clause": "The student will surely pass the final exam",
    "layers": [
      { "type": "定语从句", "text": "who studies hard every day" }
    ],
    "translation": "每天刻苦学习的学生一定能通过期末考试。",
    "difficulty_points": ["定语从句"],
    "syntax_points": ["定语从句"]
  },
  "nodes": [
    { "node_id": "7b1c0a2e-1111-4a00-9c10-000000000001", "name": "定语从句", "node_kind": "句法" }
  ]
}
```
> `nodes[].node_id` 可拿去调 `/curriculum/nodes/{node_id}/resources` 看该句法点讲解。

### GET `/long-sentences/{ls_id}/verify-types`
请求:path `ls_id`
```json
{ "types": ["cloze", "struct_type", "main_clause", "translate", "span_label", "rewrite", "read_aloud"] }
```
> 仅返回后台开放且本期可用的题型(未实现的如 reorder 不返回);学生自选其一。

### GET `/long-sentences/{ls_id}/verify?type=cloze`
请求:path `ls_id`;query `type`(必,须在 verify-types 内)。题型不支持/该句无法生成 → `code 400`。
```json
{
  "type": "cloze",
  "prompt": "填入恰当的连接词:The student ____ studies hard every day will surely pass the final exam.",
  "options": ["who", "because", "although", "when"]
}
```
> 主观题(translate/rewrite/span_label/read_aloud)`options` 为 `[]`。

### POST `/long-sentences/{ls_id}/verify`
请求 body:
```json
{ "type": "cloze", "answer": "who" }
```
响应 data:
```json
{
  "correct": true,
  "correct_answer": "who",
  "mastered_nodes": ["定语从句"]
}
```
> `mastered_nodes`:本次达标判掌握的句法点(累计净做对达阈值才出现,通常为 `[]`)。
> `read_aloud` 的 `answer` 传发音总分字符串(如 `"82"`);主观题答文本由 AI 评分。

---

## 6. 词力通设置(R5,通用词库 opt-in)

### GET `/vocabulary/settings`
请求:无
```json
{
  "words_per_group": 5,
  "reps_per_group": 1,
  "wrong_carry_threshold": 2,
  "include_general_vocab": false,
  "general_vocab_list_id": null
}
```

### PUT `/vocabulary/settings`
请求 body(同上字段;开启通用词库示例):
```json
{
  "words_per_group": 8,
  "reps_per_group": 2,
  "wrong_carry_threshold": 2,
  "include_general_vocab": true,
  "general_vocab_list_id": "a0000000-0000-4000-8000-000000000777"
}
```
响应 data:回显保存后的完整设置(结构同 GET)。
> `general_vocab_list_id` 留空(null)=任一已发布通用库;`words_per_group` 1–50,`reps_per_group` 1–5,`wrong_carry_threshold` 1–5。

---

## 7. 错题(旧路径已切 wrong_record,小程序无需改路径)

### GET `/wrong-questions/review-queue`
请求:无
```json
{
  "due_items": [
    {
      "id": "9a2b0000-0000-4000-8000-00000000aa01",
      "student_id": "00000000-0000-4000-8000-0000000000u1",
      "source_image_url": "",
      "question_text": "She ___ to school every day.",
      "student_answer": "go",
      "correct_answer": "goes",
      "question_type": "单选",
      "difficulty": null,
      "tags": ["一般现在时"],
      "is_mastered": false,
      "mastered_at": null,
      "created_at": "2026-06-15T02:10:00+00:00",
      "updated_at": "2026-06-15T02:10:00+00:00",
      "ocr_status": null,
      "review_count": 2,
      "easiness_factor": "2.50",
      "review_interval_days": 6,
      "next_review_at": "2026-06-18",
      "last_review_at": "2026-06-12"
    }
  ],
  "stats": { "total_unmastered": 7, "due_today": 1, "new_unscheduled": 2 }
}
```
> wrong_record 承载:`id` 即 wrong_record id,`source_image_url` 多为空,内容由 join uploaded_question 提供,`tags` 为知识节点名。

### POST `/wrong-questions/{wq_id}/review`
请求 body:`{ "quality": 4 }`(0–5)。响应 data 为单条 `WrongQuestionOut`(结构同上 due_items 元素,`review_count/next_review_at` 已更新)。

### PATCH `/wrong-questions/{wq_id}/mastered`
请求 body:`{ "is_mastered": true }`。响应 data 为更新后的 `WrongQuestionOut`(`is_mastered=true`、`mastered_at` 填值)。

---

## 8. 个人知识点掌握台账(学生自查)

### GET `/kp-mastery/`
请求:无。**已切新表 student_kp**(node 维度,弱项在前)。
```json
[
  {
    "kp_key": "定语从句",
    "kp_id": "7b1c0a2e-1111-4a00-9c10-000000000001",
    "kp_description": "关系词引导的从句作定语",
    "correct_count": 2,
    "wrong_count": 4,
    "accuracy": 0.3333,
    "sources": ["practice", "wrong_question"],
    "last_activity_at": "2026-06-18T07:30:00+00:00"
  }
]
```

### GET `/kp-mastery/trend?kp_key=定语从句&days=30`
请求:query `kp_key`(必), `days`(7–90,默认 30)。读快照台账。
```json
[
  { "date": "2026-06-16", "accuracy": 0.5,  "correct_count": 1, "wrong_count": 1 },
  { "date": "2026-06-17", "accuracy": 0.75, "correct_count": 3, "wrong_count": 1 }
]
```

---

## 字段口径备注
- 所有 `*_at` 时间为 ISO8601(带时区)字符串;`date` 类(trend / next_review_at)为 `YYYY-MM-DD`。
- `accuracy` 为 0–1 小数(`correct/total`),`total=0` 时为 `null`(掌握台账)或 `0.0`(掌握台账列表项)。
- `mastery`(student_kp)为 `null` 或 `1.0`(达标判掌握)。
- 列表型端点直接返回数组的:`/curriculum/.../contents`、`/curriculum/units/.../mastery-summary`、`/kp-mastery/`、`/kp-mastery/trend`;其余包在对象里(`{total,items}` 或具名字段)。
