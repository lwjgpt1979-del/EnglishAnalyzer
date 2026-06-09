"""M47 — 教师出题时基于班级弱项智能推荐 KP"""
from __future__ import annotations
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


# ── helpers ───────────────────────────────────────────────────────────────────

async def _login(client: AsyncClient, openid: str) -> str:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as m:
        m.return_value = {"openid": openid}
        r = await client.post("/api/v1/auth/wx-login", json={"code": "x"})
    return r.json()["data"]["access_token"]


async def _make_certified_teacher(client: AsyncClient) -> str:
    """注册 + 创建 teacher profile + 模拟认证通过"""
    from app.models.d1_users import Teacher
    from app.core.database import get_db
    token = await _login(client, f"tch_m47_{uuid.uuid4().hex[:6]}")
    # 创建 teacher profile
    await client.post("/api/v1/teacher/profile",
                      json={"subject": "english"},
                      headers={"Authorization": f"Bearer {token}"})
    # 拿 user_id，直接写 DB 令其认证通过
    r = await client.get("/api/v1/users/me",
                         headers={"Authorization": f"Bearer {token}"})
    user_id = r.json()["data"]["id"]
    # 调内部 DB 把 Teacher.cert_status 改为 approved
    async for db in get_db():
        from sqlalchemy import update
        await db.execute(
            update(Teacher).where(Teacher.id == uuid.UUID(user_id))
            .values(cert_status="certified")
        )
        await db.commit()
        break
    return token


# ── 测试 ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_suggest_by_kp_returns_questions(client: AsyncClient):
    """suggest-by-kp?kp_key=present_simple 返回题目列表"""
    token = await _make_certified_teacher(client)
    r = await client.get(
        "/api/v1/teacher/assignments/suggest-by-kp?kp_key=present_simple&count=3",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["knowledge_point"] == "present_simple"
    assert isinstance(data["questions"], list)
    assert len(data["questions"]) >= 1


@pytest.mark.asyncio
async def test_suggest_by_kp_empty_key_is_400(client: AsyncClient):
    """kp_key 为空字符串时应返回 400"""
    token = await _make_certified_teacher(client)
    r = await client.get(
        "/api/v1/teacher/assignments/suggest-by-kp?kp_key=",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_non_teacher_cannot_use_suggest_by_kp(client: AsyncClient):
    """普通用户（学生）调用 → 403"""
    student_token = await _login(client, f"stu_m47_{uuid.uuid4().hex[:6]}")
    r = await client.get(
        "/api/v1/teacher/assignments/suggest-by-kp?kp_key=present_simple",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_class_kp_stats_feeds_recommendations(client: AsyncClient):
    """class kp-stats top_weak_kps 非空时，可以用 kp_key 直接调 suggest-by-kp"""
    token = await _make_certified_teacher(client)

    # 先创建班级
    r = await client.post("/api/v1/teacher/classes",
                          json={"name": "M47班", "grade": "初一"},
                          headers={"Authorization": f"Bearer {token}"})
    class_id = r.json()["data"]["id"]

    # 班级 KP stats（空班级 top_weak_kps 为 []，接口仍 200）
    r = await client.get(
        f"/api/v1/teacher/classes/{class_id}/kp-stats",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    stats = r.json()["data"]
    assert "top_weak_kps" in stats

    # 如果有弱项，验证可以直接用 kp_key 出题
    if stats["top_weak_kps"]:
        kp = stats["top_weak_kps"][0]["kp_key"]
        r2 = await client.get(
            f"/api/v1/teacher/assignments/suggest-by-kp?kp_key={kp}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r2.status_code == 200
        assert r2.json()["data"]["knowledge_point"] == kp
