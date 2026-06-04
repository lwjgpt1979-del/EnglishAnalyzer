# 作业统计大盘 Plan（D-115）。逐任务 TDD。代码见 spec。

## Task 1: service + schemas + API + 测试
- [ ] 写失败测试（service get_assignment_stats + API GET /teacher/assignments/{id}/stats）
- [ ] 跑失败
- [ ] 实现 get_assignment_stats + PerQuestionStat/AssignmentStatsOut + teacher 端点
- [ ] 跑通过
- [ ] commit `feat(backend): 作业统计大盘 API`

## Task 2: 前端 + 回归 + 归档
- [ ] assignment-detail.vue 统计卡片 + api/types
- [ ] build + 后端全量回归
- [ ] 归档 D-115 + commit + 询问 push
