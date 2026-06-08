# V2 M10 Plan: teacher/student-diagnosis.vue 对齐

## 步骤

### Step 1: 修改 `teacher/student-diagnosis.vue`
- 总览加 mastered_count
- 高频错误后插入题型分布卡片 + 难度分布卡片
- 添加辅助函数 distEntries / maxDistCount / difficultyLabel / difficultyBarClass
- 添加对应 CSS（`.bar-item .bar-track .bar-fill`）

### Step 2: 修改 `relative/student-view.vue`
- 在 stat-row 中加入 mastered_count 格（第3个，在 mastery_rate 之前）

### Step 3: TDD
- 测试文件已有 `test_relative.py` — 确认 `getStudentDiagnosisAsRelative` 返回 mastered_count
- 新增简单 import check

### Step 4: Build verify
```bash
TMPDIR=/tmp npx tsc --noEmit 2>&1 | grep "teacher/student-diagnosis\|relative/student-view"
```
