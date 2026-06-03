# 作业自动判分 + 错题归库 设计（D-114）

**日期：** 2026-06-03
**归属：** 老师出卷深化①。前序 D-113。需求 Module 5B 自动判分 + 错题归库。

## 目标

学生提交作业时，**客观题（有参考答案）自动判分**算总分；答错的客观题**写入现有错题库 wrong_questions**，进入错题本/学情诊断。零迁移、无 LLM。

## 关键决策（已确认）

- 仅**客观题**（question 含非空 `answer`）自动判；无答案的主观题不判（老师仍可手动 `grade_submission` 覆盖）。
- 答错题**写入 wrong_questions**（`source_image_url` 占位 `assignment://{assignment_id}`，`question_type=None` 避开 enum）。
- 复用 `question_service._grade` 归一化比较。

## 架构

### `assignment_service.py` 改 `submit_assignment` + 新增 helper

```python
from app.services.question_service import _grade
from app.models.d3_wrong_questions import WrongQuestion
from sqlalchemy import delete

def _normalize_answers(answers) -> dict[int, str]:
    """支持 [{index,answer}] / dict / 裸 list → {index: answer_str}。"""
    out: dict[int, str] = {}
    if isinstance(answers, list):
        for i, it in enumerate(answers):
            if isinstance(it, dict) and "index" in it:
                out[int(it["index"])] = str(it.get("answer", ""))
            else:
                out[i] = str(it)
    elif isinstance(answers, dict):
        for k, v in answers.items():
            try:
                out[int(k)] = str(v)
            except (ValueError, TypeError):
                pass
    return out


def _auto_judge(questions: list, answers) -> tuple[float | None, list[dict]]:
    """返回 (score|None, wrong_items)。仅对有 answer 的题判分。"""
    amap = _normalize_answers(answers)
    objective = [(i, q) for i, q in enumerate(questions) if (q or {}).get("answer")]
    if not objective:
        return None, []
    correct = 0
    wrong: list[dict] = []
    for i, q in objective:
        ua = amap.get(i, "")
        ok = _grade(str(q.get("type") or "其他"), str(q["answer"]), ua)
        if ok:
            correct += 1
        else:
            wrong.append({"stem": q.get("stem", ""), "student_answer": ua, "correct_answer": str(q["answer"])})
    score = round(correct / len(objective) * 100, 2)
    return score, wrong


async def _sync_assignment_wrongs(db, *, student_id, assignment_id, wrong_items):
    marker = f"assignment://{assignment_id}"
    await db.execute(delete(WrongQuestion).where(
        WrongQuestion.student_id == student_id,
        WrongQuestion.source_image_url == marker))
    for w in wrong_items:
        db.add(WrongQuestion(
            id=uuid.uuid4(), student_id=student_id, source_image_url=marker,
            question_text=w["stem"], student_answer=w["student_answer"],
            correct_answer=w["correct_answer"], question_type=None))
```

`submit_assignment` 末尾（写入 submission 后）追加：
```python
    score, wrong = _auto_judge(a.questions or [], answers)
    if score is not None:
        sub.score = score
    await _sync_assignment_wrongs(db, student_id=student_id, assignment_id=a.id, wrong_items=wrong)
    await db.flush()
    return sub
```
> 重复提交：每次先 delete 该作业占位错题再重建（幂等，纠正后错题消失）。
> 老师 `grade_submission` 仍可覆盖 score（手动分优先于自动分，按调用时序）。

### 不改 API/schemas

`submit` 返回不变；score 自动写入后，学生 `GET /assignments/{id}`（StudentAssignmentDetail.score）与老师详情自然显示自动分。错题经现有 `wrong-questions`/诊断接口可见。

### 前端（轻量）

学生 detail.vue：提交成功后展示「客观题自动判分：X 分」（读 `getStudentAssignment` 返回的 score）。已有 score 展示即可，补一行说明「客观题已自动判分，主观题待老师批改」。

## 测试（TDD）

**service（test_assignment_service.py 扩展）**
1. 提交全对客观题 → `sub.score==100`、无错题写入。
2. 提交部分错 → score 按比例、wrong_questions 写入对应条数（source_image_url==assignment://{id}）。
3. 重复提交纠正 → 旧错题清除、score 更新。
4. 纯主观题（无 answer）→ score 为 None、无错题。
5. `_auto_judge` / `_normalize_answers` 纯函数：[{index,answer}] / dict / 裸 list 三种格式。

## 影响范围

- `backend/app/services/assignment_service.py`（submit_assignment + _auto_judge/_normalize_answers/_sync_assignment_wrongs）
- `tests/services/test_assignment_service.py`（扩展）
- 前端 `pages/assignments/detail.vue`（自动判分说明，轻量）
- **零迁移、无花钱**（复用 _grade、wrong_questions）。

## 不做（后续）

- 主观题 AI 判分；逐题得分明细存储；错题去重合并跨来源
- 作业统计大盘（D-115）；AI 智能选题（D-116）

## 相关

D-113（出卷闭环）；question_service._grade / WrongQuestion；需求 Module 5B。
