"""V2 M26 — 机构批量续费迁移 V2 (purchased_semesters) 测试。"""
from __future__ import annotations

import uuid
import datetime as dt
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient

from app.core.database import async_session_factory
from app.models.d1_users import User, Institution, Student
from app.models.d2_payments import Order
from app.models.d14_v2_semesters import PurchasedSemester
from sqlalchemy import select


async def _login(client: AsyncClient, openid: str) -> str:
    with patch(
        "app.services.auth_service.wechat_code2session", new_callable=AsyncMock
    ) as m:
        m.return_value = {"openid": openid}
        r = await client.post("/api/v1/auth/wx-login", json={"code": "x"})
    assert r.status_code == 200, r.text
    return r.json()["data"]["access_token"]


@pytest_asyncio.fixture
async def inst_setup(client: AsyncClient):
    """创建机构管理员 + 学生 + purchased_semester，返回 (inst_token, stu_id, expires_at)。"""
    uid_suffix = uuid.uuid4().hex[:6]
    inst_openid = f"m26inst_{uid_suffix}"
    stu_openid = f"m26stu_{uid_suffix}"

    inst_token = await _login(client, inst_openid)
    stu_token = await _login(client, stu_openid)

    async with async_session_factory() as db:
        # get both users
        inst_user = (await db.execute(select(User).where(User.openid == inst_openid))).scalar_one()
        stu_user = (await db.execute(select(User).where(User.openid == stu_openid))).scalar_one()

        # create Institution and make inst_user institution_admin
        inst = Institution(id=inst_user.id, name=f"TestInst_{uid_suffix}", contact_phone="13800000000", province_code="44", city_code="4401", address="测试地址")
        db.add(inst)
        inst_user.role = "institution_admin"  # type: ignore[assignment]
        inst_user.institution_id = inst_user.id

        # create Student linked to institution
        stu = Student(id=stu_user.id, institution_id=inst_user.id)
        db.add(stu)

        # create dummy Order for FK
        order = Order(
            id=uuid.uuid4(),
            order_no=f"TST{uid_suffix.upper()}",
            payer_id=stu_user.id,
            beneficiary_id=stu_user.id,
            order_type="new",
            tier="basic",
            duration_months=6,
            amount_fen=3900,
            status="paid",
        )
        db.add(order)
        await db.flush()

        expires_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=30)
        ps = PurchasedSemester(
            id=uuid.uuid4(),
            user_id=stu_user.id,
            textbook_version="译林版",
            grade="小学5年级",
            semester="上",
            tier="basic",
            semester_no=1,
            started_at=dt.datetime.now(dt.timezone.utc),
            expires_at=expires_at,
            order_id=order.id,
        )
        db.add(ps)
        await db.commit()

    return inst_token, stu_user.id, expires_at


@pytest.mark.asyncio
async def test_batch_renew_extends_expires_at(client: AsyncClient, inst_setup):
    """batch_renew semesters=1 → purchased_semesters.expires_at 顺延 183 天。"""
    inst_token, stu_id, original_expires = inst_setup
    headers = {"Authorization": f"Bearer {inst_token}"}

    r = await client.post(
        "/api/v1/institution/batch-renew",
        json={"student_ids": [str(stu_id)], "semesters": 1},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["renewed_count"] == 1
    assert data["skipped"] == []

    async with async_session_factory() as db:
        ps = (await db.execute(
            select(PurchasedSemester)
            .where(PurchasedSemester.user_id == stu_id)
            .order_by(PurchasedSemester.expires_at.desc())
        )).scalars().first()

    assert ps is not None
    expected = original_expires + dt.timedelta(days=183)
    diff = abs((ps.expires_at - expected).total_seconds())
    assert diff < 60, f"expires_at diff={diff}s, got {ps.expires_at}, expected ~{expected}"


@pytest.mark.asyncio
async def test_batch_renew_two_semesters(client: AsyncClient, inst_setup):
    """semesters=2 → expires_at 顺延 366 天。"""
    inst_token, stu_id, original_expires = inst_setup
    headers = {"Authorization": f"Bearer {inst_token}"}

    r = await client.post(
        "/api/v1/institution/batch-renew",
        json={"student_ids": [str(stu_id)], "semesters": 2},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["renewed_count"] == 1

    async with async_session_factory() as db:
        ps = (await db.execute(
            select(PurchasedSemester)
            .where(PurchasedSemester.user_id == stu_id)
            .order_by(PurchasedSemester.expires_at.desc())
        )).scalars().first()

    expected = original_expires + dt.timedelta(days=366)
    diff = abs((ps.expires_at - expected).total_seconds())
    assert diff < 60, f"expires_at diff={diff}s"
