# 错题本按来源筛选 设计（D-118）

**日期：** 2026-06-03
**归属：** 错题本（前序 D-114/117）。需求错题本。

## 目标
错题本列表支持按来源筛选：全部 / 作业（assignment://）/ 上传（真实图）。零迁移、无花钱。

## 后端 `wrong_question_service.list_wrong_questions(..., source=None)`
- `source="assignment"` → `WrongQuestion.source_image_url.like("assignment://%")`
- `source="upload"` → `~source_image_url.like("assignment://%")`
- `None`/其他 → 不过滤
- count 与 rows 同步加该过滤条件。

## API `GET /wrong-questions/?source=`
新增 `source: str | None = Query(None)` 透传 service。

## 前端 list.vue
顶部加来源 tab（全部/作业/上传）；切换 tab → 重置分页 reload（传 source）。

## 测试（TDD）
- service：播种 2 错题（1 作业 assignment://、1 上传 http）→ source=assignment 返回 1；upload 返回 1；None 返回 2。
- API：?source=assignment 过滤生效。

## 影响范围
`wrong_question_service.py`(list +source) + `wrong_questions.py`(query 参数) + 测试 + 前端 list.vue（tab）。零迁移、无花钱。

## 不做
词力通错词来源（在 vocabulary_learning，另接口）；来源多选；点回原作业。

## 相关
D-114/117；需求错题本。
