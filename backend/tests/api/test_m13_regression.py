"""M13 — regression_service.detect_regressions tests.

R8.1:退步检测数据源改为从 answer_log(node)重放每日累计正确率(不再读 kp_mastery_snapshots)。
造 answer_log 事件让某 node 累计正确率先高后跌 → 报警;上升/样本不足不报。自包含 + finally 清理。
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

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


async def _node(db, name):
    nid = uuid.uuid4()
    await db.execute(text(
        "INSERT INTO knowledge_nodes (id,axis,name,code,status,source) "
        "VALUES (:i,'knowledge',:n,:c,'active','seed')"),
        {"i": nid, "n": name, "c": f"{_TAG}_{nid.hex[:8]}"})
    return nid


async def _events(db, uid, nid, dago, n_correct, n_wrong):
    """在 dago 天前那天写 n_correct 对 + n_wrong 错的 node 作答(answer_log)。"""
    base = datetime.now(timezone.utc) - timedelta(days=dago)
    seq = 0
    for cnt, ok in ((n_correct, True), (n_wrong, False)):
        for _ in range(cnt):
            await db.execute(text(
                "INSERT INTO answer_log (id,student_id,q_scope,question_id,is_correct,node_id,feature,answered_at) "
                "VALUES (:i,:s,'platform',:q,:ok,:n,'practice',:ts)"),
                {"i": uuid.uuid4(), "s": uid, "q": uuid.uuid4(), "ok": ok, "n": nid,
                 "ts": base + timedelta(seconds=seq)})
            seq += 1


async def _cleanup(db):
    await db.execute(text("DELETE FROM answer_log WHERE student_id IN (SELECT id FROM users WHERE openid LIKE :p)"), {"p": f"{_TAG}_%"})
    await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}_%"})
    await db.execute(text("DELETE FROM users WHERE openid LIKE :p"), {"p": f"{_TAG}_%"})
    await db.flush()


@pytest.mark.asyncio
async def test_detect_regression_high_severity_and_filters():
    """退步 node(累计 0.85→0.45,跌 0.40)报 high；上升 node 不报；样本不足不报。"""
    from app.services import regression_service as svc

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        try:
            uid = await _seed_user(db)
            # 退步：day-6 累计 17/20=0.85(峰值),day-0 追加 18 错 → 累计 17/38≈0.45
            n_down = await _node(db, f"{_TAG}_退步")
            await _events(db, uid, n_down, 6, 17, 3)
            await _events(db, uid, n_down, 0, 0, 18)
            # 上升：day-6 4/10=0.40,day-0 追加 8 对 → 累计 12/18≈0.67(不报)
            n_up = await _node(db, f"{_TAG}_上升")
            await _events(db, uid, n_up, 6, 4, 6)
            await _events(db, uid, n_up, 0, 8, 0)
            # 样本不足：day-6 1 对、day-0 1 错 → 最新累计 total=2 < 3(不报)
            n_few = await _node(db, f"{_TAG}_样本少")
            await _events(db, uid, n_few, 6, 1, 0)
            await _events(db, uid, n_few, 0, 0, 1)
            await db.flush()

            alerts = await svc.detect_regressions(db, student_id=uid)
            keys = {a["kp_key"]: a for a in alerts}
            assert f"{_TAG}_退步" in keys, "应检出退步 node"
            assert keys[f"{_TAG}_退步"]["severity"] == "high"
            assert abs(keys[f"{_TAG}_退步"]["drop"] - 0.40) < 0.01
            assert f"{_TAG}_上升" not in keys, "上升 node 不应报警"
            assert f"{_TAG}_样本少" not in keys, "样本不足不应报警"
        finally:
            await _cleanup(db)
            await db.commit()
    await engine.dispose()
