"""单元结构化解析落库:语法点+分级句 / 听力考点+句组 / 作文要求+正文。"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text as _t

from app.core.database import _async_session_factory
from app.models.d4_knowledge import CurriculumUnit
from app.models.d22_unit_structured import UnitSection, UnitSectionSentence
from app.services import curriculum_service as cs


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


@pytest.mark.asyncio
async def test_persist_unit_structured_overwrites_and_scores(db_session):
    tb = f"结构版{uuid.uuid4().hex[:6]}"
    uid = uuid.uuid4()
    db_session.add(CurriculumUnit(id=uid, textbook_version=tb, grade="七年级",
                                  semester="上", unit_no=1, unit_title="U1"))
    await db_session.flush()

    parsed = {
        "grammar": [{"point": "一般现在时", "sentences": [
            "He is always full of energy.", "He often plays football after school."]}],
        "listening": [{"point": "对话主题", "sentences": ["Good morning, class."]}],
        "writing": {"requirement": "Write about yourself.", "text": "My name is ... I am ..."},
    }
    counts = await cs.persist_unit_structured(db_session, unit_id=uid, parsed=parsed)
    await db_session.flush()
    assert counts == {"grammar": 1, "listening": 1, "writing": 1, "sentences": 3}

    from sqlalchemy import select
    secs = (await db_session.execute(
        select(UnitSection).where(UnitSection.unit_id == uid))).scalars().all()
    kinds = sorted(s.kind for s in secs)
    assert kinds == ["grammar", "listening", "writing"]
    gram = next(s for s in secs if s.kind == "grammar")
    assert gram.point_name == "一般现在时" and gram.node_id is None   # 第一步 node 留空
    wri = next(s for s in secs if s.kind == "writing")
    assert wri.body_text and "My name is" in wri.body_text

    # 句子都算了 0–100 难度
    sents = (await db_session.execute(
        select(UnitSectionSentence).where(UnitSectionSentence.section_id == gram.id))).scalars().all()
    assert len(sents) == 2
    assert all(s.difficulty is None or 0 <= s.difficulty <= 100 for s in sents)

    # 整体覆盖:再存一份只含 1 个语法点 → 旧的被清掉
    await cs.persist_unit_structured(db_session, unit_id=uid, parsed={
        "grammar": [{"point": "be 动词", "sentences": ["I am Millie."]}],
        "listening": [], "writing": None})
    await db_session.flush()
    secs2 = (await db_session.execute(
        select(UnitSection).where(UnitSection.unit_id == uid))).scalars().all()
    assert len(secs2) == 1 and secs2[0].point_name == "be 动词"

    # 清理
    await db_session.execute(_t("DELETE FROM curriculum_units WHERE id=:u"), {"u": str(uid)})
    await db_session.commit()
