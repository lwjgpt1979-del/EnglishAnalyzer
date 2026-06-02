# 合规两项：年龄核验+协议确认 + 账号注销 实施计划（Plan I）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 完成 P0 合规两项：
1. 年龄核验（出生年份 + 14岁以下监护人手机授权码 + 14-17岁购买会员勾选同意） + 协议确认（版本+时间戳）
2. 账号注销（30天冷静期 + SMS二次确认 + 冷静期内可撤销 + 脱敏匿名化）

依据需求文档 §4.1（未成年人保护机制）、§4.2（账号注销与数据保留规则）。

**Architecture:**
- DB：`users` 表新增 10 个合规相关字段（迁移 0005），不新建表（验证码临时存 users）。
- 服务：扩展 `auth_service` 加 `complete_profile/guardian_verify`；新建 `cancellation_service` 管理注销流程；`membership_service` 加 14-17 岁购买 minor consent 检查。
- API：5 个新端点挂在 `/auth` 和 `/users` 下。
- 前端：新增「完善资料」首登拦截页 + 「账号设置/注销」页 + 14-17岁购买 consent 复选框；待注销态在 profile 顶部展示撤销入口。
- SMS：复用项目"dev mock"模式（`sms_provider` 以 `placeholder` 开头 → 验证码记日志/直返响应、不真发短信）。
- 后台执行：30 天后自动注销采用**懒执行**——用户在 scheduled_at 之后任何 API 调用触发匿名化（避免立即引入 cron）。

**Tech Stack:** FastAPI 0.115 · SQLAlchemy 2.x asyncio · Pydantic v2 · pytest-asyncio STRICT · uni-app Vue3

---

## File Structure

```
新增后端文件:
  backend/alembic/versions/0005_compliance_account.py
  backend/app/schemas/compliance.py                       # 合规相关 schemas
  backend/app/services/cancellation_service.py            # 注销流程
  backend/app/services/sms_service.py                     # SMS dev mock
  tests/api/test_compliance.py

修改后端文件:
  backend/app/models/d1_users.py                          # User 加 10 列
  backend/app/services/auth_service.py                    # 加 complete_profile, guardian_verify, lazy_execute_cancellation
  backend/app/services/membership_service.py              # 14-17 岁 minor consent 检查
  backend/app/api/v1/auth.py                              # +4 端点
  backend/app/api/v1/users.py                             # 改 /me 返回新字段 + 1 撤销端点
  backend/app/api/v1/memberships.py                       # 购买前 minor consent
  backend/app/schemas/users.py                            # UserMeOut 加合规字段
  backend/app/schemas/memberships.py                      # PurchaseRequest 加 minor_consent
  backend/app/core/config.py                              # +sms_provider 配置
  backend/app/core/security.py                            # get_current_user 加注销懒触发

新增前端文件:
  frontend/miniprogram/src/api/compliance.ts              # 5 API
  frontend/miniprogram/src/pages/auth/complete-profile.vue
  frontend/miniprogram/src/pages/account/cancel.vue       # 注销页
  frontend/miniprogram/src/pages/account/settings.vue     # 账号设置入口

修改前端文件:
  frontend/miniprogram/src/pages.json                     # +3 页面
  frontend/miniprogram/src/types/api.ts                   # +类型
  frontend/miniprogram/src/stores/auth.ts                 # profile_completed 引导 + 注销态判断
  frontend/miniprogram/src/pages/index/index.vue          # 加 profile 引导拦截
  frontend/miniprogram/src/pages/profile/index.vue        # 账号设置入口 + 14-17 consent + 待注销提示
```

**Key model facts（确认再动手）：**
- 当前 User 字段：id, openid, phone(nullable), nickname, avatar_url, role, is_active, city_code, city_source, ip_at_registration, created_at, updated_at
- 现有迁移链尾：0004
- `phone` 字段已存在但当前未使用——本计划中**沿用同字段**作为用户手机号（注销时验证）

---

## Task 0: 迁移 0005 + User 模型扩展

**Files:**
- Create: `backend/alembic/versions/0005_compliance_account.py`
- Modify: `backend/app/models/d1_users.py`

- [ ] **Step 1: 修改 `backend/app/models/d1_users.py`，在 `User` 类内（updated_at 之前）追加 10 个字段**

```python
    # —— 合规：年龄核验 + 协议确认（D-073 / 需求文档 §4.1）——
    birth_year = mapped_column(sa.SmallInteger, nullable=True)
    guardian_phone = mapped_column(sa.String(20), nullable=True)
    guardian_verified_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    agreement_version = mapped_column(sa.String(16), nullable=True)
    agreement_agreed_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    profile_completed = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("false")
    )
    minor_purchase_consent_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)

    # —— 合规：账号注销（D-073 / 需求文档 §4.2）——
    deactivation_requested_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    deactivation_scheduled_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    is_anonymized = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("false")
    )

    # —— SMS 验证码临时态（任意 purpose 复用）——
    phone_verify_code = mapped_column(sa.String(6), nullable=True)
    phone_verify_purpose = mapped_column(sa.String(32), nullable=True)
    phone_verify_target = mapped_column(sa.String(20), nullable=True)
    phone_verify_expires_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
```

> 注意 13 列（不是 10——多了 3 个 phone_verify_* + is_anonymized + profile_completed）。

- [ ] **Step 2: 创建 `backend/alembic/versions/0005_compliance_account.py`**

```python
"""compliance: age verification + agreement + account cancellation

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("birth_year", sa.SmallInteger(), nullable=True))
    op.add_column("users", sa.Column("guardian_phone", sa.String(length=20), nullable=True))
    op.add_column("users", sa.Column("guardian_verified_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("users", sa.Column("agreement_version", sa.String(length=16), nullable=True))
    op.add_column("users", sa.Column("agreement_agreed_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("users", sa.Column("profile_completed", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("users", sa.Column("minor_purchase_consent_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("users", sa.Column("deactivation_requested_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("users", sa.Column("deactivation_scheduled_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("users", sa.Column("is_anonymized", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("users", sa.Column("phone_verify_code", sa.String(length=6), nullable=True))
    op.add_column("users", sa.Column("phone_verify_purpose", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("phone_verify_target", sa.String(length=20), nullable=True))
    op.add_column("users", sa.Column("phone_verify_expires_at", sa.TIMESTAMP(timezone=True), nullable=True))


def downgrade() -> None:
    for col in [
        "phone_verify_expires_at", "phone_verify_target", "phone_verify_purpose", "phone_verify_code",
        "is_anonymized", "deactivation_scheduled_at", "deactivation_requested_at",
        "minor_purchase_consent_at", "profile_completed",
        "agreement_agreed_at", "agreement_version",
        "guardian_verified_at", "guardian_phone", "birth_year",
    ]:
        op.drop_column("users", col)
```

