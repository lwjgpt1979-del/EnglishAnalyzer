"""admin_auth_service 测试（M5 / D-098）。"""
import uuid

import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.services import admin_auth_service


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


@pytest.mark.asyncio
async def test_create_and_authenticate_admin(db_session):
    uname = f"adm_{uuid.uuid4().hex[:6]}"
    user = await admin_auth_service.create_admin(
        db_session, username=uname, password="secret123",
    )
    await db_session.flush()
    assert str(user.role) == "platform_admin"
    assert user.username == uname
    ok = await admin_auth_service.authenticate(
        db_session, username=uname, password="secret123",
    )
    assert ok is not None and ok.id == user.id


@pytest.mark.asyncio
async def test_authenticate_wrong_password(db_session):
    uname = f"adm_{uuid.uuid4().hex[:6]}"
    await admin_auth_service.create_admin(db_session, username=uname, password="secret123")
    await db_session.flush()
    assert await admin_auth_service.authenticate(
        db_session, username=uname, password="WRONG",
    ) is None


@pytest.mark.asyncio
async def test_authenticate_unknown_user(db_session):
    assert await admin_auth_service.authenticate(
        db_session, username=f"nope_{uuid.uuid4().hex[:6]}", password="x",
    ) is None


@pytest.mark.asyncio
async def test_create_admin_idempotent_resets_password(db_session):
    """对已存在 username 再次 create_admin 视为重置密码，不新建行。"""
    uname = f"adm_{uuid.uuid4().hex[:6]}"
    u1 = await admin_auth_service.create_admin(db_session, username=uname, password="old123456")
    await db_session.flush()
    u2 = await admin_auth_service.create_admin(db_session, username=uname, password="new123456")
    await db_session.flush()
    assert u2.id == u1.id
    assert await admin_auth_service.authenticate(db_session, username=uname, password="new123456") is not None
    assert await admin_auth_service.authenticate(db_session, username=uname, password="old123456") is None
