# 机构端切片九：老师资源额度配置（出卷月额度，D-128）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 机构管理员给名下老师配每月出卷上限；出卷时校验本月额度，超额拒绝，未配置=不限。

**Architecture:** 迁移 0021 给 teachers 加 `monthly_paper_quota`（NULL=不限）。`create_assignment` 加闸门统计本月出卷数。零花钱、含迁移。

**Tech Stack:** FastAPI · SQLAlchemy 2.x asyncio · Alembic · Pydantic v2 · pytest · Vue3 · Element Plus

---

## 关键约定（实现者必读）

- 后端 python：`/opt/anaconda3/bin/python`；测试从 `backend/` 跑，`../tests/...`，`-p no:randomly`。
- 迁移命令：`cd backend && DATABASE_URL=$(grep -E '^DATABASE_URL=' .env | cut -d= -f2-) /opt/anaconda3/bin/python -m alembic upgrade head`
- 现有出卷测试的老师用 `upsert_user` 不建 `Teacher` 行 → `db.get(Teacher, id)` 返回 None → 闸门跳过（不破坏既有测试）。
- 测试夹具：service 用本地 `db_session`，见 `tests/services/test_institution_teacher.py` / `test_assignment_service.py`；api 用 `client`，见 `tests/api/test_institution_teacher.py`。
- 统一响应 `make_ok` + `BaseResponse[T]`；鉴权 `InstAdminDep`。

---

## File Structure

| 文件 | 职责 |
|------|------|
| `backend/alembic/versions/0021_teacher_paper_quota.py` | 迁移：teachers 加 monthly_paper_quota |
| `backend/app/models/d1_users.py` | Teacher 加列 |
| `backend/app/services/institution_service.py` | set_teacher_quota |
| `backend/app/services/assignment_service.py` | create_assignment 出卷闸门 |
| `backend/app/schemas/institution.py` | InstitutionTeacherOut +字段 / TeacherQuotaUpdate |
| `backend/app/api/v1/institution.py` | PATCH quota + list 回显 |
| `frontend/admin/src/api/institution.ts` · `views/InstitutionTeachers.vue` | 额度列 + 设额度 |

---

## Task 1: 迁移 0021 + 模型

**Files:**
- Create: `backend/alembic/versions/0021_teacher_paper_quota.py`
- Modify: `backend/app/models/d1_users.py`（Teacher）

- [ ] **Step 1: 模型加列**

在 `backend/app/models/d1_users.py` 的 `Teacher` 类内（`max_students` 之后）加：

```python
    # —— 机构出卷月额度（D-128；NULL=不限）——
    monthly_paper_quota = mapped_column(sa.Integer, nullable=True)
```

- [ ] **Step 2: 写迁移**

`backend/alembic/versions/0021_teacher_paper_quota.py`：

```python
"""teachers.monthly_paper_quota：机构出卷月额度（D-128）

Revision ID: 0021
Revises: 0020
"""
import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("teachers", sa.Column("monthly_paper_quota", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("teachers", "monthly_paper_quota")
```

- [ ] **Step 3: 跑迁移 + 验证**

Run: `cd backend && DATABASE_URL=$(grep -E '^DATABASE_URL=' .env | cut -d= -f2-) /opt/anaconda3/bin/python -m alembic upgrade head`
Expected: `Running upgrade 0020 -> 0021`。
Run: `cd backend && /opt/anaconda3/bin/python -c "from app.models.d1_users import Teacher; print('monthly_paper_quota' in Teacher.__table__.columns)"`
Expected: `True`。

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/0021_teacher_paper_quota.py backend/app/models/d1_users.py
git commit -m "feat(institution): 迁移0021 teachers.monthly_paper_quota + 模型加列"
```

---

## Task 2: set_teacher_quota service + 出卷闸门

**Files:**
- Modify: `backend/app/services/institution_service.py`, `backend/app/services/assignment_service.py`
- Test: `tests/services/test_teacher_quota.py`

- [ ] **Step 1: 写失败测试**

`tests/services/test_teacher_quota.py`：

```python
import uuid
import pytest
import pytest_asyncio
from datetime import datetime, timezone

