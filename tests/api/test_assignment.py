"""老师出卷 API 全链路测试（D-113）。"""
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from unittest.mock import AsyncMock, patch

from app.core.database import _async_session_factory
from app.main import app
from app.models.d1_users import Teacher, User
from app.models.d7_teacher import ClassStudent


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _login(client: AsyncClient, openid: str) -> tuple[dict, uuid.UUID]:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as mock_wx:
        mock_wx.return_value = {"openid": openid}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}
    me = (await client.get("/api/v1/users/me", headers=headers)).json()["data"]
    return headers, uuid.UUID(me["id"])


async def _make_certified_teacher(client: AsyncClient, suffix: str) -> tuple[dict, uuid.UUID]:
    headers, uid = await _login(client, f"tch_{suffix}")
    async with _async_session_factory() as s:
        u = (await s.execute(select(User).where(User.id == uid))).scalar_one()
        u.role = "teacher"  # type: ignore[assignment]
        s.add(Teacher(id=uid, cert_status="certified"))
        await s.commit()
    return headers, uid


async def _add_student_to_class(class_id: uuid.UUID, student_id: uuid.UUID) -> None:
    async with _async_session_factory() as s:
        s.add(ClassStudent(class_id=class_id, student_id=student_id, joined_at=datetime.now(timezone.utc)))
        await s.commit()


@pytest.mark.asyncio
async def test_assignment_full_flow(client):
    t_headers, _ = await _make_certified_teacher(client, uuid.uuid4().hex[:6])
    s_headers, sid = await _login(client, f"stu_{uuid.uuid4().hex[:6]}")

    # 老师建班
    cls = (await client.post("/api/v1/teacher/classes", json={"name": "一班"}, headers=t_headers)).json()["data"]
    class_id = uuid.UUID(cls["id"])
    await _add_student_to_class(class_id, sid)

    # 出卷（draft）
    body = {"class_id": str(class_id), "title": "周末作业",
            "questions": [{"stem": "1+1=?", "answer": "2"}]}
    a = (await client.post("/api/v1/teacher/assignments", json=body, headers=t_headers)).json()["data"]
    aid = a["id"]
    assert a["status"] == "draft"

    # 发布
    r_pub = await client.post(f"/api/v1/teacher/assignments/{aid}/publish", headers=t_headers)
    assert r_pub.status_code == 200 and r_pub.json()["data"]["status"] == "published"

    # 学生收到
    recv = (await client.get("/api/v1/assignments", headers=s_headers)).json()["data"]
    assert any(it["id"] == aid for it in recv)

    # 学生作答提交
    r_sub = await client.post(f"/api/v1/assignments/{aid}/submit",
                              json={"answers": [{"index": 0, "answer": "2"}]}, headers=s_headers)
    assert r_sub.status_code == 200

    # 老师看详情 + 批改
    detail = (await client.get(f"/api/v1/teacher/assignments/{aid}", headers=t_headers)).json()["data"]
    assert len(detail["submissions"]) == 1
    sub_id = detail["submissions"][0]["id"]
    r_grade = await client.post(f"/api/v1/teacher/submissions/{sub_id}/grade",
                                json={"score": 90}, headers=t_headers)
    assert r_grade.status_code == 200

    # 学生看分
    sd = (await client.get(f"/api/v1/assignments/{aid}", headers=s_headers)).json()["data"]
    assert sd["submitted"] is True and float(sd["score"]) == 90.0


@pytest.mark.asyncio
async def test_assignment_requires_auth(client):
    r = await client.get("/api/v1/assignments")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_create_assignment_requires_certified(client):
    # 普通学生（非 certified teacher）出卷 → 403
    headers, _ = await _login(client, f"plain_{uuid.uuid4().hex[:6]}")
    r = await client.post("/api/v1/teacher/assignments",
                          json={"class_id": str(uuid.uuid4()), "title": "x", "questions": []},
                          headers=headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_assignment_stats_api(client):
    t_headers, _ = await _make_certified_teacher(client, uuid.uuid4().hex[:6])
    s_headers, sid = await _login(client, f"stu_{uuid.uuid4().hex[:6]}")
    cls = (await client.post("/api/v1/teacher/classes", json={"name": "一班"}, headers=t_headers)).json()["data"]
    await _add_student_to_class(uuid.UUID(cls["id"]), sid)
    body = {"class_id": cls["id"], "title": "t",
            "questions": [{"stem": "1+1", "answer": "2"}]}
    aid = (await client.post("/api/v1/teacher/assignments", json=body, headers=t_headers)).json()["data"]["id"]
    await client.post(f"/api/v1/teacher/assignments/{aid}/publish", headers=t_headers)
    await client.post(f"/api/v1/assignments/{aid}/submit",
                      json={"answers": [{"index": 0, "answer": "2"}]}, headers=s_headers)
    r = await client.get(f"/api/v1/teacher/assignments/{aid}/stats", headers=t_headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total_students"] == 1 and data["submitted_count"] == 1
    assert data["per_question"][0]["rate"] == 1.0


@pytest.fixture(autouse=True)
def _force_qai_dev_mock_api(monkeypatch):
    from app.services import question_ai_service
    monkeypatch.setattr(question_ai_service, "is_llm_dev_mode", lambda: True)


@pytest.mark.asyncio
async def test_suggest_questions_api(client):
    from app.models.d3_wrong_questions import WrongQuestion, AiAnalysis
    t_headers, _ = await _make_certified_teacher(client, uuid.uuid4().hex[:6])
    s_headers, sid = await _login(client, f"stu_{uuid.uuid4().hex[:6]}")
    async with _async_session_factory() as s:
        wq = WrongQuestion(id=uuid.uuid4(), student_id=sid, source_image_url="x://1")
        s.add(wq); await s.flush()
        s.add(AiAnalysis(id=uuid.uuid4(), wrong_question_id=wq.id, student_id=sid,
                         llm_provider="deepseek", error_types=["语法"],
                         knowledge_points=["一般现在时"], diagnosis="d", suggestions="s", tokens_used=0))
        await s.commit()
    r = await client.get("/api/v1/teacher/assignments/suggest",
                         params={"student_id": str(sid), "count": 3}, headers=t_headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["knowledge_point"] == "一般现在时" and len(data["questions"]) == 3


@pytest.mark.asyncio
async def test_suggest_requires_certified(client):
    headers, _ = await _login(client, f"plain_{uuid.uuid4().hex[:6]}")
    r = await client.get("/api/v1/teacher/assignments/suggest",
                         params={"student_id": str(uuid.uuid4())}, headers=headers)
    assert r.status_code == 403
