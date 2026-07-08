"""adaptive_question_service 单元维度弱项推题(KP-First 重写)。

验证:
1. _weak_nodes_unit() 排序:未练习 node 最优先,其次正确率低,再次正确率高(unit_node + student_kp)
2. get_adaptive_set(unit_id=...) 端到端:weak_kp_names[0] 是未练习 node,返回题来自本单元 platform 仿真

不再涉及老 simulated_questions/knowledge_points/student_kp_mastery。
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_TAG = "m6test"


def _engine():
    db_url = os.environ.get(
        "ASYNC_DATABASE_URL",
        "postgresql+psycopg_async://postgres:dev@localhost:5432/enggramer",
    )
    return create_async_engine(db_url, echo=False)


async def _seed(db):
    """1 用户 + 1 单元 + 3 node(高/低/未练习)+ 各 2 道 platform 仿真。"""
    uid, unit_id = uuid.uuid4(), uuid.uuid4()
    n_high, n_low, n_unprac = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    name_high = f"{_TAG}_high_{n_high.hex[:8]}"
    name_low = f"{_TAG}_low_{n_low.hex[:8]}"
    name_unprac = f"{_TAG}_unprac_{n_unprac.hex[:8]}"

    await db.execute(text("INSERT INTO users (id, openid, role) VALUES (:id, :o, 'student')"),
                     {"id": uid, "o": f"{_TAG}_{uid.hex[:10]}"})
    await db.execute(text(
        "INSERT INTO curriculum_units (id, textbook_version, grade, semester, unit_no, unit_title) "
        "VALUES (:id, :tb, :g, '上', 999, :t)"),
        {"id": unit_id, "tb": f"{_TAG}版", "g": f"{_TAG}年级", "t": f"{_TAG} Unit"})

    opts = json.dumps(["A. go", "B. goes", "C. going", "D. gone"])
    for nid, nm in [(n_high, name_high), (n_low, name_low), (n_unprac, name_unprac)]:
        await db.execute(text(
            "INSERT INTO knowledge_nodes (id, axis, node_kind, name, code, status, source) "
            "VALUES (:id, 'knowledge', '句法', :nm, :code, 'active', 'seed')"),
            {"id": nid, "nm": nm, "code": f"{_TAG}_{nid.hex[:10]}"})
        await db.execute(text("INSERT INTO unit_node (unit_id, node_id) VALUES (:u, :n)"),
                         {"u": unit_id, "n": nid})
        for _ in range(5):   # 每 node 备 5 题:total=5 时首个弱 node 即可填满,不触发现生成
            qid = uuid.uuid4()
            await db.execute(text(
                "INSERT INTO platform_question (id, type, is_fallback, question_type, stem, options, answer, difficulty, status) "
                "VALUES (:id, 'sim', true, '单选', :stem, CAST(:opts AS jsonb), 'B', 1, 'published')"),
                {"id": qid, "stem": f"{_TAG} stem", "opts": opts})
            await db.execute(text(
                "INSERT INTO platform_question_kp (question_id, node_id) VALUES (:q, :n)"),
                {"q": qid, "n": nid})

    now = datetime.now(timezone.utc)
    await db.execute(text(
        "INSERT INTO student_kp (student_id, node_id, practice_count, wrong_count, last_practice_at, in_scope) "
        "VALUES (:s, :n, 10, 1, :ts, true)"), {"s": uid, "n": n_high, "ts": now})
    await db.execute(text(
        "INSERT INTO student_kp (student_id, node_id, practice_count, wrong_count, last_practice_at, in_scope) "
        "VALUES (:s, :n, 10, 9, :ts, true)"), {"s": uid, "n": n_low, "ts": now - timedelta(days=1)})
    await db.flush()
    return {"uid": uid, "unit_id": unit_id,
            "name_high": name_high, "name_low": name_low, "name_unprac": name_unprac}


async def _cleanup(db):
    await db.execute(text(
        "DELETE FROM platform_question_kp WHERE node_id IN (SELECT id FROM knowledge_nodes WHERE code LIKE :p)"),
        {"p": f"{_TAG}_%"})
    await db.execute(text("DELETE FROM platform_question WHERE stem LIKE :p"), {"p": f"{_TAG}%"})
    await db.execute(text("DELETE FROM student_kp WHERE node_id IN (SELECT id FROM knowledge_nodes WHERE code LIKE :p)"),
                     {"p": f"{_TAG}_%"})
    await db.execute(text("DELETE FROM unit_node WHERE node_id IN (SELECT id FROM knowledge_nodes WHERE code LIKE :p)"),
                     {"p": f"{_TAG}_%"})
    await db.execute(text("DELETE FROM answer_log WHERE student_id IN (SELECT id FROM users WHERE openid LIKE :p)"),
                     {"p": f"{_TAG}_%"})
    await db.execute(text("DELETE FROM curriculum_units WHERE textbook_version = :tb"), {"tb": f"{_TAG}版"})
    await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}_%"})
    await db.execute(text("DELETE FROM users WHERE openid LIKE :p"), {"p": f"{_TAG}_%"})
    await db.flush()


@pytest.mark.asyncio
async def test_weak_nodes_for_unit_prioritizes_unpracticed_then_lowest():
    from app.services import adaptive_question_service as svc
    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        try:
            ids = await _seed(db)
            weak = await svc._weak_nodes_unit(
                db, student_id=ids["uid"], unit_id=ids["unit_id"], top_n=3)
            names = [n for _, n in weak]
            assert names[0] == ids["name_unprac"], f"未练习应排第一, got {names}"
            assert names[1] == ids["name_low"], f"低正确率应排第二, got {names}"
            assert names[2] == ids["name_high"], f"高正确率应排最后, got {names}"
        finally:
            await _cleanup(db)
            await db.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_adaptive_set_unit_mode_returns_unit_questions():
    from app.services import adaptive_question_service as svc
    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        try:
            ids = await _seed(db)
            result = await svc.get_adaptive_set(
                db, student_id=ids["uid"], total=5, unit_id=ids["unit_id"])
            assert len(result.questions) > 0, "应返回题目"
            assert result.weak_kp_names[0] == ids["name_unprac"], \
                f"弱项首位应为未练习 node, got {result.weak_kp_names}"
            assert all(q.stem == f"{_TAG} stem" for q in result.questions)
        finally:
            await _cleanup(db)
            await db.commit()
    await engine.dispose()
