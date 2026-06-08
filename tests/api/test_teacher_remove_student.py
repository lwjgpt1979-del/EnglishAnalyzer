"""V2 M18 — 教师移除学生接口测试。"""
import pytest
from httpx import AsyncClient
import uuid


@pytest.mark.asyncio
async def test_teacher_can_remove_student(client: AsyncClient, teacher_token: str, student_token: str):
    """教师绑定学生后可移除，列表中不再出现。"""
    t_headers = {"Authorization": f"Bearer {teacher_token}"}
    s_headers = {"Authorization": f"Bearer {student_token}"}

    # 教师生成邀请码
    code_r = await client.post("/api/v1/teacher/invite-code", headers=t_headers)
    assert code_r.status_code == 200
    code = code_r.json()["data"]["code"]

    # 学生绑定
    bind_r = await client.post("/api/v1/teacher/bind", json={"code": code}, headers=s_headers)
    assert bind_r.status_code == 200
    student_id = bind_r.json()["data"]["student_id"]

    # 教师移除
    del_r = await client.delete(f"/api/v1/teacher/students/{student_id}", headers=t_headers)
    assert del_r.status_code == 200
    assert del_r.json()["data"]["removed"] is True

    # 列表中不再出现
    list_r = await client.get("/api/v1/teacher/students", headers=t_headers)
    ids = [str(s["student_id"]) for s in (list_r.json().get("data") or [])]
    assert str(student_id) not in ids


@pytest.mark.asyncio
async def test_teacher_cannot_remove_unrelated_student(client: AsyncClient, teacher_token: str):
    """不能移除不属于自己的学生。"""
    headers = {"Authorization": f"Bearer {teacher_token}"}
    fake_id = str(uuid.uuid4())
    r = await client.delete(f"/api/v1/teacher/students/{fake_id}", headers=headers)
    if r.status_code == 200:
        assert r.json().get("code") == 404
    else:
        assert r.status_code == 404
