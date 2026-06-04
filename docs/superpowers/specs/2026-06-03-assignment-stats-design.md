# 作业统计大盘 设计（D-115）

**日期：** 2026-06-03
**归属：** 老师出卷深化②（前序 D-113/114）。

## 目标
老师查看某作业统计：班级人数 / 已交 / 完成率 / 平均·最高·最低分 / 逐题正确率（客观题）。零迁移、无 LLM。

## 后端 `assignment_service.get_assignment_stats(db, *, teacher_id, assignment_id) -> dict`
- `_get_owned_assignment` 校验归属。
- `total_students` = ClassStudent count（该作业 class_id）。
- submissions（select where assignment_id）→ `submitted_count`、`completion_rate = round(submitted/total, 2)`（total=0 → 0）。
- `scores = [s.score for s in subs if s.score is not None]` → `graded_count`、`avg_score`/`max_score`/`min_score`（空→None）。
- 逐题（客观题，有 answer）：对每题 index，遍历 subs 用 `_normalize_answers(su.answers).get(index)` + `_grade(type or '其他', answer, ua)` 统计 correct/total（total=有提交数）→ `{index, stem, correct, total, rate}`。
- 返回 `{total_students, submitted_count, completion_rate, graded_count, avg_score, max_score, min_score, per_question:[...]}`。

## schemas（assignment.py 追加）
```python
class PerQuestionStat(BaseModel):
    index: int; stem: str; correct: int; total: int; rate: float
class AssignmentStatsOut(BaseModel):
    total_students: int; submitted_count: int; completion_rate: float
    graded_count: int; avg_score: float | None = None
    max_score: float | None = None; min_score: float | None = None
    per_question: list[PerQuestionStat]
```

## API（teacher.py）
`GET /teacher/assignments/{id}/stats` → `_require_certified_teacher` → AssignmentStatsOut。

## 前端
`assignment-detail.vue` 加「统计」卡片：完成率、均分、逐题正确率列表。onLoad 拉 `getAssignmentStats(id)`。api/types 补。

## 测试（TDD）
- service：3 人班 2 交、客观题部分对 → total_students=3/submitted=2/completion_rate=0.67；avg/max/min；per_question rate 正确；逐题 total=已交数。
- API：返回结构；非本人 → 404。

## 影响范围
`assignment_service.py`(+get_assignment_stats) + `schemas/assignment.py`(+2) + `teacher.py`(+stats 端点) + 测试 + 前端 assignment-detail/api/types。零迁移、无花钱。

## 不做（后续）
跨作业趋势/班级对比；导出；主观题统计；学生维度雷达。

## 相关
D-113/114；需求 Module 5B。
