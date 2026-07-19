"""用户相关 Schemas。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class UserMeOut(BaseModel):
    """GET /users/me 响应体（含合规字段）。"""

    id: str
    role: str
    nickname: str | None
    avatar_url: str | None
    is_active: bool
    phone: str | None = None
    preferred_grade: str | None = None
    exam_target: str | None = None  # junior(中考)|senior(高考);null=未设(前端按年级推荐)

    # 合规字段（默认值保持向后兼容）
    profile_completed: bool = False
    birth_year: int | None = None
    deactivation_scheduled_at: datetime | None = None
    days_until_cancellation: int | None = None