- [ ] **Step 3: 运行迁移**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
DATABASE_URL="postgresql+psycopg://postgres:dev@localhost:5432/enggramer" alembic upgrade head
```

Expected: `Running upgrade 0004 -> 0005`

- [ ] **Step 4: 全量测试通过**

```bash
python -m pytest ../tests/ -q
```

Expected: 之前的全部测试仍 PASS（数量不变）

- [ ] **Step 5: 提交**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add backend/alembic/versions/0005_compliance_account.py backend/app/models/d1_users.py
git commit -m "feat(db): migration 0005 — compliance fields on users (age/agreement/cancellation)"
```

---

## Task 1: Compliance Schemas + SMS dev mock + Config

**Files:**
- Create: `backend/app/schemas/compliance.py`
- Create: `backend/app/services/sms_service.py`
- Modify: `backend/app/core/config.py`
- Create test stub: `tests/api/test_compliance.py` (空文件)

- [ ] **Step 1: 在 `backend/app/core/config.py` 的 Settings 类中加字段**

找到 Settings 类（pydantic-settings），在合适位置加：
```python
    sms_provider: str = "placeholder-dev"  # 'placeholder-*' 触发 dev mock；生产填真实 provider 名
```

不需要 secret_key（dev mock 不发短信）。

- [ ] **Step 2: 创建 `backend/app/services/sms_service.py`**

```python
"""SMS 验证码服务。MVP 阶段 dev mock：不真发短信，验证码记日志并固定为 '123456'。
生产接入：替换 `_send_real_sms` 内实现（阿里云/腾讯云短信 SDK）。
"""
from __future__ import annotations

import logging
import random
import string
from datetime import datetime, timedelta, timezone

from app.core.config import settings

logger = logging.getLogger(__name__)

CODE_TTL_MINUTES = 10
DEV_FIXED_CODE = "123456"  # dev mode 固定码，便于自测


def _is_dev_mode() -> bool:
    return settings.sms_provider.startswith("placeholder")


def generate_code() -> str:
    if _is_dev_mode():
        return DEV_FIXED_CODE
    return "".join(random.choices(string.digits, k=6))


def expires_at_from_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=CODE_TTL_MINUTES)


async def send_sms_code(*, phone: str, code: str, purpose: str) -> None:
    """发送短信验证码。Dev mode 仅记日志。"""
    if _is_dev_mode():
        logger.warning(
            "[SMS DEV MOCK] phone=%s purpose=%s code=%s (dev固定%s)",
            phone, purpose, code, DEV_FIXED_CODE,
        )
        return
    await _send_real_sms(phone=phone, code=code, purpose=purpose)


async def _send_real_sms(*, phone: str, code: str, purpose: str) -> None:
    raise NotImplementedError("生产 SMS provider 未接入")
```

- [ ] **Step 3: 创建 `backend/app/schemas/compliance.py`**

```python
"""合规相关 Schemas：年龄核验 + 协议确认 + 账号注销。"""
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field

CURRENT_AGREEMENT_VERSION = "v1.0"


class CompleteProfileRequest(BaseModel):
    """首次登录完善资料。"""
    birth_year: int = Field(..., ge=1900, le=2030, description="出生年份")
    guardian_phone: str | None = Field(None, min_length=11, max_length=20, description="<14岁必填监护人手机号")
    user_phone: str | None = Field(None, min_length=11, max_length=20, description="可选，用户本人手机号，注销时验证用")
    agreement_version: str = Field(..., description="同意的协议版本（当前 v1.0）")


class CompleteProfileResponse(BaseModel):
    profile_completed: bool
    needs_guardian_verify: bool
    age: int


class GuardianVerifyRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)


class CancelAccountRequestStart(BaseModel):
    """Step 1: 申请注销，触发 SMS 验证码发送。"""
    pass  # 不需要 body（取自当前用户）


class CancelAccountConfirm(BaseModel):
    """Step 2: 提交 SMS 验证码确认注销。"""
    code: str = Field(..., min_length=6, max_length=6)


class CancellationStatusOut(BaseModel):
    requested_at: datetime | None
    scheduled_at: datetime | None
    days_remaining: int | None  # None=非待注销态
```

- [ ] **Step 4: 创建 `tests/api/test_compliance.py`（空 + schema 冒烟）**

```python
"""合规两项测试：年龄核验 + 协议确认 + 账号注销。"""
from app.schemas.compliance import (
    CURRENT_AGREEMENT_VERSION,
    CancelAccountConfirm,
    CompleteProfileRequest,
)


def test_agreement_version_defined():
    assert CURRENT_AGREEMENT_VERSION == "v1.0"


def test_complete_profile_request():
    req = CompleteProfileRequest(birth_year=2010, agreement_version="v1.0")
    assert req.birth_year == 2010
    assert req.guardian_phone is None


def test_cancel_account_confirm_validates_code_length():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        CancelAccountConfirm(code="123")  # 短于6位
```

- [ ] **Step 5: 运行 + 通过**

```bash
python -m pytest ../tests/api/test_compliance.py -v
```

Expected: 3 passed

- [ ] **Step 6: 提交**

```bash
git add backend/app/schemas/compliance.py backend/app/services/sms_service.py \
        backend/app/core/config.py tests/api/test_compliance.py
git commit -m "feat(compliance): schemas + SMS dev mock + config"
```

---

## Task 2: Auth Service 扩展 + Cancellation Service

**Files:**
- Modify: `backend/app/services/auth_service.py`
- Create: `backend/app/services/cancellation_service.py`
- Modify: `tests/api/test_compliance.py` (追加 service 测试)

- [ ] **Step 1: 追加 `tests/api/test_compliance.py`（service 测试 — 先红）**

