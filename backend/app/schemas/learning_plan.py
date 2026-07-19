"""个性化每日学习计划 schema（M9 / 两来源重构）。

今日学习计划 = 两来源(作业精讲 / 课程精讲)× 各自模块的今日待做 + 今日复习。
无独立任务表：数字/进度由各模块既有 studied 口径实时派生，幂等、每日自刷新。
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class PlanTile(BaseModel):
    """来源下的一个模块格（单词 / 语法 / 长难句 / 阅读）。"""

    module: str = Field(..., description="模块：word|grammar|sentence|reading")
    title: str = Field(..., description="模块名：单词/语法/长难句/阅读")
    count: int = Field(..., description="今日待做（剩余未学 = total - studied）")
    studied: int = Field(0, description="已学数")
    total: int = Field(0, description="总数")
    route: str | None = Field(None, description="点击跳转的小程序路由")


class PlanSource(BaseModel):
    """一个学习来源（作业精讲 / 课程精讲）及其模块格。"""

    source: str = Field(..., description="来源：homework|course")
    title: str = Field(..., description="作业精讲 / 课程精讲")
    subtitle: str = Field("", description="副标题：优先 / 8上册 等")
    available: bool = Field(True, description="是否有内容（课程未选教材=False）")
    tiles: list[PlanTile] = Field(default_factory=list)


class PlanReview(BaseModel):
    """今日复习条（当前只含错题，后续并入词/句）。"""

    count: int = Field(..., description="今日待复习数")
    subtitle: str = Field("", description="说明文案")
    route: str = Field(..., description="跳转路由")


class TodayPlanOut(BaseModel):
    """今日学习计划（两来源 × 模块 + 复习）。"""

    date: str = Field(..., description="计划日期（UTC）YYYY-MM-DD")
    sources: list[PlanSource] = Field(default_factory=list)
    review: PlanReview
    completed_count: int = Field(..., description="已学完模块格数")
    total_count: int = Field(..., description="有内容的模块格数 + 复习")
    checkin_done: bool = Field(..., description="今日是否已打卡")
    review_pending: int = Field(0, description="待复习错题数（兼容旧字段）")
