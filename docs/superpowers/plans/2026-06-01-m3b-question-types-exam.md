# M3b: V2 仿真题题型扩 + 模拟考批量流 + 测试隔离修复 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把仿真题题型从 3 类（单选/填空/判断）扩到 7 类（+ 完型/阅读/作文/连线）；新增"模拟考"批量流（一次 10 题、批后看总分+错题）；修 M3a 暴露的测试隔离缺陷（`_seed_unit` 污染 U1 真 AI KP 名）。

**Architecture:** 复用 M3a 已有 `simulated_questions`/`question_ai_service`/`question_service`/`question_service.submit_attempt`/`questions` API/`v2-session.vue` 全套。Alembic 0010 加 `连线` enum；question_ai_service prompt 加 4 题型 + 题数比例；新增 1 个批量 service 方法 + 1 个 API + 1 个前端页面。复杂题型用"长 stem + 简单 answer 格式"消化到现有数据模型，不引入子题表。

**Tech Stack:** 同 M3a（Alembic + FastAPI + Pydantic + DeepSeek + uni-app Vue3）

---

## 任务列表

### Task 0: Alembic 0010 — Enum 加 "连线"

- 新建 `backend/alembic/versions/0010_add_match_question_type.py`
- 同步 `backend/app/models/d6_ai_questions.py` enum 加 "连线"
- 验证 `enum_range = {单选,填空,完型,阅读,写作,判断,连线}`
- Commit

### Task 1: 修测试隔离缺陷

**问题：** `tests/api/test_curriculum.py::_seed_unit(1)` 用 dev mock commit 数据，污染生产 U1 的前 3 个真 AI KP 名（覆盖回 "知识点 1-1（mock 语法）"）。

**修法：** 把 `_seed_unit` 改为使用 unit_no=99（生产永不会用的高位号），并在 fixture teardown 时 truncate 测试单元相关数据。

**Files：**
- Modify `tests/api/test_curriculum.py`：`_seed_unit(unit_no)` 默认参数改 99，所有调用点 `_seed_unit(1)` → `_seed_unit(99)`, `_seed_unit(2)` → `_seed_unit(99); _seed_unit(100)`，相应调整 lookup unit_no 也用 99/100
- Modify `tests/services/test_question_service.py`：seeded_kp fixture 已用 `test-kp-*` 前缀不污染，但 `simulated_questions` 行也需清理 — 加 teardown
- 加一个 `cleanup_test_data` 通用 fixture（可放在新建的 `tests/conftest.py` 或就近）

**验收：** 跑全套 pytest 不会改变 `WHERE code LIKE 'yl-g5s1-u1-%'` 的 KP name 字段。

### Task 2: 重生 U1 真 AI 内容（修复测试污染留下的 3 个 mock 名 KP）

- SQL 清掉 U1 的所有 KP + contents + words 链
- `python backend/scripts/seed_curriculum.py --grade 小学5年级 --semester 上 --unit 1` 真 AI 跑一次
- 清掉 U1 的所有 simulated_questions
- `python backend/scripts/seed_questions.py --grade 小学5年级 --semester 上 --unit-no 1` 真 AI 跑一次
- 验证 8 KP 都是真名 + 40 道真题

### Task 3: 扩 AI prompt 加 4 题型

**Files：**
- Modify `backend/app/services/question_ai_service.py`：
  - `_USER_PROMPT_TEMPLATE` 加 完型/阅读/作文/连线 的格式说明 + 题数比例（≥1 单选/填空/判断 + 0-2 完型/阅读，每 KP 5-7 题）
  - `_make_mock_questions` 加 4 种 mock 样本，count=7 时返回所有 7 类
- Modify `backend/app/schemas/questions.py`：`AIGeneratedQuestion.question_type` 的 Literal 扩到 7 类
- Modify tests/services/test_question_ai_service.py：assert types == {7 全集}

**完型/阅读：** stem 可超长（包含小短文），options A-D 单选格式，answer 'A'-'D'
**作文：** stem 是题目要求，options=None，answer 是参考范文（200+ 字）
**连线：** stem 是 "左列：①cat ②dog ... 右列：A.猫 B.狗 ..."，options=None，answer "1-A\|2-B\|3-C"

### Task 4: question_service 加 4 题型判分 + 错题映射 + 批量提交

**Files：**
- Modify `backend/app/services/question_service.py`：
  - `_grade()` 加 完型/阅读 (= 单选逻辑) + 作文 (= 永远 True，无标准答案不算错) + 连线 (sort 双方对儿后 strict equal)
  - `_WQ_QTYPE_MAP` 加 完型→"完型", 阅读→"阅读", 作文→"作文", 连线→"其他"
  - 新增 `submit_exam_attempts(db, *, user_id, answers: list[dict]) -> ExamResultOut`：批量调 _grade（不 commit 中间状态），返回 ExamResultOut(total, correct_count, items: list[PracticeResultOut])
