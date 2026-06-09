import uuid
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.core.config import settings
from app.core.database import async_session_factory
from app.models.d1_users import User


@pytest.fixture(autouse=True)
def _force_all_ai_dev_mode(monkeypatch):
    """全局 fixture：强制所有 AI 服务走 dev mock，避免任何测试意外调真实 API。

    各测试文件的 force_dev_mode fixture 与本 fixture 并存时不冲突
    （monkeypatch 是幂等的）。
    """
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-placeholder-for-test")
    monkeypatch.setattr(settings, "doubao_api_key", "placeholder-doubao-dev")


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


async def _wx_login(client: AsyncClient, openid: str) -> str:
    """Helper: wx-login with patched code2session, return access_token."""
    with patch(
        "app.services.auth_service.wechat_code2session", new_callable=AsyncMock
    ) as m:
        m.return_value = {"openid": openid}
        r = await client.post("/api/v1/auth/wx-login", json={"code": "x"})
    assert r.status_code == 200, r.text
    return r.json()["data"]["access_token"]


@pytest_asyncio.fixture
async def admin_client(client: AsyncClient) -> AsyncClient:
    """An AsyncClient pre-authenticated as platform_admin."""
    openid = f"conf_adm_{uuid.uuid4().hex[:8]}"
    token = await _wx_login(client, openid)
    async with async_session_factory() as db:
        u = (await db.execute(select(User).where(User.openid == openid))).scalars().first()
        if u:
            u.role = "platform_admin"  # type: ignore[assignment]
            await db.commit()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


@pytest_asyncio.fixture
async def student_token(client: AsyncClient) -> str:
    """A freshly created student JWT."""
    return await _wx_login(client, f"conf_stu_{uuid.uuid4().hex[:8]}")


@pytest_asyncio.fixture
async def teacher_token(client: AsyncClient) -> str:
    """A freshly created teacher JWT (role upgraded to teacher)."""
    token = await _wx_login(client, f"conf_tch_{uuid.uuid4().hex[:8]}")
    headers = {"Authorization": f"Bearer {token}"}
    # 成为教师（POST /teacher/profile）
    r = await client.post(
        "/api/v1/teacher/profile",
        json={"subject": "英语"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    # 提交认证（dev 模式 AUTO_APPROVE_TEACHER_CERT=True 直接 certified）
    r2 = await client.post(
        "/api/v1/teacher/cert/submit",
        json={"cert_doc_url": "https://example.com/cert.jpg"},
        headers=headers,
    )
    # cert endpoint might return 200 or 404; if ok we're certified
    return token
