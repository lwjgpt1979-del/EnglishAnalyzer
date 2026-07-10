"""TDD: M41 — 作业提交 + 错题AI分析写入知识点台账。

测试覆盖：
  1. 作业提交后，自动判分的对/错题各自写入 correct_count / wrong_count
  2. 作业台账记录的 source 包含 'assignment'
  3. 错题AI分析完成后，台账写入 wrong_count（source='wrong_question'）
  4. 两种来源可同时出现在同一 kp_key 的 sources 数组里
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.core.config import settings


# R8.0:掌握账只统计树内 node。dev-mock 分类出的 KP 名(assignment/整卷→「英语综合」,
# 错题AI→「动词短语…」)本不在受控树里,故先把它们 seed 成 active node+alias,
# 让 upsert_mastery 的 match_kp 能解析到 node 并写 student_kp。
_MOCK_KP_NAMES = ["英语综合", "动词短语 hand in/out/over/up"]


@pytest_asyncio.fixture(autouse=True)
async def _seed_mock_kp_nodes():
    from app.core.database import _async_session_factory
    from app.services.kp_normalize import normalize_kp_name
    created: list = []
    async with _async_session_factory() as s:
        for name in _MOCK_KP_NAMES:
            norm = normalize_kp_name(name)
            if (await s.execute(text("SELECT 1 FROM knowledge_node_aliases WHERE alias_norm=:n"), {"n": norm})).first():
                continue   # 树里已有,不动
            nid = uuid.uuid4()
            await s.execute(text(
                "INSERT INTO knowledge_nodes (id,axis,name,code,status,source) "
                "VALUES (:i,'knowledge',:nm,:c,'active','seed')"),
                {"i": nid, "nm": name, "c": f"m41seed-{nid.hex[:8]}"})
            await s.execute(text(
                "INSERT INTO knowledge_node_aliases (id,node_id,alias,alias_norm,source) "
                "VALUES (:i,:n,:a,:an,'seed')"),
                {"i": uuid.uuid4(), "n": nid, "a": name, "an": norm})
            created.append(nid)
        await s.commit()
    yield
    if created:
        async with _async_session_factory() as s:
            await s.execute(text("DELETE FROM student_kp WHERE node_id = ANY(:ids)"), {"ids": created})
            await s.execute(text("DELETE FROM knowledge_node_aliases WHERE node_id = ANY(:ids)"), {"ids": created})
            await s.execute(text("DELETE FROM knowledge_nodes WHERE id = ANY(:ids)"), {"ids": created})
            await s.commit()


# ── helpers ───────────────────────────────────────────────────────────────────

async def _login(client, openid: str) -> str:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as m:
        m.return_value = {"openid": openid}
        r = await client.post("/api/v1/auth/wx-login", json={"code": "x"})
    return r.json()["data"]["access_token"]


async def _make_teacher_and_class(client) -> tuple[str, str]:
    """创建教师账号 + 班级，返回 (teacher_token, class_id)。"""
    token = await _login(client, f"tch_{uuid.uuid4().hex[:8]}")
    h = {"Authorization": f"Bearer {token}"}
    await client.post("/api/v1/teacher/profile", json={"subject": "英语"}, headers=h)
    await client.post("/api/v1/teacher/cert/submit",
                      json={"cert_doc_url": "https://example.com/cert.jpg"}, headers=h)
    r = await client.post("/api/v1/teacher/classes", json={"name": "M41班"}, headers=h)
    class_id = r.json()["data"]["id"]
    return token, class_id


async def _add_student_to_class(
    client, teacher_token: str, class_id: str, student_token: str
) -> None:
    """通过邀请码将学生绑定到教师，再加入班级。"""
    tch_h = {"Authorization": f"Bearer {teacher_token}"}
    stu_h = {"Authorization": f"Bearer {student_token}"}

    # 1. 教师生成邀请码
    r = await client.post("/api/v1/teacher/invite-code", headers=tch_h)
    code = r.json()["data"]["code"]

    # 2. 学生绑定教师
    await client.post("/api/v1/teacher/bind", json={"code": code}, headers=stu_h)

    # 3. 拿到学生 ID，加入班级
    r = await client.get("/api/v1/users/me", headers=stu_h)
    student_id = r.json()["data"]["id"]
    await client.post(
        f"/api/v1/teacher/classes/{class_id}/students",
        json={"student_ids": [student_id]},
        headers=tch_h,
    )


async def _ledger(client, stu_h: dict) -> list[dict]:
    """读旧台账 student_kp_mastery(掌握 hook 写入处;/kp-mastery 端点已切 student_kp,
    本系列验证的是写入,故直接查台账服务)。"""
    from app.core.database import _async_session_factory
    from app.services import kp_mastery_service
    r = await client.get("/api/v1/users/me", headers=stu_h)
    uid = r.json()["data"]["id"]
    async with _async_session_factory() as s:
        rows = await kp_mastery_service.get_mastery_tree(s, student_id=uid)
    return [{"sources": list(x.sources or []), "correct_count": x.correct_count,
             "wrong_count": x.wrong_count} for x in rows]


# ── 测试：作业提交 → 台账写入 ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_assignment_submit_writes_mastery(client):
    """提交作业后，对/错题正确写入知识点台账，source 含 assignment。"""
    # 创建教师 + 班级
    tch_token, class_id = await _make_teacher_and_class(client)

    # 创建学生并加入班级
    stu_token = await _login(client, f"stu_{uuid.uuid4().hex[:8]}")
    await _add_student_to_class(client, tch_token, class_id, stu_token)

    # 教师创建并发布作业（含一道有答案的客观题）
    tch_h = {"Authorization": f"Bearer {tch_token}"}
    r = await client.post("/api/v1/teacher/assignments", json={
        "class_id": class_id,
        "title": "M41测试作业",
        "questions": [
            {
                "stem": "She ___ to school every day.",
                "type": "单选",
                "options": ["A. go", "B. goes", "C. going", "D. went"],
                "answer": "B",
            }
        ],
    }, headers=tch_h)
    assert r.status_code == 200, r.text
    asgn_id = r.json()["data"]["id"]

    await client.post(f"/api/v1/teacher/assignments/{asgn_id}/publish", headers=tch_h)

    # 学生提交答案（答对：B）
    stu_h = {"Authorization": f"Bearer {stu_token}"}
    r2 = await client.post(f"/api/v1/assignments/{asgn_id}/submit",
                           json={"answers": {0: "B"}}, headers=stu_h)
    assert r2.status_code == 200, r2.text

    # 查知识点台账
    items = await _ledger(client, stu_h)
    assert len(items) >= 1, "提交作业后台账应有写入"

    sources_all = [s for item in items for s in item["sources"]]
    assert "assignment" in sources_all, "来源应包含 assignment"

    total_correct = sum(i["correct_count"] for i in items)
    assert total_correct >= 1, "答对题应写入 correct_count"


@pytest.mark.asyncio
async def test_assignment_wrong_answer_writes_wrong_count(client):
    """提交作业答错后，wrong_count 写入台账。"""
    tch_token, class_id = await _make_teacher_and_class(client)
    stu_token = await _login(client, f"stu_{uuid.uuid4().hex[:8]}")
    await _add_student_to_class(client, tch_token, class_id, stu_token)

    tch_h = {"Authorization": f"Bearer {tch_token}"}
    r = await client.post("/api/v1/teacher/assignments", json={
        "class_id": class_id,
        "title": "M41错题测试",
        "questions": [{
            "stem": "They ___ happy yesterday.",
            "type": "单选",
            "options": ["A. is", "B. are", "C. were", "D. was"],
            "answer": "C",
        }],
    }, headers=tch_h)
    asgn_id = r.json()["data"]["id"]
    await client.post(f"/api/v1/teacher/assignments/{asgn_id}/publish", headers=tch_h)

    # 学生提交错误答案（答 A，正确是 C）
    stu_h = {"Authorization": f"Bearer {stu_token}"}
    await client.post(f"/api/v1/assignments/{asgn_id}/submit",
                      json={"answers": {0: "A"}}, headers=stu_h)

    items = await _ledger(client, stu_h)
    total_wrong = sum(i["wrong_count"] for i in items)
    assert total_wrong >= 1, "答错题应写入 wrong_count"


# ── 测试：错题AI分析 → 台账写入 ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ai_analysis_writes_mastery(client):
    """错题AI分析完成后，台账写入 wrong_count，source 含 wrong_question。"""
    stu_token = await _login(client, f"stu_{uuid.uuid4().hex[:8]}")
    stu_h = {"Authorization": f"Bearer {stu_token}"}

    # 创建错题
    r = await client.post("/api/v1/wrong-questions/",
                          json={"source_image_url": "https://cdn.example.com/wq.jpg"},
                          headers=stu_h)
    wq_id = r.json()["data"]["id"]

    # 触发 AI 分析（dev mock 返回固定 knowledge_points）
    r2 = await client.post(f"/api/v1/wrong-questions/{wq_id}/analyze", headers=stu_h)
    assert r2.status_code == 200

    # 查台账
    items = await _ledger(client, stu_h)
    assert len(items) >= 1, "AI分析完成后台账应有写入"

    sources_all = [s for item in items for s in item["sources"]]
    assert "wrong_question" in sources_all, "来源应包含 wrong_question"

    total_wrong = sum(i["wrong_count"] for i in items)
    assert total_wrong >= 1, "错题分析应写入 wrong_count"


@pytest.mark.asyncio
async def test_mastery_sources_merge_assignment_and_wrong_question(client):
    """同一知识点通过作业和错题分析各写入一次，sources 同时包含两种来源。"""
    tch_token, class_id = await _make_teacher_and_class(client)
    stu_token = await _login(client, f"stu_{uuid.uuid4().hex[:8]}")
    await _add_student_to_class(client, tch_token, class_id, stu_token)
    stu_h = {"Authorization": f"Bearer {stu_token}"}

    # 1. 提交作业（dev mock KP 归类结果为固定值）
    tch_h = {"Authorization": f"Bearer {tch_token}"}
    r = await client.post("/api/v1/teacher/assignments", json={
        "class_id": class_id,
        "title": "合并测试作业",
        "questions": [{
            "stem": "She ___ her homework.",
            "type": "单选",
            "options": ["A. do", "B. does", "C. doing", "D. did"],
            "answer": "B",
        }],
    }, headers=tch_h)
    asgn_id = r.json()["data"]["id"]
    await client.post(f"/api/v1/teacher/assignments/{asgn_id}/publish", headers=tch_h)
    await client.post(f"/api/v1/assignments/{asgn_id}/submit",
                      json={"answers": {0: "B"}}, headers=stu_h)

    # 2. 上传错题 + AI 分析
    r_wq = await client.post("/api/v1/wrong-questions/",
                              json={"source_image_url": "https://cdn.example.com/wq2.jpg"},
                              headers=stu_h)
    wq_id = r_wq.json()["data"]["id"]
    await client.post(f"/api/v1/wrong-questions/{wq_id}/analyze", headers=stu_h)

    # 查台账 — 至少有一个 KP 的 sources 包含两种来源
    items = await _ledger(client, stu_h)
    all_sources = {s for item in items for s in item["sources"]}
    assert "assignment" in all_sources
    assert "wrong_question" in all_sources
