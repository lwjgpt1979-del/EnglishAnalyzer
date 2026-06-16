"""§5.6 敏感词过滤 / §5.7 定价历史 / §5.8 老师认证增强 tests。"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

_TAG = "cpctest"


def _engine():
    url = os.environ.get("ASYNC_DATABASE_URL")
    if not url:
        from app.core.config import settings
        url = settings.async_database_url
    return create_async_engine(url)


@pytest.mark.asyncio
async def test_sensitive_words_filter():
    from app.services import content_filter_service as cf
    from app.core.exceptions import AppError

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        adm = uuid.uuid4()
        word = f"{_TAG}badword"
        try:
            await cf.admin_add(db, admin_id=adm, word=word, category="ad", action="block")
            maskw = f"{_TAG}maskme"
            await cf.admin_add(db, admin_id=adm, word=maskw, category="other", action="mask")
            await db.flush()

            hits = await cf.find_hits(db, f"这是 {word} 测试")
            assert word.lower() in hits
            # block 词 → assert_clean 抛错
            with pytest.raises(AppError):
                await cf.assert_clean(db, f"含 {word} 的内容")
            # 干净内容通过
            await cf.assert_clean(db, "完全正常的内容")
            # mask 词替换
            masked = await cf.mask(db, f"x {maskw} y")
            assert maskw not in masked and "*" in masked
        finally:
            await db.execute(text("DELETE FROM sensitive_words WHERE word LIKE :p"), {"p": f"{_TAG}%"})
            await db.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_pricing_history():
    from app.services import pricing_service as ps
    from app.schemas.semesters import SemesterPricing

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        adm = uuid.uuid4()
        await db.execute(text("INSERT INTO users (id,openid,role,is_active) VALUES (:i,:o,'platform_admin',true)"),
                         {"i": adm, "o": f"{_TAG}_padm_{adm.hex[:8]}"})
        await db.flush()
        before = len(await ps.pricing_history(db, limit=200))
        await ps.update_semester_pricing(
            db, pricing=SemesterPricing(basic=39, pro=79, promax=159, list_pro=99),
            updated_by=adm)
        await db.flush()
        hist = await ps.pricing_history(db, limit=200)
        assert len(hist) == before + 1
        assert hist[0]["snapshot"]["list_pro"] == 99
        # 回滚定价改动（system_configs 不留测试痕迹）
        await db.rollback()
        async with sf() as db2:
            await db2.execute(text("DELETE FROM price_change_logs WHERE changed_by=:a"), {"a": adm})
            await db2.execute(text("DELETE FROM users WHERE id=:a"), {"a": adm})
            await db2.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_teacher_cert_claim_review_quality():
    from app.services import teacher_service as ts
    from app.core.exceptions import AppError

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        uid = uuid.uuid4()
        adm1, adm2 = uuid.uuid4(), uuid.uuid4()
        await db.execute(text("INSERT INTO users (id,openid,role,is_active) VALUES (:i,:o,'teacher',true)"),
                         {"i": uid, "o": f"{_TAG}_{uid.hex[:8]}"})
        await db.execute(text(
            "INSERT INTO teachers (id,cert_status,cert_submitted_at) VALUES (:i,'pending',now())"),
            {"i": uid})
        await db.flush()
        try:
            # 认领
            await ts.claim_cert(db, teacher_id=uid, admin_id=adm1)
            # 他人不可再认领
            with pytest.raises(AppError):
                await ts.claim_cert(db, teacher_id=uid, admin_id=adm2)
            # 驳回必须填原因
            with pytest.raises(AppError):
                await ts.review_cert(db, teacher_id=uid, approve=False, reason="")
            # 驳回写原因 + 通知
            await ts.review_cert(db, teacher_id=uid, approve=False, reason="盖章不清晰")
            row = (await db.execute(text(
                "SELECT cert_status, cert_reject_reason FROM teachers WHERE id=:i"), {"i": uid})).first()
            assert row[0] == "rejected" and row[1] == "盖章不清晰"
            ntf = await db.scalar(text(
                "SELECT count(*) FROM notifications WHERE user_id=:u AND title LIKE '%认证未通过%'"), {"u": uid})
            assert ntf >= 1
            # 质量监控
            q = await ts.cert_quality(db, days=30)
            assert q["applied"] >= 1 and "pass_rate_pct" in q
            assert any(x["reason"] == "盖章不清晰" for x in q["reject_reasons_top"])
        finally:
            await db.execute(text("DELETE FROM notifications WHERE user_id=:u"), {"u": uid})
            await db.execute(text("DELETE FROM teachers WHERE id=:i"), {"i": uid})
            await db.execute(text("DELETE FROM users WHERE openid LIKE :p"), {"p": f"{_TAG}_%"})
            await db.commit()
    await engine.dispose()
