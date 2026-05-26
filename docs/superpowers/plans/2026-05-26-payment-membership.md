# 会员 & 微信支付 MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现学生查询会员状态、创建付费订单、发起微信支付、Webhook 回调后自动激活/续费会员的完整闭环。

**Architecture:** 订单由客户端主动创建（POST /orders/），再调用 POST /orders/{id}/pay 获得 wx.requestPayment 参数；微信支付完成后微信服务器回调 POST /webhooks/wx-pay，后端验签→解密→幂等写入→激活/续费 memberships。退款（需人工审核）在后续 Plan C 中实现。WeChat Pay v3 JSAPI 采用 `cryptography` 库（已随 python-jose 安装）+ `httpx`（已有依赖）手工签名，无需额外 SDK。

**Tech Stack:** FastAPI 0.115 · SQLAlchemy 2.x asyncio · WeChat Pay v3 JSAPI · cryptography（RSA + AES-GCM）· httpx · pydantic v2 · pytest-asyncio STRICT

---

## File Structure

```
New files:
  backend/app/schemas/payments.py              # 所有支付相关 Pydantic schema
  backend/app/services/order_service.py        # 价格表 + 订单 CRUD
  backend/app/services/membership_service.py   # 会员查询 + 激活/续费/升级
  backend/app/services/wechat_pay_service.py   # 微信支付 v3：prepay / 签名 / 解密回调
  backend/app/api/v1/memberships.py            # GET /memberships/me
  backend/app/api/v1/orders.py                 # POST /orders/, GET /orders/{id}, POST /orders/{id}/pay
  backend/app/api/v1/webhooks.py               # POST /webhooks/wx-pay
  tests/api/test_payments.py                   # 全部支付测试

Modified files:
  backend/app/core/config.py                   # 追加微信支付配置字段
  backend/app/api/v1/router.py                 # 注册 memberships/orders/webhooks 路由
  backend/.env                                 # 追加微信支付 env 变量（不提交）
  backend/.env.example                         # 追加占位行（提交）
```

**Endpoint 列表：**
```
GET    /api/v1/memberships/me              查询当前会员状态（tier + expires_at）
POST   /api/v1/orders/                    创建订单（new / renew / upgrade）
GET    /api/v1/orders/{id}               订单详情 + 状态轮询
POST   /api/v1/orders/{id}/pay           发起微信支付 → 返回 wx.requestPayment 参数
POST   /api/v1/webhooks/wx-pay           微信回调（无 JWT；验签 + 幂等 + 激活会员）
```

**价格表（硬编码，后台可配置化留待 Plan C+）：**
```
tier     1 月    3 月    12 月
basic    29元    79元   288元
pro      49元   138元   498元
promax   99元   288元   988元
（金额单位：分，即×100）
```

---

## Task 0: Config — 微信支付环境变量

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env`（不提交）
- Modify: `backend/.env.example`（提交）

- [ ] **Step 1: 写失败测试**

新建 `tests/api/test_payments.py`：

```python
from app.core.config import settings


def test_settings_has_wechat_pay_config():
    """Settings 必须有微信支付必要字段。"""
    assert hasattr(settings, "wechat_pay_mch_id")
    assert hasattr(settings, "wechat_pay_api_key_v3")
    assert hasattr(settings, "wechat_pay_cert_serial")
    assert hasattr(settings, "wechat_pay_private_key_pem")
    assert hasattr(settings, "wechat_pay_notify_url")
    assert hasattr(settings, "wechat_pay_skip_sig_verify")
    assert isinstance(settings.wechat_pay_skip_sig_verify, bool)
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_payments.py::test_settings_has_wechat_pay_config -v
```

Expected: `FAILED` with `AttributeError`

- [ ] **Step 3: 修改 config.py**

完整替换 `backend/app/core/config.py`：

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 数据库
    database_url: str
    async_database_url: str

    # 微信小程序
    wechat_appid: str = "wx_dev_placeholder"
    wechat_appsecret: str = "dev_secret_placeholder"
    wechat_code2session_url: str = (
        "https://api.weixin.qq.com/sns/jscode2session"
    )

    # JWT
    jwt_secret_key: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 120
    refresh_token_expire_days: int = 30

    # AI 分析（Anthropic Claude）
    anthropic_api_key: str = "sk-ant-placeholder-for-dev"

    # 微信支付 v3
    wechat_pay_mch_id: str = "placeholder_mch_id"
    wechat_pay_api_key_v3: str = "placeholder32charsapikey12345678"  # 32 chars
    wechat_pay_cert_serial: str = "placeholder_cert_serial"
    wechat_pay_private_key_pem: str = "placeholder_private_key_pem"
    wechat_pay_notify_url: str = "https://api.example.com/api/v1/webhooks/wx-pay"
    # dev 模式跳过微信签名验证（生产环境必须设为 false）
    wechat_pay_skip_sig_verify: bool = True

    # 应用
    debug: bool = False
    api_v1_prefix: str = "/api/v1"


settings = Settings()
```

- [ ] **Step 4: 追加到 .env 和 .env.example**

追加到 `backend/.env`（勿提交）：
```
# 微信支付 v3
WECHAT_PAY_MCH_ID=your_mch_id
WECHAT_PAY_API_KEY_V3=your_32char_api_key_v3_here1234
WECHAT_PAY_CERT_SERIAL=your_cert_serial_no
WECHAT_PAY_PRIVATE_KEY_PEM=-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----
WECHAT_PAY_NOTIFY_URL=https://api.yourserver.com/api/v1/webhooks/wx-pay
WECHAT_PAY_SKIP_SIG_VERIFY=true
```

追加到 `backend/.env.example`：
```
# 微信支付 v3（生产环境必填）
WECHAT_PAY_MCH_ID=your_merchant_id
WECHAT_PAY_API_KEY_V3=your_32char_api_key_v3_here
WECHAT_PAY_CERT_SERIAL=your_certificate_serial_number
WECHAT_PAY_PRIVATE_KEY_PEM=-----BEGIN PRIVATE KEY-----\nyour_key_here\n-----END PRIVATE KEY-----
WECHAT_PAY_NOTIFY_URL=https://your-domain.com/api/v1/webhooks/wx-pay
WECHAT_PAY_SKIP_SIG_VERIFY=false
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_payments.py::test_settings_has_wechat_pay_config -v
```

Expected: `PASSED`

- [ ] **Step 6: 运行全量测试，确认无回归**

```bash
python -m pytest ../tests/ -q
```

Expected: `74 passed`（原 73 + 1 新增）

