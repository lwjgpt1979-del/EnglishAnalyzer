"""TDD: M44 — 教师端 KP 接口。

测试覆盖：
  1. GET /teacher/students/{id}/kp-mastery — 教师查学生台账，弱项优先
  2. GET /teacher/students/{id}/kp-mastery — 非绑定学生返回 403
  3. GET /teacher/classes/{id}/kp-stats — 班级 KP 统计结构完整
  4. top_weak_kps 按全班平均正确率升序（最弱优先）
  5. students_attention 按整体平均正确率升序（最差优先）
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

async def _login(client, openid: str) -> str:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as m:
        m.return_value = {"openid": openid}
        r = await client.post("/api/v1/auth/wx-login", json={"code": "x"})
    return r.json()["data"]["access_token"]


async def _setup_teacher(client) -> tuple[str, str]:
    """创建认证教师，返回 (token, teacher_id)。"""
    token = await _login(client, f"tch_{uuid.uuid4().hex[:8]}")
    h = {"Authorization": f"Bearer {token}"}
    await client.post("/api/v1/teacher/profile", json={"subject": "英语"}, headers=h)
    await client.post("/api/v1/teacher/cert/submit",
                      json={"cert_doc_url": "https://x.com/c.jpg"}, headers=h)
    r = await client.get("/api/v1/users/me", headers=h)
    return token, r.json()["data"]["id"]


async def _setup_student_in_class(client, teacher_token: str, class_id: str) -> tuple[str, str]:
    """创建学生，绑定到教师，加入班级，返回 (token, student_id)。"""
    stu_token = await _login(client, f"stu_{uuid.uuid4().hex[:8]}")
    stu_h = {"Authorization": f"Bearer {stu_token}"}
    tch_h = {"Authorization": f"Bearer {teacher_token}"}

    # 学生绑定教师（邀请码流程）
    r = await client.post("/api/v1/teacher/invite-code", headers=tch_h)
    code = r.json()["data"]["code"]
    await client.post("/api/v1/teacher/bind", json={"code": code}, headers=stu_h)

    # 拿学生 ID，加入班级
    r_me = await client.get("/api/v1/users/me", headers=stu_h)
    stu_id = r_me.json()["data"]["id"]
    await client.post(f"/api/v1/teacher/classes/{class_id}/students",
                      json={"student_ids": [stu_id]}, headers=tch_h)
    return stu_token, stu_id


async def _do_practice(client, token: str, kp: str, answer: str):
    """做一道练习并提交指定答案。"""
    h = {"Authorization": f"Bearer {token}"}
    r = await client.post("/api/v1/practice/generate",
                          json={"knowledge_point": kp, "count": 1, "difficulty": 3},
                          headers=h)
    q_id = r.json()["data"][0]["id"]
    await client.post("/api/v1/practice/submit",
                      json={"question_id": q_id, "answer": answer}, headers=h)


# ── 测试 1：教师查学生台账 ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_teacher_can_view_student_kp_mastery(client):
    """教师可查看绑定学生的 KP 台账。"""
    tch_token, _ = await _setup_teacher(client)
    tch_h = {"Authorization": f"Bearer {tch_token}"}

    r_cls = await client.post("/api/v1/teacher/classes", json={"name": "M44班"}, headers=tch_h)
    class_id = r_cls.json()["data"]["id"]

    stu_token, stu_id = await _setup_student_in_class(client, tch_token, class_id)

    # 学生做练习，产生台账数据
    await _do_practice(client, stu_token, "过去完成时", "WRONG_XYZ")

    # 教师查该学生 KP 台账
    r = await client.get(f"/api/v1/teacher/students/{stu_id}/kp-mastery", headers=tch_h)
    assert r.status_code == 200, r.text
    items = r.json()["data"]
    assert len(items) >= 1, "学生有答题记录，台账应有数据"

    item = items[0]
    assert "kp_key" in item
    assert "correct_count" in item
    assert "wrong_count" in item
    assert "accuracy" in item
    assert "sources" in item


@pytest.mark.asyncio
async def test_teacher_cannot_view_unbound_student_kp_mastery(client):
    """教师不能查看未绑定学生的 KP 台账，返回 403。"""
    tch_token, _ = await _setup_teacher(client)
    tch_h = {"Authorization": f"Bearer {tch_token}"}

    # 另一个学生，没有绑定这个教师
    stranger_token = await _login(client, f"str_{uuid.uuid4().hex[:8]}")
    str_h = {"Authorization": f"Bearer {stranger_token}"}
    r_me = await client.get("/api/v1/users/me", headers=str_h)
    stranger_id = r_me.json()["data"]["id"]

    r = await client.get(f"/api/v1/teacher/students/{stranger_id}/kp-mastery", headers=tch_h)
    assert r.status_code == 403, f"未绑定学生应返回 403，实际: {r.status_code} {r.text}"


# ── 测试 2：班级 KP 统计 ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_class_kp_stats_structure(client):
    """班级 KP 统计接口返回正确结构。"""
    tch_token, _ = await _setup_teacher(client)
    tch_h = {"Authorization": f"Bearer {tch_token}"}

    r_cls = await client.post("/api/v1/teacher/classes", json={"name": "M44统计班"}, headers=tch_h)
    class_id = r_cls.json()["data"]["id"]

    stu_token, _ = await _setup_student_in_class(client, tch_token, class_id)
    await _do_practice(client, stu_token, "一般现在时", "WRONG_XYZ")

    r = await client.get(f"/api/v1/teacher/classes/{class_id}/kp-stats", headers=tch_h)
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    # 结构检查
    assert "class_id" in data
    assert "class_name" in data
    assert "student_count" in data
    assert "top_weak_kps" in data
    assert "students_attention" in data

    # top_weak_kps 每项字段
    if data["top_weak_kps"]:
        kp = data["top_weak_kps"][0]
        assert "kp_key" in kp
        assert "avg_accuracy" in kp
        assert "student_count" in kp  # 有记录的学生数
        assert "weak_count" in kp     # accuracy < 0.6 的学生数


@pytest.mark.asyncio
async def test_class_kp_stats_sorted_by_avg_accuracy(client):
    """top_weak_kps 按全班平均正确率升序排列（最弱在前）。"""
    tch_token, _ = await _setup_teacher(client)
    tch_h = {"Authorization": f"Bearer {tch_token}"}

    r_cls = await client.post("/api/v1/teacher/classes", json={"name": "M44排序班"}, headers=tch_h)
    class_id = r_cls.json()["data"]["id"]

    stu_token, _ = await _setup_student_in_class(client, tch_token, class_id)
    # KP A：全错（avg_accuracy=0）
    await _do_practice(client, stu_token, "虚拟语气", "WRONG_XYZ")
    # KP B：全对（avg_accuracy=1，dev mock 正确答案是 "goes"）
    await _do_practice(client, stu_token, "一般现在时", "goes")

    r = await client.get(f"/api/v1/teacher/classes/{class_id}/kp-stats", headers=tch_h)
    data = r.json()["data"]
    kps = data["top_weak_kps"]
    assert len(kps) >= 2, f"应有至少两个 KP，实际: {len(kps)}"

    # 第一个应该是正确率最低的（虚拟语气）
    assert kps[0]["kp_key"] == "虚拟语气", f"最弱KP应排首位，实际: {kps[0]['kp_key']}"
    assert kps[0]["avg_accuracy"] < kps[-1]["avg_accuracy"], "应按 avg_accuracy 升序"


@pytest.mark.asyncio
async def test_students_attention_sorted_by_worst_accuracy(client):
    """students_attention 按学生整体平均正确率升序（最差在前）。"""
    tch_token, _ = await _setup_teacher(client)
    tch_h = {"Authorization": f"Bearer {tch_token}"}

    r_cls = await client.post("/api/v1/teacher/classes", json={"name": "M44关注班"}, headers=tch_h)
    class_id = r_cls.json()["data"]["id"]

    # 学生 A：全错
    stu_a_token, stu_a_id = await _setup_student_in_class(client, tch_token, class_id)
    await _do_practice(client, stu_a_token, "虚拟语气", "WRONG_XYZ")

    # 学生 B：全对
    stu_b_token, stu_b_id = await _setup_student_in_class(client, tch_token, class_id)
    await _do_practice(client, stu_b_token, "一般现在时", "goes")

    r = await client.get(f"/api/v1/teacher/classes/{class_id}/kp-stats", headers=tch_h)
    data = r.json()["data"]
    attention = data["students_attention"]

    assert len(attention) >= 1
    # 有答题记录的学生应出现在 students_attention
    attention_ids = [s["student_id"] for s in attention]

    # 最差的学生（全错）应排在最前面
    if len(attention) >= 2:
        assert attention[0]["avg_accuracy"] <= attention[1]["avg_accuracy"]
