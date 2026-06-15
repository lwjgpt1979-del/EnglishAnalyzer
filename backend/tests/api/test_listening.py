"""听力精听答题 + 错题归集 tests（§6.4）。"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

_TAG = "lsttest"


def _engine():
    url = os.environ.get("ASYNC_DATABASE_URL")
    if not url:
        from app.core.config import settings
        url = settings.async_database_url
    return create_async_engine(url)


@pytest.mark.asyncio
async def test_submit_and_wrongbook():
    from app.services import listening_service as svc

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        uid = uuid.uuid4()
        await db.execute(text(
            "INSERT INTO users (id,openid,role) VALUES (:i,:o,'student')"),
            {"i": uid, "o": f"{_TAG}_{uid.hex[:10]}"})
        await db.flush()
        try:
            ex = svc.list_exercises()[0]
            eid = ex["id"]
            full = svc.get_exercise(eid)
            n = len(full["questions"])
            correct_answers = [q["answer_index"] for q in full["questions"]]

            # 1) 故意全答错(每题选 (正确+1)%4) → 全部入错题库
            wrong_answers = [(a + 1) % 4 for a in correct_answers]
            r = await svc.submit_answers(db, student_id=uid, exercise_id=eid, answers=wrong_answers)
            assert r["correct_count"] == 0 and r["total"] == n
            assert r["transcript"] and len(r["results"]) == n
            wb = await svc.list_wrong(db, student_id=uid)
            assert len(wb) == n
            assert all(w["wrong_count"] == 1 for w in wb)

            # 2) 再次全错 → wrong_count 累加
            await svc.submit_answers(db, student_id=uid, exercise_id=eid, answers=wrong_answers)
            wb2 = await svc.list_wrong(db, student_id=uid)
            assert all(w["wrong_count"] == 2 for w in wb2)

            # 3) 重练全对 → 移出错题库
            r3 = await svc.submit_answers(db, student_id=uid, exercise_id=eid, answers=correct_answers)
            assert r3["correct_count"] == n
            wb3 = await svc.list_wrong(db, student_id=uid)
            assert len(wb3) == 0
        finally:
            await db.execute(text("DELETE FROM listening_wrong_questions WHERE student_id=:i"), {"i": uid})
            await db.execute(text("DELETE FROM users WHERE id=:i"), {"i": uid})
            await db.commit()
    await engine.dispose()