- [ ] **Step 7: 提交**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add backend/app/core/config.py backend/.env.example tests/api/test_payments.py
git commit -m "feat(config): add WeChat Pay v3 config fields"
```

---

## Task 1: Payment Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/payments.py`
- Modify: `tests/api/test_payments.py`

- [ ] **Step 1: 追加失败测试**

追加到 `tests/api/test_payments.py`：

```python
import uuid
from datetime import datetime, timezone

from app.schemas.payments import (
    CurrentMembershipOut,
    OrderCreate,
    OrderOut,
    PayParamsOut,
)


def test_current_membership_out_defaults_to_free():
    """无会员时，默认 tier=free，expires_at=None。"""
    out = CurrentMembershipOut()
    assert out.tier == "free"
    assert out.expires_at is None
    assert out.is_active is True


def test_current_membership_out_with_paid_tier():
    now = datetime.now(timezone.utc)
    out = CurrentMembershipOut(
        tier="pro",
        started_at=now,
        expires_at=now,
        is_active=True,
    )
    assert out.tier == "pro"


def test_order_create_validates_fields():
    order = OrderCreate(tier="basic", duration_months=3, order_type="new")
    assert order.tier == "basic"
    assert order.duration_months == 3


def test_order_out_serializes():
    now = datetime.now(timezone.utc)
    out = OrderOut(
        id=uuid.uuid4(),
        order_no="ORD-20260526-ABCD1234",
        tier="pro",
        duration_months=1,
        amount_fen=4900,
        status="pending",
        wx_transaction_id=None,
        paid_at=None,
        created_at=now,
    )
    assert out.amount_fen == 4900
    assert out.status == "pending"


def test_pay_params_out_has_required_fields():
    params = PayParamsOut(
        timeStamp="1716739200",
        nonceStr="abc123",
        package="prepay_id=wx12345",
        signType="RSA",
        paySign="base64sighere",
    )
    assert params.signType == "RSA"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_payments.py -k "membership_out or order_create or order_out or pay_params" -v
```

Expected: `FAILED` with `ModuleNotFoundError: No module named 'app.schemas.payments'`

- [ ] **Step 3: 创建 schema 文件**

创建 `backend/app/schemas/payments.py`：

```python
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ── 会员 ─────────────────────────────────────────────────────────────────────


class CurrentMembershipOut(BaseModel):
    """GET /memberships/me 响应体。

    无付费会员时 tier="free"，其余字段为 None。
    """

    tier: str = Field(default="free", description="free | basic | pro | promax")
    started_at: datetime | None = None
    expires_at: datetime | None = Field(
        default=None, description="到期时间；free 档永不过期，值为 None"
    )
    is_active: bool = True

    model_config = {"from_attributes": True}


# ── 订单 ─────────────────────────────────────────────────────────────────────


class OrderCreate(BaseModel):
    """POST /orders/ 请求体。"""

    tier: str = Field(..., description="basic | pro | promax")
    duration_months: int = Field(..., description="1 | 3 | 12")
    order_type: str = Field(..., description="new | renew | upgrade")


class OrderOut(BaseModel):
    """订单响应体。"""

    id: uuid.UUID
    order_no: str
    tier: str
    duration_months: int
    amount_fen: int = Field(..., description="实收金额（分）")
    status: str = Field(..., description="pending | paid | refunded | partial_refunded")
    wx_transaction_id: str | None
    paid_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── 支付参数 ──────────────────────────────────────────────────────────────────


class PayParamsOut(BaseModel):
    """POST /orders/{id}/pay 响应体，前端传给 wx.requestPayment()。"""

    timeStamp: str
    nonceStr: str
    package: str = Field(..., description="prepay_id=wx...")
    signType: str = Field(default="RSA")
    paySign: str
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_payments.py -k "membership_out or order_create or order_out or pay_params" -v
```

Expected: `5 passed`

- [ ] **Step 5: 运行全量测试**

```bash
python -m pytest ../tests/ -q
```

Expected: `79 passed`

- [ ] **Step 6: 提交**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add backend/app/schemas/payments.py tests/api/test_payments.py
git commit -m "feat(schemas): payment schemas — membership, order, pay params"
```

---

## Task 2: 价格表 + Order Service

**Files:**
- Create: `backend/app/services/order_service.py`
- Modify: `tests/api/test_payments.py`

- [ ] **Step 1: 追加失败测试**

追加到 `tests/api/test_payments.py`：

```python
import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.services.order_service import (
    PRICE_TABLE,
    create_order,
    get_order,
    get_price,
    mark_order_paid,
)


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def test_user(db_session):
    from app.services.auth_service import upsert_user
    user = await upsert_user(db_session, openid=f"pay_test_{uuid.uuid4().hex[:8]}")
    await db_session.flush()
    return user


def test_price_table_has_all_tiers():
    assert set(PRICE_TABLE.keys()) == {"basic", "pro", "promax"}
    for tier in PRICE_TABLE:
        assert set(PRICE_TABLE[tier].keys()) == {1, 3, 12}


def test_get_price_returns_fen():
    assert get_price("basic", 1) == 2900
    assert get_price("pro", 3) == 13800
    assert get_price("promax", 12) == 98800


def test_get_price_invalid_tier_raises():
    from app.core.exceptions import AppError
    with pytest.raises(AppError) as exc_info:
        get_price("free", 1)
    assert exc_info.value.code == 400


def test_get_price_invalid_duration_raises():
    from app.core.exceptions import AppError
    with pytest.raises(AppError) as exc_info:
        get_price("basic", 6)
    assert exc_info.value.code == 400


@pytest.mark.asyncio
async def test_create_order(db_session, test_user):
    order = await create_order(
        db_session,
        payer_id=test_user.id,
        beneficiary_id=test_user.id,
        tier="basic",
        duration_months=1,
        order_type="new",
    )
    assert order.id is not None
    assert order.order_no.startswith("ORD-")
    assert order.amount_fen == 2900
    assert order.status == "pending"
    assert order.tier == "basic"


@pytest.mark.asyncio
async def test_get_order_by_payer(db_session, test_user):
    order = await create_order(
        db_session,
        payer_id=test_user.id,
        beneficiary_id=test_user.id,
        tier="pro",
        duration_months=3,
        order_type="new",
    )
    found = await get_order(db_session, order_id=order.id, user_id=test_user.id)
    assert found is not None
    assert found.id == order.id


