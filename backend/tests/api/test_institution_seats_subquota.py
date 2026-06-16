"""机构套餐 S3（席位上限）+ S4（池内老师子上限设置）tests。"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

_TAG = "seatq"


def _engine():
    url = os.environ.get("ASYNC_DATABASE_URL")
    if not url:
        from app.core.config import settings
        url = settings.async_database_url
    return create_async_engine(url)


@pytest.mark.asyncio
async def test_seat_limit_and_sub_quota():
    from app.services import institution_package_service as pkg
    from app.services import institution_service
    from app.models.d1_users import Teacher
    from app.core.exceptions import AppError

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        inst_id = uuid.uuid4()
        t1, t2 = uuid.uuid4(), uuid.uuid4()
        free_inst = None
        await db.execute(text("INSERT INTO institutions (id,name,contact_phone,province_code,city_code,address,status,package_tier,teacher_seats_override) "
                              "VALUES (:i,:n,'13800000000','110000','110100','a','active','starter',2)"),
                         {"i": inst_id, "n": f"{_TAG}_inst"})
        for t in (t1, t2):
            await db.execute(text("INSERT INTO users (id,openid,role,is_active) VALUES (:i,:o,'teacher',true)"),
                             {"i": t, "o": f"{_TAG}_t_{t.hex[:6]}"})
            await db.execute(text("INSERT INTO teachers (id,institution_id,cert_status) VALUES (:i,:inst,'certified')"),
                             {"i": t, "inst": inst_id})
        await db.flush()
        try:
            # S3：席位上限=2，已 2 人 → 再加被拦
            with pytest.raises(AppError) as ei:
                await pkg.assert_can_add_teacher(db, institution_id=inst_id)
            assert ei.value.code == 403 and "席位" in ei.value.message

            # 非套餐机构 → 不限
            free_inst = uuid.uuid4()
            await db.execute(text("INSERT INTO institutions (id,name,contact_phone,province_code,city_code,address,status) "
                                  "VALUES (:i,:n,'13800000000','110000','110100','a','active')"),
                             {"i": free_inst, "n": f"{_TAG}_free"})
            await db.flush()
            await pkg.assert_can_add_teacher(db, institution_id=free_inst)  # 不抛

            # S4：给 t1 设池内子上限（出卷=5，批改=3）
            await institution_service.set_teacher_quota(
                db, institution_id=inst_id, teacher_id=t1,
                monthly_paper_quota=5, monthly_grading_quota=3, set_grading=True)
            db.expire_all()
            tt = await db.get(Teacher, t1)
            assert tt.monthly_paper_quota == 5 and tt.monthly_grading_quota == 3
            # 清空出卷子上限（随池共享），批改保留
            await institution_service.set_teacher_quota(
                db, institution_id=inst_id, teacher_id=t1,
                monthly_paper_quota=None, monthly_grading_quota=3, set_grading=True)
            db.expire_all()
            tt = await db.get(Teacher, t1)
            assert tt.monthly_paper_quota is None and tt.monthly_grading_quota == 3
            # 跨机构拒绝
            with pytest.raises(AppError):
                await institution_service.set_teacher_quota(
                    db, institution_id=free_inst, teacher_id=t1, monthly_paper_quota=1)
        finally:
            await db.execute(text("DELETE FROM teachers WHERE institution_id=:i"), {"i": inst_id})
            await db.execute(text("DELETE FROM users WHERE openid LIKE :p"), {"p": f"{_TAG}_%"})
            await db.execute(text("DELETE FROM institutions WHERE id=:i"), {"i": inst_id})
            if free_inst:
                await db.execute(text("DELETE FROM institutions WHERE id=:i"), {"i": free_inst})
            await db.commit()
    await engine.dispose()
