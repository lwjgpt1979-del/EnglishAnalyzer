"""企业微信「会话内容存档」接入(P2)。

真·拉取链路(签约 + 腾讯原生 libWeWorkFinanceSdk 后填 pull_via_sdk):
  GetChatData(seq 分页 ≤1000, ≤4000次/分钟) → 每条含 encrypt_random_key + encrypt_chat_msg
  → 用企业 RSA 私钥解出随机密钥(rsa_decrypt_random_key,已实现)→ 原生 SDK DecryptData
  出明文 → ingest_messages 落库 + 关联线索 + 复用意向分析。

合规红线:员工告知页(SDK 强制)+ 外部联系人同意方可取 + 私钥安全存储。
可测部分(RSA 随机密钥解密 / 入库+关联+分析)现在就跑;native SDK 拉取/AES 解密为接入位。
方案见 docs/电销CRM-方案设计.md §5。
"""
from __future__ import annotations

import base64
import logging
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d9_system import SystemConfig
from app.models.d23_sales_crm import SalesLead, WecomChatArchive
from app.services import sales_analysis_service as ana

_log = logging.getLogger(__name__)
_CFG_KEY = "wecom_archive"

DEFAULTS: dict = {
    "enabled": False,          # 是否已接入会话存档
    "corp_id": "",             # 企业 corpid(secret/私钥走 env/密钥管理,不落配置明文)
    "last_seq": 0,             # 拉取游标(GetChatData 分页)
    "analyze_window": 40,      # 关联线索后,取最近 N 条文本做一次意向分析
}


async def get_config(db: AsyncSession) -> dict:
    row = (await db.execute(
        sa.select(SystemConfig).where(SystemConfig.key == _CFG_KEY))).scalar_one_or_none()
    cfg = dict(DEFAULTS)
    if row is not None and isinstance(row.value, dict):
        for k in DEFAULTS:
            if k in row.value:
                cfg[k] = row.value[k]
    return cfg


async def update_config(db: AsyncSession, *, patch: dict, updated_by: uuid.UUID) -> dict:
    clean = {k: v for k, v in (patch or {}).items() if k in DEFAULTS}
    row = (await db.execute(
        sa.select(SystemConfig).where(SystemConfig.key == _CFG_KEY))).scalar_one_or_none()
    merged = dict(DEFAULTS)
    if row is not None and isinstance(row.value, dict):
        merged.update(row.value)
    merged.update(clean)
    if row is None:
        db.add(SystemConfig(id=uuid.uuid4(), key=_CFG_KEY, value=merged,
                            description="企微会话存档接入(开关/corpid/游标)", updated_by=updated_by))
    else:
        row.value = merged
        row.updated_by = updated_by
    await db.flush()
    return {k: merged.get(k, DEFAULTS[k]) for k in DEFAULTS}


# ── 解密(RSA 部分真做;AES/DecryptData 在原生 SDK) ─────────────────────────────

def rsa_decrypt_random_key(encrypt_random_key_b64: str, private_key_pem: str) -> bytes:
    """用企业 RSA 私钥(2048)解出会话随机对称密钥。WeWork:RSA/ECB/PKCS1v1.5。

    解出的密钥再交原生 SDK DecryptData(random_key, encrypt_chat_msg) 出明文。
    """
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    from cryptography.hazmat.primitives.asymmetric import padding
    key = load_pem_private_key(private_key_pem.encode(), password=None)
    return key.decrypt(base64.b64decode(encrypt_random_key_b64), padding.PKCS1v15())


async def pull_via_sdk(db: AsyncSession, *, limit: int = 1000) -> dict:
    """接入位:真·拉取(GetChatData → RSA 解密钥 → 原生 DecryptData → ingest)。

    需:签约会话存档 + 部署 libWeWorkFinanceSdk_C.so(ctypes 绑定)+ corpid/secret/私钥。
    未就绪时明确报错,避免"假装拉到"。就绪后在此拼装 messages 调 ingest_messages。
    """
    raise NotImplementedError(
        "企微会话存档真·拉取未接入:需签约 + 部署 libWeWorkFinanceSdk + 配置 corpid/secret/RSA 私钥。"
        "当前可用 ingest_messages 接入位喂已解密消息(见 /admin/sales/wecom/ingest)。")


# ── 入库 + 关联线索 + 分析 ────────────────────────────────────────────────────

