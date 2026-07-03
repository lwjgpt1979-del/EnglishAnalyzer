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

import asyncio
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


def _load_private_key_pem() -> str | None:
    """会话存档 RSA 私钥:优先 env WECOM_ARCHIVE_PRIVATE_KEY(PEM),否则 _FILE 指向的文件。"""
    import os
    pem = os.environ.get("WECOM_ARCHIVE_PRIVATE_KEY")
    if pem and "PRIVATE KEY" in pem:
        return pem
    path = os.environ.get("WECOM_ARCHIVE_PRIVATE_KEY_FILE")
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return None


def _to_msg(plain: dict, seq) -> dict:
    """企微会话明文 JSON → 内部消息 dict(供 ingest_messages)。"""
    mt = plain.get("msgtype") or "text"
    text = ""
    if mt == "text":
        text = (plain.get("text") or {}).get("content") or ""
    # 外部联系人 id 以 wm/wo 开头;取 from 或 tolist 里的外部 id
    ext = None
    cand = [plain.get("from")] + list(plain.get("tolist") or [])
    ext = next((c for c in cand if isinstance(c, str) and c[:2] in ("wm", "wo")), None)
    return {"msg_id": plain.get("msgid"), "seq": seq, "from_userid": plain.get("from"),
            "external_userid": ext, "roomid": plain.get("roomid"), "msgtype": mt,
            "content_text": text or None, "msgtime": plain.get("msgtime")}


async def _set_last_seq(db: AsyncSession, seq: int) -> None:
    row = (await db.execute(
        sa.select(SystemConfig).where(SystemConfig.key == _CFG_KEY))).scalar_one_or_none()
    if row is not None and isinstance(row.value, dict):
        row.value = {**row.value, "last_seq": int(seq)}
        await db.flush()


def _pull_real_sync(lib_path: str, corp_id: str, secret: str, private_key_pem: str,
                    seq: int, limit: int) -> tuple[list[dict], int]:
    """ctypes 绑定 libWeWorkFinanceSdk_C:GetChatData → RSA 解随机密钥 → DecryptData → 明文。

    ⚠️ 部署时按你拿到的 .so 版本核对 ABI(尤其 DecryptData 的 encrypt_key 传 base64 还是原始)。
    """
    import base64
    import ctypes
    import json
    lib = ctypes.CDLL(lib_path)
    lib.NewSdk.restype = ctypes.c_void_p
    lib.NewSlice.restype = ctypes.c_void_p
    lib.GetContentFromSlice.restype = ctypes.c_char_p
    lib.GetContentFromSlice.argtypes = [ctypes.c_void_p]
    lib.Init.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
    lib.GetChatData.argtypes = [ctypes.c_void_p, ctypes.c_ulonglong, ctypes.c_uint,
                                ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p]
    lib.DecryptData.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p]
    lib.FreeSlice.argtypes = [ctypes.c_void_p]
    lib.DestroySdk.argtypes = [ctypes.c_void_p]

    sdk = lib.NewSdk()
    try:
        if lib.Init(sdk, corp_id.encode(), secret.encode()) != 0:
            raise RuntimeError("会话存档 Init 失败(检查 corpid/secret)")
        chat_slice = lib.NewSlice()
        try:
            if lib.GetChatData(sdk, seq, limit, b"", b"", 5, chat_slice) != 0:
                raise RuntimeError("GetChatData 失败(检查存档权限/IP 白名单)")
            data = json.loads((lib.GetContentFromSlice(chat_slice) or b"{}").decode())
        finally:
            lib.FreeSlice(chat_slice)
        out, max_seq = [], seq
        for c in (data.get("chatdata") or []):
            random_key = rsa_decrypt_random_key(c["encrypt_random_key"], private_key_pem)
            msg_slice = lib.NewSlice()
            try:
                r = lib.DecryptData(sdk, base64.b64encode(random_key),
                                    c["encrypt_chat_msg"].encode(), msg_slice)
                if r != 0:
                    continue
                plain = json.loads((lib.GetContentFromSlice(msg_slice) or b"{}").decode())
            finally:
                lib.FreeSlice(msg_slice)
            out.append(_to_msg(plain, c.get("seq")))
            max_seq = max(max_seq, int(c.get("seq") or 0))
        return out, max_seq
    finally:
        lib.DestroySdk(sdk)


async def pull_via_sdk(db: AsyncSession, *, limit: int = 1000) -> dict:
    """真·拉取:GetChatData → RSA 解密钥 → 原生 DecryptData → ingest_messages(去重+关联+分析)。

    就绪条件:corp_id(配置)+ env WECOM_ARCHIVE_SECRET + RSA 私钥(env)+ libWeWorkFinanceSdk_C.so(env)。
    未就绪 → 返回 dev-mock 状态(列出缺什么),不"假装拉到"、不污染库。
    """
    import os
    cfg = await get_config(db)
    corp_id = cfg.get("corp_id") or ""
    secret = os.environ.get("WECOM_ARCHIVE_SECRET") or ""
    pkey = _load_private_key_pem()
    lib_path = os.environ.get("WECOM_FINANCE_SDK_LIB") or ""
    missing = [n for n, v in [
        ("corp_id(配置)", corp_id), ("env WECOM_ARCHIVE_SECRET", secret),
        ("env WECOM_ARCHIVE_PRIVATE_KEY(_FILE)", pkey),
        ("env WECOM_FINANCE_SDK_LIB", lib_path and os.path.exists(lib_path))] if not v]
    if missing:
        return {"dev_mock": True, "stored": 0, "linked": 0, "analyzed_leads": 0,
                "missing": missing,
                "note": "会话存档真拉取未就绪;配齐后自动走 GetChatData→解密→ingest。"
                        "联调可先用 /admin/sales/wecom/ingest 喂已解密消息。"}
    seq = int(cfg.get("last_seq") or 0)
    msgs, new_seq = await asyncio.to_thread(_pull_real_sync, lib_path, corp_id, secret, pkey, seq, limit)
    res = await ingest_messages(db, messages=msgs)
    if new_seq and new_seq != seq:
        await _set_last_seq(db, new_seq)
    res["last_seq"] = new_seq
    res["pulled"] = len(msgs)
    return res


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