```python


# ── Service 测试 ──────────────────────────────────────────────────────────────
import pytest
import pytest_asyncio
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import _async_session_factory
from app.core.exceptions import AppError
from app.services.auth_service import (
    upsert_user,
    complete_profile,
    guardian_verify,
    compute_age,
)
from app.services.cancellation_service import (
    request_cancellation,
    confirm_cancellation,
    revoke_cancellation,
    execute_cancellation_if_due,
)


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def new_user(db_session):
    user = await upsert_user(db_session, openid=f"cmp_{uuid.uuid4().hex[:8]}")
    await db_session.flush()
    return user


def test_compute_age():
    assert compute_age(2010) == datetime.now(timezone.utc).year - 2010


@pytest.mark.asyncio
async def test_complete_profile_adult(db_session, new_user):
    res = await complete_profile(
        db_session, user=new_user, birth_year=1990, guardian_phone=None,
        user_phone="13800001111", agreement_version="v1.0",
    )
    assert res.profile_completed is True
    assert res.needs_guardian_verify is False


@pytest.mark.asyncio
async def test_complete_profile_minor_requires_guardian(db_session, new_user):
    with pytest.raises(AppError) as exc:
        await complete_profile(
            db_session, user=new_user, birth_year=2020, guardian_phone=None,
            user_phone=None, agreement_version="v1.0",
        )
    assert exc.value.code == 400


@pytest.mark.asyncio
async def test_complete_profile_minor_with_guardian(db_session, new_user):
    res = await complete_profile(
        db_session, user=new_user, birth_year=2020, guardian_phone="13800001234",
        user_phone=None, agreement_version="v1.0",
    )
    assert res.needs_guardian_verify is True
    assert new_user.profile_completed is False  # 未验证不算完成
    assert new_user.guardian_phone == "13800001234"


@pytest.mark.asyncio
async def test_guardian_verify_success(db_session, new_user):
    await complete_profile(
        db_session, user=new_user, birth_year=2020, guardian_phone="13800001234",
        user_phone=None, agreement_version="v1.0",
    )
    # 模拟已发码：直接写 phone_verify_code 字段
    from app.services.sms_service import DEV_FIXED_CODE, expires_at_from_now
    new_user.phone_verify_code = DEV_FIXED_CODE
    new_user.phone_verify_purpose = "guardian_verify"
    new_user.phone_verify_target = "13800001234"
    new_user.phone_verify_expires_at = expires_at_from_now()
    await db_session.flush()

    await guardian_verify(db_session, user=new_user, code=DEV_FIXED_CODE)
    assert new_user.profile_completed is True
    assert new_user.guardian_verified_at is not None


@pytest.mark.asyncio
async def test_request_and_confirm_cancellation(db_session, new_user):
    new_user.phone = "13800009999"
    await db_session.flush()

    await request_cancellation(db_session, user=new_user)
    assert new_user.phone_verify_code is not None

    from app.services.sms_service import DEV_FIXED_CODE
    await confirm_cancellation(db_session, user=new_user, code=DEV_FIXED_CODE)
    assert new_user.deactivation_requested_at is not None
    assert new_user.deactivation_scheduled_at is not None
    assert new_user.is_active is False


@pytest.mark.asyncio
async def test_revoke_cancellation(db_session, new_user):
    new_user.phone = "13800009999"
    await db_session.flush()
    await request_cancellation(db_session, user=new_user)
    from app.services.sms_service import DEV_FIXED_CODE
    await confirm_cancellation(db_session, user=new_user, code=DEV_FIXED_CODE)

    await revoke_cancellation(db_session, user=new_user)
    assert new_user.deactivation_requested_at is None
    assert new_user.is_active is True


@pytest.mark.asyncio
async def test_execute_cancellation_if_due_anonymizes(db_session, new_user):
    new_user.phone = "13800009999"
    new_user.nickname = "Original"
    await db_session.flush()
    await request_cancellation(db_session, user=new_user)
    from app.services.sms_service import DEV_FIXED_CODE
    await confirm_cancellation(db_session, user=new_user, code=DEV_FIXED_CODE)

    # 模拟时间已过 30 天：手动改 scheduled_at 为过去
    new_user.deactivation_scheduled_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.flush()

    await execute_cancellation_if_due(db_session, user=new_user)
    assert new_user.is_anonymized is True
    assert new_user.nickname is None
    assert new_user.phone is None
    assert new_user.openid.startswith("deleted_")
```

- [ ] **Step 2: 运行 → FAIL（imports 不存在）**

```bash
python -m pytest ../tests/api/test_compliance.py -v 2>&1 | head -20
```

Expected: ImportError / 函数未定义

- [ ] **Step 3: 扩展 `backend/app/services/auth_service.py`**

在文件末尾追加：

```python


# ─── 合规扩展：年龄核验 + 协议确认 ────────────────────────────────────────────
from datetime import datetime, timezone
import uuid

from app.schemas.compliance import (
    CURRENT_AGREEMENT_VERSION,
    CompleteProfileResponse,
)
from app.services.sms_service import (
    generate_code,
    expires_at_from_now,
    send_sms_code,
)

GUARDIAN_AGE_THRESHOLD = 14  # < 此年龄需监护人授权


def compute_age(birth_year: int) -> int:
    return datetime.now(timezone.utc).year - birth_year


async def complete_profile(
    db: AsyncSession,
    *,
    user: User,
    birth_year: int,
    guardian_phone: str | None,
    user_phone: str | None,
    agreement_version: str,
) -> CompleteProfileResponse:
    """首次登录完善资料。<14岁需监护人手机号 + 发码（profile_completed 暂为 false 直到 guardian_verify）。"""
    age = compute_age(birth_year)
    needs_guardian = age < GUARDIAN_AGE_THRESHOLD

    if needs_guardian and not guardian_phone:
        raise AppError(code=400, message=f"未满 {GUARDIAN_AGE_THRESHOLD} 岁需提供监护人手机号")

    user.birth_year = birth_year
    user.agreement_version = agreement_version
    user.agreement_agreed_at = datetime.now(timezone.utc)
    if user_phone:
        user.phone = user_phone

    if needs_guardian:
        user.guardian_phone = guardian_phone
        # 发码（dev mock 实际不发，记日志）
        code = generate_code()
        user.phone_verify_code = code
        user.phone_verify_purpose = "guardian_verify"
        user.phone_verify_target = guardian_phone
        user.phone_verify_expires_at = expires_at_from_now()
        await send_sms_code(phone=guardian_phone, code=code, purpose="guardian_verify")
        user.profile_completed = False  # 待监护人验证
    else:
        user.profile_completed = True

    await db.flush()
    return CompleteProfileResponse(
        profile_completed=user.profile_completed,
        needs_guardian_verify=needs_guardian,
        age=age,
    )


async def guardian_verify(
    db: AsyncSession,
    *,
    user: User,
    code: str,
) -> None:
    """监护人填写验证码确认。"""
    if user.phone_verify_purpose != "guardian_verify":
        raise AppError(code=400, message="无待确认的监护人验证")
    if (
        user.phone_verify_code != code
        or user.phone_verify_expires_at is None
        or user.phone_verify_expires_at < datetime.now(timezone.utc)
    ):
        raise AppError(code=400, message="验证码错误或已过期")

    user.guardian_verified_at = datetime.now(timezone.utc)
    user.profile_completed = True
    user.phone_verify_code = None
    user.phone_verify_purpose = None
    user.phone_verify_target = None
    user.phone_verify_expires_at = None
    await db.flush()


def is_minor_14_to_17(user: User) -> bool:
    """14-17 岁返回 True（购买会员需勾选监护人同意）。"""
    if user.birth_year is None:
        return False
    age = compute_age(user.birth_year)
    return 14 <= age <= 17
```

