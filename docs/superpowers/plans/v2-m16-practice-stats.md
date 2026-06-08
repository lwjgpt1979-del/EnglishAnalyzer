# V2 M16 Plan

1. 新建 `tests/api/test_practice_stats.py` — RED
2. `practice/index.vue`：
   - import `getPracticeStats` from `@/api/practice`
   - import `PracticeStatsOut` from `@/types/api`
   - 添加 `stats = ref<PracticeStatsOut | null>(null)`
   - `onMounted` 中 try/catch 调用 `getPracticeStats()`
   - 在 template 搜索卡片上方添加统计卡片（v-if="stats && stats.total_practiced > 0"）
3. 实现测试（GREEN）
4. build verify → commit
