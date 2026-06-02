# 老师端 P0 三项实施计划（Plan K）

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development

**Goal:** 补齐老师端 3 个 P0 缺口：
1. **注册认证审核流程**（cert 提交 + 审核 + 等待期权限控制）
2. **老师查看学生完整学情报告**（复用学生侧 diagnosis_service）
3. **班级综合报告**（班级 CRUD + 全班聚合诊断）

依据需求文档 P0 老师端清单及 §4.7 老师认证审核相关条款。

**Architecture:**
- 数据层：**无新迁移**——Teacher 表已含 `cert_status` / `cert_doc_url`；Class/ClassStudent 已在迁移 0001。
- 服务：`teacher_service` 扩展 cert 提交/审核 + 全部写操作加 cert_status="certified" 权限 gate；新建 `class_service` 管班级与综合报告。
- API：`/teacher/cert/*`、`/teacher/students/{id}/diagnosis-report`、`/teacher/classes/*`、`/admin/teachers/{id}/review`。
- 权限：cert 未认证（uncertified/pending/rejected）老师**只能浏览本人 profile + cert 上传**，不能生成邀请码、查看学生、批注、管班级。dev 模式开关 `auto_approve_teacher_cert` 可自动通过（默认 True，避免本地自测被卡）。
- 前端：教师中心顶部加认证状态条；学生详情加学情报告入口；新增班级管理 + 班级详情/报告页。

**Tech Stack:** FastAPI · SQLAlchemy 2.x asyncio · Pydantic v2 · pytest-asyncio STRICT · uni-app Vue3

---

## File Structure

```
新增后端:
  backend/app/services/class_service.py
  backend/app/schemas/classes.py
  backend/app/api/v1/admin.py                  # admin 审核端点（与 teacher router 分离）
  tests/api/test_teacher_p0.py                 # 本批次综合测试

修改后端:
  backend/app/services/teacher_service.py       # +submit_cert/+权限 gate helper
  backend/app/api/v1/teacher.py                 # +cert 端点 +diagnosis 端点 +classes 端点；写操作前 gate
  backend/app/api/v1/router.py                  # +admin_router
  backend/app/schemas/teacher.py                # +CertSubmitRequest/+TeacherProfileOut 扩字段
  backend/app/core/config.py                    # +auto_approve_teacher_cert
  backend/app/core/security.py                  # +require_role helper（admin gate 用）

新增前端:
  frontend/miniprogram/src/api/classes.ts
  frontend/miniprogram/src/pages/teacher/cert.vue
  frontend/miniprogram/src/pages/teacher/student-diagnosis.vue
  frontend/miniprogram/src/pages/teacher/classes.vue
  frontend/miniprogram/src/pages/teacher/class-detail.vue

修改前端:
  frontend/miniprogram/src/api/teacher.ts       # +submitCert/+studentDiagnosis
  frontend/miniprogram/src/types/api.ts         # +类型
  frontend/miniprogram/src/pages.json           # +4 页
  frontend/miniprogram/src/pages/teacher/students.vue        # 顶部加认证状态条 + 班级入口
  frontend/miniprogram/src/pages/teacher/student-detail.vue  # 加"查看学情报告"入口
```

**Key model/fact 确认:**
- Teacher.cert_status enum: `"uncertified" | "pending" | "certified" | "rejected"` (Teacher 表已有)
- Teacher.cert_doc_url: 已存在
- d7_teacher.Class: id/teacher_id/institution_id/name/created_at/updated_at
- d7_teacher.ClassStudent: 复合 PK (class_id, student_id) + joined_at
- User.role enum 已含 `platform_admin`
- 现有 teacher_service 测试 11 个（含 D-069 add_comment 等）—— 不能破坏

---

## Task 0: cert 提交 + 审核 + 权限 gate

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/core/security.py`
- Modify: `backend/app/schemas/teacher.py`
- Modify: `backend/app/services/teacher_service.py`
- Modify: `backend/app/api/v1/teacher.py`
- Create: `backend/app/api/v1/admin.py`
- Modify: `backend/app/api/v1/router.py`
- Create: `tests/api/test_teacher_p0.py`

- [ ] **Step 1: config.py 加开关**

在 Settings 类找合适位置加：
```python
    auto_approve_teacher_cert: bool = True  # dev 自动通过；生产置 False，由 admin 审核
```

- [ ] **Step 2: security.py 加 require_role helper**

末尾追加：
```python
from typing import Callable, Awaitable

def require_role(*allowed_roles: str) -> Callable[..., Awaitable[User]]:
    """生成一个依赖：要求 current_user.role 在 allowed_roles 中，否则 403。"""
    async def _dep(current_user: User = Depends(get_current_user)) -> User:
        if str(current_user.role) not in allowed_roles:
            raise AppError(code=403, message="权限不足")
        return current_user
    return _dep
```
（如果 `from app.core.exceptions import AppError` 未 import 则加）

- [ ] **Step 3: schemas/teacher.py 扩展**

追加 + 修改 `TeacherProfileOut` 加字段：
```python
class CertSubmitRequest(BaseModel):
    cert_doc_url: str = Field(..., min_length=1, description="证书文档 URL（已上传至 COS）")


class CertReviewRequest(BaseModel):
    approve: bool
    reason: str | None = Field(None, description="拒绝时填理由")
```

`TeacherProfileOut` 加 `cert_doc_url: str | None = None`（如果已有 cert_status 字段就不动）。

- [ ] **Step 4: teacher_service.py 加 submit_cert + ensure_certified helper**

末尾追加：
```python
async def submit_cert(
    db: AsyncSession,
    *,
    teacher: Teacher,
    cert_doc_url: str,
) -> Teacher:
    """老师提交认证材料。cert_status uncertified/rejected → pending。
    若 settings.auto_approve_teacher_cert=True 则直接 certified（dev 便利）。
    """
    from app.core.config import settings
    teacher.cert_doc_url = cert_doc_url
    if settings.auto_approve_teacher_cert:
        teacher.cert_status = "certified"  # type: ignore[assignment]
    else:
        teacher.cert_status = "pending"  # type: ignore[assignment]
    await db.flush()
    return teacher


async def review_cert(
    db: AsyncSession,
    *,
    teacher_id: uuid.UUID,
    approve: bool,
    reason: str | None = None,
) -> Teacher:
    """admin 审核老师认证。"""
    r = await db.execute(select(Teacher).where(Teacher.id == teacher_id))
    teacher = r.scalar_one_or_none()
    if teacher is None:
        raise AppError(code=404, message="老师不存在")
    teacher.cert_status = ("certified" if approve else "rejected")  # type: ignore[assignment]
    await db.flush()
    return teacher


def ensure_certified(teacher: Teacher | None) -> None:
    """权限 gate：未认证（uncertified/pending/rejected）禁止教师写操作。"""
    if teacher is None or str(teacher.cert_status) != "certified":
        raise AppError(code=403, message="老师认证未通过，无法执行此操作")
```

- [ ] **Step 5: teacher.py API 加 cert 端点 + 写操作前 gate**

在 `backend/app/api/v1/teacher.py`：

a) 新增端点：
```python
from app.schemas.teacher import CertSubmitRequest

@router.post("/cert/submit", response_model=BaseResponse[TeacherProfileOut])
async def submit_cert_api(body: CertSubmitRequest, db: DbDep, current_user: UserDep):
    if str(current_user.role) != "teacher":
        raise AppError(code=403, message="请先成为教师")
    await get_rls_db(db, str(current_user.id))
    # 查 Teacher 扩展记录
    from sqlalchemy import select
    from app.models.d1_users import Teacher
    r = await db.execute(select(Teacher).where(Teacher.id == current_user.id))
    teacher = r.scalar_one_or_none()
    if teacher is None:
        raise AppError(code=400, message="教师扩展记录缺失，请先调用 /teacher/profile")
    teacher = await teacher_service.submit_cert(db, teacher=teacher, cert_doc_url=body.cert_doc_url)
    await db.commit()
    return make_ok(TeacherProfileOut(
        user_id=teacher.id, subject=teacher.subject,
        cert_status=str(teacher.cert_status),
        cert_doc_url=teacher.cert_doc_url,
        max_students=teacher.max_students,
    ))