- [ ] **Step 4: 创建 `backend/app/services/cancellation_service.py`**

```python
"""账号注销流程（需求文档 §4.2）。

3 步：申请（发 SMS） → 确认（提交码）→ 30天冷静期 → 懒执行匿名化。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d1_users import User
from app.schemas.compliance import CancellationStatusOut
from app.services.sms_service import (
    DEV_FIXED_CODE,
    generate_code,
    expires_at_from_now,
    send_sms_code,
)

COOLING_PERIOD_DAYS = 30


async def request_cancellation(db: AsyncSession, *, user: User) -> None:
    """Step 1：发 SMS 验证码到用户本人手机。"""
    if not user.phone:
        raise AppError(code=400, message="请先在账号设置补填本人手机号")
    if user.deactivation_requested_at is not None:
        raise AppError(code=409, message="账号已在注销冷静期内")

    code = generate_code()
    user.phone_verify_code = code
    user.phone_verify_purpose = "cancel_account"
    user.phone_verify_target = user.phone
    user.phone_verify_expires_at = expires_at_from_now()
    await send_sms_code(phone=user.phone, code=code, purpose="cancel_account")
    await db.flush()


async def confirm_cancellation(db: AsyncSession, *, user: User, code: str) -> None:
    """Step 2：核码 → 进入 30 天冷静期，is_active=false。"""
    if user.phone_verify_purpose != "cancel_account":
        raise AppError(code=400, message="无待确认的注销申请")
    if (
        user.phone_verify_code != code
        or user.phone_verify_expires_at is None
        or user.phone_verify_expires_at < datetime.now(timezone.utc)
    ):
        raise AppError(code=400, message="验证码错误或已过期")

    now = datetime.now(timezone.utc)
    user.deactivation_requested_at = now
    user.deactivation_scheduled_at = now + timedelta(days=COOLING_PERIOD_DAYS)
    user.is_active = False
    user.phone_verify_code = None
    user.phone_verify_purpose = None
    user.phone_verify_target = None
    user.phone_verify_expires_at = None
    await db.flush()


async def revoke_cancellation(db: AsyncSession, *, user: User) -> None:
    """冷静期内撤销注销。"""
    if user.deactivation_requested_at is None:
        raise AppError(code=400, message="账号不在注销冷静期内")
    if user.deactivation_scheduled_at and user.deactivation_scheduled_at < datetime.now(timezone.utc):
        raise AppError(code=410, message="冷静期已结束，无法撤销")
    user.deactivation_requested_at = None
    user.deactivation_scheduled_at = None
    user.is_active = True
    await db.flush()


async def execute_cancellation_if_due(db: AsyncSession, *, user: User) -> bool:
    """懒执行：若 scheduled_at 已过则脱敏匿名化，返回是否执行。"""
    if user.is_anonymized:
        return False
    if user.deactivation_scheduled_at is None:
        return False
    if user.deactivation_scheduled_at > datetime.now(timezone.utc):
        return False

    user.openid = f"deleted_{uuid.uuid4().hex}"
    user.nickname = None
    user.avatar_url = None
    user.phone = None
    user.guardian_phone = None
    user.is_anonymized = True
    user.is_active = False
    # 订单/支付记录按财务合规保留 5 年——本步骤不动 orders/refunds 表，靠 user_id 反查无个人信息即可
    await db.flush()
    return True


def status_for(user: User) -> CancellationStatusOut:
    days_remaining = None
    if user.deactivation_scheduled_at is not None:
        delta = user.deactivation_scheduled_at - datetime.now(timezone.utc)
        days_remaining = max(0, delta.days)
    return CancellationStatusOut(
        requested_at=user.deactivation_requested_at,
        scheduled_at=user.deactivation_scheduled_at,
        days_remaining=days_remaining,
    )
```

- [ ] **Step 5: 运行 service 测试 → PASS**

```bash
python -m pytest ../tests/api/test_compliance.py -v
```

Expected: 9 个测试 PASS（3 schema + 6 service）

- [ ] **Step 6: 全量测试不回归**

```bash
python -m pytest ../tests/ -q
```

- [ ] **Step 7: 提交**

```bash
git add backend/app/services/auth_service.py backend/app/services/cancellation_service.py tests/api/test_compliance.py
git commit -m "feat(compliance): auth_service +complete_profile/guardian_verify; cancellation_service"
```

---

## Task 3: API 端点 + Memberships 联动 + 注销懒触发

**Files:**
- Modify: `backend/app/api/v1/auth.py`
- Modify: `backend/app/api/v1/users.py`
- Modify: `backend/app/api/v1/memberships.py`
- Modify: `backend/app/schemas/users.py`
- Modify: `backend/app/schemas/memberships.py`
- Modify: `backend/app/core/security.py` (注销懒触发)
- Modify: `tests/api/test_compliance.py` (追加 API 测试)

- [ ] **Step 1: 改 `backend/app/schemas/users.py` 的 UserMeOut**

READ 现有内容，找到 UserMeOut，加字段：
```python
    profile_completed: bool = False
    birth_year: int | None = None
    needs_guardian_verify: bool = False  # 计算属性：未通过监护人验证
    deactivation_scheduled_at: datetime | None = None
    days_until_cancellation: int | None = None
```

- [ ] **Step 2: 改 `backend/app/api/v1/users.py` 的 /me 端点，组合返回上面字段**

具体：读出 user 后构造响应时填上这些字段；并在 /me 调用 `execute_cancellation_if_due` 懒触发（如果到期则匿名化后返回 401 "账号已注销"）。

- [ ] **Step 3: 改 `backend/app/api/v1/auth.py`，追加 4 个端点**

