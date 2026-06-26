"""R10 语法流程不变量测试(由 scripts/audit_grammar_flow 沉淀为 CI 回归)。

dev-mock 下离线确定(tests/services/conftest 已强制 is_llm_dev_mode=True),自建 KP、
不依赖种子数据。覆盖:分级测验收敛/暖启动、四维门槛 gating、confirmed 需复测、
间隔复测回落、推进环新点与维持不重叠(上次审计发现的双重出现回归守卫)。
"""
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.core.database import _async_session_factory
from app.models.d1_users import User
from app.models.d4_knowledge import KnowledgePoint, StudentGrammarMastery
from app.services import (
    grammar_probe_service as gp, grammar_placement_service as pl,
    grammar_path_service as path,
)


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _student(s) -> uuid.UUID:
    from app.services.auth_service import upsert_user
    u = await upsert_user(s, openid=f"gram_{uuid.uuid4().hex[:8]}")
    await s.flush()
    return u.id


async def _make_kps(s, n: int) -> list[str]:
    ids = []
    for i in range(n):
        kp = KnowledgePoint(
            id=uuid.uuid4(), code=f"grtest-{uuid.uuid4().hex[:10]}", name=f"测试语法点{i}",
            category="grammar", description="用于测试的语法点",
            applicable_grades=["八年级"], applicable_textbooks=["译林版"], sort_order=i)
        s.add(kp)
        ids.append(str(kp.id))
    await s.flush()
    return ids


@pytest.mark.asyncio
async def test_placement_converges_and_warm_starts(db_session):
    sid = await _student(db_session)
    kps = await _make_kps(db_session, 8)
    r = await pl.start(db_session, student_id=sid, kp_ids=kps, use_paper_priors=False)
    asked = 0
    while not r.get("done"):
        it = r["item"]
        # dev-mock recognize[0] 正确答案是 "A";随机对错
        pick = "A" if asked % 2 == 0 else "__wrong__"
        r = await pl.answer(db_session, student_id=sid, session_id=uuid.UUID(r["session_id"]),
                            kp_id=it["kp_id"], chosen=pick)
        asked += 1
        assert asked <= 25 + 1, "placement 未在上限内收敛"
    heat = r.get("heatmap") or []
    assert len(heat) == len(kps), "热力图应覆盖整个题库"
    # 暖启动:写入 prior_source=placement 先验,BKT 值合法
    rows = (await db_session.execute(sa.select(StudentGrammarMastery).where(
        StudentGrammarMastery.student_id == sid))).scalars().all()
    assert any(m.prior_source == "placement" for m in rows), "未写入 placement 先验"
    for m in rows:
        if m.mastery_recognize is not None:
            assert 0.0 <= float(m.mastery_recognize) <= 1.0


@pytest.mark.asyncio
async def test_four_axis_gating_and_bkt_bounds(db_session):
    sid = await _student(db_session)
    kid = (await _make_kps(db_session, 1))[0]
    kp = await db_session.get(KnowledgePoint, uuid.UUID(kid))
    out = await gp.comprehension_probes(db_session, student_id=sid, kp=kp)
    # 只答识别/纠错(不碰产出/迁移)→ 永远不能 mastered
    for p in out["probes"]:
        ans = "A" if p["kind"] == "recognize" else "fixA"   # dev-mock 正确答案
        res = await gp.submit_probe(db_session, student_id=sid, kp_id=uuid.UUID(kid),
                                    key=p["key"], answer=ans)
        assert 0.0 <= res["detect"] <= 1.0 and 0.0 <= res["recognize"] <= 1.0
        # 不变量:produce/transfer 未做 → 必不 mastered
        assert not res["mastered"], "缺产出/迁移不应判 mastered"


@pytest.mark.asyncio
async def test_confirmed_requires_retention(db_session):
    sid = await _student(db_session)
    kid = (await _make_kps(db_session, 1))[0]
    m = await gp._get_or_create_mastery(db_session, sid, uuid.UUID(kid))
    m.mastery_detect = 0.9
    m.mastery_produce = 0.9
    m.transfer_ok = True
    gp._maybe_schedule_retention(m)
    await db_session.flush()
    # 四维达成 → 排了复测,但未复测 → 还不算 confirmed
    assert m.mastered_at is not None and m.next_retain_at is not None, "四维达成应排复测"
    assert not gp.confirmed_mastered(m), "未复测不应 confirmed"
    assert gp._status_label(m)["status"] in ("retaining", "due_retain")


@pytest.mark.asyncio
async def test_retention_decay_on_fail(db_session):
    sid = await _student(db_session)
    kid = (await _make_kps(db_session, 1))[0]
    kp = await db_session.get(KnowledgePoint, uuid.UUID(kid))
    await gp.ensure_probes(db_session, kp)
    await gp._ensure_transfer_seed(db_session, kp)
    m = await gp._get_or_create_mastery(db_session, sid, uuid.UUID(kid))
    m.mastery_detect = 0.9
    m.mastery_produce = 0.9
    m.transfer_ok = True
    gp._maybe_schedule_retention(m)
    await db_session.flush()
    res = await gp.submit_retention(db_session, student_id=sid, kp_id=uuid.UUID(kid),
                                    key="transfer:0", answer="__wrong__")
    assert res["verdict"] == "forgotten"
    m2 = await gp._get_mastery(db_session, sid, uuid.UUID(kid))
    assert not m2.transfer_ok and m2.mastered_at is None, "复测失败应回落(transfer 作废、清排期)"


@pytest.mark.asyncio
async def test_daily_batch_no_overlap_new_and_maintain(db_session):
    """回归守卫:四维已达待复测的点只进维持,不再当新点(审计发现的双重出现)。"""
    sid = await _student(db_session)
    kid = (await _make_kps(db_session, 3))[0]
    u = await db_session.get(User, sid)
    u.preferred_textbook_version = "译林版"
    u.preferred_grade = "八年级"
    m = await gp._get_or_create_mastery(db_session, sid, uuid.UUID(kid))
    m.mastery_detect = 0.9
    m.mastery_produce = 0.9
    m.transfer_ok = True
    gp._maybe_schedule_retention(m)
    m.next_retain_at = datetime.now(timezone.utc) - timedelta(days=1)   # 到期
    await db_session.flush()
    b = await path.daily_batch(db_session, student_id=sid)
    in_new = any(n["kp_id"] == kid for n in b["new"])
    in_maint = any(x["kp_id"] == kid for x in b["maintain"])
    assert in_maint and not in_new, "四维已达待复测的点应只在维持、不在新点"
    # 整体不重叠
    new_ids = {n["kp_id"] for n in b["new"]}
    assert not [x for x in b["maintain"] if x["kp_id"] in new_ids], "新点与维持不得重叠"
    assert abs(sum(b["ratios"].values()) - 1.0) < 1e-6
