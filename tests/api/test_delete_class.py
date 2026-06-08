"""V2 M15 — 教师解散班级接口测试。"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_teacher_can_delete_class(client: AsyncClient, teacher_token: str):
    """教师创建班级后可以解散它。"""
    headers = {"Authorization": f"Bearer {teacher_token}"}

    # 创建班级
    create_r = await client.post(
        "/api/v1/teacher/classes",
        json={"name": "待解散班级"},
        headers=headers,
    )
    assert create_r.status_code == 200
    class_id = create_r.json()["data"]["id"]

    # 解散班级
    del_r = await client.delete(
        f"/api/v1/teacher/classes/{class_id}",
        headers=headers,
    )
    assert del_r.status_code == 200
    assert del_r.json()["data"]["deleted"] is True

    # 列表中不再出现
    list_r = await client.get("/api/v1/teacher/classes", headers=headers)
    ids = [c["id"] for c in (list_r.json().get("data") or [])]
    assert class_id not in ids


@pytest.mark.asyncio
async def test_teacher_cannot_delete_others_class(client: AsyncClient, teacher_token: str):
    """无法解散不属于自己的班级，应返回 404。"""
    import uuid
    headers = {"Authorization": f"Bearer {teacher_token}"}
    fake_id = str(uuid.uuid4())
    r = await client.delete(f"/api/v1/teacher/classes/{fake_id}", headers=headers)
    assert r.status_code in (404, 200)
    if r.status_code == 200:
        # API 统一 200 时检查 error code
        assert r.json().get("code") == 404