from app.core.database import _async_session_factory
from app.core.exceptions import AppError
from app.models.d1_users import Institution, Teacher, User
from app.models.d7_teacher import ClassStudent
from app.services import assignment_service, class_service, institution_service


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _inst(s, name="A"):
    inst = Institution(id=uuid.uuid4(), name=name, contact_phone="1",
                       province_code="11", city_code="1101", address="街")
    s.add(inst)
    await s.flush()
    return inst.id


async def _teacher(s, inst_id, *, quota=None):
    uid = uuid.uuid4()
    s.add(User(id=uid, openid=f"o:{uid}", role="teacher"))
    await s.flush()
    s.add(Teacher(id=uid, institution_id=inst_id, monthly_paper_quota=quota))
    await s.flush()
    return uid


async def _class(s, teacher_id):
    return await class_service.create_class(s, teacher_id=teacher_id, name="一班")


_Q = [{"stem": "1+1=?", "answer": "2"}]


@pytest.mark.asyncio
async def test_set_teacher_quota(db_session):
    inst = await _inst(db_session)
    tid = await _teacher(db_session, inst)
    t = await institution_service.set_teacher_quota(
        db_session, institution_id=inst, teacher_id=tid, monthly_paper_quota=5)
    assert t.monthly_paper_quota == 5
    t = await institution_service.set_teacher_quota(
        db_session, institution_id=inst, teacher_id=tid, monthly_paper_quota=None)
    assert t.monthly_paper_quota is None


@pytest.mark.asyncio
async def test_set_quota_cross_institution_404(db_session):
    a = await _inst(db_session, "A")
    b = await _inst(db_session, "B")
    tid = await _teacher(db_session, b)
    with pytest.raises(AppError):
        await institution_service.set_teacher_quota(
            db_session, institution_id=a, teacher_id=tid, monthly_paper_quota=3)


@pytest.mark.asyncio
async def test_create_assignment_quota_gate(db_session):
    inst = await _inst(db_session)
    tid = await _teacher(db_session, inst, quota=1)
    cls = await _class(db_session, tid)
    # 第 1 份 OK
    await assignment_service.create_assignment(
        db_session, teacher_id=tid, class_id=cls.id, title="卷1", questions=_Q)
    # 第 2 份超额
    with pytest.raises(AppError):
        await assignment_service.create_assignment(
            db_session, teacher_id=tid, class_id=cls.id, title="卷2", questions=_Q)


@pytest.mark.asyncio
async def test_create_assignment_unlimited_when_null(db_session):
    inst = await _inst(db_session)
    tid = await _teacher(db_session, inst, quota=None)
    cls = await _class(db_session, tid)
    for i in range(3):
        await assignment_service.create_assignment(
            db_session, teacher_id=tid, class_id=cls.id, title=f"卷{i}", questions=_Q)
    # 不抛错即通过
```

- [ ] **Step 2: 跑测试看失败**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_teacher_quota.py -p no:randomly -q`
Expected: FAIL（set_teacher_quota 不存在 / 闸门未加）。

- [ ] **Step 3: 实现 set_teacher_quota**

在 `backend/app/services/institution_service.py` 末尾加（`Teacher` 已 import；`uuid`/`select`/`AppError` 已在文件内）：

```python
async def set_teacher_quota(
    db: AsyncSession, *, institution_id: uuid.UUID, teacher_id: uuid.UUID,
    monthly_paper_quota: int | None,
) -> Teacher:
    t = (await db.execute(
        select(Teacher).where(
            Teacher.id == teacher_id, Teacher.institution_id == institution_id
        )
    )).scalar_one_or_none()
    if t is None:
        raise AppError(code=404, message="老师不存在或不属于本机构")
    t.monthly_paper_quota = monthly_paper_quota
    await db.flush()
    return t
```

- [ ] **Step 4: 加出卷闸门**

在 `backend/app/services/assignment_service.py`：
- import：`from sqlalchemy import delete, select` 改为 `from sqlalchemy import delete, func, select`；加 `from app.models.d1_users import Teacher`。
- `create_assignment` 内 `await class_service._get_owned_class(...)` 之后插入：

