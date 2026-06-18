"""curriculum API 端点集成测试（D-079 / M2）。"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.database import _async_session_factory
from app.main import app
from app.services import curriculum_ai_service, curriculum_service


@pytest.fixture(autouse=True)
def force_dev_mode(monkeypatch):
    """强制 dev mock；防止环境里有真 DEEPSEEK_API_KEY 时 _seed_unit 打到真实 API。"""
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-placeholder-for-test")


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as session:
        yield session
        await session.rollback()


async def _login(client: AsyncClient, suffix: str) -> dict:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as mock_wx:
        mock_wx.return_value = {"openid": f"m2_curriculum_{suffix}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def _seed_unit(unit_no: int = 19) -> None:
    """Seed one curriculum unit with its own DB session (committed).

    Uses unit_no in 19..20 to avoid colliding with production seed data
    (which uses 1..8 per semester) while staying within the AIGeneratedUnit
    schema cap (unit_no <= 20). KP codes are tied to (grade_short,
    sem_short, unit_no) so a high unit_no guarantees code uniqueness.
    The API request will open a separate DB session, so commit is needed.
    """
    async with _async_session_factory() as s:
        ai = await curriculum_ai_service.generate_unit(
            textbook_version="译林版", grade="小学5年级", semester="上",
            unit_no=unit_no,
        )
        await curriculum_service.persist_unit(s, ai_unit=ai, content_status="published")
        await s.commit()


async def _seed_user_with_semester(openid: str) -> uuid.UUID:
    """Create a user + grant them a PurchasedSemester for 译林版/小学5年级/上.
    Returns the user_id. Used by tests that need an unlocked unit.

    NB: PurchasedSemester.order_id is NOT NULL FK → we create a paid Order first.
    """
    from datetime import datetime, timezone
    from app.services.auth_service import upsert_user
    from app.models.d2_payments import Order
    async with _async_session_factory() as s:
        user = await upsert_user(s, openid=openid)
        await s.flush()
        order = Order(
            id=uuid.uuid4(),
            order_no=f"TEST-{uuid.uuid4().hex[:8]}",
            payer_id=user.id,
            beneficiary_id=user.id,
            order_type="new",
            tier="pro",
            duration_months=6,
            amount_fen=7900,
            status="paid",
            paid_at=datetime.now(timezone.utc),
            semester_count=1,
        )
        s.add(order)
        await s.flush()
        from app.services.semester_service import create_purchased_semesters
        await create_purchased_semesters(
            s,
            user_id=user.id,
            tier="pro",
            semesters=[{"textbook_version": "译林版", "grade": "小学5年级", "semester": "上"}],
            order_id=order.id,
        )
        await s.commit()
        return user.id


@pytest.mark.asyncio
async def test_list_units_returns_locked_field(client):
    """GET /curriculum/units 必须返回 locked 字段；非购买用户对 unit_no>=19 都 locked=true。
    (unit_no=1 永久免费的逻辑在 test_curriculum_service.py 单测里覆盖。)"""
    await _seed_unit(19)
    await _seed_unit(20)

    h = await _login(client, f"list_{uuid.uuid4().hex[:6]}")
    resp = await client.get(
        "/api/v1/curriculum/units",
        params={"textbook_version": "译林版", "grade": "小学5年级", "semester": "上"},
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 200
    units = body["data"]
    u19 = next(u for u in units if u["unit_no"] == 19)
    u20 = next(u for u in units if u["unit_no"] == 20)
    # 该 test 用户未购学期，u19/u20 都应 locked
    assert u19["locked"] is True
    assert u20["locked"] is True
    assert u19["kp_count"] >= 3


@pytest.mark.asyncio
async def test_get_unit_detail_403_when_locked(client):
    """unit_no=19 详情对无学期用户返回 403。"""
    await _seed_unit(19)

    async with _async_session_factory() as s:
        from sqlalchemy import select
        from app.models.d4_knowledge import CurriculumUnit
        cu = (await s.execute(
            select(CurriculumUnit).where(
                CurriculumUnit.textbook_version == "译林版",
                CurriculumUnit.grade == "小学5年级",
                CurriculumUnit.semester == "上",
                CurriculumUnit.unit_no == 19,
            )
        )).scalar_one()
        unit_id = cu.id

    h = await _login(client, f"detail403_{uuid.uuid4().hex[:6]}")
    resp = await client.get(f"/api/v1/curriculum/units/{unit_id}", headers=h)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_unit_detail_200_for_owned_semester(client):
    """购买了 (译林版,小学5年级,上) 学期的用户访问 unit_no=19 详情应 200，不受 unit_no>1 锁限制。"""
    await _seed_unit(19)

    async with _async_session_factory() as s:
        from sqlalchemy import select
        from app.models.d4_knowledge import CurriculumUnit
        cu = (await s.execute(
            select(CurriculumUnit).where(
                CurriculumUnit.textbook_version == "译林版",
                CurriculumUnit.grade == "小学5年级",
                CurriculumUnit.semester == "上",
                CurriculumUnit.unit_no == 19,
            )
        )).scalar_one()
        unit_id = cu.id

    # 让本测试用户拥有该学期
    suffix = f"d200_{uuid.uuid4().hex[:6]}"
    await _seed_user_with_semester(f"m2_curriculum_{suffix}")

    h = await _login(client, suffix)
    resp = await client.get(f"/api/v1/curriculum/units/{unit_id}", headers=h)
    assert resp.status_code == 200, resp.text
    detail = resp.json()["data"]
    assert detail["unit_no"] == 19
    assert detail["locked"] is False
    assert len(detail["knowledge_points"]) >= 3
    assert len(detail["words"]) >= 5


def _norm(s: str) -> str:
    from app.services.kp_normalize import normalize_kp_name
    return normalize_kp_name(s)


async def _seed_kp_node_with_lectures(*, unit_version, unit_grade, unit_sem, unit_no,
                                      kp_name, dims_published, dims_draft=()):
    """建 单元+旧KP+UnitKP边 + 句法node+alias(kp_name) + node_resource(lecture 各维度)。返回 kp_id。"""
    from sqlalchemy import select as _sel
    from app.models.d4_knowledge import CurriculumUnit, KnowledgePoint, UnitKnowledgePoint
    from app.models.d15_knowledge_graph import KnowledgeNode, NodeAlias
    from app.models.d19_node_resource import NodeResource
    async with _async_session_factory() as s:
        cu = (await s.execute(_sel(CurriculumUnit).where(
            CurriculumUnit.textbook_version == unit_version, CurriculumUnit.grade == unit_grade,
            CurriculumUnit.semester == unit_sem, CurriculumUnit.unit_no == unit_no))).scalar_one_or_none()
        if cu is None:
            cu = CurriculumUnit(id=uuid.uuid4(), textbook_version=unit_version, grade=unit_grade,
                                semester=unit_sem, unit_no=unit_no, unit_title="单元")
            s.add(cu)
            await s.flush()
        kp = KnowledgePoint(id=uuid.uuid4(), code=f"lc-{uuid.uuid4().hex[:6]}", name=kp_name,
                            category="grammar", description="d",
                            applicable_grades=[unit_grade], applicable_textbooks=[unit_version])
        node = KnowledgeNode(id=uuid.uuid4(), axis="knowledge", node_kind="句法", name=kp_name,
                             code=f"lcn-{uuid.uuid4().hex[:6]}", status="active", source="seed")
        s.add_all([kp, node])
        await s.flush()
        s.add(UnitKnowledgePoint(unit_id=cu.id, knowledge_point_id=kp.id))
        s.add(NodeAlias(id=uuid.uuid4(), node_id=node.id, alias=kp_name,
                        alias_norm=_norm(kp_name), source="seed"))
        for d in dims_published:
            s.add(NodeResource(id=uuid.uuid4(), node_id=node.id, resource_type="lecture",
                               dimension=d, content_md=f"published {d}", media_url=f"https://x/{d}.mp3",
                               status="published"))
        for d in dims_draft:
            s.add(NodeResource(id=uuid.uuid4(), node_id=node.id, resource_type="lecture",
                               dimension=d, content_md=f"draft {d}", status="draft"))
        await s.commit()
        return kp.id, node.id


@pytest.mark.asyncio
async def test_get_kp_contents_returns_6_dimensions(client):
    """KP-First 直切:GET contents 读 node_resource(lecture 六维),受 paywall(unit_no=19)。"""
    six = ["listening", "vocabulary", "grammar", "reading", "translation", "writing"]
    kp_id, node_id = await _seed_kp_node_with_lectures(
        unit_version="译林版", unit_grade="小学5年级", unit_sem="上", unit_no=19,
        kp_name=f"直切六维KP_{uuid.uuid4().hex[:6]}", dims_published=six)
    suffix = f"kpcontent_{uuid.uuid4().hex[:6]}"
    await _seed_user_with_semester(f"m2_curriculum_{suffix}")
    h = await _login(client, suffix)
    try:
        resp = await client.get(f"/api/v1/curriculum/knowledge-points/{kp_id}/contents", headers=h)
        assert resp.status_code == 200, resp.text
        contents = resp.json()["data"]
        dims = {c["dimension"] for c in contents}
        assert set(six).issubset(dims)
        for c in contents:
            assert c["content_md"] and "audio_url" in c
    finally:
        async with _async_session_factory() as s:
            from sqlalchemy import text as _t
            await s.execute(_t("DELETE FROM node_resource WHERE node_id = :n"), {"n": str(node_id)})
            await s.execute(_t("DELETE FROM knowledge_node_aliases WHERE node_id = :n"), {"n": str(node_id)})
            await s.execute(_t("DELETE FROM knowledge_nodes WHERE id = :n"), {"n": str(node_id)})
            await s.commit()


@pytest.mark.asyncio
async def test_get_kp_contents_filters_published(client):
    """KP-First 直切:get_kp_contents 只返回 published 的 node_resource lecture(draft 不可见)。"""
    kp_id, node_id = await _seed_kp_node_with_lectures(
        unit_version=f"测试版{uuid.uuid4().hex[:6]}", unit_grade="测试年级", unit_sem="上", unit_no=1,
        kp_name=f"过滤测试KP_{uuid.uuid4().hex[:6]}",
        dims_published=["grammar"], dims_draft=["listening"])
    try:
        async with _async_session_factory() as s:
            contents = await curriculum_service.get_kp_contents(s, user_id=uuid.uuid4(), kp_id=kp_id)
        dims = {c.dimension for c in contents}
        assert dims == {"grammar"}
    finally:
        async with _async_session_factory() as s:
            from sqlalchemy import text as _t
            await s.execute(_t("DELETE FROM node_resource WHERE node_id = :n"), {"n": str(node_id)})
            await s.execute(_t("DELETE FROM knowledge_node_aliases WHERE node_id = :n"), {"n": str(node_id)})
            await s.execute(_t("DELETE FROM knowledge_nodes WHERE id = :n"), {"n": str(node_id)})
            await s.commit()


@pytest.mark.asyncio
async def test_persist_unit_content_defaults_draft(client):
    """persist_unit 不传 content_status 时，内容默认进 draft。"""
    from sqlalchemy import select
    from app.models.d4_knowledge import UnitKnowledgePoint
    from app.models.d11_v2_curriculum import KnowledgePointContent
    # 用 g7（初中7年级）unit_no=11：生产只 seed 过小学5上(g5)，g7 码无人占用；
    # 仅 flush 不 commit，退出上下文自动回滚，不污染库。
    async with _async_session_factory() as s:
        ai = await curriculum_ai_service.generate_unit(
            textbook_version="译林版", grade="初中7年级", semester="上", unit_no=11,
        )
        cu = await curriculum_service.persist_unit(s, ai_unit=ai)  # 默认 draft
        await s.flush()
        rows = (await s.execute(
            select(KnowledgePointContent)
            .join(
                UnitKnowledgePoint,
                UnitKnowledgePoint.knowledge_point_id == KnowledgePointContent.knowledge_point_id,
            )
            .where(UnitKnowledgePoint.unit_id == cu.id)
        )).scalars().all()
        assert rows and all(str(r.status) == "draft" for r in rows)
        await s.rollback()


async def _seed_draft_content() -> tuple[uuid.UUID, uuid.UUID]:
    """建 1 个 KP + 1 条 draft 内容，返回 (kp_id, content_id)。"""
    from app.models.d4_knowledge import KnowledgePoint
    from app.models.d11_v2_curriculum import KnowledgePointContent
    async with _async_session_factory() as s:
        kp = KnowledgePoint(
            id=uuid.uuid4(), code=f"rev-{uuid.uuid4().hex[:6]}", name="审核内容KP",
            category="grammar", description="d",
            applicable_grades=["小学5年级"], applicable_textbooks=["译林版"],
        )
        s.add(kp)
        await s.flush()
        c = KnowledgePointContent(
            id=uuid.uuid4(), knowledge_point_id=kp.id, dimension="grammar",
            content_md="待审草稿正文", status="draft", generated_by="ai_full",
        )
        s.add(c)
        await s.commit()
        return kp.id, c.id


@pytest.mark.asyncio
async def test_list_contents_for_review_filters_status(client):
    kp_id, _ = await _seed_draft_content()
    async with _async_session_factory() as s:
        rows, total = await curriculum_service.list_contents_for_review(
            s, status="draft", kp_id=kp_id,
        )
        assert total == 1 and len(rows) == 1
        rows_pub, total_pub = await curriculum_service.list_contents_for_review(
            s, status="published", kp_id=kp_id,
        )
        assert total_pub == 0 and rows_pub == []


async def _make_reviewer() -> uuid.UUID:
    from app.services.auth_service import upsert_user
    async with _async_session_factory() as s:
        u = await upsert_user(s, openid=f"rev_user_{uuid.uuid4().hex[:6]}")
        await s.commit()
        return u.id


@pytest.mark.asyncio
async def test_review_content_approve_publishes(client):
    _, cid = await _seed_draft_content()
    reviewer = await _make_reviewer()
    async with _async_session_factory() as s:
        c = await curriculum_service.review_content(
            s, content_id=cid, approve=True, reviewer_id=reviewer,
        )
        assert str(c.status) == "published"
        assert c.reviewed_by == reviewer
        assert c.reviewed_at is not None
        await s.rollback()


@pytest.mark.asyncio
async def test_review_content_reject_retires(client):
    _, cid = await _seed_draft_content()
    reviewer = await _make_reviewer()
    async with _async_session_factory() as s:
        c = await curriculum_service.review_content(
            s, content_id=cid, approve=False, reviewer_id=reviewer,
        )
        assert str(c.status) == "retired"
        await s.rollback()


@pytest.mark.asyncio
async def test_update_content_edits_body(client):
    _, cid = await _seed_draft_content()
    async with _async_session_factory() as s:
        c = await curriculum_service.update_content(
            s, content_id=cid, content_md="人工修订后的正文",
        )
        assert c.content_md == "人工修订后的正文"
        assert str(c.generated_by) == "ai_with_human_review"
        await s.rollback()


@pytest.mark.asyncio
async def test_review_content_missing_raises(client):
    from app.core.exceptions import AppError
    async with _async_session_factory() as s:
        with pytest.raises(AppError):
            await curriculum_service.review_content(
                s, content_id=uuid.uuid4(), approve=True, reviewer_id=uuid.uuid4(),
            )