```

b) `become_teacher` 端点返回 TeacherProfileOut 时也要带 `cert_doc_url=teacher.cert_doc_url`。

c) 在 `create_invite_code` / `add_comment` / `get_my_students` / `get_student_wrong_questions`（所有需要"老师身份"的写/敏感读端点）前面加：
```python
# 取 Teacher 记录并校验 certified
from sqlalchemy import select as _select
from app.models.d1_users import Teacher
_r = await db.execute(_select(Teacher).where(Teacher.id == current_user.id))
teacher_service.ensure_certified(_r.scalar_one_or_none())
```
（提取为 dependency 更优，但行内 5 行也可）。`teacher_service.ensure_certified` 不通过会抛 AppError(403)。

- [ ] **Step 6: 创建 `backend/app/api/v1/admin.py`**

```python
"""平台管理员 API（D-075 / P0 老师端）。"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_role
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.teacher import CertReviewRequest, TeacherProfileOut
from app.services import teacher_service

router = APIRouter(prefix="/admin", tags=["admin"])

AdminDep = Annotated[User, Depends(require_role("platform_admin"))]
DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.post("/teachers/{teacher_id}/review", response_model=BaseResponse[TeacherProfileOut])
async def review_teacher_cert(
    teacher_id: uuid.UUID,
    body: CertReviewRequest,
    db: DbDep,
    admin: AdminDep,
):
    teacher = await teacher_service.review_cert(
        db, teacher_id=teacher_id, approve=body.approve, reason=body.reason,
    )
    await db.commit()
    return make_ok(TeacherProfileOut(
        user_id=teacher.id, subject=teacher.subject,
        cert_status=str(teacher.cert_status),
        cert_doc_url=teacher.cert_doc_url,
        max_students=teacher.max_students,
    ))
```

- [ ] **Step 7: router.py 注册 admin_router**

```python
from app.api.v1.admin import router as admin_router
# ...
v1_router.include_router(admin_router)
```

- [ ] **Step 8: 创建 `tests/api/test_teacher_p0.py`（cert 流程测试）**

```python
"""老师端 P0 三项测试（D-075）：cert + diagnosis + class。"""
import uuid
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.database import _async_session_factory
from app.models.d1_users import User
from sqlalchemy import select


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _login_as(client: AsyncClient, openid_suffix: str) -> dict:
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as mock_wx:
        mock_wx.return_value = {"openid": f"t_p0_{openid_suffix}"}
        resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


async def _make_teacher(client: AsyncClient, suffix: str) -> dict:
    headers = await _login_as(client, suffix)
    # complete profile（避免 is_active gate）
    await client.post(
        "/api/v1/auth/complete-profile",
        json={"birth_year": 1990, "agreement_version": "v1.0"}, headers=headers,
    )
    # become teacher
    await client.post("/api/v1/teacher/profile", json={"subject": "英语"}, headers=headers)
    return headers


@pytest.mark.asyncio
async def test_cert_submit_auto_approves_in_dev(client):
    """dev 模式 auto_approve_teacher_cert=True → cert_status 直接 certified。"""
    headers = await _make_teacher(client, f"cert_{uuid.uuid4().hex[:6]}")
    r = await client.post(
        "/api/v1/teacher/cert/submit",
        json={"cert_doc_url": "https://cdn.example.com/cert.jpg"},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["data"]["cert_status"] == "certified"
    assert r.json()["data"]["cert_doc_url"] == "https://cdn.example.com/cert.jpg"


@pytest.mark.asyncio
async def test_unverified_teacher_cannot_invite_or_view_students(client):
    """auto_approve=False 时未认证老师不能生成邀请码。"""
    from app.core.config import settings
    original = settings.auto_approve_teacher_cert
    settings.auto_approve_teacher_cert = False
    try:
        headers = await _make_teacher(client, f"unverif_{uuid.uuid4().hex[:6]}")
        # cert_status 默认 uncertified；生成邀请码应 403
        r = await client.post("/api/v1/teacher/invite-code", headers=headers)
        assert r.status_code == 403
        # 提交 cert → pending（也仍未通过）
        await client.post(
            "/api/v1/teacher/cert/submit",
            json={"cert_doc_url": "https://cdn.example.com/c.jpg"}, headers=headers,
        )
        r2 = await client.post("/api/v1/teacher/invite-code", headers=headers)
        assert r2.status_code == 403
    finally:
        settings.auto_approve_teacher_cert = original


@pytest.mark.asyncio
async def test_admin_review_certifies_teacher(client):
    """admin role 调用 /admin/teachers/{id}/review 后老师可正常使用。"""
    from app.core.config import settings
    original = settings.auto_approve_teacher_cert
    settings.auto_approve_teacher_cert = False
    try:
        headers = await _make_teacher(client, f"adm_t_{uuid.uuid4().hex[:6]}")
        await client.post(
            "/api/v1/teacher/cert/submit",
            json={"cert_doc_url": "https://cdn.example.com/c.jpg"}, headers=headers,
        )
        # 找到老师 user_id
        async with _async_session_factory() as s:
            user = (await s.execute(
                select(User).where(User.openid.like("t_p0_adm_t_%")).order_by(User.created_at.desc()).limit(1)
            )).scalar_one()
            tid = user.id

        # 制造 admin 用户
        admin_suffix = f"admin_{uuid.uuid4().hex[:6]}"
        admin_headers = await _login_as(client, admin_suffix)
        async with _async_session_factory() as s:
            admin = (await s.execute(
                select(User).where(User.openid == f"t_p0_{admin_suffix}")
            )).scalar_one()
            admin.role = "platform_admin"  # type: ignore[assignment]
            await s.commit()

        r = await client.post(
            f"/api/v1/admin/teachers/{tid}/review",
            json={"approve": True}, headers=admin_headers,
        )
        assert r.status_code == 200
        assert r.json()["data"]["cert_status"] == "certified"

        # 老师重新登录后应可生成邀请码
        # 重新拿一次 token 不必要：直接用 headers 即可（JWT 内不带 cert_status）
        r2 = await client.post("/api/v1/teacher/invite-code", headers=headers)
        assert r2.status_code == 200
    finally:
        settings.auto_approve_teacher_cert = original
```

- [ ] **Step 9: 跑测试 + 全量**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/api/test_teacher_p0.py -v
python -m pytest ../tests/ -q
```
Expected: 3 PASS + 全量 200 PASS。
**重要**：之前的 test_teacher.py 测试可能因新增 cert gate 而失败（生成邀请码/批注等）。需要在 test_teacher.py 的 fixture 中给 teacher_user 直接设 cert_status="certified" 让原测试通过。修复方式：在 `tests/api/test_teacher.py` 的 `teacher_headers` fixture 末尾追加 cert 提交（auto_approve=True 时一行 POST cert）。或者依赖 dev mode 默认 auto_approve=True 直接 cert/submit。

具体修复策略：
- dev settings.auto_approve_teacher_cert 默认 True，所以**原 test_teacher.py 在 become_teacher 后只要主动调一次 cert/submit 就 certified**。
- 但原测试**没调** cert/submit，cert_status 仍 uncertified → 失败。
- 修复：在原 test_teacher.py 的 `teacher_headers` / `teacher_user` fixture 创建 teacher 之后加一行：
  ```python
  await client.post("/api/v1/teacher/cert/submit", json={"cert_doc_url": "https://cdn.test.com/cert.jpg"}, headers=headers)
  ```
  这样 cert_status=certified（dev auto_approve），所有原测试可继续通过。
- 同样的 service-level fixture（test_teacher_service 或类似）直接操作 db 对象：在 fixture 内创建 Teacher 时设 `cert_status="certified"`。

如果遇到具体测试失败，按上述模式修复，并明确报告改动了哪些 fixture。

- [ ] **Step 10: 提交**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add backend/app/core/config.py backend/app/core/security.py \
        backend/app/schemas/teacher.py backend/app/services/teacher_service.py \
        backend/app/api/v1/teacher.py backend/app/api/v1/admin.py backend/app/api/v1/router.py \
        tests/api/test_teacher_p0.py tests/api/test_teacher.py
git commit -m "feat(teacher): cert submit/review flow + certified gate on all write ops"
```

---

## Task 1: 老师查看学生学情报告

**Files:**
- Modify: `backend/app/api/v1/teacher.py`
- Modify: `backend/app/services/teacher_service.py`（加 helper）
- Modify: `tests/api/test_teacher_p0.py`

- [ ] **Step 1: teacher_service 加 helper**

```python
async def get_student_diagnosis_report(
    db: AsyncSession,
    *,
    teacher_id: uuid.UUID,
    student_id: uuid.UUID,
):
    """老师查指定学生的学情报告。需绑定关系 + certified 已由 endpoint 层 gate。"""
    binding = await db.execute(
        select(TeacherStudent).where(
            TeacherStudent.teacher_id == teacher_id,
            TeacherStudent.student_id == student_id,
            TeacherStudent.status == "active",
        )
    )
    if binding.scalar_one_or_none() is None:
        raise AppError(code=403, message="无权查看该学生数据")
    from app.services.diagnosis_service import get_diagnosis_report
    return await get_diagnosis_report(db, student_id=student_id)
```

- [ ] **Step 2: teacher.py 加端点**

```python
from app.schemas.diagnosis import DiagnosisReport

@router.get(
    "/students/{student_id}/diagnosis-report",
    response_model=BaseResponse[DiagnosisReport],
)
async def student_diagnosis_api(student_id: uuid.UUID, db: DbDep, current_user: UserDep):
    if str(current_user.role) != "teacher":
        raise AppError(code=403, message="仅教师可访问")
    await get_rls_db(db, str(current_user.id))
    # cert gate
    from sqlalchemy import select as _sel
    from app.models.d1_users import Teacher as _T
    _r = await db.execute(_sel(_T).where(_T.id == current_user.id))
    teacher_service.ensure_certified(_r.scalar_one_or_none())

    report = await teacher_service.get_student_diagnosis_report(
        db, teacher_id=current_user.id, student_id=student_id,
    )
    return make_ok(report)
```

- [ ] **Step 3: 追加测试**

在 `tests/api/test_teacher_p0.py` 末尾：

```python
@pytest.mark.asyncio
async def test_teacher_view_student_diagnosis(client):
    """老师通过绑定关系查看学生学情报告，应返回 DiagnosisReport 字段。"""
    # 创建 teacher + student + bind
    t_headers = await _make_teacher(client, f"diag_t_{uuid.uuid4().hex[:6]}")
    await client.post(
        "/api/v1/teacher/cert/submit",
        json={"cert_doc_url": "https://cdn.test.com/c.jpg"}, headers=t_headers,
    )

    s_headers = await _login_as(client, f"diag_s_{uuid.uuid4().hex[:6]}")
    await client.post(
        "/api/v1/auth/complete-profile",
        json={"birth_year": 2010, "guardian_phone": "13800001234", "agreement_version": "v1.0"},
        headers=s_headers,
    )
    await client.post("/api/v1/auth/guardian-verify", json={"code": "123456"}, headers=s_headers)

    # 邀请码绑定
    iv = await client.post("/api/v1/teacher/invite-code", headers=t_headers)
    code = iv.json()["data"]["code"]
    await client.post("/api/v1/teacher/bind", json={"code": code}, headers=s_headers)

    # student_id
    async with _async_session_factory() as s:
        from app.models.d1_users import User as _U
        stu = (await s.execute(_sel := select(_U).where(_U.openid.like("t_p0_diag_s_%")).order_by(_U.created_at.desc()).limit(1))).scalar_one()
        sid = stu.id

    r = await client.get(f"/api/v1/teacher/students/{sid}/diagnosis-report", headers=t_headers)
    assert r.status_code == 200
    d = r.json()["data"]
    assert "total_questions" in d
    assert "mastery_rate" in d
    assert "top_error_types" in d


@pytest.mark.asyncio
async def test_teacher_view_unbound_student_403(client):
    t_headers = await _make_teacher(client, f"diag_unbound_{uuid.uuid4().hex[:6]}")
    await client.post(
        "/api/v1/teacher/cert/submit",
        json={"cert_doc_url": "https://cdn.test.com/c.jpg"}, headers=t_headers,
    )
    rnd_sid = uuid.uuid4()
    r = await client.get(f"/api/v1/teacher/students/{rnd_sid}/diagnosis-report", headers=t_headers)
    assert r.status_code == 403
```

- [ ] **Step 4: 跑测试**

```bash
python -m pytest ../tests/api/test_teacher_p0.py -v
python -m pytest ../tests/ -q
```

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/teacher_service.py backend/app/api/v1/teacher.py tests/api/test_teacher_p0.py
git commit -m "feat(teacher): GET /teacher/students/{id}/diagnosis-report"
```

---

## Task 2: 班级 CRUD service + API

**Files:**
- Create: `backend/app/schemas/classes.py`
- Create: `backend/app/services/class_service.py`
- Modify: `backend/app/api/v1/teacher.py`（追加 classes 端点组）
- Modify: `tests/api/test_teacher_p0.py`

- [ ] **Step 1: 创建 schemas/classes.py**

```python
"""班级相关 Schemas（D-075 / P0 老师端）。"""
from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class ClassCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)


class ClassOut(BaseModel):
    id: uuid.UUID
    name: str
    student_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ClassStudentAddRequest(BaseModel):
    student_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=50)


class ClassStudentOut(BaseModel):
    student_id: uuid.UUID
    joined_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: 创建 services/class_service.py**

```python
"""班级管理 + 综合报告（D-075 / P0 老师端）。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d1_users import TeacherStudent
from app.models.d7_teacher import Class, ClassStudent


