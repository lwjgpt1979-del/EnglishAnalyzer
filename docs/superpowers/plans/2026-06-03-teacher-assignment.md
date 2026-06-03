# 老师出卷下发闭环 Implementation Plan（D-113）

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development 或 executing-plans。逐任务 TDD。详细代码见 spec `docs/superpowers/specs/2026-06-03-teacher-assignment-design.md`。

**Goal:** 老师手动出卷→发布下发（通知）→学生作答→老师打分→学生看分。

**Architecture:** assignment_service（老师/学生两侧）+ 复用 class_service 班级归属校验 + notification_service 下发通知；零迁移、无 LLM。

**运行约定：** 后端 python=`/opt/anaconda3/bin/python`，pytest 从 `backend/` 跑、`../tests/...`、`-p no:randomly`。前端 `npm run build:mp-weixin`。

---

## Task 1: assignment_service 老师端 + 测试

**Files:** Create `backend/app/services/assignment_service.py`；Test `tests/services/test_assignment_service.py`

- [ ] **Step 1: 写失败测试** — create(draft)/非本班 403、publish(→published+published_at+班级学生收到 type=assignment 通知)、close、list、grade(本人作业写 score / 非本人 403)。helper：建 teacher(role=teacher) + class(class_service.create_class) + 班级学生(ClassStudent)。
- [ ] **Step 2: 跑测试确认失败**（模块不存在）
- [ ] **Step 3: 实现** `assignment_service.py` 老师端函数（见 spec「后端 assignment_service 老师端」全部代码）：`_get_owned_assignment`/`create_assignment`/`publish_assignment`(emit 通知)/`close_assignment`/`list_teacher_assignments`/`get_assignment_for_teacher`/`grade_submission`。import: `class_service`、`notification_service`、模型 `Assignment/AssignmentSubmission/ClassStudent`、`AppError`、`datetime/timezone`。
- [ ] **Step 4: 跑测试通过**
- [ ] **Step 5: commit** `feat(backend): 老师出卷 service（建/发布通知/批改）`

```python
# 测试 helper 要点
async def _teacher(s):
    u = await upsert_user(s, openid=f"t_{uuid4().hex[:8]}"); u.role="teacher"; await s.flush(); return u.id
async def _class_with_student(s, teacher_id):
    cls = await class_service.create_class(s, teacher_id=teacher_id, name="一班")
    stu = await upsert_user(s, openid=f"s_{uuid4().hex[:8]}"); await s.flush()
    s.add(ClassStudent(class_id=cls.id, student_id=stu.id, joined_at=datetime.now(timezone.utc))); await s.flush()
    return cls, stu.id
# publish 通知断言：查 Notification where user_id==stu and type=="assignment" 计数>=1
```

---

## Task 2: assignment_service 学生端 + 测试

**Files:** Modify `assignment_service.py`；Test 扩展 `test_assignment_service.py`

- [ ] **Step 1: 写失败测试** — list_received(本班 published 可见 / 未发布不可见 / 非本班不可见)、submit(成功 / 重复 upsert 同行 / 非本班 403 / 已截止 400)、get_for_student(本班可见 / 非本班 403)。
- [ ] **Step 2: 跑测试确认失败**
- [ ] **Step 3: 实现** 学生端函数（见 spec）：`list_received`/`get_for_student`/`submit_assignment`（截止校验 `due_at` aware 比较；upsert 查既有 submission）。
- [ ] **Step 4: 跑测试通过**
- [ ] **Step 5: commit** `feat(backend): 老师作业学生端 service（接收/作答/提交）`

---

## Task 3: schemas + API（老师 + 学生）+ 全链路 API 测试

**Files:** Create `schemas/assignment.py`、`api/v1/assignments.py`；Modify `api/v1/teacher.py`、`api/v1/router.py`；Test `tests/api/test_assignment.py`

