"""老师月度限额配置化（§5.6）tests。"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

_TAG = "tllimit"


def _engine():
    url = os.environ.get("ASYNC_DATABASE_URL")
    if not url:
        from app.core.config import settings
        url = settings.async_database_url
    return create_async_engine(url)


@pytest.mark.asyncio
async def test_limits_config_override_and_gates():
    from app.services import teacher_limit_service as tl
    from app.core.exceptions import AppError
    from app.models.d1_users import Teacher

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        adm, tch, stu = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        for uid, role in ((adm, "platform_admin"), (tch, "teacher"), (stu, "student")):
            await db.execute(text("INSERT INTO users (id,openid,role,is_active) VALUES (:i,:o,:r,true)"),
                             {"i": uid, "o": f"{_TAG}_{role}_{uid.hex[:6]}", "r": role})
        await db.execute(text("INSERT INTO teachers (id,cert_status) VALUES (:i,'certified')"), {"i": tch})
        await db.flush()
        try:
            # 全局配置：改默认
            saved = await tl.update_limits(db, fields={"max_students": 1, "monthly_grading_quota": 1,
                                                       "monthly_paper_quota": 5, "warn_threshold_pct": 20},
                                           admin_id=adm)
            assert saved["max_students"] == 1
            got = await tl.get_limits(db)
            assert got["monthly_grading_quota"] == 1

            teacher = await db.get(Teacher, tch)
            # effective：无覆盖→全局
            eff = await tl.effective_for(db, teacher)
            assert eff["monthly_grading_quota"] == 1
            # 个体覆盖优先
            await tl.set_teacher_override(db, teacher_id=tch, fields={"monthly_grading_quota": 9})
            eff2 = await tl.effective_for(db, teacher)
            assert eff2["monthly_grading_quota"] == 9
            # 清回随全局
            await tl.set_teacher_override(db, teacher_id=tch, fields={"monthly_grading_quota": None})
            assert (await tl.effective_for(db, teacher))["monthly_grading_quota"] == 1

            # 绑定上限（max_students 为个体值）：设覆盖=1，插 1 条 active 绑定 → 达上限 → 再绑被拦
            await tl.set_teacher_override(db, teacher_id=tch, fields={"max_students": 1})
            await db.execute(text(
                "INSERT INTO teacher_students (id,teacher_id,student_id,bind_type,bind_source,status,requested_at,bound_at) "
                "VALUES (:i,:t,:s,'self_bound','sms_invite','active',now(),now())"),
                {"i": uuid.uuid4(), "t": tch, "s": stu})
            await db.flush()
            with pytest.raises(AppError):
                await tl.assert_can_bind_student(db, teacher_id=tch)

            # 批改额度：limit=1，0 已用 → 通过且越线预警。
            # (错题批注 TeacherComment 已随拍照单题下线,grading 用量恒为 0、不再被拦)
            await tl.check_grading_and_warn(db, teacher_id=tch)   # used_after=1 越过 0.8 线 → 发预警
            warned = await db.scalar(text(
                "SELECT count(*) FROM notifications WHERE user_id=:u AND title='额度预警'"), {"u": tch})
            assert warned >= 1
            # 批改用量恒 0 → 再次 check 仍放行(不 raise)
            await tl.check_grading_and_warn(db, teacher_id=tch)

            # 自查
            ov = await tl.quota_overview(db, teacher_id=tch)
            assert ov["students"]["limit"] == 1 and ov["students"]["used"] == 1
            assert ov["grading"]["used"] == 0 and "remaining_pct" in ov["paper"]
        finally:
            await db.execute(text("DELETE FROM teacher_students WHERE teacher_id=:t"), {"t": tch})
            await db.execute(text("DELETE FROM notifications WHERE user_id=:t"), {"t": tch})
            await db.execute(text("DELETE FROM teachers WHERE id=:t"), {"t": tch})
            # 先删配置（updated_by FK→admin 用户），再删用户，避免 FK 冲突
            await db.execute(text("DELETE FROM system_configs WHERE key='teacher_limits'"))
            await db.execute(text("DELETE FROM users WHERE openid LIKE :p"), {"p": f"{_TAG}_%"})
            await db.commit()
    await engine.dispose()