async def create_class(db: AsyncSession, *, teacher_id: uuid.UUID, name: str) -> Class:
    cls = Class(id=uuid.uuid4(), teacher_id=teacher_id, name=name)
    db.add(cls)
    await db.flush()
    return cls


async def list_classes(db: AsyncSession, *, teacher_id: uuid.UUID) -> list[tuple[Class, int]]:
    """返回 (class, student_count) 列表。"""
    r = await db.execute(
        select(Class).where(Class.teacher_id == teacher_id).order_by(Class.created_at.desc())
    )
    classes = list(r.scalars().all())
    out: list[tuple[Class, int]] = []
    for c in classes:
        cnt_r = await db.execute(
            select(func.count(ClassStudent.student_id)).where(ClassStudent.class_id == c.id)
        )
        out.append((c, cnt_r.scalar_one()))
    return out


async def _get_owned_class(db: AsyncSession, *, teacher_id: uuid.UUID, class_id: uuid.UUID) -> Class:
    r = await db.execute(
        select(Class).where(Class.id == class_id, Class.teacher_id == teacher_id)
    )
    cls = r.scalar_one_or_none()
    if cls is None:
        raise AppError(code=404, message="班级不存在或无权访问")
    return cls


async def delete_class(db: AsyncSession, *, teacher_id: uuid.UUID, class_id: uuid.UUID) -> None:
    cls = await _get_owned_class(db, teacher_id=teacher_id, class_id=class_id)
    # 先删 class_students 再删 class
    await db.execute(delete(ClassStudent).where(ClassStudent.class_id == cls.id))
    await db.delete(cls)
    await db.flush()


async def add_students(
    db: AsyncSession,
    *,
    teacher_id: uuid.UUID,
    class_id: uuid.UUID,
    student_ids: list[uuid.UUID],
) -> int:
    """添加学生到班级。学生必须与老师有 active 绑定。返回实际新增数（已存在跳过）。"""
    cls = await _get_owned_class(db, teacher_id=teacher_id, class_id=class_id)

    # 校验所有 student 都和该老师有 active 绑定
    bound_r = await db.execute(
        select(TeacherStudent.student_id).where(
            TeacherStudent.teacher_id == teacher_id,
            TeacherStudent.status == "active",
            TeacherStudent.student_id.in_(student_ids),
        )
    )
    bound_set = {row[0] for row in bound_r.all()}
    invalid = set(student_ids) - bound_set
    if invalid:
        raise AppError(code=400, message=f"以下学生未绑定到该老师：{list(invalid)}")

    # 已在班级里的跳过
    existing_r = await db.execute(
        select(ClassStudent.student_id).where(
            ClassStudent.class_id == cls.id,
            ClassStudent.student_id.in_(student_ids),
        )
    )
    existing_set = {row[0] for row in existing_r.all()}

    now = datetime.now(timezone.utc)
    added = 0
    for sid in student_ids:
        if sid in existing_set:
            continue
        db.add(ClassStudent(class_id=cls.id, student_id=sid, joined_at=now))
        added += 1
    await db.flush()
    return added


