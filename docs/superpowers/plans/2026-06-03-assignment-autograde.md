# 作业自动判分 + 错题归库 Implementation Plan（D-114）

> REQUIRED SUB-SKILL: subagent-driven-development / executing-plans。逐任务 TDD。代码细节见 spec `2026-06-03-assignment-autograde-design.md`。

**Goal:** 提交作业时客观题自动判分算总分 + 答错题写入 wrong_questions。零迁移、无 LLM。

## Task 1: service 自动判分 + 错题归库 + 测试
**Files:** Modify `backend/app/services/assignment_service.py`；Test `tests/services/test_assignment_service.py`
- [ ] Step1 写失败测试：全对→score 100 无错题；部分错→比例分 + wrong_questions 写入；重复纠正→旧错题清除+score更新；纯主观→None；_auto_judge/_normalize_answers 纯函数三格式。
- [ ] Step2 跑失败
- [ ] Step3 实现：import `_grade`/`WrongQuestion`/`delete`；新增 `_normalize_answers`/`_auto_judge`/`_sync_assignment_wrongs`；`submit_assignment` 末尾接自动判分+归库（见 spec 代码）。
- [ ] Step4 跑通过
- [ ] Step5 commit `feat(backend): 作业客观题自动判分 + 答错入错题库`

## Task 2: 前端说明 + 全量回归 + 归档 D-114
**Files:** `pages/assignments/detail.vue`（自动判分说明）；`docs/决策归档.md`
- [ ] Step1 detail.vue 加「客观题已自动判分，主观题待老师批改」说明
- [ ] Step2 build:mp-weixin
- [ ] Step3 后端全量回归（约 448 passed；已知 flaky 隔离确认）
- [ ] Step4 归档 D-114（顶部 D-113 之前）
- [ ] Step5 commit + 询问 push

## Self-Review
- Spec 覆盖：自动判分(T1)/错题归库(T1)/前端说明+回归(T2) ✓
- 零迁移、无 LLM、复用 _grade+wrong_questions ✓
- 幂等：重复提交先 delete 占位错题再重建 ✓