- Modify `backend/app/schemas/questions.py`：加 `ExamAttemptIn { items: list[PracticeAttemptIn] }` + `ExamResultOut { total: int, correct_count: int, items: list[PracticeResultOut] }`
- Modify `tests/services/test_question_service.py`：加 4 个判分测试（完型/阅读/作文/连线）+ 1 个 submit_exam_attempts 测试（3 对 2 错）

### Task 5: API 加 POST /exam-attempts

**Files：**
- Modify `backend/app/api/v1/questions.py`：加 POST `/api/v1/questions/exam-attempts` 接收 `ExamAttemptIn`，调 `submit_exam_attempts`，return `make_ok(ExamResultOut.model_dump())`，最后 commit
- Modify `tests/api/test_questions.py`：加 1 个 batch 测试（_seed_kp_with_questions 拿 5 题，提交 3 对 2 错答案，断言 total=5, correct_count=3）

### Task 6: 前端 API client + types 加 batch

- Append types `ExamAttemptIn` / `ExamResultOut` 到 `types/api.ts`
- 加 `submitExam(body)` 到 `api/questions.ts`

### Task 7: 模拟考页 v2-exam.vue + KP 入口双按钮

**Files：**
- 新建 `frontend/miniprogram/src/pages/practice/v2-exam.vue`：
  - onLoad 拿 `?kp=xxx&count=10`，调 `listPracticeQuestions(kp, count)`
  - 滚动列表显示所有题（每道含 stem + 输入区，不显示反馈）
  - 底部"提交考试"按钮 → 调 `submitExam({ items: [...] })` → 显示总分页（X / 10 + 错题列表 + 每题解析）
- pages.json 注册 `pages/practice/v2-exam`
- Modify `pages/curriculum/kp-content.vue`：把单个"开始练习（5 题）"按钮改成两个：
  - `[ 练习（5 题）]` → 跳 v2-session
  - `[ 模拟考（10 题）]` → 跳 v2-exam?kp=xxx&count=10

### Task 8: 真机验证 + D-083 归档 + push

- 跑 free unit 重生 KP + 题（Task 2 已做）
- 重启 uvicorn + 前端热重
- 用户真机验证：练习页（5 题，3 类）+ 模拟考页（10 题，新题型）+ 完成总分
- 写 D-083 归档：M3b 完成、提交链、改动范围、新发现的遗留
- push origin main

---

## 文件结构概览

### 后端
- `backend/alembic/versions/0010_add_match_question_type.py` (新)
- `backend/app/models/d6_ai_questions.py` (改 enum)
- `backend/app/schemas/questions.py` (改 Literal + 加 ExamAttemptIn/ExamResultOut)
- `backend/app/services/question_ai_service.py` (改 prompt + mock)
- `backend/app/services/question_service.py` (改 _grade + _WQ_QTYPE_MAP + 加 submit_exam_attempts)
- `backend/app/api/v1/questions.py` (加 POST /exam-attempts)

### 测试
- `tests/api/test_curriculum.py` (改 _seed_unit 用 unit_no=99)
- `tests/services/test_question_ai_service.py` (改 assert 7 类)
- `tests/services/test_question_service.py` (加 4 个判分 + 1 个 batch)
- `tests/api/test_questions.py` (加 1 个 batch 集成)

### 前端
- `frontend/miniprogram/src/types/api.ts` (append batch types)
- `frontend/miniprogram/src/api/questions.ts` (加 submitExam)
- `frontend/miniprogram/src/pages/practice/v2-exam.vue` (新)
- `frontend/miniprogram/src/pages.json` (加路由)
- `frontend/miniprogram/src/pages/curriculum/kp-content.vue` (改双按钮)

---

## 风险与回滚

| 风险 | 缓解 |
|---|---|
| AI 生成 完型 stem 过长（> 500 字）导致 DB 字段溢出 | `stem` 是 TEXT 无上限；前端用 scroll-view |
| 连线 answer 格式 AI 不稳定（顺序错乱） | 判分时双方都 sort 再比 |
| 作文 无 AI 评分，用户可能困惑"为什么永远对" | UI 标注"参考答案仅供对照，不计入正误" |
| 批量提交时单题 commit 浪费 | 把 _WQ_creation 抽到独立函数，submit_exam_attempts 末尾一次 flush + commit |
| Task 1 修测试隔离会让原 247 + M3a 11 测试中部分需调整 | 跑全套，调到全绿再 commit |

---

## Self-Review

**1. 规格覆盖**
- ✅ 4 新题型：完型/阅读/作文/连线 → Task 3
- ✅ 模拟考批量流 → Task 4-7
- ✅ 修测试隔离 → Task 1
- ✅ 重生 Goldilocks 真名 → Task 2

**2. 类型一致**
- `ExamAttemptIn { items: list[PracticeAttemptIn] }` / `ExamResultOut { total, correct_count, items: list[PracticeResultOut] }` 命名贯穿 schema/service/API/前端

**3. 占位符**
- 无 TBD/TODO
- 复杂代码块在子任务 dispatch 时给出（不在此 plan 里冗余）

---
