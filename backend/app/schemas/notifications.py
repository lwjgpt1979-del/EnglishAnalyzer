"""站内消息中心 Schemas（Module 7B / D-074）。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class NotificationOut(BaseModel):
    id: uuid.UUID
    type: str
    channel: str
    title: str
    content: str
    is_read: bool
    read_at: datetime | None
    created_at: datetime
    expires_at: datetime | None
    meta: dict[str, Any] | None

    model_config = {"from_attributes": True}


class NotificationListOut(BaseModel):
    items: list[NotificationOut]
    total: int
    unread_count: int


class UnreadCountOut(BaseModel):
    count: int
