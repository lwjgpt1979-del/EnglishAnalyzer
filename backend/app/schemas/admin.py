"""运营后台专用 schemas（M5 / D-099）。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class AdminOverviewOut(BaseModel):
    """运营数据大盘概览。"""
    questions_by_status: dict[str, int] = Field(
        ..., description="仿真题各状态计数（draft/reviewing/published/retired）"
    )
    contents_by_status: dict[str, int] = Field(
        ..., description="知识点内容各状态计数"
    )
    total_users: int = Field(..., description="用户总数")
    paid_orders: int = Field(..., description="已支付订单数")
    pending_teachers: int = Field(0, description="待审教师认证数")
