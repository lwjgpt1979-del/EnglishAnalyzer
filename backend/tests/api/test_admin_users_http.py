"""端到端 HTTP 自动化测试：用户封禁/解封（打通 HTTP → 鉴权 → 端点 → DB）。

不走 UI 登录（不输密码），用应用自身 token 工具签发管理员 token 作测试夹具，
覆盖真实 require_role 鉴权 + 路由 + service + 数据库全链路。
"""
from __future__ import annotations

import os
import uuid

import pytest
import httpx
from httpx import ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

_TAG = "adminhttp"


def _engine():
    url = os.environ.get("ASYNC_DATABASE_URL")
    if not url:
        from app.core.config import settings
        url = settings.async_database_url
    return create_async_engine(url)


@pytest.mark.asyncio
async def test_admin_ban_unban_e2e():
    from app.main import app
    from app.core.security import create_access_token

    engine = _engine()
    sf = async_sessionmaker(engine, expire_on_commit=False)
    admin_id, stu_id = uuid.uuid4(), uuid.uuid4()
    async with sf() as db:
        await db.execute(text(
            "INSERT INTO users (id,openid,role,is_active,nickname) "
            "VALUES (:i,:o,'platform_admin',true,:n)"),
            {"i": admin_id, "o": f"{_TAG}_admin_{admin_id.hex[:8]}", "n": f"{_TAG}_admin"})
        await db.execute(text(
            "INSERT INTO users (id,openid,role,is_active,nickname) "
            "VALUES (:i,:o,'student',true,:n)"),
            {"i": stu_id, "o": f"{_TAG}_stu_{stu_id.hex[:8]}", "n": f"{_TAG}_target"})
        await db.commit()

    token = create_access_token(str(admin_id), "platform_admin")
    headers = {"Authorization": f"Bearer {token}"}
    transport = ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            # 1) 无 token → 401/403
            r = await c.get("/api/v1/admin/users")
            assert r.status_code in (401, 403), r.text

            # 2) 搜索到目标用户
            r = await c.get("/api/v1/admin/users", params={"q": f"{_TAG}_target"}, headers=headers)
            assert r.status_code == 200, r.text
            items = r.json()["data"]["items"]
            assert any(i["id"] == str(stu_id) for i in items)

            # 3) 封禁 7 天
            r = await c.post(f"/api/v1/admin/users/{stu_id}/ban",
                             json={"reason": "异常多设备登录", "days": 7}, headers=headers)
            assert r.status_code == 200, r.text
            d = r.json()["data"]
            assert d["banned"] is True and d["ban_type"] == "temporary"

            # 4) DB 侧确认 is_active=False（封禁真正生效）
            async with sf() as db:
                act = await db.scalar(text("SELECT is_active FROM users WHERE id=:i"), {"i": stu_id})
                assert act is False

            # 5) 原因为空 → 400
            r = await c.post(f"/api/v1/admin/users/{stu_id}/unban", headers=headers)  # 先解封
            assert r.status_code == 200
            r = await c.post(f"/api/v1/admin/users/{stu_id}/ban",
                             json={"reason": "  "}, headers=headers)
            assert r.status_code == 400, r.text

            # 6) 不能封管理员 → 400
            r = await c.post(f"/api/v1/admin/users/{admin_id}/ban",
                             json={"reason": "x", "days": 7}, headers=headers)
            assert r.status_code == 400, r.text

            # 7) 永久封禁 + 解封
            r = await c.post(f"/api/v1/admin/users/{stu_id}/ban",
                             json={"reason": "伪造支付截图"}, headers=headers)
            assert r.json()["data"]["ban_type"] == "permanent"
            r = await c.post(f"/api/v1/admin/users/{stu_id}/unban", headers=headers)
            assert r.json()["data"]["banned"] is False
    finally:
        async with sf() as db:
            await db.execute(text("DELETE FROM users WHERE openid LIKE :p"), {"p": f"{_TAG}_%"})
            await db.commit()
        await engine.dispose()
