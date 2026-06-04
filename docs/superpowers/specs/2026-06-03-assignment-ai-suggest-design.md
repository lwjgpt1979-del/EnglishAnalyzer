# AI 智能选题 / 薄弱点组卷 设计（D-116）

**日期：** 2026-06-03
**归属：** 老师出卷深化③（收尾，前序 D-113~115）。需求 Module 5B 智能推荐出卷。

## 目标
老师「智能选题」→ 读目标学生最薄弱知识点 → AI 生成 N 题（dev-mock 免费/真实需预算）→ 映射为作业题建议，老师可编辑后保存。复用 diagnosis + question_ai_service，无持久化副作用。零迁移。

## 后端 `assignment_service.suggest_questions(db, *, student_id, count=5) -> dict`
```python
from app.services import diagnosis_service, question_ai_service
async def suggest_questions(db, *, student_id, count=5) -> dict:
    report = await diagnosis_service.get_diagnosis_report(db, student_id=student_id)
    if not report.top_weak_knowledge_points:
        raise AppError(code=400, message="该生暂无薄弱知识点，请先完成错题 AI 分析")
    kp = report.top_weak_knowledge_points[0].knowledge_point
    gen = await question_ai_service.generate_questions(
        kp_name=kp, kp_category="语法", kp_description=None, count=count)
    questions = [{"stem": q.stem, "type": q.question_type, "options": q.options, "answer": q.answer} for q in gen]
    return {"knowledge_point": kp, "questions": questions}
```
> 老师归属/认证由 API 层 `_require_certified_teacher` 把关；本函数只按 student_id 取学情（MVP 不校验师生绑定，老师可为任意学生预览建议——后续可加绑定校验）。

## schemas（assignment.py 追加）
```python
class SuggestOut(BaseModel):
    knowledge_point: str
    questions: list[AssignmentQuestion]
```

## API（teacher.py）
`GET /teacher/assignments/suggest?student_id=&count=5` → `_require_certified_teacher` → SuggestOut。

## 前端
`assignments.vue` 出卷表单加「🎯 智能选题」：输入目标学生 ID + count → 调 suggestQuestions → 返回题目**填入 questions 表单**（老师可改）+ 提示薄弱点。api/types 补 `suggestAssignmentQuestions` / `AssignmentSuggest`。

## 测试（TDD，强制 dev-mock）
autouse `monkeypatch assignment_service... is_llm_dev_mode` 或直接 patch `question_ai_service.generate_questions`，绝不真打 LLM。
- service：播种 WrongQuestion+AiAnalysis(knowledge_points=["一般现在时"]) → suggest 返回 count 题、knowledge_point 命中、题含 answer；无薄弱点 → 400。
- API：certified 老师 suggest 返回；非 certified 403。

## 影响范围
`assignment_service.py`(+suggest_questions) + `schemas/assignment.py`(+SuggestOut) + `teacher.py`(+suggest 端点) + 测试 + 前端 assignments.vue/api/types。零迁移、dev-mock 无花钱。

## 不做（后续）
班级聚合薄弱点；题库已发布题混合选；难度/题型比例自定义；自动落库题库；师生绑定校验。

## 相关
D-113~115；diagnosis_service / question_ai_service；需求 Module 5B。