```python
from app.schemas.compliance import (
    CompleteProfileRequest,
    CompleteProfileResponse,
    GuardianVerifyRequest,
    CancelAccountConfirm,
    CancellationStatusOut,
)
from app.services.auth_service import complete_profile, guardian_verify
from app.services.cancellation_service import (
    request_cancellation,
    confirm_cancellation,
    revoke_cancellation,
    status_for,
)
from app.core.security import get_current_user
from app.models.d1_users import User
from typing import Annotated

UserDep = Annotated[User, Depends(get_current_user)]
DbDep   = Annotated[AsyncSession, Depends(get_db)]


@router.post("/complete-profile", response_model=BaseResponse[CompleteProfileResponse])
async def complete_profile_api(body: CompleteProfileRequest, db: DbDep, current_user: UserDep):
    res = await complete_profile(
        db, user=current_user,
        birth_year=body.birth_year,
        guardian_phone=body.guardian_phone,
        user_phone=body.user_phone,
        agreement_version=body.agreement_version,
    )
    await db.commit()
    return make_ok(res)


@router.post("/guardian-verify", response_model=BaseResponse[dict])
async def guardian_verify_api(body: GuardianVerifyRequest, db: DbDep, current_user: UserDep):
    await guardian_verify(db, user=current_user, code=body.code)
    await db.commit()
    return make_ok({"profile_completed": True})


@router.post("/cancel-account/request", response_model=BaseResponse[dict])
async def cancel_request_api(db: DbDep, current_user: UserDep):
    await request_cancellation(db, user=current_user)
    await db.commit()
    return make_ok({"sent": True})


@router.post("/cancel-account/confirm", response_model=BaseResponse[CancellationStatusOut])
async def cancel_confirm_api(body: CancelAccountConfirm, db: DbDep, current_user: UserDep):
    await confirm_cancellation(db, user=current_user, code=body.code)
    await db.commit()
    return make_ok(status_for(current_user))


@router.post("/cancel-account/revoke", response_model=BaseResponse[dict])
async def cancel_revoke_api(db: DbDep, current_user: UserDep):
    await revoke_cancellation(db, user=current_user)
    await db.commit()
    return make_ok({"revoked": True})
```

- [ ] **Step 4: 改 `backend/app/schemas/memberships.py` 的购买请求加 `minor_consent: bool`**

```python
class PurchaseRequest(BaseModel):
    tier: str
    duration_months: int
    order_type: str = "new"
    minor_consent: bool = False  # 14-17 岁首次购买必填 True
```

- [ ] **Step 5: 改 `backend/app/api/v1/memberships.py`（或 orders.py，依实际下单端点位置）：购买前 14-17 校验**

在 create_order 处理逻辑中加：
```python
from app.services.auth_service import is_minor_14_to_17
from datetime import datetime, timezone

if is_minor_14_to_17(current_user) and current_user.minor_purchase_consent_at is None:
    if not body.minor_consent:
        raise AppError(code=400, message="14-17岁用户首次购买请勾选「已告知监护人并获得同意」")
    current_user.minor_purchase_consent_at = datetime.now(timezone.utc)
```

- [ ] **Step 6: 改 `backend/app/core/security.py`：get_current_user 中懒触发注销**

在解析 user 后、校验 is_active 之前插入：
```python
from app.services.cancellation_service import execute_cancellation_if_due
if user.deactivation_scheduled_at is not None and not user.is_anonymized:
    await execute_cancellation_if_due(db, user=user)
    await db.commit()
```

- [ ] **Step 7: 追加 API 测试到 `tests/api/test_compliance.py`**

```python


# ── API 测试 ──────────────────────────────────────────────────────────────────
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from app.main import app


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _login(client: AsyncClient, openid_suffix: str) -> dict:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as mock_wx:
        mock_wx.return_value = {"openid": f"cmp_api_{openid_suffix}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


@pytest.mark.asyncio
async def test_complete_profile_api_adult(client):
    headers = await _login(client, f"adult_{uuid.uuid4().hex[:6]}")
    resp = await client.post(
        "/api/v1/auth/complete-profile",
        json={"birth_year": 1990, "agreement_version": "v1.0", "user_phone": "13800001111"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["profile_completed"] is True


@pytest.mark.asyncio
async def test_complete_profile_api_minor(client):
    headers = await _login(client, f"minor_{uuid.uuid4().hex[:6]}")
    resp = await client.post(
        "/api/v1/auth/complete-profile",
        json={"birth_year": 2020, "guardian_phone": "13800002222", "agreement_version": "v1.0"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["needs_guardian_verify"] is True
    assert resp.json()["data"]["profile_completed"] is False


@pytest.mark.asyncio
async def test_cancel_account_full_flow(client):
    headers = await _login(client, f"cancel_{uuid.uuid4().hex[:6]}")
    # 先完善 profile 拿到 phone
    await client.post(
        "/api/v1/auth/complete-profile",
        json={"birth_year": 1990, "agreement_version": "v1.0", "user_phone": "13900009999"},
        headers=headers,
    )
    # 申请
    r1 = await client.post("/api/v1/auth/cancel-account/request", headers=headers)
    assert r1.status_code == 200
    # 确认（dev 固定码 123456）
    r2 = await client.post(
        "/api/v1/auth/cancel-account/confirm",
        json={"code": "123456"}, headers=headers,
    )
    assert r2.status_code == 200
    assert r2.json()["data"]["days_remaining"] is not None
    # 撤销
    r3 = await client.post("/api/v1/auth/cancel-account/revoke", headers=headers)
    assert r3.status_code == 200
```

- [ ] **Step 8: 运行 + 全量通过**

```bash
python -m pytest ../tests/api/test_compliance.py -v
python -m pytest ../tests/ -q
```

Expected: 12 个合规测试全 PASS；全量无回归

- [ ] **Step 9: 提交**

```bash
git add backend/app/api/v1/auth.py backend/app/api/v1/users.py backend/app/api/v1/memberships.py \
        backend/app/schemas/users.py backend/app/schemas/memberships.py \
        backend/app/core/security.py tests/api/test_compliance.py
git commit -m "feat(compliance): API endpoints + memberships minor-consent + lazy cancellation trigger"
```

---

## Task 4: 前端 — 完善资料页 + 账号设置/注销页 + 引导拦截

**Files:**
- Modify: `frontend/miniprogram/src/types/api.ts`
- Create: `frontend/miniprogram/src/api/compliance.ts`
- Modify: `frontend/miniprogram/src/pages.json`
- Create: `frontend/miniprogram/src/pages/auth/complete-profile.vue`
- Create: `frontend/miniprogram/src/pages/account/settings.vue`
- Create: `frontend/miniprogram/src/pages/account/cancel.vue`
- Modify: `frontend/miniprogram/src/stores/auth.ts`
- Modify: `frontend/miniprogram/src/pages/index/index.vue` (拦截未完善资料)
- Modify: `frontend/miniprogram/src/pages/profile/index.vue` (账号设置入口 + 14-17 consent + 待注销提示)

- [ ] **Step 1: types/api.ts 加类型**