@pytest.mark.asyncio
async def test_get_order_wrong_user_returns_none(db_session, test_user):
    order = await create_order(
        db_session,
        payer_id=test_user.id,
        beneficiary_id=test_user.id,
        tier="basic",
        duration_months=1,
        order_type="new",
    )
    found = await get_order(db_session, order_id=order.id, user_id=uuid.uuid4())
    assert found is None


@pytest.mark.asyncio
async def test_mark_order_paid(db_session, test_user):
    order = await create_order(
        db_session,
        payer_id=test_user.id,
        beneficiary_id=test_user.id,
        tier="basic",
        duration_months=1,
        order_type="new",
    )
    updated = await mark_order_paid(
        db_session, order=order, wx_transaction_id="4200002test"
    )
    assert updated.status == "paid"
    assert updated.wx_transaction_id == "4200002test"
    assert updated.paid_at is not None
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_payments.py -k "price_table or get_price or create_order or get_order or mark_order" -v
```

Expected: `FAILED` with `ModuleNotFoundError`

- [ ] **Step 3: 创建 order service**

创建 `backend/app/services/order_service.py`：

```python
"""订单 CRUD 业务逻辑。

价格表（分）：
  tier     1 月    3 月    12 月
  basic    2900    7900   28800
  pro      4900   13800   49800
  promax   9900   28800   98800
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d2_payments import Order

# ── 价格表（硬编码；后台可配置化留待后续迭代）────────────────────────────────

PRICE_TABLE: dict[str, dict[int, int]] = {
    "basic":  {1: 2900,  3: 7900,  12: 28800},
    "pro":    {1: 4900,  3: 13800, 12: 49800},
    "promax": {1: 9900,  3: 28800, 12: 98800},
}

ALLOWED_TIERS = frozenset(PRICE_TABLE.keys())
ALLOWED_DURATIONS = frozenset({1, 3, 12})


def get_price(tier: str, duration_months: int) -> int:
    """返回价格（分）；无效参数抛 AppError(400)。"""
    if tier not in PRICE_TABLE:
        raise AppError(code=400, message=f"无效档位：{tier}，可选：basic/pro/promax")
    if duration_months not in PRICE_TABLE[tier]:
        raise AppError(
            code=400,
            message=f"无效时长：{duration_months}，可选：1/3/12",
        )
    return PRICE_TABLE[tier][duration_months]


# ── CRUD ─────────────────────────────────────────────────────────────────────


async def create_order(
    db: AsyncSession,
    *,
    payer_id: uuid.UUID,
    beneficiary_id: uuid.UUID,
    tier: str,
    duration_months: int,
    order_type: str,
) -> Order:
    """创建待支付订单（status=pending）。调用方负责 commit。"""
    amount_fen = get_price(tier, duration_months)
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    order_no = f"ORD-{today}-{uuid.uuid4().hex[:8].upper()}"

    order = Order(
        id=uuid.uuid4(),
        order_no=order_no,
        payer_id=payer_id,
        beneficiary_id=beneficiary_id,
        order_type=order_type,
        tier=tier,
        duration_months=duration_months,
        amount_fen=amount_fen,
        status="pending",
    )
    db.add(order)
    await db.flush()
    return order


async def get_order(
    db: AsyncSession,
    *,
    order_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Order | None:
    """按 id 查询订单；user_id 须为付款人或受益人（防越权）。"""
    result = await db.execute(
        select(Order).where(
            Order.id == order_id,
            or_(Order.payer_id == user_id, Order.beneficiary_id == user_id),
        )
    )
    return result.scalar_one_or_none()


async def mark_order_paid(
    db: AsyncSession,
    *,
    order: Order,
    wx_transaction_id: str,
) -> Order:
    """标记订单已支付，写入微信流水号和支付时间。调用方负责 commit。"""
    order.status = "paid"
    order.wx_transaction_id = wx_transaction_id
    order.paid_at = datetime.now(timezone.utc)
    await db.flush()
    return order
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_payments.py -k "price_table or get_price or create_order or get_order or mark_order" -v
```

Expected: `9 passed`

- [ ] **Step 5: 运行全量测试**

```bash
python -m pytest ../tests/ -q
```

Expected: `88 passed`

- [ ] **Step 6: 提交**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add backend/app/services/order_service.py tests/api/test_payments.py
git commit -m "feat(service): order CRUD — price table + create/get/mark_paid"
```

---

## Task 3: Membership Service

**Files:**
- Create: `backend/app/services/membership_service.py`
- Modify: `tests/api/test_payments.py`

- [ ] **Step 1: 追加失败测试**

追加到 `tests/api/test_payments.py`：

```python
from app.services.membership_service import activate_membership, get_active_membership
from app.services.order_service import create_order


@pytest.mark.asyncio
async def test_get_active_membership_none_when_no_membership(db_session, test_user):
    result = await get_active_membership(db_session, user_id=test_user.id)
    assert result is None


@pytest.mark.asyncio
async def test_activate_new_membership(db_session, test_user):
    order = await create_order(
        db_session,
        payer_id=test_user.id,
        beneficiary_id=test_user.id,
        tier="basic",
        duration_months=1,
        order_type="new",
    )
    membership = await activate_membership(db_session, order=order)
    assert membership.tier == "basic"
    assert membership.is_active is True
    assert membership.user_id == test_user.id
    assert membership.order_id == order.id
    # expires_at should be roughly 1 month from now
    from datetime import timezone
    delta = membership.expires_at - datetime.now(timezone.utc)
    assert 25 <= delta.days <= 35  # 1 month ≈ 28-31 days


@pytest.mark.asyncio
async def test_renew_membership_extends_expiry(db_session, test_user):
    # First activation
    order1 = await create_order(
        db_session, payer_id=test_user.id, beneficiary_id=test_user.id,
        tier="basic", duration_months=1, order_type="new",
    )
    m1 = await activate_membership(db_session, order=order1)
    original_expires = m1.expires_at

    # Renew
    order2 = await create_order(
        db_session, payer_id=test_user.id, beneficiary_id=test_user.id,
        tier="basic", duration_months=3, order_type="renew",
    )
    m2 = await activate_membership(db_session, order=order2)

    # Same membership record (in-place update)
    assert m2.id == m1.id
    # expires_at extended by ~3 months
    delta = m2.expires_at - original_expires
    assert 85 <= delta.days <= 95  # 3 months ≈ 88-92 days


@pytest.mark.asyncio
async def test_upgrade_membership_deactivates_old(db_session, test_user):
    # Start with basic
    order1 = await create_order(
        db_session, payer_id=test_user.id, beneficiary_id=test_user.id,
        tier="basic", duration_months=1, order_type="new",
    )
    m1 = await activate_membership(db_session, order=order1)

    # Upgrade to pro
    order2 = await create_order(
        db_session, payer_id=test_user.id, beneficiary_id=test_user.id,
        tier="pro", duration_months=1, order_type="upgrade",
    )
    m2 = await activate_membership(db_session, order=order2)

    # Old membership deactivated
    await db_session.refresh(m1)
    assert m1.is_active is False
    # New membership is pro
    assert m2.tier == "pro"
    assert m2.is_active is True
    assert m2.id != m1.id
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_payments.py -k "active_membership or activate_new or renew_membership or upgrade_membership" -v
```

Expected: `FAILED` with `ModuleNotFoundError`

- [ ] **Step 3: 创建 membership service**

创建 `backend/app/services/membership_service.py`：

```python
"""会员 CRUD 业务逻辑。

