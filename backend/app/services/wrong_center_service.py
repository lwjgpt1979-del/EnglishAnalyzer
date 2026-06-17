"""R3 统一错题中心(KP-First):各渠道做错 → 收口写 wrong_record(指题 + 定位 node)。

wrong_record 是错题**事件**(不是题):指向 platform/uploaded 题 + node_id 定位 KP。
单一收口入口 record_wrong,各渠道(练习做错/整卷错题/单题/复习再错)统一调用。
承接 SM-2 复习(字段见 m86)。旧 wrong_questions 并存供 OCR/诊断富字段。
"""
from __future__ import annotations

import datetime as _dt
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d16_question_domain import WrongRecord


async def record_wrong(
    db: AsyncSession, *, student_id: uuid.UUID, q_scope: str, question_id: uuid.UUID,
    node_id: uuid.UUID | None = None, is_original: bool = True,
    today: _dt.date | None = None,
) -> uuid.UUID:
    """收口:某题做错 → upsert wrong_record。

    新建:status=open,next_review_at=今日(立即入复习队列)。
    复发(已存在,含已 mastered):重置 status=open、清 mastered_at、SM-2 归零、今日重排。
    q_scope ∈ {platform, uploaded}。返回 wrong_record id。
    """
    today = today or _dt.date.today()
    stmt = (
        pg_insert(WrongRecord)
        .values(
            id=uuid.uuid4(), student_id=student_id, q_scope=q_scope,
            question_id=question_id, node_id=node_id, is_original=is_original,
            status="open", next_review_at=today,
        )
        .on_conflict_do_update(
            constraint="uix_wrong_record_identity",
            set_={
                "status": "open", "mastered_at": None, "mastery_source": None,
                "review_count": 0, "review_interval_days": 1,
                "next_review_at": today,
                # node_id 命中更新(保留已有非空)
                "node_id": sa.func.coalesce(sa.text("EXCLUDED.node_id"), WrongRecord.node_id),
            },
        )
        .returning(WrongRecord.id)
    )
    return (await db.execute(stmt)).scalar_one()


async def list_open_wrongs(
    db: AsyncSession, *, student_id: uuid.UUID, node_id: uuid.UUID | None = None,
    limit: int = 100,
) -> list[WrongRecord]:
    """未掌握错题(KP-First 视图);可按 node 过滤。"""
    stmt = sa.select(WrongRecord).where(
        WrongRecord.student_id == student_id, WrongRecord.status == "open"
    )
    if node_id is not None:
        stmt = stmt.where(WrongRecord.node_id == node_id)
    return list((await db.execute(
        stmt.order_by(WrongRecord.created_at.desc()).limit(limit)
    )).scalars().all())
