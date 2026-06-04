# 机构端切片三：学生账号采购与分配（闭环 3a，D-122）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 机构管理员后台批量采购学生会员（dev-mock 即付）→ 生成激活码 → 学生小程序输码激活得会员 + 归属机构。

**Architecture:** 新表 `institution_purchases` + `activation_codes`（迁移 0020）。采购即 `status=paid`（dev-mock）。激活时造一张已支付合成 `Order` 调 `membership_service.activate_membership` 发 V1 会员，并设 `students.institution_id`。无真实支付。

**Tech Stack:** FastAPI · SQLAlchemy 2.x asyncio · Pydantic v2 · Alembic · pytest · Vue3 · Element Plus · uni-app

---

## 关键约定（实现者必读）

- 后端 python：`/opt/anaconda3/bin/python`；测试从 `backend/` 跑，`../tests/...`，`-p no:randomly`。
- 测试夹具：service 用本地 `db_session`（`_async_session_factory`），见 `tests/services/test_institution_teacher.py`；api 用本地 `client` + `/api/v1/admin/auth/login`（机构管理员）和 `/api/v1/auth/wx-login`（学生，patch `wechat_code2session`），见 `tests/api/test_institution_teacher.py`。
- 迁移命令：`cd backend && DATABASE_URL=$(grep -E '^DATABASE_URL=' .env | cut -d= -f2-) /opt/anaconda3/bin/python -m alembic upgrade head`
- `activate_membership(db, *, order)` 要求 order 已 flush 出 id（Membership.order_id + 通知都用 order.id）。
- 统一响应 `make_ok` + `BaseResponse[T]`；鉴权 `InstAdminDep`（见 institution.py）、`require_role("student")`。
- admin web 构建：`cd frontend/admin && npm run build`；小程序：`cd frontend/miniprogram && npm run build:mp-weixin`。
- 本切片**无真实付费调用**（dev-mock 即付）；无 LLM/媒体。

---

## File Structure

| 文件 | 职责 |
|------|------|
| `backend/alembic/versions/0020_institution_purchase.py` | 迁移：institution_purchases + activation_codes |
| `backend/app/models/d2_payments.py` | +InstitutionPurchase / +ActivationCode |
| `backend/app/models/__init__.py` | 导出两新模型 |
| `backend/app/services/institution_purchase_service.py` | create_purchase / list_purchases / get_purchase_codes |
| `backend/app/services/activation_service.py` | activate_code |
| `backend/app/schemas/institution.py` | +采购/激活相关 schemas |
| `backend/app/api/v1/institution.py` | +采购 3 endpoints |
| `backend/app/api/v1/memberships.py` | +激活码 endpoint |
| `frontend/admin/src/api/institution.ts` | +采购 3 接口 |
| `frontend/admin/src/views/InstitutionPurchases.vue` | 学生采购页 |
| `frontend/admin/src/router/index.ts` · `layouts/MainLayout.vue` | 路由 + 菜单 |
| `frontend/miniprogram/src/api/membership.ts` | +activateCode |
| `frontend/miniprogram/src/pages/membership/activate.vue` | 激活码页 |
| `frontend/miniprogram/src/pages.json` + 会员入口 | 注册页 + 入口 |

---

## Task 1: 迁移 0020 + 模型

**Files:**
- Create: `backend/alembic/versions/0020_institution_purchase.py`
- Modify: `backend/app/models/d2_payments.py`, `backend/app/models/__init__.py`

- [ ] **Step 1: 模型加两类**

在 `backend/app/models/d2_payments.py` 末尾加（文件顶部已 `import uuid`、`import sqlalchemy as sa`、`from .base import Base`，`membership_tier_enum` 已定义于本文件）：

```python
class InstitutionPurchase(Base):
    __tablename__ = "institution_purchases"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    institution_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("institutions.id"), nullable=False
    )
    tier = mapped_column(membership_tier_enum, nullable=False)
    duration_months = mapped_column(sa.Integer, nullable=False)
    quantity = mapped_column(sa.Integer, nullable=False)
    amount_fen = mapped_column(sa.Integer, nullable=False)
    status = mapped_column(sa.String, nullable=False, server_default=sa.text("'paid'"))
    created_by = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )


class ActivationCode(Base):
    __tablename__ = "activation_codes"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = mapped_column(sa.String(12), nullable=False, unique=True)
    purchase_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("institution_purchases.id"), nullable=False
    )
    tier = mapped_column(membership_tier_enum, nullable=False)
    duration_months = mapped_column(sa.Integer, nullable=False)
    status = mapped_column(sa.String, nullable=False, server_default=sa.text("'unused'"))
    used_by = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
    )
    used_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
```

