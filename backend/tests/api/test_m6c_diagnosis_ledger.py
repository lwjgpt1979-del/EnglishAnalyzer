"""M6c — 学情报告掌握台账可视化 tests.

验证：
1. _build_review_suggestion 规则分档（weak/medium/good + 练习量少 + stale 提醒）
2. _build_mastery_ledger 端到端：弱项在前、等级正确、建议非空

测试数据用唯一前缀隔离，finally 清理。
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

_TAG = "m6ctest"


def _engine():
    db_url = os.environ.get(
        "ASYNC_DATABASE_URL",
        "postgresql+psycopg_async://postgres:dev@localhost:5432/enggramer",
    )
    return create_async_engine(db_url, echo=False)


def test_review_suggestion_tiers():
    """规则分档：正确率 → level；练习量少与久未练习有额外提示。"""
    from app.services.diagnosis_service import _build_review_suggestion

    lvl, _ = _build_review_suggestion(accuracy=0.2, total=10, days_since=0)
    assert lvl == "weak"
    lvl, _ = _build_review_suggestion(accuracy=0.55, total=10, days_since=0)
    assert lvl == "medium"
    lvl, _ = _build_review_suggestion(accuracy=0.95, total=10, days_since=0)
    assert lvl == "good"
    # 练习量少覆盖文案
    _, msg = _build_review_suggestion(accuracy=0.95, total=2, days_since=0)
    assert "练习量偏少" in msg
    # 久未练习追加提醒
    _, msg = _build_review_suggestion(accuracy=0.2, total=10, days_since=30)
    assert "未练习" in msg


async def _seed(db):
    uid = uuid.uuid4()
    await db.execute(text(
        "INSERT INTO users (id, openid, role) VALUES (:id, :o, 'student')"
    ), {"id": uid, "o": f"{_TAG}_{uid.hex[:10]}"})
    now = datetime.now(timezone.utc)
    # 三档：弱(0.1) / 中(0.5) / 好(0.9)
    rows = [
        (f"{_TAG}_weak", 1, 9, now),
        (f"{_TAG}_mid", 5, 5, now),
        (f"{_TAG}_good", 9, 1, now),
    ]
    for key, c, w, ts in rows:
        await db.execute(text(
            "INSERT INTO student_kp_mastery (student_id, kp_key, kp_id, correct_count, wrong_count, sources, last_activity_at) "
            "VALUES (:s, :k, NULL, :c, :w, ARRAY['practice'], :ts)"
        ), {"s": uid, "k": key, "c": c, "w": w, "ts": ts})
    await db.flush()
    return uid


async def _cleanup(db):
    await db.execute(text("DELETE FROM student_kp_mastery WHERE kp_key LIKE :p"), {"p": f"{_TAG}_%"})
    await db.execute(text("DELETE FROM users WHERE openid LIKE :p"), {"p": f"{_TAG}_%"})
    await db.flush()


@pytest.mark.asyncio
async def test_build_mastery_ledger_weak_first_with_levels():
    """台账弱项在前，等级与正确率对应，建议非空。"""
    from app.services import diagnosis_service as svc

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        try:
            uid = await _seed(db)
            ledger = await svc._build_mastery_ledger(db, student_id=uid)
            mine = [it for it in ledger if it.kp_key.startswith(_TAG)]
            assert len(mine) == 3
            # 弱项在前：accuracy 升序
            accs = [it.accuracy for it in mine]
            assert accs == sorted(accs), f"应按正确率升序, got {accs}"
            # 等级映射
            by_key = {it.kp_key: it for it in mine}
            assert by_key[f"{_TAG}_weak"].level == "weak"
            assert by_key[f"{_TAG}_mid"].level == "medium"
            assert by_key[f"{_TAG}_good"].level == "good"
            # 建议非空
            assert all(it.suggestion for it in mine)
            assert all(it.total == 10 for it in mine)
        finally:
            await _cleanup(db)
            await db.commit()
    await engine.dispose()