```python
    teacher = await db.get(Teacher, teacher_id)
    if teacher is not None and teacher.monthly_paper_quota is not None:
        month_start = datetime.now(timezone.utc).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0)
        used = (await db.execute(
            select(func.count()).select_from(Assignment).where(
                Assignment.teacher_id == teacher_id,
                Assignment.created_at >= month_start,
            )
        )).scalar_one()
        if used >= teacher.monthly_paper_quota:
            raise AppError(code=403, message="本月出卷额度已用尽，请联系机构管理员")
```

- [ ] **Step 5: 跑测试看通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/services/test_teacher_quota.py -p no:randomly -q`
Expected: 4 passed。

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/institution_service.py backend/app/services/assignment_service.py tests/services/test_teacher_quota.py
git commit -m "feat(institution): set_teacher_quota + 出卷月额度闸门"
```

---

## Task 3: schemas + API

**Files:**
- Modify: `backend/app/schemas/institution.py`, `backend/app/api/v1/institution.py`
- Test: `tests/api/test_teacher_quota.py`

- [ ] **Step 1: schemas**

在 `backend/app/schemas/institution.py`：
- `InstitutionTeacherOut` 加字段 `monthly_paper_quota: int | None = None`
- 末尾加：

```python
class TeacherQuotaUpdate(BaseModel):
    monthly_paper_quota: int | None
```

- [ ] **Step 2: 改 list_teachers 回显 + 加 PATCH endpoint**

在 `backend/app/api/v1/institution.py`：
- import institution schema 加 `TeacherQuotaUpdate`。
- `list_institution_teachers` 的 `InstitutionTeacherOut(...)` 构造加 `monthly_paper_quota=t.monthly_paper_quota`。
- 末尾加：

```python
@router.patch("/teachers/{teacher_id}/quota", response_model=BaseResponse[InstitutionTeacherOut])
async def set_teacher_quota_api(
    teacher_id: uuid.UUID, body: TeacherQuotaUpdate, db: DbDep, admin: InstAdminDep,
):
    inst_id = _require_inst(admin)
    t = await institution_service.set_teacher_quota(
        db, institution_id=inst_id, teacher_id=teacher_id,
        monthly_paper_quota=body.monthly_paper_quota)
    await db.commit()
    # 取 User 拼装展示
    from app.models.d1_users import User
    u = await db.get(User, teacher_id)
    return make_ok(InstitutionTeacherOut(
        id=t.id, nickname=u.nickname if u else None, phone=u.phone if u else None,
        subject=t.subject, cert_status=str(t.cert_status),
        monthly_paper_quota=t.monthly_paper_quota,
    ))
```

- [ ] **Step 3: 写 api 测试**

`tests/api/test_teacher_quota.py`：

```python
import uuid
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from httpx import ASGITransport, AsyncClient

from app.core.database import _async_session_factory
from app.main import app
from app.models.d1_users import Institution, Teacher, User
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
        tid = uuid.uuid4()
        s.add(User(id=tid, openid=f"o:{tid}", role="teacher", nickname="王老师"))
        await s.flush()
        s.add(Teacher(id=tid, institution_id=inst.id))
        await s.commit()
        return inst.id, tid


async def _login(client, username):
    r = await client.post("/api/v1/admin/auth/login",
                          json={"username": username, "password": "pw123456"})
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


@pytest.mark.asyncio
async def test_set_quota_and_list(client):
    uname = f"ia_{uuid.uuid4().hex[:6]}"
    _, tid = await _setup_admin(uname)
    h = await _login(client, uname)
    r = await client.patch(f"/api/v1/institution/teachers/{tid}/quota",
                           headers=h, json={"monthly_paper_quota": 10})
    assert r.status_code == 200
    assert r.json()["data"]["monthly_paper_quota"] == 10
    rows = (await client.get("/api/v1/institution/teachers", headers=h)).json()["data"]
    assert any(t["id"] == str(tid) and t["monthly_paper_quota"] == 10 for t in rows)
```

- [ ] **Step 4: 跑测试看通过**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests/api/test_teacher_quota.py -p no:randomly -q`
Expected: 1 passed。

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/institution.py backend/app/api/v1/institution.py tests/api/test_teacher_quota.py
git commit -m "feat(institution): 老师额度 API（PATCH quota + 列表回显）"
```