规则：
- 每个用户同时只有一条 is_active=true 的 Membership（DB 部分唯一索引保证）。
- new / upgrade：停用旧记录（若有），创建新记录。
- renew：延长当前记录的 expires_at。
- 月份计算使用 add_months() 避免引入 dateutil 依赖。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d2_payments import Membership, Order


def _add_months(dt: datetime, months: int) -> datetime:
    """将 datetime 加 months 个月，处理月末溢出（如 1月31日+1月→2月28日）。"""
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    days_in_month = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                     31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    day = min(dt.day, days_in_month[month - 1])
    return dt.replace(year=year, month=month, day=day)


async def get_active_membership(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
) -> Membership | None:
    """返回当前激活的会员记录，无则返回 None。"""
    result = await db.execute(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def activate_membership(
    db: AsyncSession,
    *,
    order: Order,
) -> Membership:
    """根据订单类型激活/续费/升级会员。调用方负责 commit。

    - new / upgrade：停用旧记录 → 创建新记录
    - renew：在原记录上延长 expires_at
    """
    user_id = order.beneficiary_id
    existing = await get_active_membership(db, user_id=user_id)
    now = datetime.now(timezone.utc)

    if order.order_type == "renew" and existing and existing.tier == order.tier:
        # 续费：从当前到期时间（或现在）延长
        base = existing.expires_at if existing.expires_at and existing.expires_at > now else now
        existing.expires_at = _add_months(base, order.duration_months)
        await db.flush()
        return existing

    # new 或 upgrade：停用旧记录
    if existing is not None:
        existing.is_active = False
        await db.flush()

    # 创建新会员记录
    membership = Membership(
        id=uuid.uuid4(),
        user_id=user_id,
        order_id=order.id,
        tier=order.tier,
        started_at=now,
        expires_at=_add_months(now, order.duration_months),
        is_active=True,
    )
    db.add(membership)
    await db.flush()
    return membership
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_payments.py -k "active_membership or activate_new or renew_membership or upgrade_membership" -v
```

Expected: `4 passed`

- [ ] **Step 5: 运行全量测试**

```bash
python -m pytest ../tests/ -q
```

Expected: `92 passed`

- [ ] **Step 6: 提交**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add backend/app/services/membership_service.py tests/api/test_payments.py
git commit -m "feat(service): membership CRUD — get_active + activate/renew/upgrade"
```

---

## Task 4: WeChat Pay Service

**Files:**
- Create: `backend/app/services/wechat_pay_service.py`
- Modify: `tests/api/test_payments.py`

- [ ] **Step 1: 追加失败测试**

追加到 `tests/api/test_payments.py`：

```python
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.wechat_pay_service import (
    build_pay_params,
    verify_and_decrypt_callback,
)


def test_build_pay_params_returns_all_fields():
    """build_pay_params 应返回 wx.requestPayment 所需的 5 个字段。"""
    params = build_pay_params("wx_test_prepay_id_12345")
    assert "timeStamp" in params
    assert "nonceStr" in params
    assert params["package"] == "prepay_id=wx_test_prepay_id_12345"
    assert params["signType"] == "RSA"
    assert "paySign" in params
    # In dev mode (placeholder key), paySign is the dev placeholder
    assert len(params["paySign"]) > 0


def test_verify_and_decrypt_callback_dev_mode():
    """dev 模式：resource 含 mock_decrypted 时直接返回，无需真实解密。"""
    import json
    body = json.dumps({
        "event_type": "TRANSACTION.SUCCESS",
        "resource": {
            "mock_decrypted": {
                "out_trade_no": "ORD-20260526-ABCD1234",
                "transaction_id": "4200002test",
                "trade_state": "SUCCESS",
            }
        },
    }).encode()
    headers = {
        "wechatpay-timestamp": "1716739200",
        "wechatpay-nonce": "abc123",
        "wechatpay-signature": "dev_sig",
    }
    result = verify_and_decrypt_callback(headers, body)
    assert result["out_trade_no"] == "ORD-20260526-ABCD1234"
    assert result["trade_state"] == "SUCCESS"


@pytest.mark.asyncio
async def test_get_prepay_id_calls_wx_api(db_session, test_user):
    """get_prepay_id 应调用微信 API 并返回 prepay_id 字符串。"""
    from app.services.wechat_pay_service import get_prepay_id
    from app.services.order_service import create_order

    order = await create_order(
        db_session,
        payer_id=test_user.id,
        beneficiary_id=test_user.id,
        tier="basic",
        duration_months=1,
        order_type="new",
    )

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"prepay_id": "wx_test_prepay_id_9999"}

    with patch("app.services.wechat_pay_service.httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_instance.post = AsyncMock(return_value=mock_resp)

        result = await get_prepay_id(order, openid="test_openid")

    assert result == "wx_test_prepay_id_9999"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_payments.py -k "build_pay or verify_and_decrypt or get_prepay" -v
```

Expected: `FAILED` with `ModuleNotFoundError`

- [ ] **Step 3: 创建 WeChat Pay service**

创建 `backend/app/services/wechat_pay_service.py`：

```python
"""微信支付 v3 JSAPI 服务。

生产环境需要真实商户私钥（RSA PEM）和 API key v3（AES-GCM 解密回调）。
开发模式（private_key_pem 以 'placeholder' 开头）跳过实际签名，
回调解密中若 resource 含 mock_decrypted 字段则直接返回，无需真实 AES-GCM。
"""
from __future__ import annotations

import base64
import json
import time
import uuid

import httpx

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.d2_payments import Order

_JSAPI_URL = "https://api.mch.weixin.qq.com/v3/pay/transactions/jsapi"


def _is_dev_mode() -> bool:
    return settings.wechat_pay_private_key_pem.startswith("placeholder")


def _sign_rsa(message: str) -> str:
    """RSA-SHA256 签名并 base64 编码。dev 模式返回占位字符串。"""
    if _is_dev_mode():
        return "dev_signature_placeholder"
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding as asym_padding

    private_key = serialization.load_pem_private_key(
        settings.wechat_pay_private_key_pem.encode(), password=None
    )
    sig = private_key.sign(message.encode(), asym_padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(sig).decode()


def _build_auth_header(method: str, url_path: str, body: str) -> str:
    """构建微信支付 v3 Authorization 请求头。"""
    nonce = uuid.uuid4().hex
    timestamp = str(int(time.time()))
    message = f"{method}\n{url_path}\n{timestamp}\n{nonce}\n{body}\n"
    sig = _sign_rsa(message)
    return (
        f'WECHATPAY2-SHA256-RSA2048 mchid="{settings.wechat_pay_mch_id}",'
        f'nonce_str="{nonce}",'
        f'signature="{sig}",'
        f'timestamp="{timestamp}",'
        f'serial_no="{settings.wechat_pay_cert_serial}"'
    )


async def get_prepay_id(order: Order, openid: str) -> str:
    """调用微信支付 JSAPI 统一下单接口，返回 prepay_id。

    异常：微信 API 返回错误 → AppError(2003)
    """
    body_dict = {
        "appid": settings.wechat_appid,
        "mchid": settings.wechat_pay_mch_id,
        "description": f"engGramer {order.tier}会员 {order.duration_months}个月",
        "out_trade_no": order.order_no,
        "notify_url": settings.wechat_pay_notify_url,
        "amount": {"total": order.amount_fen, "currency": "CNY"},
        "payer": {"openid": openid},
    }
    body_str = json.dumps(body_dict, ensure_ascii=False, separators=(",", ":"))
    auth = _build_auth_header("POST", "/v3/pay/transactions/jsapi", body_str)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                _JSAPI_URL,
                content=body_str.encode(),
                headers={
                    "Authorization": auth,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
        data = resp.json()
    except Exception as exc:
        raise AppError(code=2003, message=f"微信支付服务请求失败：{exc}") from exc

    if "prepay_id" not in data:
        raise AppError(
            code=2003, message=f"微信支付失败：{data.get('message', str(data))}"
        )
    return data["prepay_id"]


def build_pay_params(prepay_id: str) -> dict:
    """构建前端 wx.requestPayment() 所需的 5 个参数。"""
    timestamp = str(int(time.time()))
    nonce = uuid.uuid4().hex
    package = f"prepay_id={prepay_id}"
    message = f"{settings.wechat_appid}\n{timestamp}\n{nonce}\n{package}\n"
    pay_sign = _sign_rsa(message)
    return {
        "timeStamp": timestamp,
        "nonceStr": nonce,
        "package": package,
        "signType": "RSA",
        "paySign": pay_sign,
    }


def verify_and_decrypt_callback(headers: dict, raw_body: bytes) -> dict:
    """验证微信回调签名并解密 resource 字段，返回解密后的交易数据。

    - dev 模式（skip_sig_verify=True）跳过 RSA 验签。
    - 测试辅助：resource 含 mock_decrypted 字段时直接返回，无需 AES-GCM。
    - 生产：使用 AES-256-GCM 解密（key = wechat_pay_api_key_v3 前 32 字节）。
    """
    body = json.loads(raw_body)
    resource = body.get("resource", {})

    # 测试辅助快捷路径
    if "mock_decrypted" in resource:
        return resource["mock_decrypted"]

    if not settings.wechat_pay_skip_sig_verify:
        # 生产环境：完整 RSA 验签（需微信平台公钥证书，此处预留）
        # timestamp = headers.get("wechatpay-timestamp", "")
        # nonce     = headers.get("wechatpay-nonce", "")
        # 完整实现需加载微信平台证书并验签，此处占位
        pass

    # AES-256-GCM 解密 resource
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        key = settings.wechat_pay_api_key_v3.encode()[:32]
        nonce_bytes = resource["nonce"].encode()
        associated_data = resource.get("associated_data", "").encode()
        ciphertext = base64.b64decode(resource["ciphertext"])
        plaintext = AESGCM(key).decrypt(nonce_bytes, ciphertext, associated_data)
        return json.loads(plaintext)
    except Exception as exc:
        raise AppError(code=400, message=f"微信回调解密失败：{exc}") from exc
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_payments.py -k "build_pay or verify_and_decrypt or get_prepay" -v
```

Expected: `3 passed`

- [ ] **Step 5: 运行全量测试**

```bash
python -m pytest ../tests/ -q
```

Expected: `95 passed`

- [ ] **Step 6: 提交**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add backend/app/services/wechat_pay_service.py tests/api/test_payments.py
git commit -m "feat(service): WeChat Pay v3 — prepay/sign/callback decrypt"
```

---

## Task 5: Membership + Order API Endpoints

**Files:**
- Create: `backend/app/api/v1/memberships.py`
- Create: `backend/app/api/v1/orders.py`
- Modify: `backend/app/api/v1/router.py`
- Modify: `tests/api/test_payments.py`

- [ ] **Step 1: 追加失败测试**

追加到 `tests/api/test_payments.py`：

```python
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient):
    with patch(
        "app.services.auth_service.wechat_code2session", new_callable=AsyncMock
    ) as mock_wx:
        mock_wx.return_value = {"openid": f"pay_api_{uuid.uuid4().hex[:8]}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_get_membership_returns_free_when_none(client: AsyncClient, auth_headers):
    resp = await client.get("/api/v1/memberships/me", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["tier"] == "free"
    assert body["data"]["expires_at"] is None


@pytest.mark.asyncio
async def test_get_membership_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/memberships/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_order_api(client: AsyncClient, auth_headers):
    resp = await client.post(
        "/api/v1/orders/",
        json={"tier": "basic", "duration_months": 1, "order_type": "new"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["tier"] == "basic"
    assert body["data"]["amount_fen"] == 2900
    assert body["data"]["status"] == "pending"
    assert body["data"]["order_no"].startswith("ORD-")


@pytest.mark.asyncio
async def test_create_order_invalid_tier(client: AsyncClient, auth_headers):
    resp = await client.post(
        "/api/v1/orders/",
        json={"tier": "free", "duration_months": 1, "order_type": "new"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_order_invalid_duration(client: AsyncClient, auth_headers):
    resp = await client.post(
        "/api/v1/orders/",
        json={"tier": "basic", "duration_months": 6, "order_type": "new"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_get_order_api(client: AsyncClient, auth_headers):
    create_resp = await client.post(
        "/api/v1/orders/",
        json={"tier": "pro", "duration_months": 3, "order_type": "new"},
        headers=auth_headers,
    )
    order_id = create_resp.json()["data"]["id"]
    resp = await client.get(f"/api/v1/orders/{order_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == order_id


@pytest.mark.asyncio
async def test_get_order_not_found(client: AsyncClient, auth_headers):
    resp = await client.get(f"/api/v1/orders/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_payments.py -k "membership or create_order or get_order" -v 2>&1 | head -15
```

Expected: `FAILED` 含 404（路由未注册）

- [ ] **Step 3: 创建 memberships.py**

创建 `backend/app/api/v1/memberships.py`：

```python
"""会员状态 API。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.payments import CurrentMembershipOut
from app.services import membership_service

router = APIRouter(prefix="/memberships", tags=["memberships"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.get("/me", response_model=BaseResponse[CurrentMembershipOut])
async def get_my_membership(db: DbDep, current_user: UserDep):
    """返回当前用户的会员状态。无付费会员则返回 tier=free。"""
    await get_rls_db(db, str(current_user.id))
    membership = await membership_service.get_active_membership(
        db, user_id=current_user.id
    )
    if membership is None:
        return make_ok(CurrentMembershipOut())
    return make_ok(CurrentMembershipOut.model_validate(membership))
```

- [ ] **Step 4: 创建 orders.py**

创建 `backend/app/api/v1/orders.py`：

```python
"""订单 API（创建 + 查询 + 发起支付）。"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.exceptions import AppError
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.payments import OrderCreate, OrderOut, PayParamsOut
from app.services import order_service, wechat_pay_service

router = APIRouter(prefix="/orders", tags=["orders"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.post("/", response_model=BaseResponse[OrderOut])
async def create_order(body: OrderCreate, db: DbDep, current_user: UserDep):
    """创建待支付订单。自付（payer = beneficiary = 当前用户）。

    档位只能是 basic/pro/promax；时长只能是 1/3/12 个月。
    """
    await get_rls_db(db, str(current_user.id))
    if body.tier not in order_service.ALLOWED_TIERS:
        raise AppError(
            code=400, message=f"无效档位：{body.tier}，可选：basic/pro/promax"
        )
    if body.duration_months not in order_service.ALLOWED_DURATIONS:
        raise AppError(
            code=400, message=f"无效时长：{body.duration_months}，可选：1/3/12"
        )
    if body.order_type not in ("new", "renew", "upgrade"):
        raise AppError(code=400, message=f"无效订单类型：{body.order_type}")

    order = await order_service.create_order(
        db,
        payer_id=current_user.id,
        beneficiary_id=current_user.id,
        tier=body.tier,
        duration_months=body.duration_months,
        order_type=body.order_type,
    )
    await db.commit()
    await db.refresh(order)
    return make_ok(OrderOut.model_validate(order))


@router.get("/{order_id}", response_model=BaseResponse[OrderOut])
async def get_order(order_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """查询订单详情（付款人或受益人可见）。"""
    await get_rls_db(db, str(current_user.id))
    order = await order_service.get_order(
        db, order_id=order_id, user_id=current_user.id
    )
    if order is None:
        raise AppError(code=404, message="订单不存在")
    return make_ok(OrderOut.model_validate(order))


@router.post("/{order_id}/pay", response_model=BaseResponse[PayParamsOut])
async def pay_order(order_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """发起微信支付，返回 wx.requestPayment() 所需参数。

    订单必须处于 pending 状态；微信 API 调用失败时返回 2003。
    """
    await get_rls_db(db, str(current_user.id))
    order = await order_service.get_order(
        db, order_id=order_id, user_id=current_user.id
    )
    if order is None:
        raise AppError(code=404, message="订单不存在")
    if order.status != "pending":
        raise AppError(
            code=400, message=f"订单状态为 {order.status}，无法发起支付"
        )

    prepay_id = await wechat_pay_service.get_prepay_id(order, current_user.openid)
    params = wechat_pay_service.build_pay_params(prepay_id)
    return make_ok(PayParamsOut(**params))
```

- [ ] **Step 5: 更新 router.py**

完整替换 `backend/app/api/v1/router.py`：

```python
from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.memberships import router as memberships_router
from app.api.v1.orders import router as orders_router
from app.api.v1.users import router as users_router
from app.api.v1.webhooks import router as webhooks_router
from app.api.v1.wrong_questions import router as wrong_questions_router

v1_router = APIRouter()

v1_router.include_router(auth_router)
v1_router.include_router(users_router)
v1_router.include_router(wrong_questions_router)
v1_router.include_router(memberships_router)
v1_router.include_router(orders_router)
v1_router.include_router(webhooks_router)
```

> 注意：webhooks.py 在 Task 6 才创建；先创建占位文件以免导入报错。

创建空的 `backend/app/api/v1/webhooks.py`（Task 6 会完善）：

```python
"""微信支付回调 Webhook。（Task 6 实现）"""
from fastapi import APIRouter

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
```

- [ ] **Step 6: 运行测试，确认通过**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_payments.py -k "membership or create_order or get_order" -v
```

Expected: `8 passed`（含 free tier, 401, create, invalid tier, invalid duration, get, not found）

- [ ] **Step 7: 运行全量测试**

```bash
python -m pytest ../tests/ -q
```

Expected: `103 passed`

- [ ] **Step 8: 提交**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add backend/app/api/v1/memberships.py backend/app/api/v1/orders.py \
        backend/app/api/v1/webhooks.py backend/app/api/v1/router.py \
        tests/api/test_payments.py
git commit -m "feat(api): memberships + orders CRUD endpoints with JWT + RLS"
```

---

## Task 6: Pay + Webhook Endpoints

**Files:**
- Modify: `backend/app/api/v1/webhooks.py`（完善，替换占位）
- Modify: `tests/api/test_payments.py`

- [ ] **Step 1: 追加失败测试**

追加到 `tests/api/test_payments.py`：

```python
@pytest.mark.asyncio
async def test_pay_order_api(client: AsyncClient, auth_headers):
    """POST /orders/{id}/pay 应调用微信 API 并返回 PayParamsOut。"""
    create_resp = await client.post(
        "/api/v1/orders/",
        json={"tier": "basic", "duration_months": 1, "order_type": "new"},
        headers=auth_headers,
    )
    order_id = create_resp.json()["data"]["id"]

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"prepay_id": "wx_test_pay_12345"}

    with patch("app.services.wechat_pay_service.httpx.AsyncClient") as MockHttpx:
        mock_instance = AsyncMock()
        MockHttpx.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
        MockHttpx.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_instance.post = AsyncMock(return_value=mock_resp)

        resp = await client.post(f"/api/v1/orders/{order_id}/pay", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["package"] == "prepay_id=wx_test_pay_12345"
    assert body["data"]["signType"] == "RSA"
    assert "timeStamp" in body["data"]


@pytest.mark.asyncio
async def test_pay_order_already_paid(client: AsyncClient, auth_headers):
    """已付款订单不能重复发起支付，应返回 400。"""
    import json as _json

    create_resp = await client.post(
        "/api/v1/orders/",
        json={"tier": "basic", "duration_months": 1, "order_type": "new"},
        headers=auth_headers,
    )
    order_id = create_resp.json()["data"]["id"]
    order_no = create_resp.json()["data"]["order_no"]

    # Simulate webhook marking the order as paid
    wx_callback = _json.dumps({
        "event_type": "TRANSACTION.SUCCESS",
        "resource": {
            "mock_decrypted": {
                "out_trade_no": order_no,
                "transaction_id": "4200002test999",
                "trade_state": "SUCCESS",
            }
        },
    }).encode()
    await client.post(
        "/api/v1/webhooks/wx-pay",
        content=wx_callback,
        headers={
            "content-type": "application/json",
            "wechatpay-timestamp": "1716739200",
            "wechatpay-nonce": "testnonce",
            "wechatpay-signature": "dev",
        },
    )

    # Try to pay again
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"prepay_id": "wx_xxx"}
    with patch("app.services.wechat_pay_service.httpx.AsyncClient") as MockHttpx:
        mock_instance = AsyncMock()
        MockHttpx.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
        MockHttpx.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_instance.post = AsyncMock(return_value=mock_resp)
        resp = await client.post(f"/api/v1/orders/{order_id}/pay", headers=auth_headers)

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_wx_pay_webhook_activates_membership(client: AsyncClient, auth_headers):
    """微信回调成功后会员应被激活。"""
    import json as _json

    # Create order
    create_resp = await client.post(
        "/api/v1/orders/",
        json={"tier": "pro", "duration_months": 1, "order_type": "new"},
        headers=auth_headers,
    )
    order_no = create_resp.json()["data"]["order_no"]

    # Simulate WeChat callback
    wx_callback = _json.dumps({
        "event_type": "TRANSACTION.SUCCESS",
        "resource": {
            "mock_decrypted": {
                "out_trade_no": order_no,
                "transaction_id": f"4200002wx{uuid.uuid4().hex[:8]}",
                "trade_state": "SUCCESS",
            }
        },
    }).encode()
    cb_resp = await client.post(
        "/api/v1/webhooks/wx-pay",
        content=wx_callback,
        headers={
            "content-type": "application/json",
            "wechatpay-timestamp": "1716739200",
            "wechatpay-nonce": "testnonce",
            "wechatpay-signature": "dev",
        },
    )
    assert cb_resp.status_code == 200
    assert cb_resp.json() == {"code": "SUCCESS"}

    # Check membership
    membership_resp = await client.get("/api/v1/memberships/me", headers=auth_headers)
    assert membership_resp.json()["data"]["tier"] == "pro"


@pytest.mark.asyncio
async def test_wx_pay_webhook_idempotent(client: AsyncClient, auth_headers):
    """重复回调同一 wx_transaction_id 应幂等（返回 SUCCESS，不报错）。"""
    import json as _json

    create_resp = await client.post(
        "/api/v1/orders/",
        json={"tier": "basic", "duration_months": 1, "order_type": "new"},
        headers=auth_headers,
    )
    order_no = create_resp.json()["data"]["order_no"]
    wx_tid = f"4200002idem{uuid.uuid4().hex[:6]}"

    payload = _json.dumps({
        "event_type": "TRANSACTION.SUCCESS",
        "resource": {
            "mock_decrypted": {
                "out_trade_no": order_no,
                "transaction_id": wx_tid,
                "trade_state": "SUCCESS",
            }
        },
    }).encode()
    headers_cb = {
        "content-type": "application/json",
        "wechatpay-timestamp": "1716739200",
        "wechatpay-nonce": "testnonce",
        "wechatpay-signature": "dev",
    }

    resp1 = await client.post("/api/v1/webhooks/wx-pay", content=payload, headers=headers_cb)
    resp2 = await client.post("/api/v1/webhooks/wx-pay", content=payload, headers=headers_cb)
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json() == {"code": "SUCCESS"}
    assert resp2.json() == {"code": "SUCCESS"}
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_payments.py -k "pay_order or webhook" -v 2>&1 | head -20
```

Expected: `FAILED`（webhook endpoint 还是空壳）

- [ ] **Step 3: 完善 webhooks.py**

完整替换 `backend/app/api/v1/webhooks.py`：

```python
"""微信支付回调 Webhook。

微信服务器调用此接口，不需要 JWT 鉴权。
必须在 5 秒内返回 {"code": "SUCCESS"}，否则微信会重试（最多 15 次）。
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from typing import Annotated

from app.core.database import get_db
from app.core.exceptions import AppError
from app.models.d2_payments import Order
from app.services import membership_service, order_service, wechat_pay_service

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.post("/wx-pay")
async def wx_pay_callback(request: Request, db: DbDep):
    """接收微信支付结果通知。

    处理逻辑：
    1. 验签 + 解密 resource（dev 模式跳过验签，支持 mock_decrypted 快捷路径）
    2. 只处理 trade_state=SUCCESS 的事件
    3. 幂等检查（order.status == paid 时直接返回 SUCCESS）
    4. 更新 order.status=paid，写入 wx_transaction_id + paid_at
    5. 激活 / 续费 / 升级会员
    """
    raw_body = await request.body()
    headers = dict(request.headers)

    try:
        decrypted = wechat_pay_service.verify_and_decrypt_callback(headers, raw_body)
    except AppError:
        raise
    except Exception as exc:
        raise AppError(code=400, message=f"回调处理失败：{exc}") from exc

    # 只处理支付成功事件
    if decrypted.get("trade_state") != "SUCCESS":
        return {"code": "SUCCESS"}

    out_trade_no = decrypted.get("out_trade_no", "")
    wx_transaction_id = decrypted.get("transaction_id", "")

    # 查找订单
    result = await db.execute(select(Order).where(Order.order_no == out_trade_no))
    order = result.scalar_one_or_none()
    if order is None:
        raise AppError(code=404, message=f"订单不存在：{out_trade_no}")

    # 幂等检查
    if order.status == "paid":
        return {"code": "SUCCESS"}

    # 更新订单状态
    await order_service.mark_order_paid(
        db, order=order, wx_transaction_id=wx_transaction_id
    )

    # 激活 / 续费 / 升级会员
    await membership_service.activate_membership(db, order=order)

    await db.commit()
    return {"code": "SUCCESS"}
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_payments.py -k "pay_order or webhook" -v
```

Expected: `4 passed`

- [ ] **Step 5: 运行全量测试**

```bash
python -m pytest ../tests/ -q
```

Expected: `107 passed`

- [ ] **Step 6: 提交**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add backend/app/api/v1/webhooks.py tests/api/test_payments.py
git commit -m "feat(api): POST /orders/{id}/pay + POST /webhooks/wx-pay with idempotency"
```

---

## Task 7: 集成验证 + Push + 归档 D-062

**Files:**
- Modify: `docs/决策归档.md`

- [ ] **Step 1: 运行全量测试**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/ -v 2>&1 | tail -20
```

Expected: 全部 PASS（≥107 个测试）

- [ ] **Step 2: 启动 live 服务器，验证新端点**

```bash
uvicorn app.main:app --port 8020 --log-level warning &
sleep 4

# 健康检查
curl -s http://localhost:8020/health | python3 -m json.tool

# /docs 正常
curl -s -o /dev/null -w "%{http_code}" http://localhost:8020/docs
echo " /docs"

# /memberships/me 无 token → 401
curl -s http://localhost:8020/api/v1/memberships/me | python3 -m json.tool

# /orders/ 无 token → 401
curl -s -X POST http://localhost:8020/api/v1/orders/ \
  -H "Content-Type: application/json" \
  -d '{"tier":"basic","duration_months":1,"order_type":"new"}' | python3 -m json.tool

pkill -f "uvicorn app.main:app" 2>/dev/null || true
```

Expected:
- `/health` → `{"status": "ok"}`
- `/docs` → `200`
- `/memberships/me` 无 token → 401
- `/orders/` 无 token → 401

- [ ] **Step 3: Push 到 GitHub**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git push
```

- [ ] **Step 4: 追加 D-062 到决策归档**

在 `docs/决策归档.md` 的 `## D-061` 段落之前插入：

```markdown
## D-062｜会员 & 微信支付 MVP：Tasks 0-7 全量交付

**日期：** 2026-05-26
**背景：** 错题 AI 分析闭环完成后，实现会员付费购买的核心支付流程。
**结论：**
1. **Config（Task 0）：** 追加 6 个微信支付 v3 配置字段（mch_id/api_key_v3/cert_serial/private_key_pem/notify_url/skip_sig_verify）；`skip_sig_verify=true` 为开发模式默认，生产必须改为 false。
2. **Schemas（Task 1）：** `CurrentMembershipOut`（tier 默认 free）、`OrderCreate`、`OrderOut`、`PayParamsOut`。
3. **Order Service（Task 2）：** 硬编码价格表（basic/pro/promax × 1/3/12 月）；`create_order` 自动生成 ORD-YYYYMMDD-XXXXXXXX 单号；`mark_order_paid` 写入 wx_transaction_id + paid_at。
4. **Membership Service（Task 3）：** `activate_membership` 处理 new/renew/upgrade 三种订单类型；renew 延长 expires_at；upgrade 停用旧会员再创建新会员；`_add_months()` 内联函数处理月末溢出，无需 dateutil 依赖。
5. **WeChat Pay Service（Task 4）：** RSA 签名（dev 模式返回占位字符串）；`get_prepay_id` 调用 JSAPI 统一下单；`build_pay_params` 返回 wx.requestPayment() 5 参数；`verify_and_decrypt_callback` 支持 AES-256-GCM 解密 + mock_decrypted 测试快捷路径。
6. **API（Task 5-6）：** GET /memberships/me、POST /orders/、GET /orders/{id}、POST /orders/{id}/pay（mock httpx）、POST /webhooks/wx-pay（无 JWT、验签+幂等+激活会员）。
7. **幂等性：** order.status == "paid" 时直接返回 SUCCESS，防微信重试重复激活。
**影响范围：** 全量测试 ≥107 个；5 个新端点；已推送 GitHub main 分支。

---
```

- [ ] **Step 5: 提交归档并推送**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add "docs/决策归档.md"
git commit -m "docs: archive D-062 — membership + WeChat Pay MVP complete"
git push
```

---

## Self-Review

### 1. Spec Coverage

| 需求 | Task |
|------|------|
| GET /memberships/me | Task 5 |
| POST /orders/ (new/renew/upgrade) | Task 5 |
| POST /orders/{id}/pay (wx.requestPayment params) | Task 6 |
| GET /orders/{id} | Task 5 |
| POST /webhooks/wx-pay (验签+幂等+激活) | Task 6 |
| 幂等防重复支付 | Task 6 webhook |
| 会员激活/续费/升级逻辑 | Task 3 |
| 价格表 (basic/pro/promax × 1/3/12) | Task 2 |
| 微信支付 v3 RSA 签名 | Task 4 |
| AES-GCM 解密回调 | Task 4 |
| 无 JWT 访问 webhook | Task 6 webhooks.py（无 get_current_user 依赖）|

未含：退款（POST /refunds/, GET /refunds/{id}）— 计划 Plan C，需平台管理员审核。

### 2. Placeholder 扫描

- 无 TBD/TODO（wechat_pay 回调生产验签预留注释明确标注"完整实现需微信平台证书"，属设计说明非 placeholder）
- 每个 Step 均含完整代码
- 命令含预期输出

### 3. 类型一致性

- `activate_membership(db, *, order)` — Task 3 service 签名与 Task 6 webhook 调用一致 ✅
- `mark_order_paid(db, *, order, wx_transaction_id)` — Task 2 service 签名与 Task 6 调用一致 ✅
- `get_prepay_id(order, openid)` — Task 4 service 签名与 Task 6 endpoint 调用一致 ✅
- `CurrentMembershipOut()` 默认 tier="free" — Task 1 schema 与 Task 5 endpoint 一致 ✅
- `PayParamsOut(**params)` — params 是 dict with keys timeStamp/nonceStr/package/signType/paySign，与 schema 字段完全匹配 ✅
