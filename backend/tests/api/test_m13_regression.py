"""M13 — regression_service.detect_regressions tests.

验证从 kp_mastery_snapshots 检测退步：跌幅达阈值且样本足够才报警，按跌幅降序、严重度正确。
自包含造数据（唯一前缀）+ finally 清理。
"""
from __future__ import annotations

import os
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

_TAG = "m13test"


def _engine():
    return create_async_engine(os.environ.get(
        "ASYNC_DATABASE_URL",
        "postgresql+psycopg_async://postgres:dev@localhost:5432/enggramer"))


async def _seed_user(db):
    uid = uuid.uuid4()
    await db.execute(text("INSERT INTO users (id,openid,role) VALUES (:i,:o,'student')"),
                     {"i": uid, "o": f"{_TAG}_{uid.hex[:10]}"})
    await db.flush()
    return uid


async def _snap(db, uid, kp, dago, acc, cor, wro):
    await db.execute(text(
        "INSERT INTO kp_mastery_snapshots (id,student_id,kp_key,snapshot_date,accuracy,correct_count,wrong_count) "
        "VALUES (:i,:s,:k,:d,:a,:c,:w)"),
        {"i": uuid.uuid4(), "s": uid, "k": kp, "d": date.today() - timedelta(days=dago),
         "a": acc, "c": cor, "w": wro})


async def _cleanup(db):
    await db.execute(text("DELETE FROM kp_mastery_snapshots WHERE kp_key LIKE :p"), {"p": f"{_TAG}_%"})
    await db.execute(text("DELETE FROM users WHERE openid LIKE :p"), {"p": f"{_TAG}_%"})
    await db.flush()


@pytest.mark.asyncio
async def test_detect_regression_high_severity_and_filters():
    """退步 KP(跌40%) 报 high；上升 KP 不报；样本不足不报。"""
    from app.services import regression_service as svc

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        try:
            uid = await _seed_user(db)
            # 退步：峰值 0.85 → 最新 0.45（跌 0.40，样本足）
            await _snap(db, uid, f"{_TAG}_退步", 6, 0.85, 17, 3)
            await _snap(db, uid, f"{_TAG}_退步", 3, 0.70, 14, 6)
            await _snap(db, uid, f"{_TAG}_退步", 0, 0.45, 9, 11)
            # 上升：0.4 → 0.8（不报）
            await _snap(db, uid, f"{_TAG}_上升", 6, 0.40, 4, 6)
            await _snap(db, uid, f"{_TAG}_上升", 0, 0.80, 8, 2)
            # 退步但样本不足（最新 total=2 < 3，不报）
            await _snap(db, uid, f"{_TAG}_样本少", 6, 0.90, 9, 1)
            await _snap(db, uid, f"{_TAG}_样本少", 0, 0.50, 1, 1)
            await db.flush()

            alerts = await svc.detect_regressions(db, student_id=uid)
            keys = {a["kp_key"]: a for a in alerts}
            assert f"{_TAG}_退步" in keys, "应检出退步 KP"
            assert keys[f"{_TAG}_退步"]["severity"] == "high"
            assert abs(keys[f"{_TAG}_退步"]["drop"] - 0.40) < 0.001
            assert f"{_TAG}_上升" not in keys, "上升 KP 不应报警"
            assert f"{_TAG}_样本少" not in keys, "样本不足不应报警"
        finally:
            await _cleanup(db)
            await db.commit()
    await engine.dispose()
