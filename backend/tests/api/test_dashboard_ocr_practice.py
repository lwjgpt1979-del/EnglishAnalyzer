"""数据大盘 §5.5 收尾：OCR 手动修正率 + 题库练习来源拆分。"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

_TAG = "dqocrtest"


def _engine():
    url = os.environ.get("ASYNC_DATABASE_URL")
    if not url:
        from app.core.config import settings
        url = settings.async_database_url
    return create_async_engine(url)


@pytest.mark.asyncio
async def test_ocr_correction_and_practice_split():
    from app.services import dashboard_service as ds
    from app.models.d3_wrong_questions import WrongQuestion

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        uid = uuid.uuid4()
        await db.execute(text("INSERT INTO users (id,openid,role,is_active) VALUES (:i,:o,'student',true)"),
                         {"i": uid, "o": f"{_TAG}_{uid.hex[:8]}"})
        await db.flush()
        try:
            before = (await ds.get_dashboard(db))["content_quality"]["ocr_correction"]

            # 一条 completed 且被手动修正的错题
            wq = WrongQuestion(id=uuid.uuid4(), student_id=uid,
                               source_image_url="http://x/a.png",
                               ocr_status="completed", ocr_corrected=True)
            db.add(wq)
            await db.flush()

            cq = (await ds.get_dashboard(db))["content_quality"]
            after = cq["ocr_correction"]
            assert after["completed"] == before["completed"] + 1
            assert after["corrected"] == before["corrected"] + 1
            assert after["rate_pct"] >= 0

            # 练习拆分结构合法
            ps = cq["practice_split"]
            assert set(["free_entry", "review_triggered", "total", "free_pct", "review_pct"]) <= set(ps)
            assert ps["total"] == ps["free_entry"] + ps["review_triggered"]
        finally:
            await db.execute(text("DELETE FROM wrong_questions WHERE student_id=:u"), {"u": uid})
            await db.execute(text("DELETE FROM users WHERE openid LIKE :p"), {"p": f"{_TAG}_%"})
            await db.commit()
    await engine.dispose()