末尾追加：
```typescript
export interface CompleteProfileResponse {
  profile_completed: boolean
  needs_guardian_verify: boolean
  age: number
}

export interface CancellationStatus {
  requested_at: string | null
  scheduled_at: string | null
  days_remaining: number | null
}

// UserMeOut 扩展
export interface UserMeOutExtended {
  // 已有字段...
  profile_completed?: boolean
  birth_year?: number | null
  deactivation_scheduled_at?: string | null
  days_until_cancellation?: number | null
}
```

- [ ] **Step 2: api/compliance.ts**

```typescript
import { request } from './request'
import type { BaseResponse, CompleteProfileResponse, CancellationStatus } from '../types/api'

export function completeProfile(data: {
  birth_year: number
  guardian_phone?: string
  user_phone?: string
  agreement_version: string
}): Promise<BaseResponse<CompleteProfileResponse>> {
  return request('/auth/complete-profile', { method: 'POST', data })
}

export function guardianVerify(code: string): Promise<BaseResponse<{ profile_completed: boolean }>> {
  return request('/auth/guardian-verify', { method: 'POST', data: { code } })
}

export function requestCancel(): Promise<BaseResponse<{ sent: boolean }>> {
  return request('/auth/cancel-account/request', { method: 'POST' })
}

export function confirmCancel(code: string): Promise<BaseResponse<CancellationStatus>> {
  return request('/auth/cancel-account/confirm', { method: 'POST', data: { code } })
}

export function revokeCancel(): Promise<BaseResponse<{ revoked: boolean }>> {
  return request('/auth/cancel-account/revoke', { method: 'POST' })
}
```

- [ ] **Step 3: pages.json 加 3 个页面**

在 pages 数组追加：
```json
{ "path": "pages/auth/complete-profile", "style": { "navigationBarTitleText": "完善资料" } },
{ "path": "pages/account/settings", "style": { "navigationBarTitleText": "账号设置" } },
{ "path": "pages/account/cancel", "style": { "navigationBarTitleText": "注销账号" } }
```

- [ ] **Step 4: 创建 `pages/auth/complete-profile.vue`**

按黄油风（黄底深字按钮、大圆角、墨黑标题）实现：
- 出生年份输入（picker 或 input number）
- 协议勾选 checkbox + 「用户协议」「隐私协议」链接（MVP 跳 navigateTo 静态页或弹 modal）
- 计算年龄；<14 时显示监护人手机号输入 + 「发送授权码」按钮 + 验证码输入框 + 「确认」
- 提交→ completeProfile → 若 needs_guardian_verify=true 显示验证码区域 → guardianVerify
- 完成后 navigateBack 或 redirectTo 首页

骨架（按黄油 token）：
```vue
<template>
  <view class="page">
    <view class="card">
      <view class="title">完善资料</view>
      <view class="row"><text class="label">出生年份</text><input v-model="birthYear" type="number" class="input" placeholder="如 2012"/></view>
      <view v-if="needGuardian" class="row col"><text class="label">监护人手机号</text><input v-model="guardianPhone" class="input" placeholder="11位手机号"/></view>
      <view class="row col"><text class="label">本人手机号（可选）</text><input v-model="userPhone" class="input" placeholder="用于注销验证"/></view>
      <view class="agree"><checkbox :checked="agreed" @tap="agreed = !agreed"/><text>我已阅读并同意《用户协议》《隐私政策》</text></view>
      <button class="btn-primary" :disabled="!canSubmit || submitting" @tap="onSubmit">{{ submitting ? '提交中…' : '提交' }}</button>

      <view v-if="codeSent" class="row col">
        <text class="label">监护人收到的验证码</text>
        <input v-model="code" class="input" placeholder="6位数字"/>
        <button class="btn-primary" :disabled="verifying" @tap="onVerify">{{ verifying ? '验证中…' : '完成验证' }}</button>
        <text class="dev-hint">（开发模式：固定码 123456）</text>
      </view>
    </view>
  </view>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import { completeProfile, guardianVerify } from '@/api/compliance'
const birthYear = ref(''); const guardianPhone = ref(''); const userPhone = ref(''); const agreed = ref(false)
const submitting = ref(false); const verifying = ref(false); const codeSent = ref(false); const code = ref('')
const currentYear = new Date().getFullYear()
const age = computed(() => Number(birthYear.value) ? currentYear - Number(birthYear.value) : 0)
const needGuardian = computed(() => age.value > 0 && age.value < 14)
const canSubmit = computed(() => Number(birthYear.value) >= 1900 && Number(birthYear.value) <= currentYear && agreed.value && (!needGuardian.value || guardianPhone.value.length === 11))
async function onSubmit() {
  submitting.value = true
  try {
    const r = await completeProfile({
      birth_year: Number(birthYear.value),
      guardian_phone: needGuardian.value ? guardianPhone.value : undefined,
      user_phone: userPhone.value || undefined,
      agreement_version: 'v1.0',
    })
    if (r.data?.needs_guardian_verify) {
      codeSent.value = true
      uni.showToast({ title: '已向监护人发送验证码', icon: 'success' })
    } else {
      uni.showToast({ title: '完善成功', icon: 'success' })
      setTimeout(() => uni.reLaunch({ url: '/pages/index/index' }), 800)
    }
  } catch (e: any) {
    uni.showToast({ title: e?.message || '提交失败', icon: 'none' })
  } finally { submitting.value = false }
}
async function onVerify() {
  verifying.value = true
  try {
    await guardianVerify(code.value)
    uni.showToast({ title: '验证通过', icon: 'success' })
    setTimeout(() => uni.reLaunch({ url: '/pages/index/index' }), 800)
  } catch (e: any) {
    uni.showToast({ title: e?.message || '验证失败', icon: 'none' })
  } finally { verifying.value = false }
}
</script>
<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.title { font-size: var(--fs-h1); font-weight: 800; color: var(--c-ink); margin-bottom: 24rpx; }
.row { display: flex; align-items: center; padding: 16rpx 0; border-bottom: 1rpx solid var(--c-border); }
.row.col { flex-direction: column; align-items: stretch; gap: 8rpx; }
.label { width: 200rpx; color: var(--c-text-second); font-size: 28rpx; }
.input { flex: 1; padding: 12rpx 0; font-size: 28rpx; color: var(--c-text-body); }
.row.col .input { border: 2rpx solid var(--c-border); border-radius: var(--r-md); padding: 12rpx; }
.agree { display: flex; align-items: center; gap: 8rpx; margin: 20rpx 0; font-size: 26rpx; color: var(--c-text-second); }
.btn-primary { background: var(--c-primary); color: var(--c-ink); border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; margin-top: 16rpx; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #b9a94e; }
.dev-hint { font-size: 22rpx; color: var(--c-text-hint); margin-top: 8rpx; }
</style>
```

