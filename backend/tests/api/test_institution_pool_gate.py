"""机构套餐 S2：机构池闸门（出卷/批改扣机构池 + 池内子上限 + 池预警）tests。

用批改(grading)路径覆盖 _gate 全分支；出卷(paper)为同一代码 kind 参数。
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

_TAG = "poolgate"


def _engine():
    url = os.environ.get("ASYNC_DATABASE_URL")
    if not url:
        from app.core.config import settings
        url = settings.async_database_url
    return create_async_engine(url)


async def _add_comment(db, teacher_id, student_id):
    wq = uuid.uuid4()
    await db.execute(text("INSERT INTO wrong_questions (id,student_id,source_image_url,ocr_status) "
                          "VALUES (:i,:s,'http://x/a.png','completed')"), {"i": wq, "s": student_id})
    await db.execute(text("INSERT INTO teacher_comments (id,wrong_question_id,teacher_id,comment_text,created_at) "
                          "VALUES (:i,:w,:t,'好',now())"), {"i": uuid.uuid4(), "w": wq, "t": teacher_id})
    return wq


@pytest.mark.asyncio
async def test_pool_gate_grading():
    from app.services import institution_package_service as pkg
    from app.services import teacher_limit_service as tl
    from app.models.d1_users import Teacher
    from app.core.exceptions import AppError

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        adm, inst_id = uuid.uuid4(), uuid.uuid4()
        instadm = uuid.uuid4()
        tch, tch2, stu = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        free_tch, free_stu = uuid.uuid4(), uuid.uuid4()
        await db.execute(text("INSERT INTO users (id,openid,role,is_active) VALUES (:i,:o,'platform_admin',true)"),
                         {"i": adm, "o": f"{_TAG}_adm_{adm.hex[:6]}"})
        await db.execute(text("INSERT INTO institutions (id,name,contact_phone,province_code,city_code,address,status,package_tier) "
                              "VALUES (:i,:n,'13800000000','110000','110100','a','active','starter')"),
                         {"i": inst_id, "n": f"{_TAG}_inst"})
        await db.execute(text("INSERT INTO users (id,openid,role,is_active,institution_id) VALUES (:i,:o,'institution_admin',true,:inst)"),
                         {"i": instadm, "o": f"{_TAG}_ia_{instadm.hex[:6]}", "inst": inst_id})
        for u, who in ((tch, "teacher"), (tch2, "teacher"), (stu, "student"),
                       (free_tch, "teacher"), (free_stu, "student")):
            await db.execute(text("INSERT INTO users (id,openid,role,is_active) VALUES (:i,:o,:r,true)"),
                             {"i": u, "o": f"{_TAG}_{who}_{u.hex[:6]}", "r": who})
        # 两个机构老师 + 一个自由老师
        await db.execute(text("INSERT INTO teachers (id,institution_id,cert_status) VALUES (:i,:inst,'certified')"), {"i": tch, "inst": inst_id})
        await db.execute(text("INSERT INTO teachers (id,institution_id,cert_status) VALUES (:i,:inst,'certified')"), {"i": tch2, "inst": inst_id})
        await db.execute(text("INSERT INTO teachers (id,cert_status) VALUES (:i,'certified')"), {"i": free_tch})
        await db.flush()
        try:
            # 配置：starter 批改池设为 2（配置驱动）
            cfg = await pkg.get_config(db)
            for t in cfg["tiers"]:
                if t["key"] == "starter":
                    t["grading_pool"] = 2
            await pkg.update_config(db, config=cfg, admin_id=adm)

            # 自由老师 → 池闸门返回 False（走个体逻辑）
            free_t = await db.get(Teacher, free_tch)
            assert await pkg.gate_grading(db, teacher=free_t) is False

            # 机构老师：池=2。tch 批改 1 条后，池用 1
            t1 = await db.get(Teacher, tch)
            assert await pkg.gate_grading(db, teacher=t1) is True   # 0<2 通过 (并触发越线预警)
            await _add_comment(db, tch, stu)
            await db.flush()
            # tch2 再批改：池用已 1，仍 <2 通过
            t2 = await db.get(Teacher, tch2)
            assert await pkg.gate_grading(db, teacher=t2) is True
            await _add_comment(db, tch2, stu)
            await db.flush()
            # 池已满(2)，任意机构老师被拦
            with pytest.raises(AppError) as ei:
                await pkg.gate_grading(db, teacher=t1)
            assert ei.value.code == 403 and "机构本月" in ei.value.message

            # 机构管理员收到池预警
            warned = await db.scalar(text(
                "SELECT count(*) FROM notifications WHERE user_id=:a AND title='机构额度预警'"), {"a": instadm})
            assert warned >= 1

            # 池内老师子上限：把池放大、给 tch 设子上限=1（已用1）→ 子额度拦
            cfg2 = await pkg.get_config(db)
            for t in cfg2["tiers"]:
                if t["key"] == "starter":
                    t["grading_pool"] = 999
            await pkg.update_config(db, config=cfg2, admin_id=adm)
            await db.execute(text("UPDATE teachers SET monthly_grading_quota=1 WHERE id=:i"), {"i": tch})
            await db.flush()
            db.expire_all()   # 让 ORM 重新从库读取（避免身份映射缓存旧值）
            t1 = await db.get(Teacher, tch)
            with pytest.raises(AppError) as ei2:
                await pkg.gate_grading(db, teacher=t1)
            assert "子额度" in ei2.value.message

            # 经 teacher_limit_service 入口委派：机构老师走池（池999、子上限1已满）→ 仍拦
            with pytest.raises(AppError):
                await tl.check_grading_and_warn(db, teacher_id=tch)
            # 自由老师经入口 → 个体逻辑（默认额度足够，放行）
            await tl.check_grading_and_warn(db, teacher_id=free_tch)
        finally:
            await db.execute(text("DELETE FROM teacher_comments WHERE teacher_id IN (:a,:b)"), {"a": tch, "b": tch2})
            await db.execute(text("DELETE FROM wrong_questions WHERE student_id IN (:a,:b)"), {"a": stu, "b": free_stu})
            await db.execute(text("DELETE FROM teachers WHERE id IN (:a,:b,:c)"), {"a": tch, "b": tch2, "c": free_tch})
            await db.execute(text("DELETE FROM notifications WHERE user_id=:a"), {"a": instadm})
            await db.execute(text("DELETE FROM system_configs WHERE key='institution_packages'"))
            # 先删用户（institution_admin 的 institution_id FK 引用机构），再删机构
            await db.execute(text("DELETE FROM users WHERE openid LIKE :p"), {"p": f"{_TAG}_%"})
            await db.execute(text("DELETE FROM institutions WHERE id=:i"), {"i": inst_id})
            await db.commit()
    await engine.dispose()
