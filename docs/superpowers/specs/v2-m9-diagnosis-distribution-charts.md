# V2 M9 Spec: 诊断报告补充 question_type / difficulty 分布展示

## 问题
`diagnosis/index.vue` 的 `DiagnosisReport` 后端响应已包含：
- `mastered_count`：已掌握知识点数量
- `question_type_distribution`：Record<string, number> — 各题型错题数
- `difficulty_distribution`：Record<string, number> — 各难度错题数

但这 3 个字段**从未在页面中展示**，导致诊断报告信息不完整。

## 目标
在 `diagnosis/index.vue` 补充这 3 个字段的可视化展示，零后端变更。

## 需求

### 1. 总览卡片加 `mastered_count`
在现有 "累计错题 / 已分析 / 掌握率" 三格 stat-row 中加入第四格：
- 数字：`report.mastered_count`
- 标签："已掌握"

### 2. 新增「题型分布」卡片
- 位置：高频错误类型卡片之后、薄弱知识点之前
- 条件显示：`Object.keys(report.question_type_distribution).length > 0`
- 展示方式：CSS 进度条（复用 `.bar-item` 样式），条宽 = 各题型占总数比例
- 标题：题型分布

### 3. 新增「难度分布」卡片
- 位置：题型分布卡片之后
- 条件显示：`Object.keys(report.difficulty_distribution).length > 0`
- 展示方式：CSS 进度条，同题型分布
- 难度值映射：1→简单，2→中等，3→困难（可能是数字 key）；也支持文字 key 直接展示
- 标题：难度分布

## 影响范围
- `frontend/miniprogram/src/pages/diagnosis/index.vue`（纯前端）
- 无后端变更、无路由变更
