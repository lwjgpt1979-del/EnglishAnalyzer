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