async def remove_student(
    db: AsyncSession,
    *,
    teacher_id: uuid.UUID,
    class_id: uuid.UUID,
    student_id: uuid.UUID,
) -> None:
    cls = await _get_owned_class(db, teacher_id=teacher_id, class_id=class_id)
    r = await db.execute(
        delete(ClassStudent).where(
            ClassStudent.class_id == cls.id,
            ClassStudent.student_id == student_id,
        )
    )
    if (r.rowcount or 0) == 0:
        raise AppError(code=404, message="该学生不在班级中")
    await db.flush()


async def list_class_students(
    db: AsyncSession,
    *,
    teacher_id: uuid.UUID,
    class_id: uuid.UUID,
) -> list[ClassStudent]:
    cls = await _get_owned_class(db, teacher_id=teacher_id, class_id=class_id)
    r = await db.execute(
        select(ClassStudent).where(ClassStudent.class_id == cls.id)
        .order_by(ClassStudent.joined_at.desc())
    )
    return list(r.scalars().all())
```

- [ ] **Step 3: teacher.py 加 classes 端点组**

```python
from app.schemas.classes import (
    ClassCreateRequest, ClassOut,
    ClassStudentAddRequest, ClassStudentOut,
)
from app.services import class_service


async def _require_certified_teacher(db: AsyncSession, current_user: User) -> None:
    """老师认证检查 helper（提取重复代码）。"""
    if str(current_user.role) != "teacher":
        raise AppError(code=403, message="仅教师可访问")
    from sqlalchemy import select as _sel
    from app.models.d1_users import Teacher as _T
    r = await db.execute(_sel(_T).where(_T.id == current_user.id))
    teacher_service.ensure_certified(r.scalar_one_or_none())


@router.post("/classes", response_model=BaseResponse[ClassOut])
async def create_class_api(body: ClassCreateRequest, db: DbDep, current_user: UserDep):
    await _require_certified_teacher(db, current_user)
    await get_rls_db(db, str(current_user.id))
    cls = await class_service.create_class(db, teacher_id=current_user.id, name=body.name)
    await db.commit()
    return make_ok(ClassOut(id=cls.id, name=cls.name, student_count=0, created_at=cls.created_at))


@router.get("/classes", response_model=BaseResponse[list[ClassOut]])
async def list_classes_api(db: DbDep, current_user: UserDep):
    await _require_certified_teacher(db, current_user)
    await get_rls_db(db, str(current_user.id))
    pairs = await class_service.list_classes(db, teacher_id=current_user.id)
    return make_ok([
        ClassOut(id=c.id, name=c.name, student_count=cnt, created_at=c.created_at)
        for c, cnt in pairs
    ])


@router.delete("/classes/{class_id}", response_model=BaseResponse[dict])
async def delete_class_api(class_id: uuid.UUID, db: DbDep, current_user: UserDep):
    await _require_certified_teacher(db, current_user)
    await get_rls_db(db, str(current_user.id))
    await class_service.delete_class(db, teacher_id=current_user.id, class_id=class_id)
    await db.commit()
    return make_ok({"deleted": True})


@router.post("/classes/{class_id}/students", response_model=BaseResponse[dict])
async def add_class_students_api(
    class_id: uuid.UUID, body: ClassStudentAddRequest, db: DbDep, current_user: UserDep,
):
    await _require_certified_teacher(db, current_user)
    await get_rls_db(db, str(current_user.id))
    added = await class_service.add_students(
        db, teacher_id=current_user.id, class_id=class_id, student_ids=body.student_ids,
    )
    await db.commit()
    return make_ok({"added": added})


@router.delete("/classes/{class_id}/students/{student_id}", response_model=BaseResponse[dict])
async def remove_class_student_api(
    class_id: uuid.UUID, student_id: uuid.UUID, db: DbDep, current_user: UserDep,
):
    await _require_certified_teacher(db, current_user)
    await get_rls_db(db, str(current_user.id))
    await class_service.remove_student(
        db, teacher_id=current_user.id, class_id=class_id, student_id=student_id,
    )
    await db.commit()
    return make_ok({"removed": True})


@router.get("/classes/{class_id}/students", response_model=BaseResponse[list[ClassStudentOut]])
async def list_class_students_api(class_id: uuid.UUID, db: DbDep, current_user: UserDep):
    await _require_certified_teacher(db, current_user)
    await get_rls_db(db, str(current_user.id))
    items = await class_service.list_class_students(
        db, teacher_id=current_user.id, class_id=class_id,
    )
    return make_ok([ClassStudentOut(student_id=cs.student_id, joined_at=cs.joined_at) for cs in items])
```

- [ ] **Step 4: 追加测试**

```python
@pytest.mark.asyncio
async def test_class_crud_full_flow(client):
    """创建班级 → 加学生（必须绑定）→ 查列表 → 移除 → 删班。"""
    t_headers = await _make_teacher(client, f"cls_{uuid.uuid4().hex[:6]}")
    await client.post(
        "/api/v1/teacher/cert/submit",
        json={"cert_doc_url": "https://cdn.test.com/c.jpg"}, headers=t_headers,
    )

    # 1) 创建班
    r = await client.post("/api/v1/teacher/classes", json={"name": "三年级2班"}, headers=t_headers)
    assert r.status_code == 200
    class_id = r.json()["data"]["id"]

    # 2) 列表
    r2 = await client.get("/api/v1/teacher/classes", headers=t_headers)
    assert any(c["id"] == class_id for c in r2.json()["data"])

    # 3) 创建并绑定一个学生
    s_headers = await _login_as(client, f"cls_s_{uuid.uuid4().hex[:6]}")
    await client.post(
        "/api/v1/auth/complete-profile",
        json={"birth_year": 1990, "agreement_version": "v1.0"}, headers=s_headers,
    )
    iv = await client.post("/api/v1/teacher/invite-code", headers=t_headers)
    await client.post("/api/v1/teacher/bind", json={"code": iv.json()["data"]["code"]}, headers=s_headers)
    # 查 student_id
    async with _async_session_factory() as s:
        from app.models.d1_users import User as _U
        stu = (await s.execute(
            select(_U).where(_U.openid.like("t_p0_cls_s_%")).order_by(_U.created_at.desc()).limit(1)
        )).scalar_one()
        sid = stu.id

    # 4) 加学生入班
    r3 = await client.post(
        f"/api/v1/teacher/classes/{class_id}/students",
        json={"student_ids": [str(sid)]}, headers=t_headers,
    )
    assert r3.json()["data"]["added"] == 1

    # 5) 列班级学生
    r4 = await client.get(f"/api/v1/teacher/classes/{class_id}/students", headers=t_headers)
    assert len(r4.json()["data"]) == 1

    # 6) 移除
    r5 = await client.delete(
        f"/api/v1/teacher/classes/{class_id}/students/{sid}", headers=t_headers,
    )
    assert r5.json()["data"]["removed"] is True

    # 7) 删班
    r6 = await client.delete(f"/api/v1/teacher/classes/{class_id}", headers=t_headers)
    assert r6.json()["data"]["deleted"] is True


@pytest.mark.asyncio
async def test_class_add_unbound_student_400(client):
    t_headers = await _make_teacher(client, f"cls_e_{uuid.uuid4().hex[:6]}")
    await client.post(
        "/api/v1/teacher/cert/submit",
        json={"cert_doc_url": "https://cdn.test.com/c.jpg"}, headers=t_headers,
    )
    r = await client.post("/api/v1/teacher/classes", json={"name": "X班"}, headers=t_headers)
    class_id = r.json()["data"]["id"]

    rnd_sid = uuid.uuid4()
    r2 = await client.post(
        f"/api/v1/teacher/classes/{class_id}/students",
        json={"student_ids": [str(rnd_sid)]}, headers=t_headers,
    )
    assert r2.status_code == 400
```

- [ ] **Step 5: 跑测试 + 提交**

```bash
python -m pytest ../tests/api/test_teacher_p0.py -v
python -m pytest ../tests/ -q
git add backend/app/schemas/classes.py backend/app/services/class_service.py \
        backend/app/api/v1/teacher.py tests/api/test_teacher_p0.py