- [ ] **Step 5: 创建 `pages/account/settings.vue`**

简单卡片入口：跳「注销账号」、跳「用户协议」、跳「隐私政策」。

```vue
<template>
  <view class="page">
    <view class="card" @tap="goCancel">
      <text class="row-title">注销账号</text>
      <text class="row-arrow">›</text>
    </view>
    <view class="card" @tap="goAgreement">
      <text class="row-title">用户协议</text>
      <text class="row-arrow">›</text>
    </view>
    <view class="card" @tap="goPrivacy">
      <text class="row-title">隐私政策</text>
      <text class="row-arrow">›</text>
    </view>
  </view>
</template>
<script setup lang="ts">
function goCancel() { uni.navigateTo({ url: '/pages/account/cancel' }) }
function goAgreement() { uni.showToast({ title: '协议占位（MVP）', icon: 'none' }) }
function goPrivacy() { uni.showToast({ title: '协议占位（MVP）', icon: 'none' }) }
</script>
<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: 28rpx; margin-bottom: 16rpx; display: flex; align-items: center; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.row-title { flex: 1; font-size: 28rpx; color: var(--c-ink); }
.row-arrow { font-size: 32rpx; color: var(--c-text-hint); }
</style>
```

- [ ] **Step 6: 创建 `pages/account/cancel.vue`**

注销流程页：申请→输验证码→进入待注销状态显示倒计时+撤销按钮。

```vue
<template>
  <view class="page">
    <view class="card">
      <view class="title">注销账号</view>
      <text class="warn">注销后历史数据不可恢复、剩余会员时长不退款。账号将进入 30 天冷静期，期间可撤销。</text>

      <view v-if="!sent && !inCooling">
        <button class="btn-danger" :disabled="loading" @tap="onRequest">{{ loading ? '发送中…' : '申请注销' }}</button>
      </view>

      <view v-else-if="sent && !inCooling">
        <input v-model="code" class="input" placeholder="6位验证码"/>
        <text class="dev-hint">（开发模式：固定码 123456）</text>
        <button class="btn-danger" :disabled="loading" @tap="onConfirm">{{ loading ? '确认中…' : '确认注销' }}</button>
      </view>

      <view v-else class="cooling">
        <text class="cooling-title">⏳ 待注销中</text>
        <text class="cooling-days">剩余 {{ daysRemaining }} 天</text>
        <button class="btn-primary" :disabled="loading" @tap="onRevoke">{{ loading ? '撤销中…' : '撤销注销' }}</button>
      </view>
    </view>
  </view>
</template>
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { requestCancel, confirmCancel, revokeCancel } from '@/api/compliance'
const auth = useAuthStore()
const sent = ref(false); const inCooling = ref(false); const code = ref(''); const loading = ref(false); const daysRemaining = ref<number | null>(null)
onMounted(() => {
  if (auth.user?.deactivation_scheduled_at) {
    inCooling.value = true
    daysRemaining.value = auth.user.days_until_cancellation ?? null
  }
})
async function onRequest() {
  loading.value = true
  try { await requestCancel(); sent.value = true; uni.showToast({ title: '已发送验证码', icon: 'success' }) }
  catch (e: any) { uni.showToast({ title: e?.message || '发送失败', icon: 'none' }) }
  finally { loading.value = false }
}
async function onConfirm() {
  loading.value = true
  try {
    const r = await confirmCancel(code.value)
    inCooling.value = true
    daysRemaining.value = r.data?.days_remaining ?? 30
    uni.showToast({ title: '已进入冷静期', icon: 'success' })
  } catch (e: any) { uni.showToast({ title: e?.message || '确认失败', icon: 'none' }) }
  finally { loading.value = false }
}
async function onRevoke() {
  loading.value = true
  try { await revokeCancel(); inCooling.value = false; sent.value = false; uni.showToast({ title: '已撤销', icon: 'success' }); setTimeout(() => uni.navigateBack(), 800) }
  catch (e: any) { uni.showToast({ title: e?.message || '撤销失败', icon: 'none' }) }
  finally { loading.value = false }
}
</script>
<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.title { font-size: var(--fs-h1); font-weight: 800; color: var(--c-ink); margin-bottom: 16rpx; }
.warn { font-size: 26rpx; color: var(--c-danger-dark); display: block; line-height: 1.6; margin-bottom: 24rpx; padding: 16rpx; background: var(--c-danger-bg); border-radius: var(--r-md); }
.input { width: 100%; border: 2rpx solid var(--c-border); border-radius: var(--r-md); padding: 16rpx; font-size: 28rpx; margin: 16rpx 0 8rpx; box-sizing: border-box; }
.btn-danger { background: var(--c-danger); color: #fff; border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; margin-top: 16rpx; }
.btn-danger[disabled] { opacity: .5; }
.btn-primary { background: var(--c-primary); color: var(--c-ink); border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; margin-top: 16rpx; }
.cooling { text-align: center; padding: 24rpx 0; }
.cooling-title { font-size: var(--fs-h1); font-weight: 800; color: var(--c-orange); display: block; margin-bottom: 8rpx; }
.cooling-days { font-size: var(--fs-display); font-weight: 800; color: var(--c-ink); display: block; margin-bottom: 24rpx; }
.dev-hint { font-size: 22rpx; color: var(--c-text-hint); display: block; margin-bottom: 12rpx; }
</style>
```

- [ ] **Step 7: 修改 `stores/auth.ts`**

在 user store 中：
- user 类型加 `profile_completed?: boolean` 等
- 加 helper `needsProfileCompletion()` → 返回 logged in && !user.profile_completed

具体改动：READ 现有 `stores/auth.ts`，找到 User 类型 → 加字段；找到 fetchMe 逻辑 → 透传新字段。

- [ ] **Step 8: 修改 `pages/index/index.vue` 引导拦截**

在 `<script setup>` onMounted 加：
```typescript
onMounted(() => {
  if (auth.isLoggedIn() && auth.user && !auth.user.profile_completed) {
    uni.redirectTo({ url: '/pages/auth/complete-profile' })
  }
})
```

- [ ] **Step 9: 修改 `pages/profile/index.vue`**
   - 加 14-17 岁购买 consent checkbox（在购买按钮上方）
   - 在顶部 user 卡下加「账号设置」入口卡片（跳 /pages/account/settings）
   - 顶部如有 `deactivation_scheduled_at`，展示橙色「待注销中，N 天后执行」横幅，提供「撤销」按钮跳 cancel 页