注：确认 `UUID` 与 `mapped_column` 在该文件已 import（D-062 已建 Order/Membership 用同样写法）；若 `UUID` 来自 `from sqlalchemy.dialects.postgresql import UUID`，沿用即可。

- [ ] **Step 2: 导出模型**

`backend/app/models/__init__.py` 第 21 行改为：

```python
from .d2_payments import (  # noqa: F401
    Order, Membership, RefundRecord, InstitutionPurchase, ActivationCode,
)
```

- [ ] **Step 3: 写迁移**

`backend/alembic/versions/0020_institution_purchase.py`：

```python
"""机构学生采购：institution_purchases + activation_codes（D-122）

Revision ID: 0020
Revises: 0019
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

# 复用已存在的 membership_tier 枚举，不重复建类型
_tier = postgresql.ENUM("free", "basic", "pro", "promax", name="membership_tier", create_type=False)


def upgrade() -> None:
    op.create_table(
        "institution_purchases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("institution_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("tier", _tier, nullable=False),
        sa.Column("duration_months", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("amount_fen", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'paid'")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_institution_purchases_institution_id",
                    "institution_purchases", ["institution_id"])
    op.create_table(
        "activation_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(length=12), nullable=False, unique=True),
        sa.Column("purchase_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("institution_purchases.id"), nullable=False),
        sa.Column("tier", _tier, nullable=False),
        sa.Column("duration_months", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'unused'")),
        sa.Column("used_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_activation_codes_purchase_id", "activation_codes", ["purchase_id"])


def downgrade() -> None:
    op.drop_index("ix_activation_codes_purchase_id", table_name="activation_codes")
    op.drop_table("activation_codes")
    op.drop_index("ix_institution_purchases_institution_id", table_name="institution_purchases")
    op.drop_table("institution_purchases")
```

- [ ] **Step 4: 跑迁移 + 验证**

Run: `cd backend && DATABASE_URL=$(grep -E '^DATABASE_URL=' .env | cut -d= -f2-) /opt/anaconda3/bin/python -m alembic upgrade head`
Expected: `Running upgrade 0019 -> 0020`。
Run: `cd backend && /opt/anaconda3/bin/python -c "from app.models import InstitutionPurchase, ActivationCode; print('ok')"`
Expected: `ok`。

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/0020_institution_purchase.py backend/app/models/d2_payments.py backend/app/models/__init__.py
git commit -m "feat(institution): 迁移0020 institution_purchases + activation_codes 模型"
```

---

## Task 2: institution_purchase_service

**Files:**
- Create: `backend/app/services/institution_purchase_service.py`
- Test: `tests/services/test_institution_purchase.py`

- [ ] **Step 1: 写失败测试**

`tests/services/test_institution_purchase.py`：

```python
import uuid
import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.core.exceptions import AppError
from app.models.d1_users import Institution, User
from app.services import institution_purchase_service as svc


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _inst_admin(s, name="A机构"):
    inst = Institution(id=uuid.uuid4(), name=name, contact_phone="1",
                       province_code="11", city_code="1101", address="街")
    s.add(inst)
    await s.flush()
    admin = uuid.uuid4()
    s.add(User(id=admin, openid=f"o:{admin}", role="institution_admin", institution_id=inst.id))
    await s.flush()
    return inst.id, admin


@pytest.mark.asyncio
async def test_create_purchase_generates_codes(db_session):
    inst_id, admin = await _inst_admin(db_session)
    purchase, codes = await svc.create_purchase(
        db_session, institution_id=inst_id, created_by=admin,
        tier="pro", duration_months=12, quantity=3)
    assert purchase.amount_fen == 3000 * 12 * 3
    assert purchase.status == "paid"
    assert len(codes) == 3
    assert all(len(c.code) == 12 for c in codes)


@pytest.mark.asyncio
async def test_get_purchase_codes_cross_institution_404(db_session):
    a_id, a_admin = await _inst_admin(db_session, "A")
    b_id, b_admin = await _inst_admin(db_session, "B")
    purchase, _ = await svc.create_purchase(
        db_session, institution_id=b_id, created_by=b_admin,
        tier="basic", duration_months=1, quantity=1)
    with pytest.raises(AppError):
        await svc.get_purchase_codes(db_session, institution_id=a_id, purchase_id=purchase.id)


@pytest.mark.asyncio
async def test_list_purchases(db_session):
    inst_id, admin = await _inst_admin(db_session)
    await svc.create_purchase(db_session, institution_id=inst_id, created_by=admin,
                              tier="basic", duration_months=1, quantity=2)
    rows = await svc.list_purchases(db_session, institution_id=inst_id)
    assert len(rows) == 1
    _, used, total = rows[0]
    assert used == 0 and total == 2