git commit -m "feat(teacher): class CRUD + student management"
```

---

## Task 3: 班级综合报告

**Files:**
- Modify: `backend/app/schemas/classes.py`
- Modify: `backend/app/services/class_service.py`
- Modify: `backend/app/api/v1/teacher.py`
- Modify: `tests/api/test_teacher_p0.py`

- [ ] **Step 1: schemas/classes.py 追加**

```python
class ClassReportStudent(BaseModel):
    student_id: uuid.UUID
    total_questions: int
    mastery_rate: float


class ClassReport(BaseModel):
    class_id: uuid.UUID
    class_name: str
    student_count: int
    avg_mastery_rate: float
    total_questions: int
    top_error_types: list[dict]  # [{type, count}]
    top_weak_knowledge_points: list[dict]  # [{kp, count}]
    students_ranking: list[ClassReportStudent]  # 按掌握率降序
```

- [ ] **Step 2: class_service 加 build_class_report**

```python
from collections import Counter


async def build_class_report(
    db: AsyncSession,
    *,
    teacher_id: uuid.UUID,
    class_id: uuid.UUID,
):
    """聚合全班学生的 diagnosis_service 结果。"""
    cls = await _get_owned_class(db, teacher_id=teacher_id, class_id=class_id)

    cs_r = await db.execute(
        select(ClassStudent.student_id).where(ClassStudent.class_id == cls.id)
    )
    student_ids = [row[0] for row in cs_r.all()]

    from app.services.diagnosis_service import get_diagnosis_report
    err_counter: Counter = Counter()
    kp_counter: Counter = Counter()
    total_questions = 0
    rates: list[float] = []
    rankings = []

    for sid in student_ids:
        report = await get_diagnosis_report(db, student_id=sid)
        total_questions += report.total_questions
        rates.append(report.mastery_rate)
        rankings.append({
            "student_id": sid,
            "total_questions": report.total_questions,
            "mastery_rate": report.mastery_rate,
        })
        for et in report.top_error_types:
            err_counter[et.error_type] += et.count
        for kp in report.top_weak_knowledge_points:
            kp_counter[kp.knowledge_point] += kp.count

    avg_rate = (sum(rates) / len(rates)) if rates else 0.0
    rankings.sort(key=lambda x: x["mastery_rate"], reverse=True)

    return {
        "class_id": cls.id,
        "class_name": cls.name,
        "student_count": len(student_ids),
        "avg_mastery_rate": round(avg_rate, 4),
        "total_questions": total_questions,
        "top_error_types": [{"type": t, "count": c} for t, c in err_counter.most_common(10)],
        "top_weak_knowledge_points": [{"kp": k, "count": c} for k, c in kp_counter.most_common(10)],
        "students_ranking": rankings,
    }
```

- [ ] **Step 3: teacher.py 加端点**

```python
from app.schemas.classes import ClassReport

@router.get("/classes/{class_id}/report", response_model=BaseResponse[ClassReport])
async def class_report_api(class_id: uuid.UUID, db: DbDep, current_user: UserDep):
    await _require_certified_teacher(db, current_user)
    await get_rls_db(db, str(current_user.id))
    data = await class_service.build_class_report(
        db, teacher_id=current_user.id, class_id=class_id,
    )
    return make_ok(ClassReport(**data))
```

- [ ] **Step 4: 追加测试**

```python
@pytest.mark.asyncio
async def test_class_report_empty(client):
    """空班级也应返回有效结构。"""
    t_headers = await _make_teacher(client, f"clsrpt_{uuid.uuid4().hex[:6]}")
    await client.post(
        "/api/v1/teacher/cert/submit",
        json={"cert_doc_url": "https://cdn.test.com/c.jpg"}, headers=t_headers,
    )
    r = await client.post("/api/v1/teacher/classes", json={"name": "空班"}, headers=t_headers)
    class_id = r.json()["data"]["id"]

    rep = await client.get(f"/api/v1/teacher/classes/{class_id}/report", headers=t_headers)
    assert rep.status_code == 200
    d = rep.json()["data"]
    assert d["student_count"] == 0
    assert d["avg_mastery_rate"] == 0.0
    assert d["students_ranking"] == []
```

- [ ] **Step 5: 跑测试 + 提交**

```bash
python -m pytest ../tests/api/test_teacher_p0.py -v
python -m pytest ../tests/ -q
git add backend/app/schemas/classes.py backend/app/services/class_service.py \
        backend/app/api/v1/teacher.py tests/api/test_teacher_p0.py
git commit -m "feat(teacher): class comprehensive report aggregation"
```

---

## Task 4: 前端 — 认证状态/上传 + 学生学情报告入口 + 班级管理 + 班级报告

**Files:**
- Modify: `frontend/miniprogram/src/types/api.ts`
- Modify: `frontend/miniprogram/src/api/teacher.ts`
- Create: `frontend/miniprogram/src/api/classes.ts`
- Modify: `frontend/miniprogram/src/pages.json`（+4 页）
- Create: `frontend/miniprogram/src/pages/teacher/cert.vue`
- Create: `frontend/miniprogram/src/pages/teacher/student-diagnosis.vue`
- Create: `frontend/miniprogram/src/pages/teacher/classes.vue`
- Create: `frontend/miniprogram/src/pages/teacher/class-detail.vue`
- Modify: `frontend/miniprogram/src/pages/teacher/students.vue`（顶部加认证状态条 + 班级入口）
- Modify: `frontend/miniprogram/src/pages/teacher/student-detail.vue`（加"查看学情报告"入口）

- [ ] **Step 1: types/api.ts 加类型**

```typescript
export interface TeacherProfileOutExtended {
  user_id: string
  subject: string | null
  cert_status: 'uncertified' | 'pending' | 'certified' | 'rejected'
  cert_doc_url: string | null
  max_students: number
}

export interface ClassOut {
  id: string
  name: string
  student_count: number
  created_at: string
}

export interface ClassStudentOut {
  student_id: string
  joined_at: string
}

export interface ClassReport {
  class_id: string
  class_name: string
  student_count: number
  avg_mastery_rate: number
  total_questions: number
  top_error_types: { type: string; count: number }[]
  top_weak_knowledge_points: { kp: string; count: number }[]
  students_ranking: { student_id: string; total_questions: number; mastery_rate: number }[]
}
```

- [ ] **Step 2: api/teacher.ts 追加**

```typescript
export function submitCert(certDocUrl: string) {
  return request('/teacher/cert/submit', { method: 'POST', data: { cert_doc_url: certDocUrl } })
}

export function getStudentDiagnosis(studentId: string) {
  return request(`/teacher/students/${studentId}/diagnosis-report`, { method: 'GET' })
}
```
（用项目已有 request import）

- [ ] **Step 3: api/classes.ts**

```typescript
import { request } from '@/utils/request'
import type { BaseResponse, ClassOut, ClassStudentOut, ClassReport } from '../types/api'

export function listClasses(): Promise<BaseResponse<ClassOut[]>> {
  return request('/teacher/classes', { method: 'GET' })
}
export function createClass(name: string): Promise<BaseResponse<ClassOut>> {
  return request('/teacher/classes', { method: 'POST', data: { name } })
}
export function deleteClass(classId: string): Promise<BaseResponse<{ deleted: boolean }>> {
  return request(`/teacher/classes/${classId}`, { method: 'DELETE' })
}
export function listClassStudents(classId: string): Promise<BaseResponse<ClassStudentOut[]>> {
  return request(`/teacher/classes/${classId}/students`, { method: 'GET' })
}
export function addClassStudents(classId: string, studentIds: string[]): Promise<BaseResponse<{ added: number }>> {
  return request(`/teacher/classes/${classId}/students`, { method: 'POST', data: { student_ids: studentIds } })
}
export function removeClassStudent(classId: string, studentId: string): Promise<BaseResponse<{ removed: boolean }>> {
  return request(`/teacher/classes/${classId}/students/${studentId}`, { method: 'DELETE' })
}
export function getClassReport(classId: string): Promise<BaseResponse<ClassReport>> {
  return request(`/teacher/classes/${classId}/report`, { method: 'GET' })
}
```

- [ ] **Step 4: pages.json 追加 4 页**

```json
{ "path": "pages/teacher/cert", "style": { "navigationBarTitleText": "教师认证" } },
{ "path": "pages/teacher/student-diagnosis", "style": { "navigationBarTitleText": "学生学情" } },
{ "path": "pages/teacher/classes", "style": { "navigationBarTitleText": "班级管理" } },
{ "path": "pages/teacher/class-detail", "style": { "navigationBarTitleText": "班级详情" } }
```

- [ ] **Step 5: 创建 pages/teacher/cert.vue**

```vue
<template>
  <view class="page">
    <view class="card">
      <view class="title">教师认证</view>
      <text class="status" :class="statusClass">当前状态：{{ statusLabel }}</text>
      <view class="row col">
        <text class="label">证书图片 URL（MVP）</text>
        <input v-model="url" class="input" placeholder="https://..." />
      </view>
      <text class="dev-hint">提示：dev 模式默认自动审核通过；提交后状态会变 certified。</text>
      <button class="btn-primary" :disabled="!url || submitting" @tap="onSubmit">
        {{ submitting ? '提交中…' : '提交认证' }}
      </button>
    </view>
  </view>
