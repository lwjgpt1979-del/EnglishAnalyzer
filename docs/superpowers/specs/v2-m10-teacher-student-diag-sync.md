# V2 M10 Spec: teacher/student-diagnosis.vue 对齐学生端诊断报告字段

## 问题
`frontend/miniprogram/src/pages/teacher/student-diagnosis.vue` 是教师查看学生学情报告的页面，
目前只显示 3 个字段（total_questions / total_analyzed / mastery_rate），
而 V2 M9 刚为学生端 `diagnosis/index.vue` 补充了：
- `mastered_count`（已掌握知识点数量）
- `question_type_distribution`（题型分布进度条）
- `difficulty_distribution`（难度分布进度条）

教师视角的学情报告应与学生自己看到的一致，否则教师会错过重要信息。

同时，`relative/student-view.vue` 中的诊断摘要也只显示 3 格，同样缺少 `mastered_count`。

## 目标
1. `teacher/student-diagnosis.vue`：添加 mastered_count、题型分布、难度分布（对齐 M9）
2. `relative/student-view.vue`：在统计行补充 `mastered_count` 格

## 需求

### teacher/student-diagnosis.vue
- 总览 stat-row 加第 4 格：`mastered_count`
- 高频错误卡片之后新增「题型分布」卡片（复用 bar-item 样式）
- 「题型分布」之后新增「难度分布」卡片
- 辅助函数：distEntries / maxDistCount / difficultyLabel / difficultyBarClass（与 M9 相同）

### relative/student-view.vue（小改动）
- 总览 stat-row 加第 4 格：`mastered_count`

## 影响范围
- `frontend/miniprogram/src/pages/teacher/student-diagnosis.vue`
- `frontend/miniprogram/src/pages/relative/student-view.vue`
- 无后端变更
