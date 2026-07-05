"""题目层解析(阅读试点)测试:校验器一票否决 + 建议不落库 + 人工确认唯一写库。"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.database import _async_session_factory
from app.models.d16_question_domain import PlatformQuestion
from app.services import platform_question_service as pqs
from app.services import question_analysis_service as qas

_PASSAGE = ("Tom gets up at six every morning. He runs for half an hour and then has "
            "breakfast. After that he goes to school by bike.")


def test_validator_evidence_substring():
    ok = {"rc_code": "rc-1-1", "evidence": "He runs for half an hour",
          "answer_reason": "细节定位", "distractor_types": {"B": "无中生有"}}
    assert qas.validate_reading_analysis(ok, context_text=_PASSAGE) == []
    # 幻觉定位句 → 一票否决
    bad = {**ok, "evidence": "Tom swims every evening."}
    assert any("幻觉" in e for e in qas.validate_reading_analysis(bad, context_text=_PASSAGE))
    # 空白归一:换行/多空格不影响子串比对
    ws = {**ok, "evidence": "He runs  for half\n an hour"}
    assert qas.validate_reading_analysis(ws, context_text=_PASSAGE) == []


def test_validator_enum_and_fields():
    base = {"rc_code": "rc-1-1", "evidence": "Tom gets up at six",
            "answer_reason": "ok", "distractor_types": {}}
    assert qas.validate_reading_analysis(base, context_text=_PASSAGE) == []
    assert any("枚举" in e for e in qas.validate_reading_analysis(
        {**base, "distractor_types": {"B": "瞎编的错因"}}, context_text=_PASSAGE))
    assert any("rc_code" in e for e in qas.validate_reading_analysis(
        {**base, "rc_code": "xx-9"}, context_text=_PASSAGE))
    assert any("answer_reason" in e for e in qas.validate_reading_analysis(
        {**base, "answer_reason": " "}, context_text=_PASSAGE))


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _seed_reading(s) -> uuid.UUID:
    block_id = await pqs.create_passage(s, text=_PASSAGE)
    r = await pqs.import_real_question(
        s, stem="When does Tom run?", answer="A",
        options=["A. Before breakfast", "B. After school", "C. At noon", "D. At night"],
        question_type="阅读", section="阅读理解", block_id=block_id, status="published")
    await s.flush()
    return r.question_id


@pytest.mark.asyncio
async def test_suggest_does_not_write(db_session):
    qid = await _seed_reading(db_session)
    items = await qas.suggest_reading_analysis(db_session, question_ids=[qid])
    assert len(items) == 1 and items[0]["errors"] == []
    assert items[0]["analysis"]["evidence"]          # dev-mock 定位句
    q = (await db_session.execute(
        select(PlatformQuestion).where(PlatformQuestion.id == qid))).scalar_one()
    assert not (q.meta or {}).get("analysis")        # 建议不落库


@pytest.mark.asyncio
async def test_confirm_writes_and_rejects_invalid(db_session):
    qid = await _seed_reading(db_session)
    admin_id = uuid.uuid4()
    good = {"rc_code": "rc-1-1", "evidence": "He runs for half an hour and then has breakfast.",
            "answer_reason": "then 表先后,跑步在早餐前。", "distractor_types": {"B": "无中生有"}}
    saved = await qas.confirm_analysis(
        db_session, question_id=qid, analysis=good, admin_id=admin_id)
    assert saved["confirmed_by"] == str(admin_id) and saved["confirmed_at"]
    q = (await db_session.execute(
        select(PlatformQuestion).where(PlatformQuestion.id == qid))).scalar_one()
    assert (q.meta or {}).get("analysis", {}).get("evidence") == good["evidence"]
    # 幻觉定位句 → 拒绝写库
    from app.core.exceptions import AppError
    with pytest.raises(AppError):
        await qas.confirm_analysis(db_session, question_id=qid,
                                   analysis={**good, "evidence": "made-up sentence."},
                                   admin_id=admin_id)