</template>
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { submitCert } from '@/api/teacher'
import { request } from '@/utils/request'
const url = ref('')
const submitting = ref(false)
const certStatus = ref<string>('uncertified')
const statusLabel = computed(() => ({
  uncertified: '未认证', pending: '审核中', certified: '已认证', rejected: '已拒绝',
}[certStatus.value] || certStatus.value))
const statusClass = computed(() => `s-${certStatus.value}`)

async function loadStatus() {
  try {
    const r: any = await request('/teacher/profile', { method: 'POST', data: {} })
    certStatus.value = r.data?.cert_status || 'uncertified'
    url.value = r.data?.cert_doc_url || ''
  } catch {}
}

async function onSubmit() {
  submitting.value = true
  try {
    const r: any = await submitCert(url.value)
    certStatus.value = r.data?.cert_status || certStatus.value
    uni.showToast({ title: '已提交', icon: 'success' })
  } catch (e: any) {
    uni.showToast({ title: e?.message || '提交失败', icon: 'none' })
  } finally { submitting.value = false }
}

onMounted(loadStatus)
</script>
<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.title { font-size: var(--fs-h1); font-weight: 800; color: var(--c-ink); margin-bottom: 16rpx; }
.status { display: block; font-size: 28rpx; font-weight: 700; margin-bottom: 24rpx; padding: 12rpx; border-radius: var(--r-md); }
.s-uncertified, .s-pending { background: var(--c-primary-faint); color: var(--c-ink); }
.s-certified { background: var(--c-success-bg); color: var(--c-success-dark); }
.s-rejected { background: var(--c-danger-bg); color: var(--c-danger-dark); }
.row.col { display: flex; flex-direction: column; gap: 8rpx; margin-bottom: 16rpx; }
.label { color: var(--c-text-second); font-size: 28rpx; }
.input { border: 2rpx solid var(--c-border); border-radius: var(--r-md); padding: 16rpx; font-size: 28rpx; }
.dev-hint { display: block; font-size: 22rpx; color: var(--c-text-hint); margin-bottom: 12rpx; }
.btn-primary { background: var(--c-primary); color: var(--c-ink); border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #b9a94e; }
</style>
```

- [ ] **Step 6: 创建 pages/teacher/student-diagnosis.vue**

```vue
<template>
  <view class="page">
    <view v-if="loading" class="tip">加载中…</view>
    <view v-else-if="!report" class="tip">暂无数据</view>
    <view v-else>
      <view class="card">
        <view class="stat-row">
          <view class="stat"><text class="num">{{ report.total_questions }}</text><text class="lbl">累计错题</text></view>
          <view class="stat"><text class="num">{{ report.total_analyzed }}</text><text class="lbl">已分析</text></view>
          <view class="stat"><text class="num">{{ Math.round(report.mastery_rate * 100) }}%</text><text class="lbl">掌握率</text></view>
        </view>
      </view>
      <view v-if="report.top_error_types.length" class="card">
        <view class="card-title">高频错误</view>
        <view v-for="e in report.top_error_types.slice(0, 5)" :key="e.error_type" class="bar-item">
          <text class="bar-label">{{ e.error_type }}</text>
          <text class="bar-count">{{ e.count }}</text>
        </view>
      </view>
      <view v-if="report.top_weak_knowledge_points.length" class="card">
        <view class="card-title">薄弱知识点</view>
        <view class="tags">
          <text v-for="kp in report.top_weak_knowledge_points.slice(0, 8)" :key="kp.knowledge_point" class="tag-kp">
            {{ kp.knowledge_point }}（{{ kp.count }}）
          </text>
        </view>
      </view>
      <view v-if="report.top_suggestions.length" class="card">
        <view class="card-title">AI 学习建议</view>
        <view v-for="(s, i) in report.top_suggestions" :key="i" class="sug">
          <text class="sug-num">{{ i + 1 }}</text>
          <text class="sug-text">{{ s }}</text>
        </view>
      </view>
    </view>
  </view>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getStudentDiagnosis } from '@/api/teacher'
const report = ref<any>(null)
const loading = ref(true)
onMounted(async () => {
  const pages = getCurrentPages()
  const sid = (pages[pages.length - 1] as any).options?.studentId
  if (!sid) { loading.value = false; return }
  try {
    const r: any = await getStudentDiagnosis(sid)
    report.value = r.data
  } finally { loading.value = false }
})
</script>
<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.tip { text-align: center; padding: 120rpx 0; color: var(--c-text-hint); }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 20rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.card-title { font-size: var(--fs-h2); font-weight: 700; color: var(--c-ink); margin-bottom: 16rpx; }
.stat-row { display: flex; justify-content: space-around; }
.stat { text-align: center; }
.num { font-size: 56rpx; font-weight: 800; color: var(--c-ink); display: block; }
.lbl { font-size: 24rpx; color: var(--c-text-hint); }
.bar-item { display: flex; justify-content: space-between; padding: 8rpx 0; border-bottom: 1rpx solid var(--c-border); }
.bar-label { font-size: 26rpx; color: var(--c-text-body); }
.bar-count { font-size: 26rpx; color: var(--c-gold); font-weight: 700; }
.tags { display: flex; flex-wrap: wrap; gap: 12rpx; }
.tag-kp { background: #eaeac4; color: #6b6b2e; font-size: 24rpx; font-weight: 600; padding: 6rpx 16rpx; border-radius: var(--r-pill); }
.sug { display: flex; align-items: flex-start; margin-bottom: 20rpx; }
.sug-num { width: 44rpx; height: 44rpx; background: var(--c-primary); color: var(--c-ink); border-radius: 50%; font-size: 24rpx; font-weight: 700; line-height: 44rpx; text-align: center; flex-shrink: 0; margin-right: 16rpx; }
.sug-text { flex: 1; font-size: 28rpx; color: var(--c-text-body); line-height: 1.7; }
</style>
```

- [ ] **Step 7: 创建 pages/teacher/classes.vue**

```vue
<template>
  <view class="page">
    <view class="card">
      <view class="card-title">创建班级</view>
      <input v-model="newName" class="input" placeholder="班级名称" />
      <button class="btn-primary" :disabled="!newName || creating" @tap="onCreate">
        {{ creating ? '创建中…' : '创建' }}
      </button>
    </view>
    <view v-if="loading" class="tip">加载中…</view>
    <view v-else-if="classes.length === 0" class="tip">还没有班级</view>
    <view v-for="c in classes" :key="c.id" class="card class-item" @tap="goDetail(c.id)">
      <view>
        <text class="class-name">{{ c.name }}</text>
        <text class="class-cnt">{{ c.student_count }} 名学生</text>
      </view>
      <text class="arrow">›</text>
    </view>
  </view>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listClasses, createClass } from '@/api/classes'