```

- [ ] **Step 2: 跑测试看失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_institution_purchase.py -p no:randomly -q`
Expected: FAIL（模块不存在）。

- [ ] **Step 3: 实现 service**

`backend/app/services/institution_purchase_service.py`：

```python
"""机构学生采购 service（D-122）：下单 + 生成激活码 + 采购记录。"""
from __future__ import annotations

import random
import string
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d2_payments import ActivationCode, InstitutionPurchase

_CODE_CHARS = string.ascii_uppercase + string.digits
_TIER_MONTHLY_FEN = {"basic": 1500, "pro": 3000, "promax": 5000}


async def _unique_code(db: AsyncSession) -> str:
    for _ in range(10):
        code = "".join(random.choices(_CODE_CHARS, k=12))
        r = await db.execute(select(ActivationCode).where(ActivationCode.code == code))
        if r.scalar_one_or_none() is None:
            return code
    raise AppError(code=500, message="激活码生成失败，请重试")


async def create_purchase(
    db: AsyncSession, *, institution_id: uuid.UUID, created_by: uuid.UUID,
    tier: str, duration_months: int, quantity: int,
) -> tuple[InstitutionPurchase, list[ActivationCode]]:
    if tier not in _TIER_MONTHLY_FEN:
        raise AppError(code=400, message="档位无效")
    if duration_months < 1 or quantity < 1:
        raise AppError(code=400, message="时长/数量必须 ≥ 1")

    amount_fen = _TIER_MONTHLY_FEN[tier] * duration_months * quantity
    purchase = InstitutionPurchase(
        id=uuid.uuid4(), institution_id=institution_id, tier=tier,  # type: ignore[arg-type]
        duration_months=duration_months, quantity=quantity,
        amount_fen=amount_fen, status="paid", created_by=created_by,
    )
    db.add(purchase)
    await db.flush()

    codes: list[ActivationCode] = []
    for _ in range(quantity):
        c = ActivationCode(
            id=uuid.uuid4(), code=await _unique_code(db), purchase_id=purchase.id,
            tier=tier, duration_months=duration_months, status="unused",  # type: ignore[arg-type]
        )
        db.add(c)
        codes.append(c)
    await db.flush()
    return purchase, codes


async def list_purchases(
    db: AsyncSession, *, institution_id: uuid.UUID
) -> list[tuple[InstitutionPurchase, int, int]]:
    purchases = (await db.execute(
        select(InstitutionPurchase)
        .where(InstitutionPurchase.institution_id == institution_id)
        .order_by(InstitutionPurchase.created_at.desc())
    )).scalars().all()
    out = []
    for p in purchases:
        total = (await db.execute(
            select(func.count()).select_from(ActivationCode)
            .where(ActivationCode.purchase_id == p.id)
        )).scalar_one()
        used = (await db.execute(
            select(func.count()).select_from(ActivationCode)
            .where(ActivationCode.purchase_id == p.id, ActivationCode.status == "used")
        )).scalar_one()
        out.append((p, used, total))
    return out


async def get_purchase_codes(
    db: AsyncSession, *, institution_id: uuid.UUID, purchase_id: uuid.UUID
) -> list[ActivationCode]:
    p = (await db.execute(
        select(InstitutionPurchase).where(
            InstitutionPurchase.id == purchase_id,
            InstitutionPurchase.institution_id == institution_id,
        )
    )).scalar_one_or_none()
    if p is None:
        raise AppError(code=404, message="采购单不存在或不属于本机构")
    codes = (await db.execute(
        select(ActivationCode).where(ActivationCode.purchase_id == purchase_id)
        .order_by(ActivationCode.created_at.asc())
    )).scalars().all()
    return list(codes)
```

- [ ] **Step 4: 跑测试看通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_institution_purchase.py -p no:randomly -q`
Expected: 3 passed。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/institution_purchase_service.py tests/services/test_institution_purchase.py
git commit -m "feat(institution): 采购下单+生成激活码+采购记录 service"
```

---

## Task 3: activation_service.activate_code

**Files:**
- Create: `backend/app/services/activation_service.py`
- Test: `tests/services/test_activation.py`

- [ ] **Step 1: 写失败测试**

`tests/services/test_activation.py`：

