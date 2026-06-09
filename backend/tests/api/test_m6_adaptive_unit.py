"""M6 — adaptive_question_service 单元维度弱项推题 tests.

验证两件事（针对真实 DB，AI 补题被 mock 兜底但理论上不触发）：
1. _get_weak_kps_for_unit() 排序：未练习 KP 最优先，其次正确率低，再次正确率高
2. get_adaptive_set(unit_id=...) 端到端：weak_kp_names[0] 是未练习 KP，返回题目来自该单元

测试数据用唯一前缀隔离，finally 中清理，避免污染。
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone, timedelta

import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

_TAG = "m6test"


def _engine():
    db_url = os.environ.get(
        "ASYNC_DATABASE_URL",
        "postgresql+psycopg_async://postgres:dev@localhost:5432/enggramer",
    )
    return create_async_engine(db_url, echo=False)


async def _seed(db):
    """造数据：1 用户 + 1 单元 + 3 KP（高/低/未练习），返回各 id 与 name。"""
    uid = uuid.uuid4()
    unit_id = uuid.uuid4()
    kp_high = uuid.uuid4()
    kp_low = uuid.uuid4()
    kp_unprac = uuid.uuid4()
    name_high = f"{_TAG}_high_{kp_high.hex[:8]}"
    name_low = f"{_TAG}_low_{kp_low.hex[:8]}"
    name_unprac = f"{_TAG}_unprac_{kp_unprac.hex[:8]}"

    # user
    await db.execute(text(
        "INSERT INTO users (id, openid, role) VALUES (:id, :openid, 'student')"
    ), {"id": uid, "openid": f"{_TAG}_{uid.hex[:10]}"})

    # unit
    await db.execute(text(
        "INSERT INTO curriculum_units (id, textbook_version, grade, semester, unit_no, unit_title) "
        "VALUES (:id, :tb, :g, '上', 999, :title)"
    ), {"id": unit_id, "tb": f"{_TAG}版", "g": f"{_TAG}年级", "title": f"{_TAG} Unit"})

    # 3 KPs
    for kid, kname in [(kp_high, name_high), (kp_low, name_low), (kp_unprac, name_unprac)]:
        await db.execute(text(
            "INSERT INTO knowledge_points (id, code, name, category, applicable_grades, applicable_textbooks, sort_order) "
            "VALUES (:id, :code, :name, 'grammar', ARRAY['测试年级'], ARRAY['测试版'], 0)"
        ), {"id": kid, "code": f"{_TAG}_{kid.hex[:10]}", "name": kname})
        await db.execute(text(
            "INSERT INTO unit_knowledge_points (unit_id, knowledge_point_id) VALUES (:u, :k)"
        ), {"u": unit_id, "k": kid})
        # 每个 KP 造 3 道 published 题（避免触发 AI 补题）
        for _ in range(3):
            await db.execute(text(
                "INSERT INTO simulated_questions (id, knowledge_point_id, question_type, stem, answer, difficulty, status) "
                "VALUES (:id, :k, '单选', :stem, 'A', 1, 'published')"
            ), {"id": uuid.uuid4(), "k": kid, "stem": f"{_TAG} stem"})

    now = datetime.now(timezone.utc)
    # mastery: high = 9 对 1 错 (0.9)，low = 1 对 9 错 (0.1)；unprac 无记录
    await db.execute(text(
        "INSERT INTO student_kp_mastery (student_id, kp_key, kp_id, correct_count, wrong_count, sources, last_activity_at) "
        "VALUES (:s, :k, :kid, 9, 1, ARRAY['practice'], :ts)"
    ), {"s": uid, "k": name_high, "kid": kp_high, "ts": now})
    await db.execute(text(
        "INSERT INTO student_kp_mastery (student_id, kp_key, kp_id, correct_count, wrong_count, sources, last_activity_at) "
        "VALUES (:s, :k, :kid, 1, 9, ARRAY['practice'], :ts)"
    ), {"s": uid, "k": name_low, "kid": kp_low, "ts": now - timedelta(days=1)})

    await db.flush()
    return {
        "uid": uid, "unit_id": unit_id,
        "name_high": name_high, "name_low": name_low, "name_unprac": name_unprac,
    }


async def _cleanup(db):
    """按 FK 依赖顺序清理所有 _TAG 数据。"""
    await db.execute(text(
        "DELETE FROM simulated_questions WHERE knowledge_point_id IN "
        "(SELECT id FROM knowledge_points WHERE code LIKE :p)"
    ), {"p": f"{_TAG}_%"})
    await db.execute(text(
        "DELETE FROM unit_knowledge_points WHERE knowledge_point_id IN "
        "(SELECT id FROM knowledge_points WHERE code LIKE :p)"
    ), {"p": f"{_TAG}_%"})
    await db.execute(text("DELETE FROM student_kp_mastery WHERE kp_key LIKE :p"), {"p": f"{_TAG}_%"})
    await db.execute(text("DELETE FROM curriculum_units WHERE textbook_version = :tb"), {"tb": f"{_TAG}版"})
    await db.execute(text("DELETE FROM knowledge_points WHERE code LIKE :p"), {"p": f"{_TAG}_%"})
    await db.execute(text("DELETE FROM users WHERE openid LIKE :p"), {"p": f"{_TAG}_%"})
    await db.flush()


@pytest.mark.asyncio
async def test_weak_kps_for_unit_prioritizes_unpracticed_then_lowest():
    """未练习 KP 排第一，其次正确率最低，正确率高的排最后。"""
    from app.services import adaptive_question_service as svc

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        try:
            ids = await _seed(db)
            kps = await svc._get_weak_kps_for_unit(
                db, student_id=ids["uid"], unit_id=ids["unit_id"], top_n=3
            )
            names = [k.name for k in kps]
            assert names[0] == ids["name_unprac"], f"未练习应排第一, got {names}"
            assert names[1] == ids["name_low"], f"低正确率应排第二, got {names}"
            assert names[2] == ids["name_high"], f"高正确率应排最后, got {names}"
        finally:
            await _cleanup(db)
            await db.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_adaptive_set_unit_mode_returns_unit_questions():
    """unit_id 模式：返回题目非空，弱项首位是未练习 KP。"""
    from app.services import adaptive_question_service as svc

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    # AI 补题理论上不触发（每 KP 有 3 道 published 题），但 mock 兜底防误触发外部调用
    with patch.object(svc, "generate_questions", new=AsyncMock(return_value=[])):
        async with sf() as db:
            try:
                ids = await _seed(db)
                result = await svc.get_adaptive_set(
                    db, student_id=ids["uid"], total=5, unit_id=ids["unit_id"]
                )
                assert len(result.questions) > 0, "应返回题目"
                assert result.weak_kp_names[0] == ids["name_unprac"], \
                    f"弱项首位应为未练习 KP, got {result.weak_kp_names}"
                # 返回的题目都属于本单元 3 个 KP
                assert all(q.stem == f"{_TAG} stem" for q in result.questions)
            finally:
                await _cleanup(db)
                await db.commit()
    await engine.dispose()