import type { ClassOut } from '@/types/api'
const newName = ref('')
const creating = ref(false)
const classes = ref<ClassOut[]>([])
const loading = ref(false)
async function load() { loading.value = true; try { const r = await listClasses(); classes.value = r.data || [] } finally { loading.value = false } }
async function onCreate() {
  creating.value = true
  try { await createClass(newName.value); newName.value = ''; await load(); uni.showToast({ title: '已创建', icon: 'success' }) }
  catch (e: any) { uni.showToast({ title: e?.message || '失败', icon: 'none' }) }
  finally { creating.value = false }
}
function goDetail(id: string) { uni.navigateTo({ url: `/pages/teacher/class-detail?classId=${id}` }) }
onMounted(load)
</script>
<style scoped>
.page { padding: 16rpx; background: var(--c-bg-page); min-height: 100vh; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 16rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.card-title { font-size: var(--fs-h2); font-weight: 700; color: var(--c-ink); margin-bottom: 16rpx; }
.input { border: 2rpx solid var(--c-border); border-radius: var(--r-md); padding: 16rpx; font-size: 28rpx; width: 100%; box-sizing: border-box; margin-bottom: 16rpx; }
.btn-primary { background: var(--c-primary); color: var(--c-ink); border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #b9a94e; }
.tip { text-align: center; padding: 80rpx 0; color: var(--c-text-hint); }
.class-item { display: flex; justify-content: space-between; align-items: center; }
.class-name { font-size: 28rpx; font-weight: 700; color: var(--c-ink); display: block; }
.class-cnt { font-size: 24rpx; color: var(--c-text-hint); }
.arrow { font-size: 32rpx; color: var(--c-text-hint); }
</style>
```

- [ ] **Step 8: 创建 pages/teacher/class-detail.vue**（含报告 tab）

```vue
<template>
  <view class="page">
    <view class="tabs">
      <text class="tab" :class="{ active: tab === 'students' }" @tap="tab = 'students'">学生</text>
      <text class="tab" :class="{ active: tab === 'report' }" @tap="switchReport">综合报告</text>
    </view>

    <view v-if="tab === 'students'">
      <view v-if="loading" class="tip">加载中…</view>
      <view v-else-if="students.length === 0" class="tip">班级暂无学生</view>
      <view v-for="s in students" :key="s.student_id" class="card s-item">
        <text class="s-id">学生 {{ s.student_id.slice(0, 8) }}…</text>
        <text class="s-rm" @tap.stop="onRemove(s.student_id)">移除</text>
      </view>
      <view class="card">
        <text class="hint">添加学生：从教师中心绑定学生后，到这里通过 ID 添加。</text>
        <input v-model="newStudentId" class="input" placeholder="学生 UUID" />
        <button class="btn-primary" :disabled="!newStudentId || adding" @tap="onAdd">
          {{ adding ? '添加中…' : '添加' }}
        </button>
      </view>
    </view>

    <view v-else>
      <view v-if="reportLoading" class="tip">生成报告中…</view>
      <view v-else-if="!report" class="tip">无数据</view>
      <view v-else>
        <view class="card">
          <view class="stat-row">
            <view class="stat"><text class="num">{{ report.student_count }}</text><text class="lbl">学生数</text></view>
            <view class="stat"><text class="num">{{ report.total_questions }}</text><text class="lbl">总错题</text></view>
            <view class="stat"><text class="num">{{ Math.round(report.avg_mastery_rate * 100) }}%</text><text class="lbl">班均掌握率</text></view>
          </view>
        </view>
        <view v-if="report.top_error_types.length" class="card">
          <view class="card-title">班级高频错误</view>
          <view v-for="e in report.top_error_types.slice(0, 5)" :key="e.type" class="row">
            <text>{{ e.type }}</text><text class="count">{{ e.count }}</text>
          </view>
        </view>
        <view v-if="report.students_ranking.length" class="card">
          <view class="card-title">掌握率排名</view>
          <view v-for="(s, i) in report.students_ranking" :key="s.student_id" class="row">
            <text>{{ i + 1 }}. 学生 {{ s.student_id.slice(0, 8) }}…</text>
            <text class="count">{{ Math.round(s.mastery_rate * 100) }}%</text>
          </view>
        </view>
      </view>
    </view>
  </view>
</template>
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { listClassStudents, addClassStudents, removeClassStudent, getClassReport } from '@/api/classes'
import type { ClassStudentOut, ClassReport } from '@/types/api'

const classId = ref('')
const tab = ref<'students' | 'report'>('students')
const students = ref<ClassStudentOut[]>([])
const loading = ref(false)
const adding = ref(false)
const newStudentId = ref('')
const report = ref<ClassReport | null>(null)
const reportLoading = ref(false)

async function loadStudents() {
  loading.value = true
  try { const r = await listClassStudents(classId.value); students.value = r.data || [] }
  finally { loading.value = false }
}

async function switchReport() {
  tab.value = 'report'
  reportLoading.value = true
  try { const r = await getClassReport(classId.value); report.value = r.data || null }
  finally { reportLoading.value = false }
}

async function onAdd() {
  adding.value = true
  try { await addClassStudents(classId.value, [newStudentId.value.trim()]); newStudentId.value = ''; await loadStudents(); uni.showToast({ title: '已添加', icon: 'success' }) }
  catch (e: any) { uni.showToast({ title: e?.message || '失败', icon: 'none' }) }
  finally { adding.value = false }
}

async function onRemove(sid: string) {
  try { await removeClassStudent(classId.value, sid); await loadStudents() }
  catch (e: any) { uni.showToast({ title: e?.message || '失败', icon: 'none' }) }
}

onMounted(() => {
  const pages = getCurrentPages()
  classId.value = (pages[pages.length - 1] as any).options?.classId || ''
  if (classId.value) loadStudents()
})
</script>
<style scoped>
.page { padding: 16rpx; background: var(--c-bg-page); min-height: 100vh; }
.tabs { display: flex; gap: 16rpx; padding: 8rpx 0 16rpx; }
.tab { padding: 12rpx 32rpx; background: var(--c-bg-card); border-radius: var(--r-pill); font-size: 26rpx; color: var(--c-text-second); }
.tab.active { background: var(--c-primary); color: var(--c-ink); font-weight: 700; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 16rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.card-title { font-size: var(--fs-h2); font-weight: 700; color: var(--c-ink); margin-bottom: 12rpx; }
.tip { text-align: center; padding: 80rpx 0; color: var(--c-text-hint); }
.s-item { display: flex; justify-content: space-between; align-items: center; }
.s-id { font-size: 26rpx; color: var(--c-text-body); }
.s-rm { font-size: 24rpx; color: var(--c-danger); padding: 8rpx 16rpx; }
.hint { font-size: 22rpx; color: var(--c-text-hint); display: block; margin-bottom: 12rpx; }
.input { border: 2rpx solid var(--c-border); border-radius: var(--r-md); padding: 16rpx; font-size: 26rpx; width: 100%; box-sizing: border-box; margin-bottom: 12rpx; }
.btn-primary { background: var(--c-primary); color: var(--c-ink); border-radius: var(--r-btn); padding: 16rpx; font-weight: 700; font-size: 26rpx; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #b9a94e; }
.stat-row { display: flex; justify-content: space-around; }
.stat { text-align: center; }
.num { font-size: 48rpx; font-weight: 800; color: var(--c-ink); display: block; }
.lbl { font-size: 22rpx; color: var(--c-text-hint); }
.row { display: flex; justify-content: space-between; padding: 6rpx 0; border-bottom: 1rpx solid var(--c-border); font-size: 26rpx; color: var(--c-text-body); }
.count { color: var(--c-gold); font-weight: 700; }
</style>
```

- [ ] **Step 9: 修改 pages/teacher/students.vue 顶部加认证状态条 + 班级入口**

READ 文件，在 template 的 `<view class="teacher-page">` 内最上方插入：
```vue
    <view v-if="isTeacher && certStatus !== 'certified'" class="cert-banner" @tap="goCert">
      <text>⚠️ 教师未认证（当前 {{ certStatusLabel }}）—— 点击去认证</text>
    </view>
    <view v-if="isTeacher" class="quick-row">
      <text class="quick-btn" @tap="goCert">📋 认证</text>
      <text class="quick-btn" @tap="goClasses">🏫 班级管理</text>
    </view>
```
script 加：
```typescript
import { request } from '@/utils/request'
const certStatus = ref<string>('uncertified')
const certStatusLabel = computed(() => ({ uncertified: '未认证', pending: '审核中', rejected: '已拒绝', certified: '已认证' } as any)[certStatus.value] || certStatus.value)
function goCert() { uni.navigateTo({ url: '/pages/teacher/cert' }) }
function goClasses() { uni.navigateTo({ url: '/pages/teacher/classes' }) }
async function loadCertStatus() {
  if (!isTeacher.value) return
  try { const r: any = await request('/teacher/profile', { method: 'POST', data: {} }); certStatus.value = r.data?.cert_status || 'uncertified' } catch {}
}
```
现有 onMounted 末尾加 `await loadCertStatus()`。

样式追加：
```css
.cert-banner { background: var(--c-orange); color: #fff; font-size: 24rpx; font-weight: 700; padding: 16rpx 24rpx; border-radius: var(--r-md); margin-bottom: 12rpx; text-align: center; }
.quick-row { display: flex; gap: 12rpx; margin-bottom: 12rpx; }
.quick-btn { flex: 1; text-align: center; background: var(--c-primary-faint); color: var(--c-ink); border: 2rpx solid var(--c-gold); border-radius: var(--r-md); padding: 16rpx; font-size: 26rpx; font-weight: 600; }
```

- [ ] **Step 10: 修改 pages/teacher/student-detail.vue 加"查看学情报告"入口**

READ 文件，在第一个 wq-card **之前**（即学生错题列表之前）加：
```vue
    <view class="card report-entry" @tap="goReport">
      <text class="report-text">📊 查看学情报告</text>
      <text class="arrow">›</text>
    </view>
```
script 加：
```typescript
function goReport() { uni.navigateTo({ url: `/pages/teacher/student-diagnosis?studentId=${studentId.value}` }) }
```
样式：
```css
.report-entry { display: flex; justify-content: space-between; align-items: center; }
.report-text { font-size: 28rpx; color: var(--c-ink); font-weight: 700; }
.arrow { font-size: 32rpx; color: var(--c-text-hint); }
```

- [ ] **Step 11: 提交前端**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add frontend/miniprogram/src/types/api.ts \
        frontend/miniprogram/src/api/teacher.ts \
        frontend/miniprogram/src/api/classes.ts \
        frontend/miniprogram/src/pages.json \
        frontend/miniprogram/src/pages/teacher/cert.vue \
        frontend/miniprogram/src/pages/teacher/student-diagnosis.vue \
        frontend/miniprogram/src/pages/teacher/classes.vue \
        frontend/miniprogram/src/pages/teacher/class-detail.vue \
        frontend/miniprogram/src/pages/teacher/students.vue \
        frontend/miniprogram/src/pages/teacher/student-detail.vue
git commit -m "feat(teacher): frontend — cert + student diagnosis + class management + class report"
```

---

## Task 5: 集成验证 + 归档 D-075 + Push

- [ ] **Step 1: 全量后端测试**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer/backend
python -m pytest ../tests/ -q
```
Expected: 200+ PASS（含 7 个新 test_teacher_p0）

- [ ] **Step 2: live server 冒烟，确认所有新端点**

```bash
uvicorn app.main:app --port 8026 --log-level warning &
UVICORN_PID=$!
sleep 3
curl -s http://localhost:8026/openapi.json | python3 -c "
import json,sys
spec = json.load(sys.stdin)
paths = sorted([p for p in spec['paths'].keys() if any(k in p for k in ['cert/', '/classes', 'diagnosis-report', '/admin/'])])
print('Plan K 新端点:')
for p in paths: print('  ', p)
"
kill $UVICORN_PID 2>/dev/null || true
sleep 1
```
Expected: cert/submit + 6 classes + diagnosis-report + admin review ≈ 9 个

- [ ] **Step 3: 归档 D-075 到 `docs/决策归档.md`（插入在 D-074 之前）**

```markdown
## D-075｜老师端 P0 三项补完：cert 审核 + 学生学情 + 班级综合报告

**日期：** 2026-05-29
**背景：** P0 学生端完成后，老师端尚缺 3 项关键能力：(1) 认证审核流程（含等待期权限控制）、(2) 老师查看绑定学生的完整学情报告、(3) 班级综合报告。本批补齐使老师端进入可用状态。
**结论：**
1. **无新迁移：** Teacher.cert_status/cert_doc_url、Class/ClassStudent（d7_teacher）均已在迁移 0001 内。
2. **cert 流程：** 老师调 `POST /teacher/cert/submit { cert_doc_url }` 提交认证；`auto_approve_teacher_cert=True`（dev 默认）时直接 certified，便于本地全链路自测；生产置 False 由 admin 调 `POST /admin/teachers/{id}/review { approve, reason }` 审核（require_role("platform_admin") gate）。
3. **认证 gate：** 新 helper `teacher_service.ensure_certified` + `_require_certified_teacher`，所有教师写操作（生成邀请码 / 加批注 / 查学生列表 / 查学生错题 / 查学生学情 / 班级 CRUD）前调用，cert_status != certified 抛 403。原 test_teacher.py 的 teacher_headers fixture 同步补 cert/submit 一行避免回归。
4. **学生学情：** `GET /teacher/students/{id}/diagnosis-report` 复用 `diagnosis_service.get_diagnosis_report`，前置绑定校验 + cert gate；前端在学生详情页加入口跳到 `pages/teacher/student-diagnosis.vue`（复用学生侧诊断报告 UI 风格）。
5. **班级：** 6 个 CRUD 端点 `/teacher/classes` POST/GET、`/teacher/classes/{id}` DELETE、`/teacher/classes/{id}/students` POST/GET、`/teacher/classes/{id}/students/{sid}` DELETE。加学生时校验必须是该老师的绑定学生（防越权拉人）。
6. **班级综合报告：** `GET /teacher/classes/{id}/report` 调 `class_service.build_class_report`，对班内每个学生跑 `get_diagnosis_report` 后用 Counter 聚合（高频错误 top10、薄弱知识点 top10、班均掌握率、按掌握率降序的学生排名）；MVP 班级规模 < 50 内存聚合可接受，后续可换 SQL 聚合。
7. **管理员入口：** 新 `/admin` router，第一个端点是 teacher cert review；为后续平台管理功能（机构审核等）预留挂点。
8. **前端：** 4 个新页 cert / student-diagnosis / classes / class-detail（含学生 tab + 综合报告 tab）；教师中心首页顶部加未认证横幅 + 班级管理快捷按钮；学生详情加学情报告入口。全部使用黄油相机风 token。
9. **测试：** 7 个新测试（cert auto-approve + 未认证拦截 + admin 审核通过 + 学生学情 + unbound 403 + class CRUD + add unbound 400 + 空班报告），全量 200+ PASS。
**遗留：** 平台管理 Web 端 UI（admin endpoint 已就绪可用 curl）；班级综合报告 SQL 聚合化（性能优化）；班级与机构（institution_id）联动（待机构端就绪）；老师查看学生**未绑定时** 的引导提示（按需可加 UI）；前端"添加学生到班级"目前需手填 UUID（可优化为从绑定学生下拉选择）。

**影响范围：** 无新迁移；后端 9 个新端点；4 个新前端页 + 2 个修改；测试 +7；已推送 GitHub main 分支。

---

```

- [ ] **Step 4: 提交 + push**

```bash
cd /Users/johnlu/Desktop/ComeMoney/项目/ai-education/engGramer
git add "docs/决策归档.md"
git commit -m "docs: archive D-075 — teacher P0 three items complete"
git push
```

---

## Self-Review

### Spec 覆盖
| P0 老师端条目 | 实现 |
|---|---|
| 注册认证（含审核等待期权限控制） | Task 0：cert submit + admin review + ensure_certified gate |
| 绑定学生 | 已有（D-069）|
| 查看学生学情报告 | Task 1：复用 diagnosis_service |
| 班级综合报告 | Task 2+3：class CRUD + build_class_report |

### 类型一致性
- `cert_status` 在 model / schema / 前端 chip / banner 都是 4 值字符串
- `ensure_certified` 被所有写操作和敏感读操作复用，签名一致
- `build_class_report` 内部用 `diagnosis_service.get_diagnosis_report` 字段名（mastery_rate / top_error_types / top_weak_knowledge_points）与 DiagnosisReport schema 完全一致

### Placeholder 扫描
无 TBD/TODO；前端"添加学生到班级"用 UUID 手填属 MVP 简化已在归档明列；admin Web UI 未做也明列。
