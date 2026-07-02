"""V2 仿真题 + 练习 Pydantic schemas（D-079 / M3a）。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ─── AI 生成输出（question_ai_service → question_service.persist）─

class AIGeneratedQuestion(BaseModel):
    question_type: Literal["单选", "填空", "判断", "完型", "阅读", "写作", "连线"]
    stem: str = Field(..., min_length=5, description="题干文本")
    options: list[str] | None = Field(
        None, description="单选题为 4 个选项字符串；填空/判断为 null"
    )
    answer: str = Field(..., min_length=1, description="单选: A-D；填空: 答案 或 多候选用 | 分隔；判断: 对/错")
    explanation: str = Field(..., min_length=10, description="解析")
    difficulty: int = Field(..., ge=1, le=5)


# ─── API 响应/请求 ─────────────────────────────────────────────────────────

class SimQuestionOut(BaseModel):
    """前端拿到的题目（不带 answer 防作弊）。"""
    id: uuid.UUID
    question_type: str
    stem: str
    options: list[str] | None = None
    difficulty: int
    kp_name: str | None = None  # 所属知识点名称，自适应练习用于完成页按 KP 分析
    passage: str | None = None  # 完型/阅读题组短文(逐空/逐问微题的上下文);无则 null（P1）


# ─── 运营审核（M5）：运营可见完整字段（含 answer），仅 platform_admin 可访问 ──

class AdminQuestionItem(BaseModel):
    id: uuid.UUID
    knowledge_point_id: uuid.UUID
    question_type: str
    stem: str
    options: list[str] | None = None
    answer: str
    explanation: str | None = None
    difficulty: int
    dimension: str | None = None
    status: str


class AdminQuestionListOut(BaseModel):
    total: int
    items: list[AdminQuestionItem]


class QuestionReviewRequest(BaseModel):
    approve: bool = Field(..., description="true=通过→published，false=驳回→retired")


class PracticeAttemptIn(BaseModel):
    question_id: uuid.UUID
    user_answer: str = Field(..., min_length=1, max_length=500)


class PracticeResultOut(BaseModel):
    correct: bool
    correct_answer: str
    explanation: str
    wrong_question_id: uuid.UUID | None = Field(
        None, description="做错时自动落 wrong_questions 表，返回 id 方便前端跳错题详情"
    )


# ─── 模拟考批量（M3b）─────────────────────────────────────────────────────

class ExamAttemptIn(BaseModel):
    items: list[PracticeAttemptIn] = Field(..., min_length=1)


class ExamItemResult(BaseModel):
    """单题批量结果（轻量版，不重复 explanation）。"""
    question_id: uuid.UUID
    correct: bool
    correct_answer: str
    user_answer: str
    explanation: str
    wrong_question_id: uuid.UUID | None = None


class ExamResultOut(BaseModel):
    total: int
    correct_count: int
    items: list[ExamItemResult]


# ─── 学情：知识点正确率（D-084 后续）────────────────────────────────────────

class KPAccuracyItem(BaseModel):
    """单个知识点的练习正确率聚合。"""
    knowledge_point_id: uuid.UUID
    knowledge_point_name: str
    attempts: int = Field(..., description="该 KP 累计作答次数")
    correct: int = Field(..., description="累计答对次数")
    accuracy: float = Field(..., description="正确率，保留 4 位小数")


class KPAccuracyOut(BaseModel):
    """学生维度的逐 KP 正确率，弱项（正确率低）在前。"""
    total_attempts: int
    overall_accuracy: float
    items: list[KPAccuracyItem]


# ─── 模拟考成绩历史（D-086 后续）─────────────────────────────────────────────

class ExamHistoryItem(BaseModel):
    """一次模拟考的成绩快照。"""
    id: uuid.UUID
    total: int
    correct_count: int
    accuracy: float = Field(..., description="正确率，保留 4 位小数")
    created_at: datetime


class ExamHistoryOut(BaseModel):
    """学生的模拟考成绩历史，最新在前。"""
    total_exams: int
    items: list[ExamHistoryItem]


# ─── 班级排名（学生端百分位，不暴露他人姓名，D-088）──────────────────────────

class ExamRankOut(BaseModel):
    """学生在所属班级的模拟考排名（百分位）。

    隐私：仅返回本人名次/百分位与班级聚合值，绝不返回其他同学的姓名或个人成绩。
    排名口径：按每位学生模拟考平均正确率降序。
    """
    in_class: bool = Field(..., description="是否在任一班级中")
    ranked: bool = Field(..., description="是否已纳入排名（本人 + 班级均有模拟考成绩）")
    class_name: str | None = Field(None, description="参与排名的班级名")
    my_rank: int | None = Field(None, description="名次，1 为第一名（并列同名次）")
    total_ranked: int | None = Field(None, description="班级内有模拟考成绩的学生数")
    percentile: float | None = Field(
        None, description="超过的同班同学比例 0~1（仅本人有成绩或班级仅 1 人时为 null）"
    )
    my_avg_accuracy: float | None = Field(None, description="本人模拟考平均正确率")
    class_avg_accuracy: float | None = Field(None, description="班级模拟考平均正确率")


# ─── 智能出题（D-130 AI 智能出题）──────────────────────────────────────────────

class AdaptiveSetOut(BaseModel):
    """GET /questions/adaptive-set 返回结构。"""
    questions: list[SimQuestionOut]
    weak_kp_names: list[str] = Field(..., description="本次推题依据的薄弱知识点名称")
