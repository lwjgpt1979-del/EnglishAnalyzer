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


def test_classify_cloze_slot():
    c = qas.classify_cloze_slot
    assert c(["A. Happily", "B. Usually", "C. Unluckily", "D. Hopefully"]) == "副词槽"
    assert c(["A. but", "B. and", "C. so", "D. or"]) == "连词槽"
    assert c(["A. in", "B. on", "C. at", "D. for"]) == "介词槽"
    assert c(["A. Thanks", "B. Sorry", "C. Excuse me", "D. Please"]) == "交际用语槽"
    assert c(["A. goes", "B. going", "C. gone", "D. go"]) == "动词形式槽"
    # 混合词性/短语(his brother/himself…)→ 拿不准交 LLM
    assert c(["A. his brother", "B. his sister", "C. his parents", "D. himself"]) is None
    assert c(None) is None


def test_validate_cloze_analysis():
    ok = {"slot": "副词槽", "clue_type": "跨句逻辑关系",
          "clue": "He runs for half an hour", "kp_codes": ["rc-6-1"],
          "distractors": {"A": {"meaning": "开心地", "why_wrong": "与沮丧基调相反"}}}
    assert qas.validate_cloze_analysis(ok, context_text=_PASSAGE) == []
    assert any("幻觉" in e for e in qas.validate_cloze_analysis(
        {**ok, "clue": "made-up sentence"}, context_text=_PASSAGE))
    assert any("clue_type" in e for e in qas.validate_cloze_analysis(
        {**ok, "clue_type": "瞎编类型"}, context_text=_PASSAGE))
    assert any("kp_codes" in e for e in qas.validate_cloze_analysis(
        {**ok, "kp_codes": []}, context_text=_PASSAGE))
    assert any("载体槽" in e for e in qas.validate_cloze_analysis(
        {**ok, "slot": "神仙槽"}, context_text=_PASSAGE))
    # 干扰项必须 原义+干扰机制 双全(半空/枚举串都不行)
    assert any("meaning" in e for e in qas.validate_cloze_analysis(
        {**ok, "distractors": {"A": {"meaning": "开心地", "why_wrong": " "}}},
        context_text=_PASSAGE))
    assert any("须为对象" in e or "meaning" in e for e in qas.validate_cloze_analysis(
        {**ok, "distractors": {"A": "无中生有"}}, context_text=_PASSAGE))


def test_parse_options_from_stem():
    # 切题器把选项留在 stem、options 列为空(徐州卷实况:tab 分隔)
    stem = "11. A. Happily\tB. Usually\tC. Unluckily\tD. Hopefully"
    assert qas.parse_options_from_stem(stem) == ["Happily", "Usually", "Unluckily", "Hopefully"]
    assert qas.classify_cloze_slot(qas.parse_options_from_stem(stem)) == "副词槽"
    assert qas.parse_options_from_stem("plain sentence no options") is None
    assert qas.parse_options_from_stem("") is None


def test_analysis_constraints_text():
    t = qas.analysis_constraints_text({
        "clue_type": "跨句逻辑关系", "slot": "副词槽",
        "distractors": {"B": {"meaning": "通常", "why_wrong": "与一次性事件矛盾"}}})
    assert "同线索类型" in t and "副词槽" in t and "与一次性事件矛盾" in t
    t2 = qas.analysis_constraints_text({"rc_code": "rc-1-1",
                                        "distractor_types": {"B": "无中生有"}})
    assert "rc-1-1" in t2 and "回文定位" in t2 and "无中生有" in t2
    assert qas.analysis_constraints_text(None) == ""


async def _seed_cloze(s) -> uuid.UUID:
    block_id = await pqs.create_passage(s, text=_PASSAGE)
    r = await pqs.import_real_question(
        s, stem="___11___", answer="C",
        options=["A. Happily", "B. Usually", "C. Unluckily", "D. Hopefully"],
        question_type="完型", section="完形填空", block_id=block_id, status="published")
    await s.flush()
    return r.question_id


@pytest.mark.asyncio
async def test_suggest_dispatch_cloze(db_session):
    """分发:完型走双轴建议(载体槽=程序判定的副词槽),不写库。"""
    qid = await _seed_cloze(db_session)
    items = await qas.suggest_analysis(db_session, question_ids=[qid])
    assert len(items) == 1 and items[0]["errors"] == []
    ana = items[0]["analysis"]
    assert ana["slot"] == "副词槽" and ana["clue_type"] in qas.CLUE_TYPES
    q = (await db_session.execute(
        select(PlatformQuestion).where(PlatformQuestion.id == qid))).scalar_one()
    assert not (q.meta or {}).get("analysis")


@pytest.mark.asyncio
async def test_suggest_cloze_options_embedded_in_stem(db_session):
    """徐州卷实况:options 列为空、选项嵌在 stem → 仍能程序判出载体槽。"""
    block_id = await pqs.create_passage(db_session, text=_PASSAGE)
    r = await pqs.import_real_question(
        db_session, stem="11. A. Happily\tB. Usually\tC. Unluckily\tD. Hopefully",
        answer=None, options=None,
        question_type="完型", section="完形填空", block_id=block_id, status="published")
    await db_session.flush()
    items = await qas.suggest_analysis(db_session, question_ids=[r.question_id])
    assert items[0]["analysis"]["slot"] == "副词槽"


@pytest.mark.asyncio
async def test_confirm_cloze_writes_with_kind(db_session):
    qid = await _seed_cloze(db_session)
    good = {"slot": "副词槽", "clue_type": "跨句逻辑关系",
            "clue": "Tom gets up at six every morning.",
            "kp_codes": ["rc-6-1"],
            "distractors": {"A": {"meaning": "开心地", "why_wrong": "与沮丧基调相反"}}}
    saved = await qas.confirm_analysis(
        db_session, question_id=qid, analysis=good, admin_id=uuid.uuid4())
    assert saved["kind"] == "cloze" and saved["confirmed_at"]
    from app.core.exceptions import AppError
    with pytest.raises(AppError):   # 图谱不存在的编码 → 拒绝
        await qas.confirm_analysis(db_session, question_id=qid,
                                   analysis={**good, "kp_codes": ["rc-99-99"]},
                                   admin_id=uuid.uuid4())


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