```python
import uuid
import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.core.exceptions import AppError
from app.models.d1_users import Institution, Student, User
from app.services import activation_service, institution_purchase_service as psvc
from app.services import membership_service


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _setup(db_session):
    inst = Institution(id=uuid.uuid4(), name="A", contact_phone="1",
                       province_code="11", city_code="1101", address="街")
    db_session.add(inst)
    await db_session.flush()
    admin = uuid.uuid4()
    db_session.add(User(id=admin, openid=f"o:{admin}", role="institution_admin", institution_id=inst.id))
    sid = uuid.uuid4()
    db_session.add(User(id=sid, openid=f"o:{sid}", role="student"))
    await db_session.flush()
    db_session.add(Student(id=sid))
    await db_session.flush()
    _, codes = await psvc.create_purchase(
        db_session, institution_id=inst.id, created_by=admin,
        tier="pro", duration_months=6, quantity=1)
    return inst.id, sid, codes[0].code


@pytest.mark.asyncio
async def test_activate_code_grants_membership(db_session):
    inst_id, sid, code = await _setup(db_session)
    await activation_service.activate_code(db_session, student_user_id=sid, code=code)
    m = await membership_service.get_active_membership(db_session, user_id=sid)
    assert m is not None and str(m.tier) == "pro"
    stu = await db_session.get(Student, sid)
    assert stu.institution_id == inst_id


@pytest.mark.asyncio
async def test_activate_used_code_rejected(db_session):
    _, sid, code = await _setup(db_session)
    await activation_service.activate_code(db_session, student_user_id=sid, code=code)
    # 另一个学生用同码
    sid2 = uuid.uuid4()
    db_session.add(User(id=sid2, openid=f"o:{sid2}", role="student"))
    await db_session.flush()
    db_session.add(Student(id=sid2))
    await db_session.flush()
    with pytest.raises(AppError):
        await activation_service.activate_code(db_session, student_user_id=sid2, code=code)


@pytest.mark.asyncio
async def test_activate_bad_code(db_session):
    _, sid, _ = await _setup(db_session)
    with pytest.raises(AppError):
        await activation_service.activate_code(db_session, student_user_id=sid, code="ZZZZZZZZZZZZ")
```

