"""电销 CRM 服务测试(P0 线索闭环 / P1 意向分析 / P2 企微存档 + 打磨)。

固化已上线行为、防回归。LLM 走 dev-mock(tests/services/conftest.py autouse),
意向分析用关键词启发式,离线确定。DB 用 db_session(rollback,不落库)。
"""
from __future__ import annotations

import base64
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.core.database import _async_session_factory
from app.core.exceptions import AppError
from app.models.d1_users import User
from app.models.d23_sales_crm import SalesLead, SalesLeadActivity, WecomChatArchive
from app.services import sales_crm_service as crm
from app.services import sales_analysis_service as ana
from app.services import wecom_archive_service as wa

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _admin(s) -> uuid.UUID:
    uid = uuid.uuid4()
    s.add(User(id=uid, openid=f"o:{uid}", role="platform_admin"))
    await s.flush()
    return uid


def _uniq(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# ── P0 线索闭环 ───────────────────────────────────────────────────────────────

async def test_create_lead_defaults(db_session):
    lead = await crm.create_lead(db_session, data={"name": "甲店", "phone": "13800000001"})
    assert lead.pool == "public" and lead.status == "new"
    assert lead.consent is False and lead.dnc is False


async def test_claim_release_and_anti_grab(db_session):
    a, b = await _admin(db_session), await _admin(db_session)
    lead = await crm.create_lead(db_session, data={"name": "乙店"})
    claimed = await crm.claim_lead(db_session, lead_id=lead.id, admin_id=a)
    assert claimed.pool == "private" and claimed.owner_admin_id == a
    # 防撞单:他人认领应 409
    with pytest.raises(AppError):
        await crm.claim_lead(db_session, lead_id=lead.id, admin_id=b)
    released = await crm.release_lead(db_session, lead_id=lead.id)
    assert released.pool == "public" and released.owner_admin_id is None


async def test_import_dedup_by_phone(db_session):
    ph = "139" + uuid.uuid4().hex[:8]
    await crm.create_lead(db_session, data={"name": "已存在", "phone": ph})
    res = await crm.import_leads(db_session, items=[
        {"name": "重复", "phone": ph}, {"name": "新", "phone": "139" + uuid.uuid4().hex[:8]}])
    assert res == {"created": 1, "skipped": 1}


async def test_activity_advances_status(db_session):
    admin = await _admin(db_session)
    lead = await crm.create_lead(db_session, data={"name": "丙店"})
    act = await crm.add_activity(db_session, lead_id=lead.id, admin_id=admin,
                                 channel="call", outcome="connected")
    assert act.channel == "call"
    fresh = await crm.get_lead(db_session, lead.id)
    assert fresh.status == "contacted" and fresh.last_contacted_at is not None


async def test_recommend_scores_by_won_profile(db_session):
    ind = _uniq("ind")
    won = await crm.create_lead(db_session, data={"name": "赢单", "industry": ind, "region_code": "3204"})
    won.status = "won"
    match = await crm.create_lead(db_session, data={"name": "像赢单", "industry": ind, "region_code": "3204"})
    miss = await crm.create_lead(db_session, data={"name": "不像", "industry": _uniq("other"), "region_code": "1101"})
    await db_session.flush()
    rows, _total = await crm.recommend(db_session, skip=0, limit=500)
    by_id = {r.id: r for r in rows}
    assert by_id[match.id].similar_score > by_id[miss.id].similar_score
    assert by_id[match.id].similar_score > 0


async def test_recycle_public_pool(db_session):
    admin = await _admin(db_session)
    lead = await crm.create_lead(db_session, data={"name": "久未跟"})
    lead.pool = "private"
    lead.owner_admin_id = admin
    lead.claimed_at = datetime.now(timezone.utc) - timedelta(days=30)
    await db_session.flush()
    n = await crm.recycle_public_pool(db_session)
    assert n >= 1
    assert (await crm.get_lead(db_session, lead.id)).pool == "public"


async def test_batch_assign(db_session):
    admin = await _admin(db_session)
    a = await crm.create_lead(db_session, data={"name": "派A"})
    b = await crm.create_lead(db_session, data={"name": "派B"})
    n = await crm.batch_assign(db_session, lead_ids=[a.id, b.id], owner_admin_id=admin)
    assert n == 2
    # 批量 UPDATE 不刷新身份映射,直接读列(避免 ORM 惰性加载)验证已落库
    row = (await db_session.execute(sa.select(SalesLead.owner_admin_id, SalesLead.pool)
                                    .where(SalesLead.id == a.id))).one()
    assert row.owner_admin_id == admin and row.pool == "private"


async def test_merge_leads_moves_activities(db_session):
    admin = await _admin(db_session)
    ph = "139" + uuid.uuid4().hex[:8]
    survivor = await crm.create_lead(db_session, data={"name": "主", "phone": ph})
    dup = await crm.create_lead(db_session, data={"name": "副", "phone": ph, "region_code": "3204",
                                                  "region_name": "江苏省常州市"})
    await crm.add_activity(db_session, lead_id=dup.id, admin_id=admin, channel="note", content="副跟进")
    res = await crm.merge_leads(db_session, survivor_id=survivor.id, dup_ids=[dup.id])
    assert res["merged"] == 1 and res["moved_activities"] == 1
    # 副已删,跟进改挂到主,主补上地区
    assert await db_session.get(SalesLead, dup.id) is None
    fresh = await crm.get_lead(db_session, survivor.id)
    assert fresh.region_code == "3204"
    acts, total = await crm.list_activities(db_session, lead_id=survivor.id)
    assert total == 1


async def test_find_duplicate_groups(db_session):
    ph = "139" + uuid.uuid4().hex[:8]
    await crm.create_lead(db_session, data={"name": "重1", "phone": ph})
    await crm.create_lead(db_session, data={"name": "重2", "phone": ph})
    await db_session.flush()
    groups = await crm.find_duplicate_groups(db_session)
    grp = [g for g in groups if g["phone"] == ph]
    assert grp and len(grp[0]["leads"]) == 2


async def test_source_stats_conversion(db_session):
    src = "tungee"
    a = await crm.create_lead(db_session, data={"name": "源A", "source": src})
    a.status = "won"
    await crm.create_lead(db_session, data={"name": "源B", "source": src})
    await db_session.flush()
    stats = {row["source"]: row for row in await crm.source_stats(db_session)}
    assert src in stats and stats[src]["won"] >= 1 and stats[src]["total"] >= 2


async def test_due_and_sla_filters(db_session):
    admin = await _admin(db_session)
    overdue = await crm.create_lead(db_session, data={"name": "超时"})
    overdue.pool = "private"; overdue.owner_admin_id = admin
    overdue.next_follow_at = datetime.now(timezone.utc) - timedelta(hours=100)
    future = await crm.create_lead(db_session, data={"name": "未来"})
    future.next_follow_at = datetime.now(timezone.utc) + timedelta(days=1)
    await db_session.flush()
    due_rows, _ = await crm.list_leads(db_session, due=True, limit=1000)
    sla_rows, _ = await crm.list_leads(db_session, sla=True, limit=1000)
    due_ids = {r.id for r in due_rows}
    sla_ids = {r.id for r in sla_rows}
    assert overdue.id in due_ids and overdue.id in sla_ids
    assert future.id not in due_ids and future.id not in sla_ids


async def test_seat_scope_hides_others_private(db_session):
    a, b = await _admin(db_session), await _admin(db_session)
    pub = await crm.create_lead(db_session, data={"name": "公海"})
    mine = await crm.create_lead(db_session, data={"name": "我的"})
    await crm.batch_assign(db_session, lead_ids=[mine.id], owner_admin_id=a)
    theirs = await crm.create_lead(db_session, data={"name": "他的"})
    await crm.batch_assign(db_session, lead_ids=[theirs.id], owner_admin_id=b)
    rows, _ = await crm.list_leads(db_session, seat_admin_id=a, limit=1000)
    ids = {r.id for r in rows}
    assert pub.id in ids and mine.id in ids and theirs.id not in ids


async def test_tags_filter(db_session):
    tag = _uniq("tag")
    lead = await crm.create_lead(db_session, data={"name": "带标签", "tags": [tag, "高意向"]})
    await db_session.flush()
    rows, total = await crm.list_leads(db_session, tag=tag, limit=50)
    assert total >= 1 and lead.id in {r.id for r in rows}


async def test_scripts_get_set(db_session):
    admin = await _admin(db_session)
    saved = await crm.set_scripts(db_session, scripts=[
        {"title": "开场", "content": "您好", "stage": "new"},
        {"title": "", "content": "空标题应被过滤"}], updated_by=admin)
    assert len(saved) == 1 and saved[0]["title"] == "开场"
    assert (await crm.get_scripts(db_session))[0]["title"] == "开场"


async def test_export_xlsx_valid(db_session):
    await crm.create_lead(db_session, data={"name": "导出店", "region_code": "3204"})
    await db_session.flush()
    data = await crm.export_leads_xlsx(db_session)
    assert len(data) > 500 and data[:2] == b"PK"   # xlsx = zip(PK)


async def test_board_stats_shape(db_session):
    admin = await _admin(db_session)
    lead = await crm.create_lead(db_session, data={"name": "看板"})
    lead.pool = "private"; lead.owner_admin_id = admin
    lead.next_follow_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await crm.add_activity(db_session, lead_id=lead.id, admin_id=admin, channel="call", outcome="connected")
    await db_session.flush()
    b = await crm.board_stats(db_session, admin_id=admin)
    for k in ("total", "today_new", "today_calls", "today_connected",
              "connect_rate", "my_due", "sla_breach"):
        assert k in b
    assert b["today_calls"] >= 1 and b["my_due"] >= 1


async def test_seat_scope_for_config(db_session):
    admin = await _admin(db_session)
    assert await crm.seat_scope_for(db_session, admin) is None      # 默认非座席
    await crm.update_config(db_session, patch={"seat_only_admin_ids": [str(admin)]}, updated_by=admin)
    assert await crm.seat_scope_for(db_session, admin) == admin     # 名单内 → 座席


# ── P1 意向分析 ───────────────────────────────────────────────────────────────

async def test_analyze_transcript_devmock(db_session):
    a = await ana.analyze_transcript("你们课程多少钱?怎么合作?", source="call")
    assert isinstance(a["intent_score"], int)
    assert a["signals"]["asked_price"] is True
    assert a["signals"]["asked_next_step"] is True


async def test_grade_from_score():
    th = {"A": 80, "B": 60, "C": 40}
    assert ana.grade_from_score(90, th) == "A"
    assert ana.grade_from_score(65, th) == "B"
    assert ana.grade_from_score(45, th) == "C"
    assert ana.grade_from_score(10, th) == "D"


async def test_analyze_activity_rollup(db_session):
    admin = await _admin(db_session)
    lead = await crm.create_lead(db_session, data={"name": "分析店"})
    act = await crm.add_activity(db_session, lead_id=lead.id, admin_id=admin, channel="call")
    act.asr_text = "价格多少?能支持中考冲刺吗?"
    await db_session.flush()
    updated = await ana.analyze_activity(db_session, activity_id=act.id)
    assert updated.analysis is not None and isinstance(updated.intent_score, int)
    fresh = await crm.get_lead(db_session, lead.id)
    assert fresh.intent_score is not None and fresh.intent_grade in ("A", "B", "C", "D")


async def test_ingest_call_record(db_session):
    admin = await _admin(db_session)
    lead = await crm.create_lead(db_session, data={"name": "呼入店"})
    act = await ana.ingest_call_record(
        db_session, lead_id=lead.id, admin_id=admin, recording_url="cos://r.mp3",
        asr_text="多少钱?", call_duration_sec=60, outcome="connected")
    assert act.recording_url == "cos://r.mp3" and act.intent_score is not None
    assert (await crm.get_lead(db_session, lead.id)).status == "contacted"


# ── P2 企微会话存档 ───────────────────────────────────────────────────────────

async def test_rsa_decrypt_random_key_roundtrip():
    from cryptography.hazmat.primitives.asymmetric import rsa, padding
    from cryptography.hazmat.primitives import serialization
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM,
                            serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    sample = b"0123456789abcdef0123456789abcdef"
    enc = base64.b64encode(key.public_key().encrypt(sample, padding.PKCS1v15())).decode()
    assert wa.rsa_decrypt_random_key(enc, pem) == sample


async def test_wecom_ingest_link_dedup_analyze(db_session):
    ext = _uniq("ext")
    lead = await crm.create_lead(db_session, data={"name": "企微店", "wechat_id": ext})
    msgs = [
        {"msg_id": _uniq("m"), "external_userid": ext, "msgtype": "text",
         "content_text": "你们多少钱?能支持中考冲刺吗?", "msgtime": 1782980000000},
        {"msg_id": _uniq("m"), "external_userid": ext, "msgtype": "text",
         "content_text": "想要机构版,怎么合作?", "msgtime": 1782980060000},
    ]
    dup = dict(msgs[0])                       # 同 msg_id 重复
    res = await wa.ingest_messages(db_session, messages=msgs + [dup])
    assert res["stored"] == 2 and res["skipped"] == 1 and res["linked"] == 2
    assert res["analyzed_leads"] == 1
    fresh = await crm.get_lead(db_session, lead.id)
    assert fresh.intent_score is not None
    rows, total = await wa.list_lead_messages(db_session, lead_id=lead.id)
    assert total == 2


async def test_wecom_ingest_unknown_contact_not_linked(db_session):
    res = await wa.ingest_messages(db_session, messages=[
        {"msg_id": _uniq("m"), "external_userid": _uniq("nobody"), "msgtype": "text",
         "content_text": "无主消息"}])
    assert res["stored"] == 1 and res["linked"] == 0


async def test_wecom_config_update(db_session):
    admin = await _admin(db_session)
    assert (await wa.get_config(db_session))["enabled"] is False
    await wa.update_config(db_session, patch={"enabled": True, "corp_id": "wwabc"}, updated_by=admin)
    cfg = await wa.get_config(db_session)
    assert cfg["enabled"] is True and cfg["corp_id"] == "wwabc"
