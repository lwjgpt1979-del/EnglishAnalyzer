"""R3.5 整卷管线接入错题中心:整卷上传→管线→整卷错题进 wrong_record(q_scope=uploaded)。"""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, func, text
from unittest.mock import AsyncMock, patch

from app.core.config import settings
from app.core.database import _async_session_factory
from app.main import app
from app.models.d1_users import User
from app.models.d16_question_domain import WrongRecord
from app.services import user_paper_service

_TAG = "pwc"


@pytest.fixture(autouse=True)
def force_dev_mode(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-placeholder-for-test")
    monkeypatch.setattr(settings, "doubao_api_key", "placeholder-doubao-dev")


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _login(client, openid):
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as m:
        m.return_value = {"openid": openid}
        r = await client.post("/api/v1/auth/wx-login", json={"code": "x"})
    token = r.json()["data"]["access_token"]
    async with _async_session_factory() as s:
        uid = (await s.execute(select(User.id).where(User.openid == openid))).scalar_one()
    return {"Authorization": f"Bearer {token}"}, uid


@pytest.mark.asyncio
async def test_paper_wrong_enters_wrong_record(client):
    openid = f"{_TAG}_{uuid.uuid4().hex[:8]}"
    headers, uid = await _login(client, openid)
    try:
        r = await client.post("/api/v1/user-papers",
                              json={"title": f"{_TAG}卷", "source_image_urls": ["https://cdn.x/p.jpg"]},
                              headers=headers)
        paper_id = r.json()["data"]["id"]
        await user_paper_service.run_paper_pipeline(paper_id)

        async with _async_session_factory() as db:
            cnt = (await db.execute(
                select(func.count()).select_from(WrongRecord).where(
                    WrongRecord.student_id == uid, WrongRecord.q_scope == "uploaded")
            )).scalar_one()
            assert cnt >= 1, "整卷错题应收口进 wrong_record(q_scope=uploaded)"
            # 错题事件 open 且带 next_review_at(入复习队列)
            rec = (await db.execute(
                select(WrongRecord).where(WrongRecord.student_id == uid).limit(1)
            )).scalar_one()
            assert rec.status == "open" and rec.next_review_at is not None
    finally:
        async with _async_session_factory() as db:
            await db.execute(text("DELETE FROM wrong_record WHERE student_id = :s"), {"s": str(uid)})
            await db.commit()