- [ ] **Step 1: 写失败测试**（全链路：老师建→发布→学生列表→作答→老师批改→学生看分；鉴权 401/403）。teacher 登录复用 wx-login + DB 改 role=teacher + Teacher cert（参 test_admin_pricing/_make_admin 范式；teacher 需 certified → 造 Teacher(cert_status='certified')）。
- [ ] **Step 2: 跑测试确认失败**（404）
- [ ] **Step 3: schemas** `schemas/assignment.py`（见 spec 全部 schema）。
- [ ] **Step 4: 老师端 API**（teacher.py 追加 6 端点，`_require_certified_teacher` 闸门；due_at ISO 解析）。
- [ ] **Step 5: 学生端 API** `api/v1/assignments.py`（prefix `/assignments`，3 端点，get_current_user）+ router.py 注册 `assignments_router`。
- [ ] **Step 6: 跑测试通过**
- [ ] **Step 7: commit** `feat(backend): 老师作业 API（老师出卷/批改 + 学生接收/作答）`

> 注意：teacher.py 追加端点放在文件末尾即可（无路径冲突，`/assignments` 与 `/classes` 不同）。学生端 `/assignments/{id}` 用 uuid 类型参数，无 `/templates` 类静态路径冲突。

---

## Task 4: 前端老师端

**Files:** Create `pages/teacher/assignments.vue`、`assignment-detail.vue`；Modify `pages/teacher/class-detail.vue`（入口）、`pages.json`、`api/assignments.ts`、`types/api.ts`

- [ ] **Step 1: types + api**（teacher 部分：createAssignment/listAssignments/getAssignmentDetail/publishAssignment/closeAssignment/gradeSubmission）。
- [ ] **Step 2: assignments.vue**（班级作业列表 + 出卷表单：title + 动态题目数组 + due；发布/关闭按钮）。
- [ ] **Step 3: assignment-detail.vue**（题目 + 提交列表 + 每份打分输入 + 提交批改）。
- [ ] **Step 4: class-detail.vue** 加「作业/出卷」按钮 → `assignments?classId=`；pages.json 注册两页。
- [ ] **Step 5: build** `npm run build:mp-weixin`
- [ ] **Step 6: commit** `feat(frontend): 老师端出卷中心（列表/出卷/批改）`

---

## Task 5: 前端学生端 + 入口

**Files:** Create `pages/assignments/index.vue`、`detail.vue`；Modify `pages/index/index.vue`（宫格入口）、`pages.json`、`api/assignments.ts`、`types/api.ts`

- [ ] **Step 1: types + api**（student：getReceivedAssignments/getStudentAssignment/submitAssignment）。
- [ ] **Step 2: index.vue**（收到作业列表：标题/状态/截止/是否已交/分数）。
- [ ] **Step 3: detail.vue**（题目 + 作答输入 + 提交；已交展示答案+分数）。
- [ ] **Step 4: 首页宫格** 加「📋 老师任务」→ `/pages/assignments/index`；pages.json 注册两页。
- [ ] **Step 5: build** `npm run build:mp-weixin`
- [ ] **Step 6: commit** `feat(frontend): 学生端老师任务（作业列表/作答）+ 首页入口`

---

## Task 6: 全量回归 + 归档 D-113

- [ ] **Step 1:** 后端全量 `cd backend && /opt/anaconda3/bin/python -m pytest ../tests -p no:randomly -q`（约 445 passed；已知 flaky 隔离确认）
- [ ] **Step 2:** 前端 build 确认
- [ ] **Step 3:** 归档 D-113（顶部，`## D-112` 之前）：结论（service 两侧 / API 老师6+学生3 端点 / 发布下发通知 / 前端老师出卷中心+学生老师任务+首页入口）、测试、影响范围、未做（AI选题/自动判分/评语/统计大盘）、相关（D-069/074、Module 5B/5B-S）。
- [ ] **Step 4:** commit `docs: 归档 D-113 老师出卷下发闭环`
- [ ] **Step 5:** 报告 commit 列表 + 测试/构建，征求同意后 push。

---

## Self-Review

- Spec 覆盖：老师端 service(T1)/学生端 service(T2)/schemas+API(T3)/前端老师(T4)/前端学生(T5)/回归归档(T6) ✓
- 零迁移（表就绪）、无 LLM 花钱、复用 class_service+notification_service ✓
- 类型一致：service 返回 ORM / API 组装 schema；questions/answers JSONB 透传；teacher cert 闸门复用 `_require_certified_teacher`；学生端 get_current_user ✓
- 占位：详细代码在 spec，plan 给测试要点 + 步骤；无 TBD ✓
