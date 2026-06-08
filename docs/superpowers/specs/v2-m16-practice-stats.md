# V2 M16 — 练习统计卡片

## 背景
`getPracticeStats()` API (`GET /api/v1/practice/stats`) 返回
`total_practiced`, `total_correct`, `correct_rate`, `by_knowledge_point`，
但 `practice/index.vue` 从未调用，用户无法看到累计练习数据。

## 目标
在 `practice/index.vue` 搜索卡片上方添加「我的练习统计」卡片，显示：
- 累计练习题数 / 答对题数 / 正确率
- 若数据全为 0 则不显示（避免新用户看到空卡片）

## 验收标准
- 页面 onMounted 时调用 `getPracticeStats()`，失败静默忽略
- `total_practiced > 0` 时显示统计卡片
- 显示：累计 N 题 / 答对 M 题 / 正确率 X%
