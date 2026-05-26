from __future__ import annotations

from pydantic import BaseModel, Field


class ErrorTypeCount(BaseModel):
    error_type: str
    count: int


class KnowledgePointCount(BaseModel):
    knowledge_point: str
    count: int


class DailyActivity(BaseModel):
    date: str = Field(..., description="ISO 日期，如 '2026-05-26'")
    count: int


class DiagnosisReport(BaseModel):
    """学情诊断报告。

    基于当前学生所有错题及 AI 分析结果聚合生成。
    """

    # ── 总览 ──────────────────────────────────────────────────────────────────
    total_questions: int = Field(..., description="累计提交错题数")
    total_analyzed: int = Field(..., description="已完成 AI 分析的错题数")
    mastered_count: int = Field(..., description="已标记掌握的错题数")
    mastery_rate: float = Field(..., description="掌握率 = mastered_count / total_questions")

    # ── 错误类型分布（前10，按频次降序）──────────────────────────────────────
    top_error_types: list[ErrorTypeCount]

    # ── 知识点薄弱项（前10，按出现频次降序）─────────────────────────────────
    top_weak_knowledge_points: list[KnowledgePointCount]

    # ── 题型分布 ──────────────────────────────────────────────────────────────
    question_type_distribution: dict[str, int] = Field(
        ..., description="键=题型, 值=数量"
    )

    # ── 难度分布 ──────────────────────────────────────────────────────────────
    difficulty_distribution: dict[int, int] = Field(
        ..., description="键=难度(1-5), 值=数量"
    )

    # ── 近30天每日错题提交数 ─────────────────────────────────────────────────
    recent_daily_activity: list[DailyActivity] = Field(
        ..., description="长度固定为30，从30天前到今日"
    )

    # ── 综合建议（最近5条不重复 AI 建议）────────────────────────────────────
    top_suggestions: list[str] = Field(
        ..., description="最近5条不重复的 AI 分析建议"
    )
