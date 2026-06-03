"""作文 AI 精修 service 测试（D-109）。"""
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.core.exceptions import AppError
from app.models.d2_payments import Membership
from app.services import essay_service


@pytest.fixture(autouse=True)
def _force_llm_dev_mock(monkeypatch):
    """强制 dev-mock，绝不真打付费 LLM（无论 .env 是否配真实 key）。"""
    monkeypatch.setattr(essay_service, "is_llm_dev_mode", lambda: True)


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _student(s, tier: str | None) -> uuid.UUID:
    from app.services.auth_service import upsert_user
    u = await upsert_user(s, openid=f"essay_{uuid.uuid4().hex[:8]}")
    await s.flush()
    if tier:
        s.add(Membership(id=uuid.uuid4(), user_id=u.id, tier=tier,
                         started_at=datetime.now(timezone.utc), is_active=True))
        await s.flush()
    return u.id


@pytest.mark.asyncio
async def test_polish_pro_devmock(db_session):
    sid = await _student(db_session, "pro")
    essay = await essay_service.polish_essay(
        db_session, student_id=sid, original_text="I am very good at English.", essay_type="话题作文")
    assert str(essay.status) == "completed"
    assert essay.polished_text
    assert len(essay.dimensions["scores"]) == 4
    assert "total" in essay.dimensions
    assert isinstance(essay.dimensions["issues"], list)


@pytest.mark.asyncio
async def test_polish_free_forbidden(db_session):
    sid = await _student(db_session, None)  # 无会员 = free
    with pytest.raises(AppError):
        await essay_service.polish_essay(db_session, student_id=sid, original_text="hello")


@pytest.mark.asyncio
async def test_pro_monthly_limit(db_session):
    sid = await _student(db_session, "pro")
    for _ in range(3):
        await essay_service.polish_essay(db_session, student_id=sid, original_text="essay text")
    with pytest.raises(AppError):
        await essay_service.polish_essay(db_session, student_id=sid, original_text="essay text 4")


@pytest.mark.asyncio
async def test_promax_unlimited(db_session):
    sid = await _student(db_session, "promax")
    for _ in range(5):
        e = await essay_service.polish_essay(db_session, student_id=sid, original_text="essay text")
    assert str(e.status) == "completed"


# ─── D-110: 多轮迭代 + 模板 ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_repolish_promax(db_session):
    sid = await _student(db_session, "promax")
    e1 = await essay_service.polish_essay(db_session, student_id=sid, original_text="round1 text", essay_type="话题作文")
    e2 = await essay_service.repolish_essay(db_session, student_id=sid, essay_id=e1.id, revised_text="round2 better text")
    assert e2.round_count == 2
    assert len(e2.dimensions["rounds"]) == 2
    assert e2.dimensions["total"] == e2.dimensions["rounds"][-1]["total"]


@pytest.mark.asyncio
async def test_repolish_pro_forbidden(db_session):
    sid = await _student(db_session, "pro")
    e1 = await essay_service.polish_essay(db_session, student_id=sid, original_text="text")
    with pytest.raises(AppError):
        await essay_service.repolish_essay(db_session, student_id=sid, essay_id=e1.id, revised_text="v2")


@pytest.mark.asyncio
async def test_repolish_max_rounds(db_session):
    from sqlalchemy.orm.attributes import flag_modified
    sid = await _student(db_session, "promax")
    e1 = await essay_service.polish_essay(db_session, student_id=sid, original_text="text", essay_type="话题作文")
    e1.dimensions = {**e1.dimensions, "rounds": [
        {"text": "t", "scores": [], "total": 80, "issues": [], "polished_text": "p"} for _ in range(5)]}
    flag_modified(e1, "dimensions")
    e1.round_count = 5
    await db_session.flush()
    with pytest.raises(AppError):
        await essay_service.repolish_essay(db_session, student_id=sid, essay_id=e1.id, revised_text="v6")


def test_get_templates():
    t = essay_service.get_templates("书信作文")
    assert ("Dear" in t["template"]) or ("称呼" in t["template"])
    assert len(t["samples"]) >= 3
    d = essay_service.get_templates(None)
    assert d["template"] and len(d["samples"]) >= 3


# ─── D-111: 配置化模板 + 进步聚合 ────────────────────────────────────

@pytest.mark.asyncio
async def test_configured_templates_fallback(db_session):
    t = await essay_service.get_configured_templates(db_session, "话题作文")
    assert t["template"] and len(t["samples"]) >= 1


@pytest.mark.asyncio
async def test_configured_templates_hit(db_session):
    from app.models.d9_system import SystemConfig
    sid = await _student(db_session, None)  # updated_by 需非空
    db_session.add(SystemConfig(
        id=uuid.uuid4(), key="essay_templates", updated_by=sid,
        value={"话题作文": {"template": "自定义模板X", "samples": ["s1"]}, "_default": {"template": "兜底", "samples": ["d"]}},
    ))
    await db_session.flush()
    t = await essay_service.get_configured_templates(db_session, "话题作文")
    assert t["template"] == "自定义模板X"
    t2 = await essay_service.get_configured_templates(db_session, "不存在题型")
    assert t2["template"] == "兜底"


@pytest.mark.asyncio
async def test_get_progress(db_session):
    sid = await _student(db_session, "promax")
    for _ in range(3):
        await essay_service.polish_essay(db_session, student_id=sid, original_text="text", essay_type="话题作文")
    p = await essay_service.get_progress(db_session, student_id=sid)
    assert p["total_essays"] == 3
    assert p["avg_total"] == 88.0
    assert len(p["trend"]) == 3
    assert len(p["dimension_avg"]) == 4 and p["dimension_avg"][0]["avg"] == 22.0


@pytest.mark.asyncio
async def test_get_progress_empty(db_session):
    sid = await _student(db_session, "pro")
    p = await essay_service.get_progress(db_session, student_id=sid)
    assert p["total_essays"] == 0 and p["avg_total"] == 0 and p["trend"] == []
