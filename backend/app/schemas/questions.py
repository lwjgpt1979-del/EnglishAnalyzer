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

# R8 Phase6a-2 part2 已退役:AdminQuestionItem / AdminQuestionListOut / QuestionReviewRequest
# —— 旧仿真题运营审核(读 simulated_questions)的 DTO,审核已改走 platform_question,零引用。


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


# R8 Phase6a-2 part3 已退役:KPAccuracyItem/KPAccuracyOut/ExamHistoryItem/ExamHistoryOut/ExamRankOut
# —— 诊断页三张读冻结 sim 表的卡片(知识点正确率/模考历史/班级排名)的 DTO,随卡片退役,零引用。


# ─── 智能出题（D-130 AI 智能出题）──────────────────────────────────────────────

class AdaptiveSetOut(BaseModel):
    """GET /questions/adaptive-set 返回结构。"""
    questions: list[SimQuestionOut]
    weak_kp_names: list[str] = Field(..., description="本次推题依据的薄弱知识点名称")