def _to_dt(msgtime) -> datetime | None:
    """企微 msgtime 是毫秒时间戳;也容忍已是 datetime/秒。"""
    if msgtime in (None, ""):
        return None
    if isinstance(msgtime, datetime):
        return msgtime
    try:
        ts = int(msgtime)
        if ts > 10_000_000_000:      # 毫秒
            ts /= 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except (ValueError, TypeError):
        return None


async def ingest_messages(
    db: AsyncSession, *, messages: list[dict], run_analysis: bool = True,
) -> dict:
    """落一批**已解密**消息:按 msg_id 去重,按 external_userid 关联线索(=lead.wechat_id),
    文本消息触发所属线索的会话意向分析。返回 {stored, skipped, linked, analyzed_leads}。"""
    stored = skipped = linked = 0
    # 预取已存在 msg_id + external→lead 映射
    ext_ids = [m.get("external_userid") for m in messages if m.get("external_userid")]
    lead_by_ext: dict[str, uuid.UUID] = {}
    if ext_ids:
        for lid, wx in (await db.execute(sa.select(SalesLead.id, SalesLead.wechat_id)
                                         .where(SalesLead.wechat_id.in_(ext_ids)))).all():
            if wx:
                lead_by_ext[wx] = lid
    msg_ids = [m.get("msg_id") for m in messages if m.get("msg_id")]
    existing: set[str] = set()
    if msg_ids:
        existing = set((await db.execute(
            sa.select(WecomChatArchive.msg_id)
            .where(WecomChatArchive.msg_id.in_(msg_ids)))).scalars().all())

    affected: set[uuid.UUID] = set()
    for m in messages:
        mid = m.get("msg_id")
        if not mid or mid in existing:
            skipped += 1
            continue
        ext = m.get("external_userid")
        lead_id = lead_by_ext.get(ext) if ext else None
        row = WecomChatArchive(
            id=uuid.uuid4(), seq=m.get("seq"), msg_id=mid,
            from_userid=m.get("from_userid"), external_userid=ext, roomid=m.get("roomid"),
            msgtype=m.get("msgtype") or "text", content_text=m.get("content_text"),
            media_url=m.get("media_url"), msgtime=_to_dt(m.get("msgtime")), lead_id=lead_id)
        db.add(row)
        existing.add(mid)
        stored += 1
        if lead_id:
            linked += 1
            if m.get("msgtype", "text") == "text" and (m.get("content_text") or "").strip():
                affected.add(lead_id)
    await db.flush()

    analyzed = 0
    if run_analysis:
        for lead_id in affected:
            try:
                await analyze_lead_conversation(db, lead_id=lead_id)
                analyzed += 1
            except Exception as exc:  # noqa: BLE001
                _log.warning("wecom analyze lead %s failed: %s", lead_id, exc)
    return {"stored": stored, "skipped": skipped, "linked": linked, "analyzed_leads": analyzed}


async def analyze_lead_conversation(db: AsyncSession, *, lead_id: uuid.UUID) -> dict | None:
    """取线索最近 N 条企微文本 → 一次意向分析 → 落最新一条 + 汇总到线索。返回 analysis。"""
    cfg = await get_config(db)
    n = int(cfg["analyze_window"])
    rows = (await db.execute(
        sa.select(WecomChatArchive).where(
            WecomChatArchive.lead_id == lead_id,
            WecomChatArchive.msgtype == "text",
            WecomChatArchive.content_text.isnot(None),
        ).order_by(WecomChatArchive.msgtime.desc().nullslast()).limit(n)
    )).scalars().all()
    if not rows:
        return None
    rows = list(reversed(rows))                       # 时间正序拼成会话
    transcript = "\n".join((r.content_text or "").strip() for r in rows if r.content_text)
    analysis = await ana.analyze_transcript(transcript, source="wechat")
    latest = rows[-1]
    latest.analysis = analysis
    latest.analyzed = True
    await ana._rollup_to_lead(
        db, lead_id=lead_id, score=int(analysis.get("intent_score") or 0), analysis=analysis)
    await db.flush()
    return analysis


async def list_lead_messages(
    db: AsyncSession, *, lead_id: uuid.UUID, skip: int = 0, limit: int = 50,
) -> tuple[list[WecomChatArchive], int]:
    base = sa.select(WecomChatArchive).where(WecomChatArchive.lead_id == lead_id)
    total = (await db.execute(
        sa.select(sa.func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(
        base.order_by(WecomChatArchive.msgtime.desc().nullslast()).offset(skip).limit(limit)
    )).scalars().all()
    return list(rows), total
