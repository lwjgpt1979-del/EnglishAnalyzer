"""机构端老师管理 service 测试（D-121）。"""
import uuid

import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.core.exceptions import AppError
from app.models.d1_users import Institution, Teacher, User
from app.services import institution_service


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _inst(s, name="A机构"):
    inst = Institution(id=uuid.uuid4(), name=name, contact_phone="138",
                       province_code="11", city_code="1101", address="街")
    s.add(inst)
    await s.flush()
    return inst


async def _teacher(s, inst_id, *, nickname="王老师"):
    uid = uuid.uuid4()
    s.add(User(id=uid, openid=f"o:{uid}", role="teacher", nickname=nickname))
    await s.flush()
    s.add(Teacher(id=uid, institution_id=inst_id))
    await s.flush()
    return uid


@pytest.mark.asyncio
async def test_generate_join_code(db_session):
    inst = await _inst(db_session)
    admin = uuid.uuid4()
    db_session.add(User(id=admin, openid=f"o:{admin}", role="institution_admin",
                        institution_id=inst.id))
    await db_session.flush()
    code = await institution_service.generate_join_code(
        db_session, institution_id=inst.id, issuer_id=admin)
    assert len(code.code) == 6
    assert str(code.type) == "institution_join"


@pytest.mark.asyncio
async def test_list_teachers_isolated(db_session):
    a = await _inst(db_session, "A")
    b = await _inst(db_session, "B")
    await _teacher(db_session, a.id)
    await _teacher(db_session, b.id)
    rows = await institution_service.list_teachers(db_session, institution_id=a.id)
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_remove_teacher(db_session):
    a = await _inst(db_session, "A")
    tid = await _teacher(db_session, a.id)
    await institution_service.remove_teacher(db_session, institution_id=a.id, teacher_id=tid)
    t = await db_session.get(Teacher, tid)
    assert t.institution_id is None


@pytest.mark.asyncio
async def test_remove_teacher_cross_institution_404(db_session):
    a = await _inst(db_session, "A")
    b = await _inst(db_session, "B")
    tid = await _teacher(db_session, b.id)
    with pytest.raises(AppError):
        await institution_service.remove_teacher(db_session, institution_id=a.id, teacher_id=tid)
