"""个性化每日学习计划 schema（M9）。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class PlanTask(BaseModel):
    """单条学习任务。完成状态由当日真实活动派生，无独立任务表。"""

    type: str = Field(..., description="任务类型：weak_kp / review / learn")
    title: str = Field(..., description="任务标题")
    subtitle: str = Field(..., description="副标题/说明")
    action: str = Field(..., description="动作类型：practice / review / learn")
    done: bool = Field(..., description="是否已完成（由当日活动派生）")
    kp_id: str | None = Field(None, description="目标知识点 id（weak_kp 任务）")
    kp_key: str | None = Field(None, description="知识点名称")
    accuracy: float | None = Field(None, description="当前正确率")
    level: str | None = Field(None, description="掌握等级 weak/medium/good")
    count: int | None = Field(None, description="数量（如待复习错题数）")


class TodayPlanOut(BaseModel):
    """今日学习计划。"""

    date: str = Field(..., description="计划日期（UTC）YYYY-MM-DD")
    tasks: list[PlanTask] = Field(default_factory=list)
    completed_count: int = Field(..., description="已完成任务数")
    total_count: int = Field(..., description="任务总数")
    checkin_done: bool = Field(..., description="今日是否已打卡")
    review_pending: int = Field(..., description="待复习错题数")
