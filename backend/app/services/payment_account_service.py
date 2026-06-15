"""收款主体路由 + 凭证装载（渠道无关）。

- resolve_for_order：按学生归属城市 → 分公司 → 该分公司收款主体；无则回退默认主体。
- load_credentials：非密 config 来自 DB；密钥按 secret_alias 从 env 读取（永不入库）。
- 密钥 env 命名：PAY__<ALIAS>__<KEY>，<KEY> 由各渠道适配器 required_secret_keys() 声明。
"""
from __future__ import annotations

import datetime as dt
import os
import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.d1_users import User
from app.models.d10_branch import BranchCompanyCity, PaymentAccount
from app.services.payment.base import Creds

# 兼容旧单商户：该 alias 缺 env 时回退到现有 WECHAT_PAY_* settings
LEGACY_ALIAS = "legacy_wechat"


def _env(alias: str | None, key: str) -> str | None:
    if not alias:
        return None
    return os.environ.get(f"PAY__{alias}__{key}")


async def get_default(db: AsyncSession) -> PaymentAccount | None:
    return await db.scalar(
        select(PaymentAccount).where(
            and_(PaymentAccount.is_default.is_(True),
                 PaymentAccount.is_active.is_(True))
        )
    )


async def get(db: AsyncSession, account_id: uuid.UUID) -> PaymentAccount | None:
    return await db.get(PaymentAccount, account_id)


async def _branch_account(db: AsyncSession, city_code: str) -> PaymentAccount | None:
    """城市 → 有效期内分公司 → 该分公司 active 收款主体。"""
    today = dt.date.today()
    branch_id = await db.scalar(
        select(BranchCompanyCity.branch_company_id).where(and_(
            BranchCompanyCity.city_code == city_code,
            BranchCompanyCity.effective_from <= today,
            or_(BranchCompanyCity.effective_to.is_(None),
                BranchCompanyCity.effective_to >= today),
        )).limit(1)
    )
    if branch_id is None:
        return None
    return await db.scalar(
        select(PaymentAccount).where(and_(
            PaymentAccount.branch_company_id == branch_id,
            PaymentAccount.is_active.is_(True),
        )).limit(1)
    )


async def resolve_for_order(db: AsyncSession, beneficiary: User) -> PaymentAccount | None:
    """选择该订单的收款主体：城市归属分公司主体 → 默认主体。"""
    if beneficiary is not None and beneficiary.city_code:
        acc = await _branch_account(db, beneficiary.city_code)
        if acc is not None:
            return acc
    return await get_default(db)


async def branch_company_id_for(db: AsyncSession, beneficiary: User) -> uuid.UUID | None:
    """结算归属分公司（按城市），与收款主体解析独立，下单一并固化。"""
    if beneficiary is None or not beneficiary.city_code:
        return None
    today = dt.date.today()
    return await db.scalar(
        select(BranchCompanyCity.branch_company_id).where(and_(
            BranchCompanyCity.city_code == beneficiary.city_code,
            BranchCompanyCity.effective_from <= today,
            or_(BranchCompanyCity.effective_to.is_(None),
                BranchCompanyCity.effective_to >= today),
        )).limit(1)
    )


def load_credentials(account: PaymentAccount | None) -> Creds:
    """装载某收款主体的运行时凭证。非密来自 config，密钥来自 env by alias。

    account 为空（无任何主体配置）→ 回退全局 settings 的微信单商户（兼容现状）。
    """
    if account is None:
        # 完全没配主体：回退现有单商户 settings
        pem = settings.wechat_pay_private_key_pem
        return Creds(
            provider="wechat",
            is_dev=pem.startswith("placeholder"),
            app_id=settings.wechat_appid,
            mch_id=settings.wechat_pay_mch_id,
            cert_serial=settings.wechat_pay_cert_serial,
            private_key_pem=pem,
            api_key_v3=settings.wechat_pay_api_key_v3,
            notify_url=settings.wechat_pay_notify_url,
        )

    cfg = account.config or {}
    alias = account.secret_alias

    if account.provider == "wechat":
        pem = _env(alias, "WECHAT_PRIVATE_KEY_PEM")
        api_key = _env(alias, "WECHAT_API_KEY_V3")
        # legacy 主体：env 缺失时回退现有 settings，保持当前 dev 行为不变
        if alias == LEGACY_ALIAS:
            pem = pem or settings.wechat_pay_private_key_pem
            api_key = api_key or settings.wechat_pay_api_key_v3
        is_dev = (not pem) or pem.startswith("placeholder")
        return Creds(
            provider="wechat", is_dev=is_dev,
            app_id=cfg.get("app_id") or settings.wechat_appid,
            mch_id=cfg.get("mch_id"),
            cert_serial=cfg.get("cert_serial"),
            private_key_pem=pem,
            api_key_v3=api_key,
            notify_url=cfg.get("notify_url") or settings.wechat_pay_notify_url,
            extra=cfg,
        )

    # 其他渠道（支付宝/苹果…）：密钥就绪则非 dev，否则 dev-mock
    from app.services.payment.base import required_secret_keys
    keys = required_secret_keys(account.provider)
    ready = all(_env(alias, k) for k in keys) if keys else False
    return Creds(provider=account.provider, is_dev=not ready, extra=cfg)


