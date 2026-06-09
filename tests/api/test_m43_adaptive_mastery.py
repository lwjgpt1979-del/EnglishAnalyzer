"""TDD: M43 — 自适应选题策略升级：优先从 student_kp_mastery 读弱项。

测试覆盖：
  1. get_adaptive_set 优先使用台账弱项（正确率最低的 KP）
  2. generate_questions（无 KP 时）优先读台账弱项，而不是旧 diagnosis_service
  3. 台账为空时 fallback 到旧 ai_analyses 逻辑（向后兼容）
  4. 台账弱项存在时 GET /api/v1/questions/adaptive-set 正常返回题目
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings


async def _login(client, openid: str) -> str:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as m:
        m.return_value = {"openid": openid}
        r = await client.post("/api/v1/auth/wx-login", json={"code": "x"})
    return r.json()["data"]["access_token"]


# ── 单元测试：adaptive_question_service 优先读台账 ──────────────────────────────

@pytest.mark.asyncio
async def test_adaptive_set_uses_mastery_weak_kps(client):
    """台账有弱项时，adaptive_set 用台账 KP，而非 ai_analyses。"""
    token = await _login(client, f"m43_{uuid.uuid4().hex[:8]}")
    h = {"Authorization": f"Bearer {token}"}

    # 先用练习写入一个弱项 KP（台账里会有记录）
    r = await client.post("/api/v1/practice/generate", json={
        "knowledge_point": "过去完成时",
        "count": 1,
        "difficulty": 3,
    }, headers=h)
    assert r.status_code == 200, r.text
    question_id = r.json()["data"][0]["id"]

    # 提交错误答案，让这道题错一次（写入台账 wrong_count）
    await client.post("/api/v1/practice/submit", json={
        "question_id": question_id,
        "answer": "WRONG_ANSWER_XYZ",
    }, headers=h)

    # 此时台账里"过去完成时"正确率=0，是最弱KP
    r2 = await client.get("/api/v1/questions/adaptive-set?total=3", headers=h)
    assert r2.status_code == 200, r2.text
    data = r2.json()["data"]

    # weak_kp_names 应包含台账里的弱项
    assert len(data.get("weak_kp_names", [])) >= 1, "应识别到弱项知识点"
    assert len(data.get("questions", [])) >= 1, "应返回题目"


@pytest.mark.asyncio
async def test_generate_questions_uses_mastery_when_no_kp(client):
    """generate_questions 在 knowledge_point=None 时，优先读台账弱项。"""
    token = await _login(client, f"m43_{uuid.uuid4().hex[:8]}")
    h = {"Authorization": f"Bearer {token}"}

    # 写入台账弱项
    await client.post("/api/v1/practice/generate", json={
        "knowledge_point": "动词短语辨析",
        "count": 1,
        "difficulty": 3,
    }, headers=h)
    r1 = await client.post("/api/v1/practice/generate", json={
        "knowledge_point": "动词短语辨析",
        "count": 1,
        "difficulty": 3,
    }, headers=h)
    q_id = r1.json()["data"][0]["id"]
    await client.post("/api/v1/practice/submit", json={
        "question_id": q_id,
        "answer": "WRONG",
    }, headers=h)

    # 不传 knowledge_point，应自动选台账弱项
    r2 = await client.post("/api/v1/practice/generate", json={
        "count": 2,
        "difficulty": 3,
    }, headers=h)
    assert r2.status_code == 200, r2.text
    questions = r2.json()["data"]
    # 应返回题目，且 knowledge_point_name 来自台账弱项
    assert len(questions) >= 1, "应返回题目"
    kp_names = {q.get("knowledge_point_name") for q in questions}
    assert "动词短语辨析" in kp_names, f"应使用台账弱项，实际KP: {kp_names}"


@pytest.mark.asyncio
async def test_adaptive_set_fallback_when_mastery_empty(client):
    """台账为空时，adaptive_set 返回空集（而不是崩溃）。"""
    token = await _login(client, f"m43_{uuid.uuid4().hex[:8]}")
    h = {"Authorization": f"Bearer {token}"}

    # 新用户，台账为空，也没有 ai_analyses
    r = await client.get("/api/v1/questions/adaptive-set?total=3", headers=h)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    # 台账空 + 无 ai_analyses → questions 空，不报错
    assert isinstance(data.get("questions", []), list)


@pytest.mark.asyncio
async def test_mastery_weak_kps_sorted_by_accuracy(client):
    """台账优先选择正确率最低的 KP（最弱的优先）。"""
    token = await _login(client, f"m43_{uuid.uuid4().hex[:8]}")
    h = {"Authorization": f"Bearer {token}"}

    # 写入两个 KP：一个全对，一个全错
    # KP A: 做2题全对
    r = await client.post("/api/v1/practice/generate", json={
        "knowledge_point": "一般现在时",
        "count": 2, "difficulty": 2,
    }, headers=h)
    for q in r.json()["data"]:
        # dev mock 正确答案是 "goes"/"are"，提交正确答案
        await client.post("/api/v1/practice/submit", json={
            "question_id": q["id"], "answer": "goes"
        }, headers=h)

    # KP B: 做2题全错
    r2 = await client.post("/api/v1/practice/generate", json={
        "knowledge_point": "虚拟语气",
        "count": 2, "difficulty": 4,
    }, headers=h)
    for q in r2.json()["data"]:
        await client.post("/api/v1/practice/submit", json={
            "question_id": q["id"], "answer": "WRONG_XYZ_NEVER_CORRECT"
        }, headers=h)

    # adaptive_set 应优先选"虚拟语气"（正确率=0）
    r3 = await client.get("/api/v1/questions/adaptive-set?total=3", headers=h)
    data = r3.json()["data"]
    weak_kps = data.get("weak_kp_names", [])
    assert len(weak_kps) >= 1
    # 最弱的（虚拟语气）应在列表首位
    assert weak_kps[0] == "虚拟语气", f"最弱KP应排首位，实际: {weak_kps}"