- [ ] **Step 2: 跑测试看失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_activation.py -p no:randomly -q`
Expected: FAIL（模块不存在）。

- [ ] **Step 3: 实现 activate_code**

`backend/app/services/activation_service.py`：

```python
"""激活码兑换 service（D-122）：学生输码 → 发会员 + 归属机构。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d1_users import Student
from app.models.d2_payments import ActivationCode, InstitutionPurchase, Order
from app.services import membership_service


async def activate_code(
    db: AsyncSession, *, student_user_id: uuid.UUID, code: str
):
    now = datetime.now(timezone.utc)
    ac = (await db.execute(
        select(ActivationCode).where(
            ActivationCode.code == code, ActivationCode.status == "unused"
        )
    )).scalar_one_or_none()
    if ac is None:
        raise AppError(code=400, message="激活码无效或已使用")

    purchase = await db.get(InstitutionPurchase, ac.purchase_id)
    if purchase is None:
        raise AppError(code=400, message="激活码对应采购单不存在")

    student = await db.get(Student, student_user_id)
    if student is None:
        raise AppError(code=404, message="学生档案不存在")
    if student.institution_id is not None:
        raise AppError(code=409, message="您已是机构学生，不能重复激活")

    # 造一张已支付合成 Order（机构采购激活，不走真实支付）
    order = Order(
        id=uuid.uuid4(),
        order_no=f"ACT{now.strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6].upper()}",
        payer_id=purchase.created_by,
        beneficiary_id=student_user_id,
        order_type="new",  # type: ignore[arg-type]
        tier=ac.tier,
        duration_months=ac.duration_months,
        amount_fen=0,
        status="paid",  # type: ignore[arg-type]
    )
    db.add(order)
    await db.flush()

    membership = await membership_service.activate_membership(db, order=order)

    student.institution_id = purchase.institution_id
    ac.status = "used"
    ac.used_by = student_user_id
    ac.used_at = now
    await db.flush()
    return membership
```

- [ ] **Step 4: 跑测试看通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_activation.py -p no:randomly -q`
Expected: 3 passed。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/activation_service.py tests/services/test_activation.py
git commit -m "feat(institution): 激活码兑换 activate_code（发会员+归属机构）service"
```

---

## Task 4: schemas + API（管理员 3 + 学生 1）

**Files:**
- Modify: `backend/app/schemas/institution.py`, `backend/app/api/v1/institution.py`, `backend/app/api/v1/memberships.py`
- Test: `tests/api/test_institution_purchase.py`

- [ ] **Step 1: schemas**

在 `backend/app/schemas/institution.py` 末尾加：

```python
class PurchaseCreateRequest(BaseModel):
    tier: str
    duration_months: int
    quantity: int


class ActivationCodeOut(BaseModel):
    code: str
    status: str
    used_at: dt.datetime | None = None


class PurchaseOut(BaseModel):
    id: uuid.UUID
    tier: str
    duration_months: int
    quantity: int
    amount_fen: int
    status: str
    created_at: dt.datetime
    codes: list[ActivationCodeOut]


class PurchaseListItem(BaseModel):
    id: uuid.UUID
    tier: str
    duration_months: int
    quantity: int
    amount_fen: int
    status: str
    created_at: dt.datetime
    used_count: int
    total_count: int


class ActivateCodeRequest(BaseModel):
    code: str
```

- [ ] **Step 2: 写失败 api 测试**

`tests/api/test_institution_purchase.py`：

```python
import uuid
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from httpx import ASGITransport, AsyncClient

from app.core.database import _async_session_factory
from app.main import app
from app.models.d1_users import Institution, Student, User
from app.services import admin_auth_service


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _setup_admin(username, inst_name="机构A"):
    async with _async_session_factory() as s:
        inst = Institution(id=uuid.uuid4(), name=inst_name, contact_phone="1",
                           province_code="11", city_code="1101", address="街")
        s.add(inst)
        await s.flush()
        await admin_auth_service.create_institution_admin(
            s, username=username, password="pw123456", institution_id=inst.id)
        await s.commit()
        return inst.id


async def _admin_login(client, username):
    r = await client.post("/api/v1/admin/auth/login",
                          json={"username": username, "password": "pw123456"})
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


async def _student_login(client, openid):
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as m:
        m.return_value = {"openid": openid}
        r = await client.post("/api/v1/auth/wx-login", json={"code": "x"})
    h = {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
    me = (await client.get("/api/v1/users/me", headers=h)).json()["data"]
    uid = uuid.UUID(me["id"])
    async with _async_session_factory() as s:
        u = await s.get(User, uid)
        u.role = "student"
        s.add(Student(id=uid))
        await s.commit()
    return h, uid


@pytest.mark.asyncio
async def test_purchase_to_activation_flow(client):
    uname = f"ia_{uuid.uuid4().hex[:6]}"
    await _setup_admin(uname)
    ah = await _admin_login(client, uname)

    r = await client.post("/api/v1/institution/purchases", headers=ah,
                          json={"tier": "pro", "duration_months": 6, "quantity": 2})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["quantity"] == 2 and len(data["codes"]) == 2
    code = data["codes"][0]["code"]

    rows = (await client.get("/api/v1/institution/purchases", headers=ah)).json()["data"]
    assert rows[0]["total_count"] == 2 and rows[0]["used_count"] == 0

    sh, sid = await _student_login(client, f"s_{uuid.uuid4().hex[:6]}")
    r = await client.post("/api/v1/memberships/activate-code", headers=sh, json={"code": code})
    assert r.status_code == 200

    me = (await client.get("/api/v1/memberships/me", headers=sh)).json()["data"]
    assert me["tier"] == "pro"


@pytest.mark.asyncio
async def test_activate_used_code_400(client):
    uname = f"ia_{uuid.uuid4().hex[:6]}"
    await _setup_admin(uname)
    ah = await _admin_login(client, uname)
    code = (await client.post("/api/v1/institution/purchases", headers=ah,
            json={"tier": "basic", "duration_months": 1, "quantity": 1})).json()["data"]["codes"][0]["code"]
    sh, _ = await _student_login(client, f"s_{uuid.uuid4().hex[:6]}")
    await client.post("/api/v1/memberships/activate-code", headers=sh, json={"code": code})
    sh2, _ = await _student_login(client, f"s_{uuid.uuid4().hex[:6]}")
    r = await client.post("/api/v1/memberships/activate-code", headers=sh2, json={"code": code})
    assert r.status_code == 400
```

- [ ] **Step 3: 跑测试看失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/api/test_institution_purchase.py -p no:randomly -q`
Expected: FAIL（endpoint 不存在）。

- [ ] **Step 4: 管理员 endpoints**

在 `backend/app/api/v1/institution.py`：import 区把 institution schema import 扩为：

```python
from app.schemas.institution import (
    ActivationCodeOut, InstitutionOverviewOut, InstitutionProfileOut,
    InstitutionProfileUpdate, InstitutionTeacherOut, InviteCodeOut,
    PurchaseCreateRequest, PurchaseListItem, PurchaseOut,
)
from app.services import institution_purchase_service
```

（保留已有 `from app.services import institution_service`。）

文件末尾加：

```python
@router.post("/purchases", response_model=BaseResponse[PurchaseOut])
async def create_purchase(body: PurchaseCreateRequest, db: DbDep, admin: InstAdminDep):
    inst_id = _require_inst(admin)
    purchase, codes = await institution_purchase_service.create_purchase(
        db, institution_id=inst_id, created_by=admin.id,
        tier=body.tier, duration_months=body.duration_months, quantity=body.quantity)
    await db.commit()
    return make_ok(PurchaseOut(
        id=purchase.id, tier=str(purchase.tier), duration_months=purchase.duration_months,
        quantity=purchase.quantity, amount_fen=purchase.amount_fen, status=purchase.status,
        created_at=purchase.created_at,
        codes=[ActivationCodeOut(code=c.code, status=c.status, used_at=c.used_at) for c in codes],
    ))


@router.get("/purchases", response_model=BaseResponse[list[PurchaseListItem]])
async def list_purchases(db: DbDep, admin: InstAdminDep):
    inst_id = _require_inst(admin)
    rows = await institution_purchase_service.list_purchases(db, institution_id=inst_id)
    return make_ok([
        PurchaseListItem(
            id=p.id, tier=str(p.tier), duration_months=p.duration_months,
            quantity=p.quantity, amount_fen=p.amount_fen, status=p.status,
            created_at=p.created_at, used_count=used, total_count=total,
        ) for p, used, total in rows
    ])


@router.get("/purchases/{purchase_id}/codes", response_model=BaseResponse[list[ActivationCodeOut]])
async def get_purchase_codes(purchase_id: uuid.UUID, db: DbDep, admin: InstAdminDep):
    inst_id = _require_inst(admin)
    codes = await institution_purchase_service.get_purchase_codes(
        db, institution_id=inst_id, purchase_id=purchase_id)
    return make_ok([ActivationCodeOut(code=c.code, status=c.status, used_at=c.used_at) for c in codes])
```

- [ ] **Step 5: 学生激活 endpoint**

在 `backend/app/api/v1/memberships.py`：import 区补 `from app.core.security import require_role`、`from app.schemas.institution import ActivateCodeRequest`、`from app.services import activation_service`；文件末尾加：

```python
StudentDep = Annotated[User, Depends(require_role("student"))]


@router.post("/activate-code", response_model=BaseResponse[dict])
async def activate_code(body: ActivateCodeRequest, db: DbDep, current_user: StudentDep):
    await get_rls_db(db, str(current_user.id))
    m = await activation_service.activate_code(
        db, student_user_id=current_user.id, code=body.code)
    await db.commit()
    tier = str(m.tier) if m is not None else "free"
    expires = m.expires_at.isoformat() if (m is not None and m.expires_at) else None
    return make_ok({"tier": tier, "expires_at": expires})
```

- [ ] **Step 6: 跑测试看通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/api/test_institution_purchase.py -p no:randomly -q`
Expected: 2 passed。

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/institution.py backend/app/api/v1/institution.py backend/app/api/v1/memberships.py tests/api/test_institution_purchase.py
git commit -m "feat(institution): 采购/激活码 API（管理员下单看码 + 学生激活）"
```

---

## Task 5: 后端全量回归

- [ ] **Step 1: 跑全量**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests -p no:randomly -q`
Expected: 新增 8 测试全过；已知偶发污染项若红，隔离复跑确认通过。

- [ ] **Step 2: 偶发项隔离复跑（如需）**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/api/test_wrong_questions.py::test_create_wrong_question_api -p no:randomly -q`
Expected: PASS。

---

## Task 6: admin web 学生采购页

**Files:**
- Modify: `frontend/admin/src/api/institution.ts`, `router/index.ts`, `layouts/MainLayout.vue`
- Create: `frontend/admin/src/views/InstitutionPurchases.vue`

- [ ] **Step 1: api 层**

在 `frontend/admin/src/api/institution.ts` 末尾加：

```typescript
export interface ActivationCode { code: string; status: string; used_at: string | null }
export interface PurchaseDetail {
  id: string; tier: string; duration_months: number; quantity: number
  amount_fen: number; status: string; created_at: string; codes: ActivationCode[]
}
export interface PurchaseListItem {
  id: string; tier: string; duration_months: number; quantity: number
  amount_fen: number; status: string; created_at: string
  used_count: number; total_count: number
}

export function createPurchase(data: { tier: string; duration_months: number; quantity: number }): Promise<PurchaseDetail> {
  return unwrap<PurchaseDetail>(request.post('/institution/purchases', data))
}
export function listPurchases(): Promise<PurchaseListItem[]> {
  return unwrap<PurchaseListItem[]>(request.get('/institution/purchases'))
}
export function getPurchaseCodes(purchaseId: string): Promise<ActivationCode[]> {
  return unwrap<ActivationCode[]>(request.get(`/institution/purchases/${purchaseId}/codes`))
}
```

- [ ] **Step 2: 采购页**

`frontend/admin/src/views/InstitutionPurchases.vue`：

```vue
<script setup lang="ts">
import { onMounted, reactive, ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import {
  createPurchase, listPurchases, getPurchaseCodes,
  type PurchaseListItem, type ActivationCode,
} from '../api/institution'

const TIER_FEN: Record<string, number> = { basic: 1500, pro: 3000, promax: 5000 }
const form = reactive({ tier: 'pro', duration_months: 6, quantity: 1 })
const purchases = ref<PurchaseListItem[]>([])
const codes = ref<ActivationCode[]>([])
const codesTitle = ref('')

const estimate = computed(() =>
  ((TIER_FEN[form.tier] || 0) * form.duration_months * form.quantity / 100).toFixed(2))

async function load() { purchases.value = await listPurchases() }

async function submit() {
  const d = await createPurchase({ ...form })
  ElMessage.success(`已生成 ${d.codes.length} 个激活码`)
  codes.value = d.codes
  codesTitle.value = `本次采购（${d.tier} / ${d.duration_months}个月 / ${d.quantity}个）`
  await load()
}

async function viewCodes(p: PurchaseListItem) {
  codes.value = await getPurchaseCodes(p.id)
  codesTitle.value = `采购 ${p.created_at.slice(0, 10)}（${p.tier}）`
}

onMounted(load)
</script>

<template>
  <div>
    <h2 class="title">学生采购</h2>
    <el-card style="margin-bottom: 16px">
      <el-form inline>
        <el-form-item label="档位">
          <el-select v-model="form.tier" style="width: 120px">
            <el-option label="基础" value="basic" />
            <el-option label="Pro" value="pro" />
            <el-option label="ProMax" value="promax" />
          </el-select>
        </el-form-item>
        <el-form-item label="时长(月)">
          <el-input-number v-model="form.duration_months" :min="1" />
        </el-form-item>
        <el-form-item label="数量">
          <el-input-number v-model="form.quantity" :min="1" />
        </el-form-item>
        <el-form-item label="预估金额">
          <span>¥ {{ estimate }}</span>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="submit">采购（dev-mock 即付）</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-table :data="purchases" border style="margin-bottom: 16px">
      <el-table-column prop="tier" label="档位" />
      <el-table-column prop="duration_months" label="时长(月)" />
      <el-table-column prop="quantity" label="数量" />
      <el-table-column label="金额(元)">
        <template #default="{ row }">{{ (row.amount_fen / 100).toFixed(2) }}</template>
      </el-table-column>
      <el-table-column label="已用/总数">
        <template #default="{ row }">{{ row.used_count }} / {{ row.total_count }}</template>
      </el-table-column>
      <el-table-column label="操作">
        <template #default="{ row }">
          <el-button text type="primary" @click="viewCodes(row)">查看激活码</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-card v-if="codes.length">
      <div class="codes-title">{{ codesTitle }}</div>
      <el-tag v-for="c in codes" :key="c.code" :type="c.status === 'used' ? 'info' : 'success'" class="code-tag">
        {{ c.code }}{{ c.status === 'used' ? '（已用）' : '' }}
      </el-tag>
    </el-card>
  </div>
</template>

<style scoped>
.title { margin: 0 0 16px; font-size: 18px; }
.codes-title { margin-bottom: 12px; color: #555; }
.code-tag { margin: 4px 8px 4px 0; font-family: monospace; }
</style>
```

- [ ] **Step 3: 路由 + 菜单**

`router/index.ts` children 内（机构 teachers 之后）加：

```typescript
        { path: 'institution/purchases', name: 'institution-purchases', component: () => import('../views/InstitutionPurchases.vue'), meta: { roles: ['institution_admin'] } },
```

`layouts/MainLayout.vue` 的 institution_admin 分支内加：

```html
          <el-menu-item index="/institution/purchases">学生采购</el-menu-item>
```

- [ ] **Step 4: 构建**

Run: `cd frontend/admin && npm run build`
Expected: 构建成功。

- [ ] **Step 5: Commit**

```bash
git add frontend/admin/src/api/institution.ts frontend/admin/src/views/InstitutionPurchases.vue frontend/admin/src/router/index.ts frontend/admin/src/layouts/MainLayout.vue
git commit -m "feat(institution-web): 学生采购页（下单/激活码/采购记录）"
```

---

## Task 7: 小程序学生激活页

**Files:**
- Modify: `frontend/miniprogram/src/api/membership.ts`, `pages.json`, 会员/个人中心入口
- Create: `frontend/miniprogram/src/pages/membership/activate.vue`

- [ ] **Step 1: api**

在 `frontend/miniprogram/src/api/membership.ts` 末尾加（`request` 导入照抄文件现有风格）：

```typescript
export function activateCode(code: string) {
  return request('/api/v1/memberships/activate-code', { method: 'POST', data: { code } })
}
```

- [ ] **Step 2: 激活页**

`frontend/miniprogram/src/pages/membership/activate.vue`：

```vue
<template>
  <view class="page">
    <view class="hint">输入机构发放的激活码，激活学生会员</view>
    <input class="code-input" v-model="code" placeholder="激活码" maxlength="12" />
    <button class="btn" :disabled="code.length < 6" @tap="submit">激活</button>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { activateCode } from '@/api/membership'

const code = ref('')

async function submit() {
  try {
    await activateCode(code.value.trim().toUpperCase())
    uni.showToast({ title: '激活成功', icon: 'success' })
    setTimeout(() => uni.navigateBack(), 1200)
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'none' })
  }
}
</script>

<style scoped>
.page { padding: 48rpx; }
.hint { color: var(--c-text-second); font-size: 28rpx; margin-bottom: 32rpx; }
.code-input { background: var(--c-bg-card); border-radius: var(--r-md); padding: 24rpx; font-size: 34rpx; letter-spacing: 6rpx; text-align: center; }
.btn { margin-top: 48rpx; background: var(--c-primary); color: var(--c-ink); font-weight: 700; border-radius: var(--r-btn); }
</style>
```

> 若 `frontend/miniprogram/src/api/membership.ts` 不存在，则在 `api/` 下沿用其它 api 文件的 `request` 导入新建该文件，仅含上面的 `activateCode`。

- [ ] **Step 3: 注册页 + 入口**

`pages.json` 的 pages 数组加：

```json
    { "path": "pages/membership/activate", "style": { "navigationBarTitleText": "激活码" } }
```

在会员页或个人中心（`pages/profile/index.vue`）加按钮：

```html
<button class="entry-btn" @tap="() => uni.navigateTo({ url: '/pages/membership/activate' })">输入激活码</button>
```

（样式照抄该页现有按钮 class。）

- [ ] **Step 4: 构建**

Run: `cd frontend/miniprogram && npm run build:mp-weixin`
Expected: 构建成功。

- [ ] **Step 5: Commit**

```bash
git add frontend/miniprogram/src/api/membership.ts frontend/miniprogram/src/pages/membership/activate.vue frontend/miniprogram/src/pages.json frontend/miniprogram/src/pages/profile/index.vue
git commit -m "feat(student-mp): 激活码兑换页 + 入口"
```

---

## Task 8: 归档 D-122 + 清单同步

**Files:**
- Modify: `docs/决策归档.md`, `docs/上线前清单.md`

- [ ] **Step 1: 归档**

在 `docs/决策归档.md` 顶部按既有格式加 D-122（日期 2026-06-04 / 背景 / 结论 / 测试 / 影响范围 / 未做 / 相关 D-120 D-121、需求 5B.5）。

- [ ] **Step 2: 清单**

`docs/上线前清单.md` 机构端表加 M5（学生采购：下单→激活码→学生激活得会员）；dev-mock 表注明机构采购为 dev-mock 即付（prod 需真实支付对接）。

- [ ] **Step 3: Commit**

```bash
git add docs/决策归档.md docs/上线前清单.md docs/superpowers/plans/2026-06-04-institution-purchase.md
git commit -m "docs: 归档 D-122 学生账号采购与分配（闭环3a）"
```

---

## Self-Review 结论

- **Spec 覆盖**：迁移+模型→Task1；采购 service→Task2；激活 service→Task3；schemas+4 endpoints→Task4；回归→Task5；admin 采购页→Task6；学生激活页→Task7；归档→Task8。全覆盖。
- **占位符**：无 TBD；每个改码步骤含完整代码；前端少数“照抄现有风格”处点名了参照文件。
- **类型一致**：`create_purchase(institution_id,created_by,tier,duration_months,quantity)→(purchase,codes)`、`list_purchases→list[(p,used,total)]`、`get_purchase_codes(institution_id,purchase_id)`、`activate_code(student_user_id,code)` 在 service/api/test 三处一致；`PurchaseOut/PurchaseListItem/ActivationCodeOut` 字段在 api 拼装、前端 interface、测试断言一致；激活码 12 位、`status` unused/used、amount_fen=月单价×月×量（pro=3000）三处一致。
