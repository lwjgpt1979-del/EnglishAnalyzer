from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class ErrorTypeCount(BaseModel):
    """错误类型及出现次数（聚合自 AI 分析）。"""

    error_type: str = Field(..., description="错误类型标签，如'语法错误'/'时态错误'")
    count: int = Field(..., description="该错误类型在所有 AI 分析中出现的总次数")


class KnowledgePointCount(BaseModel):
    """知识点及出现次数（聚合自 AI 分析）。"""

    knowledge_point: str = Field(..., description="知识点名称，如'现在完成时'/'主谓一致'")
    count: int = Field(..., description="该知识点在所有 AI 分析中出现的总次数")


class DailyActivity(BaseModel):
    """某一天的错题提交数量（用于近30天活跃度图表）。"""

    date: str = Field(..., description="ISO 日期，如 '2026-05-26'")
    count: int = Field(..., description="当日提交的错题数量，无数据日为0")


class KpDimensionItem(BaseModel):
    """按知识点维度的练习正确率（来自 sim_practice_records，M3 / D-094）。"""

    knowledge_point_id: uuid.UUID
    knowledge_point_name: str
    category: str | None = None
    attempts: int = Field(..., description="该知识点累计作答次数")
    correct: int = Field(..., description="累计答对次数")
    accuracy: float = Field(..., ge=0.0, le=1.0, description="正确率，保留 4 位小数")


class SemesterDimensionItem(BaseModel):
    """按学期维度的练习正确率（M3 / D-094）。"""

    grade: str = Field(..., description="年级，如'七年级'")
    semester: str = Field(..., description="学期：上 / 下")
    label: str = Field(..., description="展示标签，如'七年级上'")
    attempts: int = Field(..., description="该学期累计作答次数")
    correct: int = Field(..., description="累计答对次数")
    accuracy: float = Field(..., ge=0.0, le=1.0, description="正确率，保留 4 位小数")


class DiagnosisReport(BaseModel):
    """学情诊断报告。

    基于当前学生所有错题及 AI 分析结果聚合生成。
    """

    # ── 总览 ──────────────────────────────────────────────────────────────────
    total_questions: int = Field(..., description="累计提交错题数")
    total_analyzed: int = Field(..., description="已完成 AI 分析的错题数")
    mastered_count: int = Field(..., description="已标记掌握的错题数")
    mastery_rate: float = Field(
        ..., ge=0.0, le=1.0, description="掌握率 = mastered_count / total_questions"
    )

    # ── 错误类型分布（前10，按频次降序）──────────────────────────────────────
    top_error_types: list[ErrorTypeCount] = Field(
        ..., description="出现频次最高的错误类型（最多10条，按频次降序）"
    )

    # ── 知识点薄弱项（前10，按出现频次降序）─────────────────────────────────
    top_weak_knowledge_points: list[KnowledgePointCount] = Field(
        ..., description="出现频次最高的薄弱知识点（最多10条，按频次降序）"
    )

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

    # ── M3 结构化维度（练习正确率，来自 sim_practice_records，D-094）──────────
    kp_dimension: list[KpDimensionItem] = Field(
        default_factory=list, description="按知识点维度的练习正确率（弱项在前）"
    )
    semester_dimension: list[SemesterDimensionItem] = Field(
        default_factory=list, description="按学期维度的练习正确率"
    )
