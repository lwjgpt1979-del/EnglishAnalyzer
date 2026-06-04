"""老师出卷月额度 service 测试（D-128）。"""
import uuid

import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.core.exceptions import AppError
from app.models.d1_users import Institution, Teacher, User
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
    await assignment_service.create_assignment(
        db_session, teacher_id=tid, class_id=cls.id, title="卷1", questions=_Q)
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
