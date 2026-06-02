# M3 知识点关联视图（3-Tab）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把知识点详情页（kp-content.vue）从「只有 4 个维度 tab」升级为页面级「课本内容 / 仿真题 / 我做过的相关题」3-Tab 关联视图，把已有课本内容、仿真题、错题数据围绕一个知识点串成学习闭环。

**Architecture:** 复用现有读取接口（课本内容 `getKpContents`、仿真题 `listPracticeQuestions`）；新增 1 个后端接口 `GET /wrong-questions/by-kp/{kp_id}`（按知识点 + 当前用户过滤错题），前端重构 kp-content.vue 为外层 3-Tab，第 1 个 Tab 内保留原有 4 维度子 Tab + 课本内容 + 练习/模拟考按钮。

**Tech Stack:** FastAPI + SQLAlchemy 2.x async（join `wrong_question_knowledge_points`）；uni-app Vue 3（小程序）。

---

### Task 1: 后端 service —— 按知识点查当前学生错题

**Files:**
- Modify: `backend/app/services/wrong_question_service.py`
- Test: `tests/api/test_wrong_questions.py`

新增 `list_wrong_questions_by_kp`：join 关联表 `WrongQuestionKnowledgePoint`，按 `student_id + knowledge_point_id` 过滤，按 `created_at` 倒序，返回 `(items, total)`。

```python
async def list_wrong_questions_by_kp(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    kp_id: uuid.UUID,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[WrongQuestion], int]:
    """按知识点查当前学生的错题（join 关联表），按创建时间倒序。"""
    from app.models.d4_knowledge import WrongQuestionKnowledgePoint

    base = (
        select(WrongQuestion)
        .join(
            WrongQuestionKnowledgePoint,
            WrongQuestionKnowledgePoint.wrong_question_id == WrongQuestion.id,
        )
        .where(
            WrongQuestion.student_id == student_id,
            WrongQuestionKnowledgePoint.knowledge_point_id == kp_id,
        )
    )
    total = (await db.execute(
        select(func.count()).select_from(base.subquery())
    )).scalar_one()
    rows = await db.execute(
        base.order_by(WrongQuestion.created_at.desc()).offset(skip).limit(limit)
    )
    return list(rows.scalars().all()), total
```

- [ ] Step 1: 写失败测试（service 级，建知识点 + 错题 + 关联，验证能查到、跨学生隔离）
- [ ] Step 2: 跑测试确认失败（函数不存在）
- [ ] Step 3: 实现 `list_wrong_questions_by_kp`
- [ ] Step 4: 跑测试确认通过
- [ ] Step 5: commit

### Task 2: 后端 API —— GET /wrong-questions/by-kp/{kp_id}

**Files:**
- Modify: `backend/app/api/v1/wrong_questions.py`
- Test: `tests/api/test_wrong_questions.py`

在 `list_wrong_questions`（`GET /`）之后、`GET /{wq_id}` 之前新增：

```python
@router.get("/by-kp/{kp_id}", response_model=BaseResponse[WrongQuestionListOut])
async def list_wrong_questions_by_kp(
    kp_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    """按知识点查当前学生的相关错题（关联视图用）。"""
    await get_rls_db(db, str(current_user.id))
    items, total = await wrong_question_service.list_wrong_questions_by_kp(
        db, student_id=current_user.id, kp_id=kp_id, skip=skip, limit=limit
    )
    return make_ok(
        WrongQuestionListOut(
            items=[WrongQuestionOut.model_validate(wq) for wq in items],
            total=total,
        )
    )
```

- [ ] Step 1: 写失败 API 测试（无关联返回空；有关联返回 1 条）
- [ ] Step 2: 跑测试确认失败（404，路由不存在）
- [ ] Step 3: 实现接口
- [ ] Step 4: 跑全量测试确认通过
- [ ] Step 5: commit

### Task 3: 前端 API 封装

**Files:**
- Modify: `frontend/miniprogram/src/api/wrongQuestions.ts`

```typescript
export function listWrongQuestionsByKp(
  kpId: string, skip = 0, limit = 20,
): Promise<WrongQuestionListOut> {
  return request<WrongQuestionListOut>(
    `/api/v1/wrong-questions/by-kp/${kpId}?skip=${skip}&limit=${limit}`,
  )
}
```

- [ ] Step 1: 加函数
- [ ] Step 2: commit

### Task 4: 前端 kp-content.vue 改造为 3-Tab 关联视图

**Files:**
- Modify: `frontend/miniprogram/src/pages/curriculum/kp-content.vue`

外层 3 个 Tab：`content`（课本内容，保留原 4 维度子 tab + 内容 + 练习/模拟考按钮）、`questions`（仿真题列表，复用 `listPracticeQuestions(kpId, 20)`，展示题型/难度/题干，点击跳练习）、`wrong`（我做过的相关题，调 `listWrongQuestionsByKp`，展示题干/对错/已掌握，点击跳错题详情 `/pages/wrong-questions/detail?id=`）。后两个 Tab 首次切换时懒加载。

- [ ] Step 1: 重构 template + script（外层 tab + 懒加载 + 两个新列表）
- [ ] Step 2: `npm run build:mp-weixin` 验证可编译
- [ ] Step 3: commit

### Task 5: 集成验证 + 归档 D-093

- [ ] Step 1: 跑后端全量测试（确认绿）
- [ ] Step 2: docs/决策归档.md 顶部加 D-093
- [ ] Step 3: commit + （征得同意后）push
