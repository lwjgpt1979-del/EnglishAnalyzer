"""M10 — incentive_service.get_summary 派生逻辑 tests.

验证 XP/等级/成就 从活动数据正确派生（无新表）。
自包含造数据（唯一前缀）+ finally 清理。
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

_TAG = "m10test"


def _engine():
    return create_async_engine(os.environ.get(
        "ASYNC_DATABASE_URL",
        "postgresql+psycopg_async://postgres:dev@localhost:5432/enggramer"))


async def _seed(db):
    uid = uuid.uuid4()
    await db.execute(text("INSERT INTO users (id,openid,role) VALUES (:i,:o,'student')"),
                     {"i": uid, "o": f"{_TAG}_{uid.hex[:10]}"})
    now = datetime.now(timezone.utc)
    today = now.date()
    # 2 天打卡（含今日）→ checkin XP 20，且 longest_streak=2
    for d in range(2):
        await db.execute(text(
            "INSERT INTO study_checkins (id,student_id,checkin_date,new_words_count,review_done,streak_days) "
            "VALUES (:i,:s,:d,5,true,:st)"), {"i": uuid.uuid4(), "s": uid, "d": today - timedelta(days=d), "st": 2 - d})
    # 1 个达标 KP（acc=1.0）→ kp XP 20（R8.1:掌握台账走 student_kp/node）
    nid = uuid.uuid4()
    await db.execute(text(
        "INSERT INTO knowledge_nodes (id,axis,name,code,status,source) "
        "VALUES (:n,'knowledge',:nm,:c,'active','seed')"),
        {"n": nid, "nm": f"{_TAG}_kp", "c": f"{_TAG}_{nid.hex[:8]}"})
    await db.execute(text(
        "INSERT INTO student_kp (student_id,node_id,practice_count,wrong_count,source_tags,last_practice_at) "
        "VALUES (:s,:n,10,0,ARRAY['practice'],:ts)"),
        {"s": uid, "n": nid, "ts": now})
    # 1 道已掌握错题 → wrong XP 15
    await db.execute(text(
        "INSERT INTO wrong_questions (id,student_id,source_image_url,is_mastered,created_at,mastered_at) "
        "VALUES (:i,:s,'seed',true,:c,:c)"), {"i": uuid.uuid4(), "s": uid, "c": now})
    # 1 场模拟考 acc=0.9 → exam XP 10 + exam_ace 解锁
    # KP-First:一场 = 同一 answered_at 的一批 exam 作答(10题9对);feature='exam' 不计练习 XP
    exam_ts = now - timedelta(hours=1)
    for i in range(10):
        await db.execute(text(
            "INSERT INTO answer_log (id,student_id,q_scope,question_id,is_correct,node_id,feature,answered_at) "
            "VALUES (:i,:s,'platform',:q,:ok,NULL,'exam',:ts)"),
            {"i": uuid.uuid4(), "s": uid, "q": uuid.uuid4(), "ok": i < 9, "ts": exam_ts})
    await db.flush()
    return uid


async def _cleanup(db):
    for t in ["study_checkins", "answer_log"]:
        await db.execute(text(
            f"DELETE FROM {t} WHERE student_id IN (SELECT id FROM users WHERE openid LIKE :p)"),
            {"p": f"{_TAG}_%"})
    await db.execute(text(
        "DELETE FROM wrong_questions WHERE student_id IN (SELECT id FROM users WHERE openid LIKE :p)"),
        {"p": f"{_TAG}_%"})
    await db.execute(text("DELETE FROM student_kp WHERE student_id IN (SELECT id FROM users WHERE openid LIKE :p)"), {"p": f"{_TAG}_%"})
    await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}_%"})
    await db.execute(text("DELETE FROM users WHERE openid LIKE :p"), {"p": f"{_TAG}_%"})
    await db.flush()


@pytest.mark.asyncio
async def test_incentive_xp_level_achievements():
    """XP = 打卡20 + KP20 + 错题15 + 模拟考10 = 65；Lv1；exam_ace 解锁。"""
    from app.services import incentive_service as svc

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        try:
            uid = await _seed(db)
            s = await svc.get_summary(db, student_id=uid)
            # 0 练习 + 2打卡*10 + 1KP*20 + 1错题*15 + 1考*10 = 65
            assert s["xp"] == 65, f"XP 应为 65, got {s['xp']}"
            assert s["level"] == 1
            assert s["xp_in_level"] == 65 and s["xp_to_next"] == 35
            assert s["longest_streak"] == 2
            ach = {a["key"]: a for a in s["achievements"]}
            assert ach["exam_ace"]["unlocked"] is True          # acc 0.9 ≥ 0.8
            assert ach["first_step"]["unlocked"] is False        # 0 练习
            assert ach["kp_master"]["current"] == 1 and ach["kp_master"]["target"] == 10
            assert s["stats"]["mastered_kp"] == 1
            assert s["stats"]["wrong_mastered"] == 1
        finally:
            await _cleanup(db)
            await db.commit()
    await engine.dispose()
