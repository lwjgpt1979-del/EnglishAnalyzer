"""词力通 API 测试（P1 / D-100）。"""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch

from app.core.database import _async_session_factory
from app.main import app
from app.models.d5_learning import VocabularyWord


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _login(client: AsyncClient, suffix: str) -> dict:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as mock_wx:
        mock_wx.return_value = {"openid": f"vocabapi_{suffix}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def _seed_word() -> uuid.UUID:
    async with _async_session_factory() as s:
        w = VocabularyWord(
            id=uuid.uuid4(), word=f"apivocab_{uuid.uuid4().hex[:6]}",
            phonetic="ˈtest", definitions=[{"pos": "n.", "meaning": "测试"}],
            examples=None, difficulty=1,
        )
        s.add(w)
        await s.commit()
        return w.id


@pytest.mark.asyncio
async def test_daily_task_requires_auth(client):
    r = await client.get("/api/v1/vocabulary/daily-task")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_daily_task_and_answer_flow(client):
    await _seed_word()
    headers = await _login(client, uuid.uuid4().hex[:6])

    r1 = await client.get("/api/v1/vocabulary/daily-task", headers=headers)
    assert r1.status_code == 200
    data = r1.json()["data"]
    assert "new_words" in data and "review_words" in data
    assert data["new_limit"] == 5  # free 档
    assert len(data["new_words"]) >= 1

    wid = data["new_words"][0]["word_id"]
    r2 = await client.post(
        "/api/v1/vocabulary/answer",
        json={"word_id": wid, "correct": True, "hesitant": False},
        headers=headers,
    )
    assert r2.status_code == 200
    res = r2.json()["data"]
    assert res["word_id"] == wid
    assert res["repetitions"] == 1
    assert res["level"] == "learning"


@pytest.mark.asyncio
async def test_answer_wrong_resets(client):
    await _seed_word()
    headers = await _login(client, uuid.uuid4().hex[:6])
    data = (await client.get("/api/v1/vocabulary/daily-task", headers=headers)).json()["data"]
    wid = data["new_words"][0]["word_id"]
    await client.post("/api/v1/vocabulary/answer", json={"word_id": wid, "correct": True}, headers=headers)
    r = await client.post("/api/v1/vocabulary/answer", json={"word_id": wid, "correct": False}, headers=headers)
    assert r.status_code == 200
    assert r.json()["data"]["level"] == "new"
    assert r.json()["data"]["repetitions"] == 0


@pytest.mark.asyncio
async def test_wrong_words_requires_auth(client):
    r = await client.get("/api/v1/vocabulary/wrong-words")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_wrong_words_flow(client):
    await _seed_word()
    headers = await _login(client, uuid.uuid4().hex[:6])
    # 取今日任务，对第一个词答错 → 进错词本
    data = (await client.get("/api/v1/vocabulary/daily-task", headers=headers)).json()["data"]
    wid = data["new_words"][0]["word_id"]
    await client.post("/api/v1/vocabulary/answer", json={"word_id": wid, "correct": False}, headers=headers)
    r = await client.get("/api/v1/vocabulary/wrong-words", headers=headers)
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["total"] >= 1
    item = next(it for it in body["items"] if it["word_id"] == wid)
    assert item["wrong_count"] >= 1


@pytest.mark.asyncio
async def test_checkin_status_requires_auth(client):
    r = await client.get("/api/v1/vocabulary/checkin/status")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_checkin_blocked_when_incomplete(client):
    """未学满今日新词 → completed False、不写打卡。"""
    await _seed_word()
    headers = await _login(client, uuid.uuid4().hex[:6])
    r = await client.post("/api/v1/vocabulary/checkin", headers=headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["completed"] is False
    st = await client.get("/api/v1/vocabulary/checkin/status", headers=headers)
    assert st.json()["data"]["checked_in_today"] is False


@pytest.mark.asyncio
async def test_checkin_completed_flow(client):
    """学满今日新词后打卡 → completed True、streak=1。"""
    for _ in range(5):
        await _seed_word()
    headers = await _login(client, uuid.uuid4().hex[:6])
    task = (await client.get("/api/v1/vocabulary/daily-task", headers=headers)).json()["data"]
    assert len(task["new_words"]) == 5  # free 档上限
    for w in task["new_words"]:
        await client.post("/api/v1/vocabulary/answer", headers=headers,
                          json={"word_id": w["word_id"], "correct": True})
    r = await client.post("/api/v1/vocabulary/checkin", headers=headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["completed"] is True and data["streak_days"] == 1
    st = (await client.get("/api/v1/vocabulary/checkin/status", headers=headers)).json()["data"]
    assert st["checked_in_today"] is True and st["current_streak"] == 1
