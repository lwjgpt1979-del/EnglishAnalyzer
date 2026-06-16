"""数据大盘补全（§5.5）：复盘率拆分 / ARPU / OCR成功率 / 机构续费率。"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

_TAG = "dqtest"


def _engine():
    url = os.environ.get("ASYNC_DATABASE_URL")
    if not url:
        from app.core.config import settings
        url = settings.async_database_url
    return create_async_engine(url)


@pytest.mark.asyncio
async def test_mastery_source_and_dashboard_quality():
    from app.services import dashboard_service as ds
    from app.services import wrong_question_service as wqs
    from app.models.d3_wrong_questions import WrongQuestion

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        uid = uuid.uuid4()
        await db.execute(text("INSERT INTO users (id,openid,role,is_active) VALUES (:i,:o,'student',true)"),
                         {"i": uid, "o": f"{_TAG}_{uid.hex[:8]}"})
        wq = WrongQuestion(id=uuid.uuid4(), student_id=uid,
                           source_image_url="http://x/a.png", ocr_status="completed")
        db.add(wq)
        await db.flush()
        try:
            before = await ds.get_dashboard(db)
            rr0 = before["content_quality"]["review_rate"]

            # 手动标记掌握 → mastery_source=manual
            await wqs.mark_mastered(db, wq=wq, is_mastered=True)
            await db.flush()
            assert wq.mastery_source == "manual"

            after = await ds.get_dashboard(db)
            rr1 = after["content_quality"]["review_rate"]
            assert rr1["by_manual"] == rr0["by_manual"] + 1
            assert rr1["mastered"] == rr0["mastered"] + 1

            # 其它指标结构存在且合法
            assert "arpu_month_yuan" in after["revenue"]
            assert after["content_quality"]["ocr_success"]["wrong_questions"]["rate_pct"] >= 0
            assert "rate_pct" in after["institution"]["renewal"]

            # 取消掌握 → source 清空
            await wqs.mark_mastered(db, wq=wq, is_mastered=False)
            assert wq.mastery_source is None
        finally:
            await db.execute(text("DELETE FROM wrong_questions WHERE student_id=:u"), {"u": uid})
            await db.execute(text("DELETE FROM users WHERE openid LIKE :p"), {"p": f"{_TAG}_%"})
            await db.commit()
    await engine.dispose()
