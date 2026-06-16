"""机构套餐 S1（§9.1/§5.6）：配置驱动 + 有效配额 + 用量只读 tests。"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

_TAG = "pkgtest"


def _engine():
    url = os.environ.get("ASYNC_DATABASE_URL")
    if not url:
        from app.core.config import settings
        url = settings.async_database_url
    return create_async_engine(url)


@pytest.mark.asyncio
async def test_package_config_effective_and_usage():
    from app.services import institution_package_service as pkg
    from app.models.d1_users import Institution
    from app.core.exceptions import AppError

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        adm = uuid.uuid4()
        inst_id = uuid.uuid4()
        t1, t2 = uuid.uuid4(), uuid.uuid4()
        await db.execute(text("INSERT INTO users (id,openid,role,is_active) VALUES (:i,:o,'platform_admin',true)"),
                         {"i": adm, "o": f"{_TAG}_adm_{adm.hex[:6]}"})
        await db.execute(text(
            "INSERT INTO institutions (id,name,contact_phone,province_code,city_code,address,status) "
            "VALUES (:i,:n,'13800000000','110000','110100','addr','active')"),
            {"i": inst_id, "n": f"{_TAG}_inst"})
        # 两个机构老师（占席位）
        for t in (t1, t2):
            await db.execute(text("INSERT INTO users (id,openid,role,is_active) VALUES (:i,:o,'teacher',true)"),
                             {"i": t, "o": f"{_TAG}_t_{t.hex[:6]}"})
            await db.execute(text("INSERT INTO teachers (id,institution_id,cert_status) VALUES (:i,:inst,'certified')"),
                             {"i": t, "inst": inst_id})
        await db.flush()
        try:
            # 默认配置含 starter/standard/flagship
            cfg = await pkg.get_config(db)
            assert any(t["key"] == "starter" for t in cfg["tiers"])

            inst = await db.get(Institution, inst_id)
            # 非套餐机构 → None
            assert await pkg.effective_for(db, inst) is None
            uo0 = await pkg.usage_overview(db, institution_id=inst_id)
            assert uo0 == {"package_tier": None}

            # 指定 starter（默认 teacher_seats=5）
            await pkg.set_institution_package(db, institution_id=inst_id, package_tier="starter")
            inst = await db.get(Institution, inst_id)
            eff = await pkg.effective_for(db, inst)
            assert eff["teacher_seats"] == 5 and eff["paper_pool"] == 100
            uo = await pkg.usage_overview(db, institution_id=inst_id)
            assert uo["teacher_seats"]["used"] == 2 and uo["teacher_seats"]["limit"] == 5

            # 配置驱动验证：把 starter 的 teacher_seats 改成 9 → effective 随之变
            new_cfg = await pkg.get_config(db)
            for t in new_cfg["tiers"]:
                if t["key"] == "starter":
                    t["teacher_seats"] = 9
            await pkg.update_config(db, config=new_cfg, admin_id=adm)
            inst = await db.get(Institution, inst_id)
            assert (await pkg.effective_for(db, inst))["teacher_seats"] == 9

            # 机构 override 优先
            await pkg.set_institution_package(db, institution_id=inst_id, package_tier="starter",
                                              overrides={"teacher_seats_override": 3})
            inst = await db.get(Institution, inst_id)
            assert (await pkg.effective_for(db, inst))["teacher_seats"] == 3

            # 未知档位被拦
            with pytest.raises(AppError):
                await pkg.set_institution_package(db, institution_id=inst_id, package_tier="nope")
            # custom（不在列表）→ 仅靠 override
            await pkg.set_institution_package(db, institution_id=inst_id, package_tier="custom",
                                              overrides={"paper_pool_override": 7})
            inst = await db.get(Institution, inst_id)
            effc = await pkg.effective_for(db, inst)
            assert effc["is_custom"] and effc["paper_pool"] == 7
        finally:
            await db.execute(text("DELETE FROM teachers WHERE institution_id=:i"), {"i": inst_id})
            await db.execute(text("DELETE FROM institutions WHERE id=:i"), {"i": inst_id})
            await db.execute(text("DELETE FROM system_configs WHERE key='institution_packages'"))
            await db.execute(text("DELETE FROM users WHERE openid LIKE :p"), {"p": f"{_TAG}_%"})
            await db.commit()
    await engine.dispose()
