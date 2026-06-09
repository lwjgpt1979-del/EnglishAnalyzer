"""V2 M28 — 教师出卷 API 集成测试（TDD RED→GREEN）。"""
from __future__ import annotations

import uuid
import pytest
from httpx import AsyncClient


# ── 仿真题浏览 ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_browse_sim_questions_requires_auth(client: AsyncClient):
    """未鉴权 → 401。"""
    r = await client.get("/api/v1/teacher/sim-questions")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_browse_sim_questions_returns_list(client: AsyncClient, teacher_token: str):
    """已认证老师 → 200 + {items, total} 结构。"""
    r = await client.get(
        "/api/v1/teacher/sim-questions",
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert "items" in data and "total" in data
    assert isinstance(data["items"], list)
    assert isinstance(data["total"], int)


# ── 创建班级卷子 ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_class_paper_requires_auth(client: AsyncClient):
    """未鉴权 → 401。"""
    r = await client.post(
        f"/api/v1/teacher/classes/{uuid.uuid4()}/papers",
        json={"title": "未鉴权卷", "question_ids": []},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_create_class_paper_success(client: AsyncClient, teacher_token: str):
    """老师创建空卷（无题）→ 200 + paper_id。"""
    h = {"Authorization": f"Bearer {teacher_token}"}
    rc = await client.post("/api/v1/teacher/classes", json={"name": f"出卷班_{uuid.uuid4().hex[:4]}"}, headers=h)
    assert rc.status_code == 200, rc.text
    class_id = rc.json()["data"]["id"]

    r = await client.post(
        f"/api/v1/teacher/classes/{class_id}/papers",
        json={"title": "期中仿真卷", "question_ids": []},
        headers=h,
    )
    assert r.status_code == 200, r.text
    paper = r.json()["data"]
    assert paper["title"] == "期中仿真卷"
    assert "paper_id" in paper
    assert paper["question_count"] == 0


@pytest.mark.asyncio
async def test_create_class_paper_wrong_class(client: AsyncClient, teacher_token: str):
    """对不属于自己的班级出卷 → 404。"""
    h = {"Authorization": f"Bearer {teacher_token}"}
    r = await client.post(
        f"/api/v1/teacher/classes/{uuid.uuid4()}/papers",
        json={"title": "越权卷", "question_ids": []},
        headers=h,
    )
    assert r.status_code == 404


# ── 列出班级卷子 ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_class_papers(client: AsyncClient, teacher_token: str):
    """老师查班级卷子列表 → 200 + 列表（含刚建的卷子）。"""
    h = {"Authorization": f"Bearer {teacher_token}"}
    rc = await client.post("/api/v1/teacher/classes", json={"name": f"列表班_{uuid.uuid4().hex[:4]}"}, headers=h)
    class_id = rc.json()["data"]["id"]
    await client.post(
        f"/api/v1/teacher/classes/{class_id}/papers",
        json={"title": "测试卷A", "question_ids": []},
        headers=h,
    )
    r = await client.get(f"/api/v1/teacher/classes/{class_id}/papers", headers=h)
    assert r.status_code == 200, r.text
    papers = r.json()["data"]
    assert isinstance(papers, list)
    assert any(p["title"] == "测试卷A" for p in papers)


# ── 删除卷子 ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_class_paper(client: AsyncClient, teacher_token: str):
    """老师删除自己的卷子 → 200；删后不再出现在列表。"""
    h = {"Authorization": f"Bearer {teacher_token}"}
    rc = await client.post("/api/v1/teacher/classes", json={"name": f"删除班_{uuid.uuid4().hex[:4]}"}, headers=h)
    class_id = rc.json()["data"]["id"]
    rp = await client.post(
        f"/api/v1/teacher/classes/{class_id}/papers",
        json={"title": "待删卷", "question_ids": []},
        headers=h,
    )
    paper_id = rp.json()["data"]["paper_id"]

    rd = await client.delete(f"/api/v1/teacher/papers/{paper_id}", headers=h)
    assert rd.status_code == 200

    # 删后列表不再有该卷
    rl = await client.get(f"/api/v1/teacher/classes/{class_id}/papers", headers=h)
    assert all(p["paper_id"] != paper_id for p in rl.json()["data"])


@pytest.mark.asyncio
async def test_delete_other_teacher_paper(client: AsyncClient, teacher_token: str):
    """删除不属于自己的卷子 → 404。"""
    h = {"Authorization": f"Bearer {teacher_token}"}
    r = await client.delete(f"/api/v1/teacher/papers/{uuid.uuid4()}", headers=h)
    assert r.status_code == 404


# ── 学生查看班级试卷 ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_student_can_see_class_paper(
    client: AsyncClient, teacher_token: str, student_token: str
):
    """学生加入班级后能看到老师出的卷子。"""
    th = {"Authorization": f"Bearer {teacher_token}"}
    sh = {"Authorization": f"Bearer {student_token}"}

    # 老师建班 + 出卷
    rc = await client.post("/api/v1/teacher/classes", json={"name": f"可见班_{uuid.uuid4().hex[:4]}"}, headers=th)
    class_id = rc.json()["data"]["id"]
    await client.post(
        f"/api/v1/teacher/classes/{class_id}/papers",
        json={"title": "学生可见卷", "question_ids": []},
        headers=th,
    )

    # 获取学生 user_id
    me_r = await client.get("/api/v1/users/me", headers=sh)
    student_id = me_r.json()["data"]["id"]

    # 学生先通过邀请码绑定老师
    ri = await client.post("/api/v1/teacher/invite-code", headers=th)
    assert ri.status_code == 200, ri.text
    invite_code = ri.json()["data"]["code"]
    rb = await client.post("/api/v1/teacher/bind", json={"code": invite_code}, headers=sh)
    assert rb.status_code == 200, rb.text

    # 老师把绑定学生加入班级
    rj = await client.post(
        f"/api/v1/teacher/classes/{class_id}/students",
        json={"student_ids": [student_id]},
        headers=th,
    )
    assert rj.status_code == 200, rj.text

    # 学生查看班级试卷列表
    r = await client.get(f"/api/v1/student/classes/{class_id}/papers", headers=sh)
    assert r.status_code == 200, r.text
    papers = r.json()["data"]
    assert any(p["title"] == "学生可见卷" for p in papers)


@pytest.mark.asyncio
async def test_student_outside_class_cannot_see_papers(
    client: AsyncClient, teacher_token: str, student_token: str
):
    """未加入班级的学生无法查看试卷 → 403。"""
    th = {"Authorization": f"Bearer {teacher_token}"}
    sh = {"Authorization": f"Bearer {student_token}"}

    rc = await client.post("/api/v1/teacher/classes", json={"name": f"私密班_{uuid.uuid4().hex[:4]}"}, headers=th)
    class_id = rc.json()["data"]["id"]

    r = await client.get(f"/api/v1/student/classes/{class_id}/papers", headers=sh)
    assert r.status_code == 403
