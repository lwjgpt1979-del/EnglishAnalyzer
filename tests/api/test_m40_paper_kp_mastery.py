"""TDD: M40 整卷上传 → 豆包Vision拆题 → DeepSeek KP归类 → 知识点台账写入。

测试覆盖：
  1. DoubaoVisionProvider dev mock 返回合法 OcrResult
  2. KP 归类 dev mock 返回知识点映射
  3. 整卷上传流水线完成后 student_kp_mastery 有写入（source=paper_upload）
  4. 对题（is_wrong=False）写入 correct_count；错题写入 wrong_count
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.services import user_paper_service


@pytest.fixture(autouse=True)
def force_dev_mode(monkeypatch):
    """强制所有 AI 服务走 dev mock，避免测试调真实 API。"""
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-placeholder-for-test")
    monkeypatch.setattr(settings, "doubao_api_key", "placeholder-doubao-dev")


async def _login(client, openid: str) -> str:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as m:
        m.return_value = {"openid": openid}
        r = await client.post("/api/v1/auth/wx-login", json={"code": "x"})
    return r.json()["data"]["access_token"]


# ── 单元测试：DoubaoVisionProvider dev mock ───────────────────────────────────

@pytest.mark.asyncio
async def test_doubao_vision_provider_dev_mock():
    """dev 模式下 DoubaoVisionProvider 返回合法 OcrResult，不调真实 API。"""
    from app.services.doubao_vision_service import DoubaoVisionProvider
    provider = DoubaoVisionProvider()
    result = await provider.recognize("https://cdn.example.com/paper.jpg")
    assert result.printed_text, "dev mock 应返回非空印刷体文字（豆包直出 JSON）"
    assert result.printed_text.strip().startswith("["), "豆包 dev mock 应返回 JSON 数组字符串"
    assert result.handwritten_text == "", "豆包模式 handwritten_text 为空（学生答案已在 JSON 里）"


# ── 单元测试：KP 归类 dev mock ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_kp_classifier_dev_mock():
    """dev 模式下 classify_kps 返回合法的 {题号: kp_key} 映射。"""
    from app.services.kp_classifier_service import classify_kps
    from app.services.paper_split_service import ParsedPaperQuestion

    questions = [
        ParsedPaperQuestion(
            question_no="1",
            question_type="单选",
            stem="She ___ to school every day.",
            student_answer="A",
            correct_answer="A",
            explanation=None,
        ),
        ParsedPaperQuestion(
            question_no="2",
            question_type="单选",
            stem="They ___ very happy yesterday.",
            student_answer="B",
            correct_answer="A",
            explanation=None,
        ),
    ]
    result = await classify_kps(questions)
    assert isinstance(result, dict)
    assert len(result) == 2
    for qno, kp in result.items():
        assert isinstance(kp, str) and len(kp) > 0


# ── 集成测试：整卷流水线完成后台账写入 ────────────────────────────────────────

@pytest.mark.asyncio
async def test_paper_pipeline_writes_kp_mastery(client):
    """上传整卷 → 流水线完成 → student_kp_mastery 有写入，source 含 paper_upload。"""
    token = await _login(client, f"m40_{uuid.uuid4().hex[:8]}")
    headers = {"Authorization": f"Bearer {token}"}

    # 上传整卷（dev mock 会自动触发后台流水线同步执行）
    r = await client.post(
        "/api/v1/user-papers",
        json={
            "title": "期中英语试卷",
            "source_image_urls": ["https://cdn.example.com/paper1.jpg"],
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    paper_id = r.json()["data"]["id"]

    # 后台流水线是 BackgroundTask，在测试 client 里同步执行完毕后再查
    await user_paper_service.run_paper_pipeline(paper_id)

    r2 = await client.get(f"/api/v1/user-papers/{paper_id}", headers=headers)
    assert r2.json()["data"]["ocr_status"] == "completed", r2.text

    # 查知识点台账(/kp-mastery 端点已切 student_kp;整卷掌握写旧台账,直接查台账服务)
    from app.core.database import _async_session_factory
    from app.services import kp_mastery_service
    me = await client.get("/api/v1/users/me", headers=headers)
    uid = me.json()["data"]["id"]
    async with _async_session_factory() as s:
        rows = await kp_mastery_service.get_mastery_tree(s, student_id=uid)
    items = [{"sources": list(x.sources or [])} for x in rows]
    assert len(items) >= 1, "整卷完成后台账应有知识点写入"

    # 验证来源标注
    sources_all = [s for item in items for s in item["sources"]]
    assert "paper_upload" in sources_all, "来源应包含 paper_upload"


@pytest.mark.asyncio
async def test_paper_correct_wrong_count(client):
    """对题写 correct_count，错题写 wrong_count。"""
    token = await _login(client, f"m40_{uuid.uuid4().hex[:8]}")
    headers = {"Authorization": f"Bearer {token}"}

    r0 = await client.post(
        "/api/v1/user-papers",
        json={
            "title": "测试卷",
            "source_image_urls": ["https://cdn.example.com/p2.jpg"],
        },
        headers=headers,
    )
    await user_paper_service.run_paper_pipeline(r0.json()["data"]["id"])

    # /kp-mastery 端点已切 student_kp(B);整卷掌握写入旧台账,故直接查台账验证写入
    from app.core.database import _async_session_factory
    from app.services import kp_mastery_service
    me = await client.get("/api/v1/users/me", headers=headers)
    uid = me.json()["data"]["id"]
    async with _async_session_factory() as s:
        rows = await kp_mastery_service.get_mastery_tree(s, student_id=uid)
    items = [{"correct_count": x.correct_count, "wrong_count": x.wrong_count} for x in rows]
    assert len(items) >= 1

    total_correct = sum(i["correct_count"] for i in items)
    total_wrong = sum(i["wrong_count"] for i in items)
    # dev mock 固定 2 题（题27对，题28错），所以应各有计数
    assert total_correct >= 1, "应有对题写入 correct_count"
    assert total_wrong >= 1, "应有错题写入 wrong_count"