---

## Task 4: 后端全量回归

- [ ] **Step 1: 跑全量**

Run: `cd backend && /opt/anaconda3/bin/python -m pytest ../tests -p no:randomly -q`
Expected: 新增 5 测试全过；既有 assignment 测试不受影响（老师无 Teacher 行→闸门跳过）；已知偶发污染项隔离复跑确认。

---

## Task 5: admin web 老师管理页加额度

**Files:**
- Modify: `frontend/admin/src/api/institution.ts`, `frontend/admin/src/views/InstitutionTeachers.vue`

- [ ] **Step 1: api 层**

在 `frontend/admin/src/api/institution.ts`：
- `InstitutionTeacher` interface 加 `monthly_paper_quota: number | null`。
- 末尾加：

```typescript
export function setTeacherQuota(teacherId: string, quota: number | null): Promise<InstitutionTeacher> {
  return unwrap<InstitutionTeacher>(request.patch(`/institution/teachers/${teacherId}/quota`, { monthly_paper_quota: quota }))
}
```

- [ ] **Step 2: 页面加额度列 + 设额度**

在 `frontend/admin/src/views/InstitutionTeachers.vue`：
- import 加 `setTeacherQuota`、`ElMessageBox`（若未引入）。
- 表格在「认证状态」列后加：

```vue
      <el-table-column label="月出卷额度">
        <template #default="{ row }">{{ row.monthly_paper_quota ?? '不限' }}</template>
      </el-table-column>
```

- 「操作」列加按钮（与「移出机构」并列）：

```vue
          <el-button type="primary" text @click="setQuota(row)">设额度</el-button>
```

- script 加方法：

```typescript
async function setQuota(t: InstitutionTeacher) {
  const { value } = await ElMessageBox.prompt(
    '每月出卷上限（留空=不限）', '设置额度',
    { inputValue: t.monthly_paper_quota?.toString() ?? '' })
  const q = value === '' || value == null ? null : Number(value)
  if (q !== null && (Number.isNaN(q) || q < 0)) { ElMessage.error('请输入非负整数'); return }
  await setTeacherQuota(t.id, q)
  ElMessage.success('已设置')
  await load()
}
```

（`load`/`ElMessage` 已在该页存在；`InstitutionTeacher` 类型从 api import。）

- [ ] **Step 3: 构建**

Run: `cd frontend/admin && npm run build`
Expected: 构建成功。

- [ ] **Step 4: Commit**

```bash
git add frontend/admin/src/api/institution.ts frontend/admin/src/views/InstitutionTeachers.vue
git commit -m "feat(institution-web): 老师管理加 月出卷额度 列 + 设额度"
```

---

## Task 6: 归档 D-128 + 清单同步

**Files:**
- Modify: `docs/决策归档.md`, `docs/上线前清单.md`

- [ ] **Step 1: 归档**

`docs/决策归档.md` 顶部加 D-128（日期 2026-06-04 / 背景 / 结论 / 测试 / 影响范围 / 未做 / 相关 D-113 D-121、需求 §1166）。

- [ ] **Step 2: 清单**

`docs/上线前清单.md`：dev-mock/迁移节注明迁移到 0021；机构端 M4（老师管理）行补「+ 月出卷额度配置（D-128）」。

- [ ] **Step 3: Commit**

```bash
git add docs/决策归档.md docs/上线前清单.md docs/superpowers/plans/2026-06-04-institution-teacher-quota.md
git commit -m "docs: 归档 D-128 老师资源额度配置（出卷月额度）"
```

---

## Self-Review 结论

- **Spec 覆盖**：迁移+模型→Task1；set_quota+闸门→Task2；schemas+API→Task3；回归→Task4；admin 页→Task5；归档→Task6。全覆盖。
- **占位符**：无 TBD；改码步骤含完整代码。
- **类型一致**：`set_teacher_quota(institution_id,teacher_id,monthly_paper_quota)→Teacher` 在 service/api/test 一致；`InstitutionTeacherOut` 加 `monthly_paper_quota`（service 拼装/前端 interface/测试断言一致）；闸门用 `Assignment.teacher_id + created_at>=月初` 计数，NULL 不限。
