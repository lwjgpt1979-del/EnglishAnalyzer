# M3 学情报告：按学期 / 按知识点维度 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development 或 superpowers:executing-plans 逐任务实现。Steps 用 checkbox (`- [ ]`) 跟踪。

**Goal:** 在现有学情诊断报告（D-063，聚合自错题 + AI 文本分析）基础上，新增两个结构化维度——「按知识点」与「按学期」的练习正确率，数据源为 `sim_practice_records`（V2 仿真题逐题作答日志）。

**Architecture:** 纯只读聚合，无 DB 迁移。`diagnosis_service.get_diagnosis_report` 内新增结构化维度聚合：①按 `knowledge_point_id` 聚合正确率（join `knowledge_points` 取名/类别）；②按学期聚合（join `unit_knowledge_points` → `curriculum_units` 拿 grade/semester）。`DiagnosisReport` 加两个带默认值的新字段（向后兼容现有 schema 测试）。前端学情报告页加两块图表区。

**Tech Stack:** FastAPI + SQLAlchemy async；uni-app Vue 3。

---

### Task 1: Schema —— 新增两个维度数据结构

**Files:**
- Modify: `backend/app/schemas/diagnosis.py`
- Test: `tests/api/test_diagnosis.py`

```python
class KpDimensionItem(BaseModel):
    """按知识点维度的练习正确率（来自 sim_practice_records）。"""
    knowledge_point_id: uuid.UUID
    knowledge_point_name: str
    category: str | None = None
    attempts: int
    correct: int
    accuracy: float = Field(..., ge=0.0, le=1.0)


class SemesterDimensionItem(BaseModel):
    """按学期维度的练习正确率。"""
    grade: str
    semester: str          # "上" / "下"
    label: str             # 如 "七年级上"
    attempts: int
    correct: int
    accuracy: float = Field(..., ge=0.0, le=1.0)
```

`DiagnosisReport` 末尾追加（默认空，保持向后兼容）：

```python
    kp_dimension: list[KpDimensionItem] = Field(
        default_factory=list, description="按知识点维度的练习正确率（弱项在前）"
    )
    semester_dimension: list[SemesterDimensionItem] = Field(
        default_factory=list, description="按学期维度的练习正确率"
    )
```

文件顶部加 `import uuid`。

- [ ] Step 1: 写 schema 测试（构造两个 Item + 验证 DiagnosisReport 默认空列表）
- [ ] Step 2: 跑测试确认失败
- [ ] Step 3: 实现 schema
- [ ] Step 4: 跑测试确认通过
- [ ] Step 5: commit

### Task 2: Service —— 聚合两个结构化维度

**Files:**
- Modify: `backend/app/services/diagnosis_service.py`
- Test: `tests/api/test_diagnosis.py`

新增内部函数 `_aggregate_structured_dimensions(db, student_id)`，在 `get_diagnosis_report` 末尾调用，结果填入新字段。

```python
async def _aggregate_structured_dimensions(db, student_id):
    from app.models.d12_v2_exams import SimPracticeRecord
    from app.models.d4_knowledge import (
        KnowledgePoint, UnitKnowledgePoint, CurriculumUnit,
    )

    recs = (await db.execute(
        select(SimPracticeRecord.knowledge_point_id, SimPracticeRecord.is_correct)
        .where(SimPracticeRecord.student_id == student_id)
    )).all()
    if not recs:
        return [], []

    # 按 KP 聚合
    kp_agg: dict = {}
    for kp_id, ok in recs:
        s = kp_agg.setdefault(kp_id, [0, 0])
        s[0] += 1
        if ok:
            s[1] += 1
    kp_ids = list(kp_agg.keys())

    kp_meta = {
        kid: (name, cat) for kid, name, cat in (await db.execute(
            select(KnowledgePoint.id, KnowledgePoint.name, KnowledgePoint.category)
            .where(KnowledgePoint.id.in_(kp_ids))
        )).all()
    }

    kp_dimension = [
        KpDimensionItem(
            knowledge_point_id=kid,
            knowledge_point_name=kp_meta.get(kid, ("未知知识点", None))[0],
            category=kp_meta.get(kid, (None, None))[1],
            attempts=a, correct=c,
            accuracy=round(c / a, 4) if a else 0.0,
        )
        for kid, (a, c) in kp_agg.items()
    ]
    kp_dimension.sort(key=lambda it: (it.accuracy, -it.attempts))  # 弱项在前

    # KP → {(grade, semester)}
    sem_map: dict = {}
    for kid, grade, sem in (await db.execute(
        select(UnitKnowledgePoint.knowledge_point_id, CurriculumUnit.grade, CurriculumUnit.semester)
        .join(CurriculumUnit, CurriculumUnit.id == UnitKnowledgePoint.unit_id)
        .where(UnitKnowledgePoint.knowledge_point_id.in_(kp_ids))
    )).all():
        sem_map.setdefault(kid, set()).add((grade, str(sem)))

    # 按 (grade, semester) 聚合：一条作答记录计入其 KP 命中的每个学期（同学期去重）
    sem_agg: dict = {}
    for kp_id, ok in recs:
        for key in sem_map.get(kp_id, set()):
            s = sem_agg.setdefault(key, [0, 0])
            s[0] += 1
            if ok:
                s[1] += 1

    semester_dimension = [
        SemesterDimensionItem(
            grade=g, semester=sem, label=f"{g}{sem}",
            attempts=a, correct=c,
            accuracy=round(c / a, 4) if a else 0.0,
        )
        for (g, sem), (a, c) in sem_agg.items()
    ]
    semester_dimension.sort(key=lambda it: (it.grade, it.semester))
    return kp_dimension, semester_dimension
```

`get_diagnosis_report` 内：构造 `DiagnosisReport(...)` 前调用并传入新字段。

- [ ] Step 1: 写 service 测试（建 KP + 单元 + 作答记录 → 验证两个维度命中、正确率正确、空数据返回空）
- [ ] Step 2: 跑测试确认失败
- [ ] Step 3: 实现聚合
- [ ] Step 4: 跑测试确认通过
- [ ] Step 5: commit

### Task 3: 前端类型 + 学情报告页展示

**Files:**
- Modify: `frontend/miniprogram/src/types/api.ts`（加 `KpDimensionItem` / `SemesterDimensionItem` + `DiagnosisReport` 两字段）
- Modify: `frontend/miniprogram/src/pages/diagnosis/*.vue`（按学期/按知识点两块列表，正确率条）

- [ ] Step 1: 加 TS 类型
- [ ] Step 2: 学情报告页加两块维度区（弱项高亮）
- [ ] Step 3: `npm run build:mp-weixin` 验证可编译
- [ ] Step 4: commit

### Task 4: 集成验证 + 归档 D-094

- [ ] Step 1: 后端全量测试绿
- [ ] Step 2: docs/决策归档.md 顶部加 D-094
- [ ] Step 3: commit +（征得同意后）push
