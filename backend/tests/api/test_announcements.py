"""平台公告（§5.6）：定向匹配 + 时间窗 + 置顶。"""
from __future__ import annotations

import os
import uuid
import datetime as dt

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

_TAG = "anntest"


def _engine():
    url = os.environ.get("ASYNC_DATABASE_URL")
    if not url:
        from app.core.config import settings
        url = settings.async_database_url
    return create_async_engine(url)


@pytest.mark.asyncio
async def test_announcement_targeting():
    from app.services import announcement_service as asvc

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        adm = uuid.uuid4()
        stu = uuid.uuid4()
        inst = uuid.uuid4()
        await db.execute(text("INSERT INTO users (id,openid,role,is_active) VALUES (:i,:o,'platform_admin',true)"),
                         {"i": adm, "o": f"{_TAG}_adm_{adm.hex[:8]}"})
        await db.execute(text("INSERT INTO users (id,openid,role,is_active) VALUES (:i,:o,'student',true)"),
                         {"i": stu, "o": f"{_TAG}_{stu.hex[:8]}"})
        await db.execute(text(
            "INSERT INTO institutions (id,name,contact_phone,province_code,city_code,address,status) "
            "VALUES (:i,:n,'13800000000','110000','110100','addr','active')"),
            {"i": inst, "n": f"{_TAG}_inst"})
        await db.execute(text("INSERT INTO students (id,institution_id,grade) VALUES (:i,:inst,:g)"),
                         {"i": stu, "inst": inst, "g": "小学5年级"})
        await db.flush()
        ids = []
        try:
            a_all = await asvc.admin_create(db, admin_id=adm, title=f"{_TAG} 全平台", content="x", audience="all", pinned=True)
            a_grade = await asvc.admin_create(db, admin_id=adm, title=f"{_TAG} 五年级", content="x", audience="grade", target_values=["小学5年级"])
            a_inst = await asvc.admin_create(db, admin_id=adm, title=f"{_TAG} 本机构", content="x", audience="institution", target_values=[str(inst)])
            a_other = await asvc.admin_create(db, admin_id=adm, title=f"{_TAG} 六年级", content="x", audience="grade", target_values=["小学6年级"])
            ids = [a_all.id, a_grade.id, a_inst.id, a_other.id]
            await db.flush()

            res = await asvc.public_list(db, user_id=stu)
            titles = [i["title"] for i in res["items"]]
            assert any("全平台" in t for t in titles)
            assert any("五年级" in t for t in titles)
            assert any("本机构" in t for t in titles)
            assert not any("六年级" in t for t in titles)   # 非本年级不可见
            # 置顶在最前
            assert "全平台" in res["items"][0]["title"]

            # 停用后不可见
            await asvc.admin_update(db, ann_id=a_grade.id, fields={"is_active": False})
            res2 = await asvc.public_list(db, user_id=stu)
            assert not any("五年级" in i["title"] for i in res2["items"])
        finally:
            for i in ids:
                await db.execute(text("DELETE FROM announcements WHERE id=:i"), {"i": i})
            await db.execute(text("DELETE FROM students WHERE id=:i"), {"i": stu})
            await db.execute(text("DELETE FROM institutions WHERE id=:i"), {"i": inst})
            await db.execute(text("DELETE FROM users WHERE openid LIKE :p"), {"p": f"{_TAG}_%"})
            await db.commit()
    await engine.dispose()
