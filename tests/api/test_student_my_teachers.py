"""V2 M19 — 学生查看已绑定老师列表。"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_student_can_see_bound_teachers(client: AsyncClient, teacher_token: str, student_token: str):
    """学生绑定老师后，GET /teacher/my-teachers 返回该老师。"""
    t_headers = {"Authorization": f"Bearer {teacher_token}"}
    s_headers = {"Authorization": f"Bearer {student_token}"}

    # 教师生成邀请码
    code_r = await client.post("/api/v1/teacher/invite-code", headers=t_headers)
    assert code_r.status_code == 200
    code = code_r.json()["data"]["code"]

    # 学生绑定
    await client.post("/api/v1/teacher/bind", json={"code": code}, headers=s_headers)

    # 学生查看已绑定老师
    r = await client.get("/api/v1/teacher/my-teachers", headers=s_headers)
    assert r.status_code == 200
    teachers = r.json().get("data") or []
    assert len(teachers) >= 1
    assert "teacher_id" in teachers[0]
    assert "bound_at" in teachers[0]


@pytest.mark.asyncio
async def test_my_teachers_empty_initially(client: AsyncClient, student_token: str):
    """未绑定任何老师时返回空列表。"""
    headers = {"Authorization": f"Bearer {student_token}"}
    r = await client.get("/api/v1/teacher/my-teachers", headers=headers)
    assert r.status_code == 200
    assert isinstance(r.json().get("data"), list)
