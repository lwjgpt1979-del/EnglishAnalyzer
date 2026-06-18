"""Admin 课程内容生成端点 TDD 测试。"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import _async_session_factory
from app.models.d4_knowledge import CurriculumUnit


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


@pytest_asyncio.fixture
async def seeded_unit_id(db: AsyncSession) -> str:
    """植入一个最小课程单元用于生成测试（幂等：先删旧行）。"""
    from sqlalchemy import delete
    from app.models.d4_knowledge import CurriculumUnit as CU
    # unit_no must be ≤ 20 (AIGeneratedUnit schema cap); use 18 to avoid clash with other tests
    # Cascade delete all FK-dependent rows before deleting the unit
    from sqlalchemy import text
    cleanup_sql = """
    DO $$
    DECLARE _ids UUID[];
    BEGIN
      SELECT ARRAY(SELECT id FROM curriculum_units
                   WHERE textbook_version='译林版' AND grade='小学5年级'
                     AND semester='上' AND unit_no=18)
      INTO _ids;
      DELETE FROM unit_knowledge_points WHERE unit_id = ANY(_ids);
      DELETE FROM curriculum_words WHERE unit_id = ANY(_ids);
      DELETE FROM curriculum_units WHERE id = ANY(_ids);
    END $$;
    """
    await db.execute(text(cleanup_sql))
    await db.commit()
    unit = CurriculumUnit(
        id=uuid.uuid4(),
        textbook_version="译林版",
        grade="小学5年级",
        semester="上",
        unit_no=18,
        unit_title="Test Unit",
    )
    db.add(unit)
    await db.flush()
    await db.commit()
    return str(unit.id)


# ── 鉴权检查 ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_units_requires_admin(client: AsyncClient):
    """未鉴权 → 401。"""
    r = await client.get("/api/v1/admin/curriculum/units")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_generate_requires_admin(client: AsyncClient):
    """非 admin 调用生成 → 401。"""
    r = await client.post(f"/api/v1/admin/curriculum/units/{uuid.uuid4()}/generate")
    assert r.status_code == 401


# ── 正常流程 ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_curriculum_units_returns_list(admin_client: AsyncClient):
    """Admin 鉴权 → 200 + list（允许为空）。"""
    r = await admin_client.get("/api/v1/admin/curriculum/units")
    assert r.status_code == 200
    data = r.json()["data"]
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_list_curriculum_units_has_correct_fields(
    admin_client: AsyncClient, seeded_unit_id: str
):
    """返回的每条数据有 unit_id / kp_count / content_count / content_rate 字段。"""
    r = await admin_client.get("/api/v1/admin/curriculum/units")
    assert r.status_code == 200
    items = r.json()["data"]
    # 找到刚植入的单元
    target = next((i for i in items if i["unit_id"] == seeded_unit_id), None)
    assert target is not None
    assert "kp_count" in target
    assert "content_count" in target
    assert "content_rate" in target


@pytest.mark.asyncio
async def test_generate_unit_content_success(
    admin_client: AsyncClient, seeded_unit_id: str
):
    """有效 unit_id → 200 + 统计字段齐全。

    KP-First:内容已切 node_resource,content_count 数经 unit_node 的 lecture;
    冷启动下新 KP 未命中 node → 落候选、无 lecture(受控匹配代价),故此处只断言生成成功 +
    统计可计算(content_count≥0)。lecture 写入的严格证明见
    tests/api/test_curriculum.py::test_persist_unit_writes_node_resource_lectures_draft。
    """
    r = await admin_client.post(
        f"/api/v1/admin/curriculum/units/{seeded_unit_id}/generate"
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["unit_id"] == seeded_unit_id
    assert data["kp_count"] > 0
    assert data["content_count"] >= 0
    assert 0.0 <= data["content_rate"] <= 1.0


@pytest.mark.asyncio
async def test_generate_unit_invalid_id(admin_client: AsyncClient):
    """不存在的 unit_id → 404。"""
    r = await admin_client.post(
        f"/api/v1/admin/curriculum/units/{uuid.uuid4()}/generate"
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_generate_unit_is_idempotent(
    admin_client: AsyncClient, seeded_unit_id: str
):
    """重复生成同一单元不会报错（persist_unit 幂等）。"""
    r1 = await admin_client.post(
        f"/api/v1/admin/curriculum/units/{seeded_unit_id}/generate"
    )
    r2 = await admin_client.post(
        f"/api/v1/admin/curriculum/units/{seeded_unit_id}/generate"
    )
    assert r1.status_code == 200
    assert r2.status_code == 200


@pytest.mark.asyncio
async def test_generate_from_pdf_async_job_isolates_failed_unit(admin_client: AsyncClient):
    """异步任务(方案A):POST 秒回 job_id;后台逐单元生成,失败单元(重试后仍失败)不连累其余,
    成功单元独立 commit 落库;轮询任务进度可见 done/failed。"""
    import asyncio as _aio
    from unittest.mock import patch
    from app.services import curriculum_ai_service
    from app.services.curriculum_ai_service import _make_mock_unit
    from sqlalchemy import text as _t

    tb = f"asyncjob版{uuid.uuid4().hex[:6]}"
    grade, sem = "测试年级", "上"

    async def _fake_gen(*, textbook_version, grade, semester, unit_no, unit_text, detected_title=None):
        if unit_no == 2:
            raise RuntimeError("LLM boom (unit 2)")   # 仅 Unit 2 失败(重试 3 次都失败)
        return _make_mock_unit(textbook_version, grade, semester, unit_no)

    segs = [{"unit_no": n, "start_page": n, "end_page": n} for n in (1, 2, 3)]
    body = {"textbook_version": tb, "grade": grade, "semester": sem,
            "segments": segs, "content_status": "draft"}
    try:
        with patch.object(curriculum_ai_service, "generate_unit_from_text", _fake_gen), \
             patch("app.services.pdf_upload_service.extract_pages", lambda fid: ["p"] * 5), \
             patch("app.services.pdf_upload_service.get_unit_text", lambda fid, s, e: "unit text"):
            r = await admin_client.post("/api/v1/admin/curriculum/pdf/anyfile/generate", json=body)
            assert r.status_code == 200, r.text
            job_id = r.json()["data"]["job_id"]
            assert r.json()["data"]["total"] == 3

            # 轮询任务直到结束(后台 asyncio 任务在同一事件循环跑)
            data = None
            for _ in range(50):
                jr = await admin_client.get(f"/api/v1/admin/curriculum/pdf-jobs/{job_id}")
                data = jr.json()["data"]
                if data["status"] != "running":
                    break
                await _aio.sleep(0.2)
        assert data["status"] == "done"           # 有成功单元 → done(非全败)
        assert data["done"] == 2 and data["failed"] == 1
        statuses = {x["unit_no"]: x["status"] for x in data["results"]}
        assert statuses == {1: "ok", 2: "error", 3: "ok"}

        # 成功单元已独立 commit 落库,失败单元不在库
        async with _async_session_factory() as s:
            unos = (await s.execute(_t(
                "SELECT unit_no FROM curriculum_units WHERE textbook_version=:tb ORDER BY unit_no"),
                {"tb": tb})).scalars().all()
        assert list(unos) == [1, 3]
    finally:
        async with _async_session_factory() as s:
            ids = (await s.execute(_t("SELECT id FROM curriculum_units WHERE textbook_version=:tb"),
                                   {"tb": tb})).scalars().all()
            for uid in ids:
                nids = (await s.execute(_t("SELECT node_id FROM unit_node WHERE unit_id=:u"),
                                        {"u": str(uid)})).scalars().all()
                await s.execute(_t("DELETE FROM unit_node WHERE unit_id=:u"), {"u": str(uid)})
                await s.execute(_t("DELETE FROM curriculum_words WHERE unit_id=:u"), {"u": str(uid)})
                for nid in nids:   # R8.4:清掉本测试新建的 node 及其资源/别名
                    await s.execute(_t("DELETE FROM node_resource WHERE node_id=:n"), {"n": str(nid)})
                    await s.execute(_t("DELETE FROM vocab_node WHERE node_id=:n"), {"n": str(nid)})
                    await s.execute(_t("DELETE FROM knowledge_node_aliases WHERE node_id=:n"), {"n": str(nid)})
                    await s.execute(_t("DELETE FROM knowledge_nodes WHERE id=:n"), {"n": str(nid)})
            await s.execute(_t("DELETE FROM curriculum_units WHERE textbook_version=:tb"), {"tb": tb})
            await s.execute(_t("DELETE FROM curriculum_gen_job WHERE textbook_version=:tb"), {"tb": tb})
            await s.commit()