具体改动：
- 模板：加 consent checkbox（在 btn-pay 之前），与 selectedPlan 同步绑定一个 ref `minorConsent`
- onPay 中：把 `minor_consent` 加入 createOrder 调用参数
- 加 settings entry card + cancel banner

- [ ] **Step 10: 提交**

```bash
git add frontend/miniprogram/src/types/api.ts \
        frontend/miniprogram/src/api/compliance.ts \
        frontend/miniprogram/src/pages.json \
        frontend/miniprogram/src/pages/auth/ \
        frontend/miniprogram/src/pages/account/ \
        frontend/miniprogram/src/stores/auth.ts \
        frontend/miniprogram/src/pages/index/index.vue \
        frontend/miniprogram/src/pages/profile/index.vue
git commit -m "feat(compliance): frontend — complete-profile gate, account settings, cancellation flow"
```

---

## Task 5: 集成验证 + 归档 D-073 + Push

**Files:**
- Modify: `docs/决策归档.md`

- [ ] **Step 1: 全量后端测试通过**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/ -q
```

- [ ] **Step 2: live server 端点冒烟**

```bash
uvicorn app.main:app --port 8022 --log-level warning &
sleep 3
curl -s http://localhost:8022/openapi.json | python3 -c "
import json,sys
spec = json.load(sys.stdin)
paths = [p for p in spec['paths'].keys() if 'cancel' in p or 'complete-profile' in p or 'guardian' in p]
print('合规端点:', paths)
"
pkill -f 'uvicorn app.main:app --port 8022' 2>/dev/null || true
```

Expected: 5 个新端点出现

- [ ] **Step 3: 归档 D-073 到 `docs/决策归档.md`（插入在 D-072 之前）**

```markdown
## D-073｜合规两项落地：年龄核验+协议确认 + 账号注销（30天冷静期 + 懒执行匿名化）

**日期：** 2026-05-27
**背景：** P0 上线合规缺口——微信小程序审核与《未成年人网络保护条例》《个人信息保护法 §47》要求平台对未成年用户实施差异化保护，并提供账号注销+数据删除入口。本批为不做无法上架的两项硬合规。
**结论：**
1. **数据层（迁移 0005）：** users 表加 13 列：birth_year/guardian_phone/guardian_verified_at/agreement_version/agreement_agreed_at/profile_completed/minor_purchase_consent_at + deactivation_requested_at/deactivation_scheduled_at/is_anonymized + phone_verify_*（code/purpose/target/expires_at 复用同一组临时态字段）。
2. **年龄分层（§4.1）：** <14岁注册必填监护人手机号 → SMS 授权码 → guardian_verified_at 写入后 profile_completed=true；14-17岁独立注册但首次购买会员强制勾选「已告知监护人并获得同意」，写 minor_purchase_consent_at；≥18岁正常。年龄数据用户自填声明，平台不接入公安实名（与文档约定一致）。
3. **注销三步流程（§4.2）：** 申请→发用户本人手机 SMS→确认（30天冷静期 is_active=false）→冷静期内可 revoke→到期由 `get_current_user` 懒触发 `execute_cancellation_if_due` 匿名化（openid→deleted_<uuid>，nickname/avatar/phone 置 null，is_anonymized=true）。订单/支付记录靠 user_id 关联，user 脱敏后不可反查个人信息，等同 5 年财务合规保留。
4. **SMS Dev Mock：** `sms_provider` 以 `placeholder` 开头 → 不真发短信、验证码固定 `123456` 并记日志，供本地全链路自测；生产替换 `_send_real_sms`。
5. **API：** 5 个新端点 `/auth/complete-profile`、`/auth/guardian-verify`、`/auth/cancel-account/request|confirm|revoke`；`/users/me` 透传 profile_completed/deactivation_scheduled_at/days_until_cancellation；`/memberships` 购买前校验 14-17 minor_consent。
6. **前端：** 新增 3 页——`pages/auth/complete-profile.vue`（首登拦截：出生年份+协议+按需监护人手机+SMS）、`pages/account/settings.vue`（设置入口）、`pages/account/cancel.vue`（注销流程+冷静期倒计时+撤销）。首页 onMounted 检测 `!profile_completed` 时 redirectTo 完善资料；profile 加 14-17 consent 复选框、账号设置入口、待注销提示横幅。
7. **未做（明确遗留）：** 真实 SMS provider 接入（生产前必做）；定时 cron 强制执行注销（当前懒执行：用户不再登录则永远不匿名化，可后续加每日 cron 全量扫一遍）；订单/支付记录 5 年后物理删除（远期）；机构学生注销前通知机构（待机构端就绪后接入）。
**影响范围：** 迁移 0005（users 表 13 新列）；5 个新 API 端点；3 个新前端页 + 引导拦截；测试新增 12 个全 PASS；已推送 GitHub main 分支。

---
```

- [ ] **Step 4: 提交 + push**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add "docs/决策归档.md"
git commit -m "docs: archive D-073 — compliance two items complete"
git push
```

---

## Self-Review

### Spec 覆盖
| 需求文档条目 | 实现位置 |
|------|------|
| §4.1 出生年份自填 | Task 0 birth_year + Task 2 complete_profile |
| §4.1 <14 监护人手机授权码 | Task 2 complete_profile + guardian_verify + Task 1 sms_service |
| §4.1 14-17 首次购买勾选同意 | Task 3 memberships 端点 minor_consent 校验 |
| §4.1 ≥18 无额外限制 | complete_profile 分支 |
| §4.2 注销入口与流程 3 步 | Task 2 cancellation_service + Task 3 5 端点 |
| §4.2 30天冷静期可撤销 | revoke_cancellation + 端点 |
| §4.2 数据匿名化（个人可识别信息）| execute_cancellation_if_due |
| §4.2 订单财务 5 年保留 | 不动 orders 表，user 脱敏后无个人关联 |
| §4.2 7 天内/有效会员期/机构学生特殊情形 | 文档说明，MVP 不实现细分（归档明列遗留） |

### 类型一致性
- `compute_age(birth_year)` 在 service / API / 前端均按 current_year - birth_year 一致计算
- `CompleteProfileResponse.needs_guardian_verify` 与前端 `codeSent` 触发条件一致
- `phone_verify_purpose` 在 guardian_verify / cancel_account 两个场景串行复用（同一时刻只有一个 purpose 待确认）

### Placeholder 扫描
无 TBD/TODO；前端协议页面用 toast 占位（已在 archive 中明列）；真实 SMS provider 留 NotImplementedError。
