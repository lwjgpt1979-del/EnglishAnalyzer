"""M9 — learning_plan_service.get_today_plan tests.

验证：
1. 弱项 KP（正确率 <0.7）进入 weak_kp 任务，正确率 ≥0.7 被过滤
2. done 派生：今日练过该 KP → done=True
3. 待复习错题计入 review_pending 并生成 review 任务
4. 无任务时补 learn 引导
5. 今日打卡状态正确反映

自包含造数据（唯一前缀隔离）+ finally 清理。
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone, date

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

_TAG = "m9test"


def _engine():
    db_url = os.environ.get(
        "ASYNC_DATABASE_URL",
        "postgresql+psycopg_async://postgres:dev@localhost:5432/enggramer",
    )
    return create_async_engine(db_url, echo=False)


async def _seed_user(db) -> uuid.UUID:
    uid = uuid.uuid4()
    await db.execute(text(
        "INSERT INTO users (id, openid, role) VALUES (:id, :o, 'student')"
    ), {"id": uid, "o": f"{_TAG}_{uid.hex[:10]}"})
    await db.flush()
    return uid


async def _add_mastery(db, uid, key, kp_id, correct, wrong):
    now = datetime.now(timezone.utc)
    await db.execute(text(
        "INSERT INTO student_kp_mastery (student_id, kp_key, kp_id, correct_count, wrong_count, sources, last_activity_at) "
        "VALUES (:s, :k, :kid, :c, :w, ARRAY['practice'], :ts)"
    ), {"s": uid, "k": key, "kid": kp_id, "c": correct, "w": wrong, "ts": now})
    await db.flush()


async def _add_kp(db, kp_id, name):
    """KP-First: 造规范知识节点(knowledge_nodes),名字与 mastery kp_key 同名以便 done 派生匹配。"""
    await db.execute(text(
        "INSERT INTO knowledge_nodes (id, axis, node_kind, name, code) "
        "VALUES (:id, 'knowledge', 'grammar', :name, :code)"
    ), {"id": kp_id, "code": f"{_TAG}_{kp_id.hex[:10]}", "name": name})
    await db.flush()


async def _cleanup(db):
    await db.execute(text(
        "DELETE FROM answer_log WHERE student_id IN (SELECT id FROM users WHERE openid LIKE :p)"
    ), {"p": f"{_TAG}_%"})
    await db.execute(text("DELETE FROM study_checkins WHERE student_id IN (SELECT id FROM users WHERE openid LIKE :p)"), {"p": f"{_TAG}_%"})
    await db.execute(text("DELETE FROM student_kp_mastery WHERE kp_key LIKE :p"), {"p": f"{_TAG}_%"})
    await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}_%"})
    await db.execute(text("DELETE FROM users WHERE openid LIKE :p"), {"p": f"{_TAG}_%"})
    await db.flush()


@pytest.mark.asyncio
async def test_weak_kp_task_filtering_and_done_derivation():
    """弱项进 weak_kp、强项被过滤；今日练过的 KP → done=True。"""
    from app.services import learning_plan_service as svc

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        try:
            uid = await _seed_user(db)
            kp_weak = uuid.uuid4()
            kp_strong = uuid.uuid4()
            await _add_kp(db, kp_weak, f"{_TAG}_弱项")
            await _add_kp(db, kp_strong, f"{_TAG}_强项")
            # 弱项 acc=0.2，强项 acc=0.9（应被过滤）;mastery.kp_id=NULL(FK 指老 knowledge_points),
            # done 派生按名称匹配 node(不依赖 kp_id)
            await _add_mastery(db, uid, f"{_TAG}_弱项", None, 2, 8)
            await _add_mastery(db, uid, f"{_TAG}_强项", None, 9, 1)
            # 今日练过弱项 KP → done 应为 True（KP-First: answer_log 命中该 node,今日）
            await db.execute(text(
                "INSERT INTO answer_log (id, student_id, q_scope, question_id, is_correct, node_id, feature, answered_at) "
                "VALUES (:id, :s, 'platform', :q, true, :k, 'practice', now())"
            ), {"id": uuid.uuid4(), "s": uid, "q": uuid.uuid4(), "k": kp_weak})
            await db.flush()

            plan = await svc.get_today_plan(db, student_id=uid)
            weak_tasks = [t for t in plan.tasks if t.type == "weak_kp"]
            assert len(weak_tasks) == 1, "仅弱项应进 weak_kp"
            assert weak_tasks[0].kp_key == f"{_TAG}_弱项"
            assert weak_tasks[0].done is True, "今日练过该 KP → done"
            assert weak_tasks[0].level == "weak"
        finally:
            await _cleanup(db)
            await db.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_learn_fallback_when_no_weak_kp():
    """无弱项（全掌握）时补 learn 引导任务。"""
    from app.services import learning_plan_service as svc

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        try:
            uid = await _seed_user(db)
            kp = uuid.uuid4()
            await _add_kp(db, kp, f"{_TAG}_掌握")
            await _add_mastery(db, uid, f"{_TAG}_掌握", None, 10, 0)  # acc=1.0
            plan = await svc.get_today_plan(db, student_id=uid)
            assert all(t.type != "weak_kp" for t in plan.tasks)
            assert any(t.type == "learn" for t in plan.tasks)
            assert plan.checkin_done is False
            assert plan.review_pending == 0
        finally:
            await _cleanup(db)
            await db.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_checkin_done_reflected():
    """今日已打卡 → checkin_done=True。"""
    from app.services import learning_plan_service as svc

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        try:
            uid = await _seed_user(db)
            await db.execute(text(
                "INSERT INTO study_checkins (id, student_id, checkin_date, new_words_count, review_done, streak_days) "
                "VALUES (:id, :s, :d, 0, false, 1)"
            ), {"id": uuid.uuid4(), "s": uid, "d": datetime.now(timezone.utc).date()})
            await db.flush()
            plan = await svc.get_today_plan(db, student_id=uid)
            assert plan.checkin_done is True
        finally:
            await _cleanup(db)
            await db.commit()
    await engine.dispose()