def credentials_ready(account: PaymentAccount) -> bool:
    """后台探测：该主体所需密钥是否已在 env 就绪（不返回密钥值）。"""
    creds = load_credentials(account)
    return not creds.is_dev


async def resolve_creds_for_order(db: AsyncSession, order) -> Creds:
    """退款/支付时：按订单固化的收款主体取凭证；无则回退默认/全局。"""
    acc = None
    if getattr(order, "payment_account_id", None):
        acc = await get(db, order.payment_account_id)
    if acc is None:
        acc = await get_default(db)
    return load_credentials(acc)


# ───────────────────── 后台管理（不涉密） ─────────────────────

def _to_item(acc: PaymentAccount) -> dict:
    """转后台展示项：含密钥就绪布尔，绝不返回密钥本身。"""
    from app.services.payment.base import required_secret_keys
    return {
        "id": acc.id,
        "name": acc.name,
        "subject_type": acc.subject_type,
        "provider": acc.provider,
        "config": acc.config or {},
        "secret_alias": acc.secret_alias,
        "branch_company_id": acc.branch_company_id,
        "is_default": acc.is_default,
        "is_active": acc.is_active,
        "credentials_ready": credentials_ready(acc),
        "required_secret_keys": required_secret_keys(acc.provider),
        "created_at": acc.created_at.isoformat() if acc.created_at else None,
    }


async def admin_list(db: AsyncSession) -> list[dict]:
    rows = (await db.execute(
        select(PaymentAccount).order_by(
            PaymentAccount.is_default.desc(), PaymentAccount.created_at.asc())
    )).scalars().all()
    return [_to_item(a) for a in rows]


async def admin_create(db: AsyncSession, *, name: str, subject_type: str,
                       provider: str, config: dict | None, secret_alias: str | None,
                       branch_company_id: uuid.UUID | None,
                       is_active: bool = True) -> PaymentAccount:
    acc = PaymentAccount(
        id=uuid.uuid4(), name=name, subject_type=subject_type, provider=provider,
        config=config or {}, secret_alias=secret_alias,
        branch_company_id=branch_company_id, is_active=is_active, is_default=False,
    )
    db.add(acc)
    await db.flush()
    return acc


async def admin_update(db: AsyncSession, account_id: uuid.UUID, *,
                       fields: dict) -> PaymentAccount:
    acc = await db.get(PaymentAccount, account_id)
    if acc is None:
        raise AppError(code=404, message="收款主体不存在")
    allowed = {"name", "subject_type", "provider", "config", "secret_alias",
               "branch_company_id", "is_active"}
    for k, v in fields.items():
        if k in allowed and v is not None:
            setattr(acc, k, v)
    await db.flush()
    return acc


async def set_default(db: AsyncSession, account_id: uuid.UUID) -> PaymentAccount:
    """设为默认收款主体（先清空其余 default，避免部分唯一索引冲突）。"""
    acc = await db.get(PaymentAccount, account_id)
    if acc is None:
        raise AppError(code=404, message="收款主体不存在")
    if not acc.is_active:
        raise AppError(code=400, message="停用的主体不能设为默认")
    from sqlalchemy import update
    await db.execute(
        update(PaymentAccount).where(PaymentAccount.is_default.is_(True))
        .values(is_default=False))
    await db.flush()
    acc.is_default = True
    await db.flush()
    return acc


async def toggle_active(db: AsyncSession, account_id: uuid.UUID) -> PaymentAccount:
    acc = await db.get(PaymentAccount, account_id)
    if acc is None:
        raise AppError(code=404, message="收款主体不存在")
    if acc.is_default and acc.is_active:
        raise AppError(code=400, message="默认主体不能停用，请先切换默认")
    acc.is_active = not acc.is_active
    await db.flush()
    return acc
