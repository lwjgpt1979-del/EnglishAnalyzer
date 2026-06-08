# V2 M9 Plan: 诊断报告补充分布图表

## 步骤

### Step 1: 修改 `diagnosis/index.vue`

#### Template
1. 总览 stat-row 新增第4格 `mastered_count`
2. 高频错误卡片后插入「题型分布」卡片（v-if question_type_distribution 非空）
3. 题型分布后插入「难度分布」卡片（v-if difficulty_distribution 非空）
4. 复用现有 `.bar-item` / `.bar-track` / `.bar-fill` CSS

#### Script computed
- `distEntries(dist)` → `Object.entries(dist).sort((a,b) => b[1]-a[1])` 按数量降序
- `maxDistCount(dist)` → max value
- 难度 key 映射函数 `difficultyLabel(k)`: '1'→'简单', '2'→'中等', '3'→'困难', else 原 key

### Step 2: TDD
- 测试文件：`tests/api/test_diagnosis_distribution_fields.py`
- 测试：调用 `GET /api/v1/diagnosis/` 接口，断言响应包含 `question_type_distribution`、`difficulty_distribution`、`mastered_count` 字段

### Step 3: Build verify
```bash
TMPDIR=/tmp npx tsc --noEmit 2>&1 | grep "diagnosis/index"
```
