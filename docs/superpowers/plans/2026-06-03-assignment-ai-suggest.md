# AI 智能选题 Plan（D-116）。逐任务 TDD。代码见 spec。强制 dev-mock。

## Task 1: suggest service + schema + API + 测试
- [ ] 写失败测试（service suggest_questions：播种 AiAnalysis + patch dev-mock；无薄弱点 400 / API certified 返回 / 非 certified 403）
- [ ] 跑失败
- [ ] 实现 suggest_questions + SuggestOut + teacher 端点（GET /teacher/assignments/suggest）
- [ ] 跑通过
- [ ] commit `feat(backend): 作业 AI 智能选题（薄弱点组卷，dev-mock）`

## Task 2: 前端智能选题 + 回归 + 归档
- [ ] assignments.vue「智能选题」按钮 + api/types
- [ ] build + 后端全量回归
- [ ] 归档 D-116（顶部）+ commit + 询问 push（收尾本组）
