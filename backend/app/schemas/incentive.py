"""学习激励中心 schema（M10）。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class BadgeItem(BaseModel):
    level: str
    name: str
    threshold: int
    unlocked: bool


class AchievementItem(BaseModel):
    key: str
    name: str
    desc: str
    icon: str
    current: int
    target: int
    unlocked: bool
    progress: float = Field(..., ge=0.0, le=1.0)


class IncentiveStats(BaseModel):
    total_practice: int
    checkin_days: int
    mastered_kp: int
    wrong_mastered: int
    exam_count: int
    speaking_count: int = 0
    unlocked_achievements: int
    total_achievements: int


class IncentiveSummaryOut(BaseModel):
    level: int
    xp: int
    xp_in_level: int
    xp_to_next: int
    current_streak: int
    longest_streak: int
    checked_in_today: bool
    badges: list[BadgeItem]
    achievements: list[AchievementItem]
    stats: IncentiveStats
