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
    # E2:受控树先有 unit18 mock 知识点名(模拟后台已定义),生成端点才能映射建边/挂内容
    from app.services import curriculum_ai_service as _ais
    from app.models.d15_knowledge_graph import KnowledgeNode, NodeAlias
    from app.services.kp_normalize import normalize_kp_name
    from sqlalchemy import select as _select
    ai = await _ais.generate_unit(textbook_version="译林版", grade="小学5年级", semester="上", unit_no=18)
    for kp in ai.knowledge_points:
        norm = normalize_kp_name(kp.name)
        if (await db.execute(_select(NodeAlias.node_id)
                             .where(NodeAlias.alias_norm == norm))).scalar_one_or_none() is not None:
            continue
        nid = uuid.uuid4()
        db.add(KnowledgeNode(id=nid, axis="knowledge", name=kp.name,
                             code=f"ttree-{uuid.uuid4().hex[:8]}", status="active", source="seed"))
        await db.flush()
        db.add(NodeAlias(id=uuid.uuid4(), node_id=nid, alias=kp.name, alias_norm=norm, source="seed"))
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

    统计已切「短文关联考点」口径:kp_count=单元各短文已关联考点去重数、content_count=已关联短文数、
    content_rate=已关联短文/短文总数。generate 走的是 unit_node 六维路径、不建短文关联,故该口径下
    三者可为 0——此处只断言生成成功 + 统计字段齐全可计算。生成本身(unit_node/lecture)的严格证明见
    tests/api/test_curriculum.py::test_persist_unit_writes_node_resource_lectures_draft。
    """
    r = await admin_client.post(
        f"/api/v1/admin/curriculum/units/{seeded_unit_id}/generate"
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["unit_id"] == seeded_unit_id
    assert data["kp_count"] >= 0
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
    """异步任务(方案A,仅拆 PDF):POST 秒回 job_id;后台逐单元只拆 PDF + 挂 url,
    失败单元(重试后仍失败)不连累其余、不留半个单元行;轮询进度可见 done/failed + pdf 标记。"""
    import asyncio as _aio
    from unittest.mock import patch
    from sqlalchemy import text as _t

    tb = f"asyncjob版{uuid.uuid4().hex[:6]}"
    grade, sem = "测试年级", "上"

    def _fake_split(fid, start, end):
        if start == 2:
            raise RuntimeError("split boom (unit 2)")   # 仅 Unit 2 拆分失败(重试 3 次都失败)
        return b"%PDF-1.4 fake"

    async def _fake_upload(pdf_bytes, key):
        return f"https://cos.example/{key}"             # 模拟 COS 上传成功

    segs = [{"unit_no": n, "start_page": n, "end_page": n} for n in (1, 2, 3)]
    body = {"textbook_version": tb, "grade": grade, "semester": sem,
            "segments": segs, "content_status": "draft"}
    try:
        with patch("app.services.pdf_upload_service.extract_pages", lambda fid: ["p"] * 5), \
             patch("app.services.pdf_upload_service.get_unit_text", lambda fid, s, e: "unit text"), \
             patch("app.services.pdf_upload_service.split_unit_pdf", _fake_split), \
             patch("app.services.pdf_upload_service.upload_pdf_to_cos", _fake_upload):
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
        results = {x["unit_no"]: x for x in data["results"]}
        assert results[1]["status"] == "ok" and results[1]["pdf"] is True
        assert results[3]["status"] == "ok" and results[3]["pdf"] is True
        assert results[2]["status"] == "error"
        # 仅拆 PDF:不产生考点/词
        assert results[1]["kp_count"] == 0 and results[1]["word_count"] == 0

        # 成功单元已独立 commit 落库(挂上 unit_pdf_url),失败单元不在库
        async with _async_session_factory() as s:
            rows = (await s.execute(_t(
                "SELECT unit_no, unit_pdf_url FROM curriculum_units "
                "WHERE textbook_version=:tb ORDER BY unit_no"), {"tb": tb})).all()
        assert [r[0] for r in rows] == [1, 3]
        assert all(r[1] for r in rows)            # 两个落库单元都挂了 PDF url
    finally:
        async with _async_session_factory() as s:
            await s.execute(_t("DELETE FROM curriculum_units WHERE textbook_version=:tb"), {"tb": tb})
            await s.execute(_t("DELETE FROM curriculum_gen_job WHERE textbook_version=:tb"), {"tb": tb})
            await s.commit()
