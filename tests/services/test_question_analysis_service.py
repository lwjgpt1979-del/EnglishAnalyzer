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
          "answer_reason": "细节定位",
          "distractors": {"B": {"meaning": "放学后跑步", "why_wrong": "与定位句时间冲突"}}}
    assert qas.validate_reading_analysis(ok, context_text=_PASSAGE) == []
    # 幻觉定位句 → 一票否决
    bad = {**ok, "evidence": "Tom swims every evening."}
    assert any("幻觉" in e for e in qas.validate_reading_analysis(bad, context_text=_PASSAGE))
    # 空白归一:换行/多空格不影响子串比对
    ws = {**ok, "evidence": "He runs  for half\n an hour"}
    assert qas.validate_reading_analysis(ws, context_text=_PASSAGE) == []


def test_validator_distractors_and_fields():
    # 阅读干扰项与完形同构:原义(meaning)+干扰机制(why_wrong);空 distractors 允许(可只标错项)
    base = {"rc_code": "rc-1-1", "evidence": "Tom gets up at six",
            "answer_reason": "ok", "distractors": {}}
    assert qas.validate_reading_analysis(base, context_text=_PASSAGE) == []
    # 干扰项半空(缺 why_wrong)→ 报错
    assert any("干扰机制" in e or "meaning" in e for e in qas.validate_reading_analysis(
        {**base, "distractors": {"B": {"meaning": "放学后", "why_wrong": " "}}}, context_text=_PASSAGE))
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


_ESSAY = ("Only by working hard can we grow. I am grateful to my parents for their love.")


def test_validate_writing_analysis():
    ok = {"genre": "应用文", "sub_format": "演讲稿",
          "points": [{"id": 1, "point": "懂感恩"}], "main_tense": "一般现在时",
          "wr_codes": ["wr-1-2"], "model_essay": _ESSAY,
          "target_expressions": ["Only by working hard can we grow"],
          "pitfalls": [{"type": "时态", "trap": "易误用过去时"}]}
    assert qas.validate_writing_analysis(ok, context_text="") == []
    # 体裁非枚举
    assert any("genre" in e for e in qas.validate_writing_analysis(
        {**ok, "genre": "神仙文"}, context_text=""))
    # 要点空
    assert any("points" in e for e in qas.validate_writing_analysis(
        {**ok, "points": []}, context_text=""))
    # wr_codes 空
    assert any("wr_codes" in e for e in qas.validate_writing_analysis(
        {**ok, "wr_codes": []}, context_text=""))
    # 范文缺
    assert any("model_essay" in e or "范文" in e for e in qas.validate_writing_analysis(
        {**ok, "model_essay": " "}, context_text=""))
    # 目标句型不是范文子串 → 幻觉
    assert any("幻觉" in e for e in qas.validate_writing_analysis(
        {**ok, "target_expressions": ["a sentence not in the essay"]}, context_text=""))
    # 结构套路选填,合式通过;每段 guide 空 → 报错
    assert qas.validate_writing_analysis(
        {**ok, "structure": [{"role": "开头", "guide": "问候引题 Good morning!"}]}, context_text="") == []
    assert any("structure" in e for e in qas.validate_writing_analysis(
        {**ok, "structure": [{"role": "开头", "guide": " "}]}, context_text=""))


async def _seed_writing(s) -> uuid.UUID:
    r = await pqs.import_real_question(
        s, stem="以 To be a better self 为题写一篇演讲稿,从懂感恩、亲自然、爱自己三方面谈。",
        answer=None, options=None,
        question_type="写作", section="书面表达", status="published")
    await s.flush()
    return r.question_id


@pytest.mark.asyncio
async def test_suggest_dispatch_writing(db_session):
    """分发:书面表达走写作建议(体裁/要点/范文/目标句型),不写库。"""
    qid = await _seed_writing(db_session)
    items = await qas.suggest_analysis(db_session, question_ids=[qid])
    assert len(items) == 1
    ana = items[0]["analysis"]
    assert ana["genre"] in qas.WRITING_GENRES and ana["points"] and ana["model_essay"]
    q = (await db_session.execute(
        select(PlatformQuestion).where(PlatformQuestion.id == qid))).scalar_one()
    assert not (q.meta or {}).get("analysis")     # 建议不落库


@pytest.mark.asyncio
async def test_confirm_writing_writes_with_kind(db_session):
    qid = await _seed_writing(db_session)
    good = {"genre": "应用文", "sub_format": "演讲稿",
            "points": [{"id": 1, "point": "懂感恩"}], "main_tense": "一般现在时",
            "wr_codes": ["wr-1-2"], "model_essay": _ESSAY,
            "target_expressions": ["Only by working hard can we grow"]}
    saved = await qas.confirm_analysis(
        db_session, question_id=qid, analysis=good, admin_id=uuid.uuid4())
    assert saved["kind"] == "writing" and saved["confirmed_at"]
    # 确认时 wr_codes 自动挂成 platform_question_kp 边(供 BKT/仿真继承/学情统计)
    from app.models.d15_knowledge_graph import KnowledgeNode
    from app.models.d16_question_domain import PlatformQuestionKp
    edge_codes = (await db_session.execute(
        select(KnowledgeNode.code).join(PlatformQuestionKp, PlatformQuestionKp.node_id == KnowledgeNode.id)
        .where(PlatformQuestionKp.question_id == qid))).scalars().all()
    assert "wr-1-2" in edge_codes
    from app.core.exceptions import AppError
    with pytest.raises(AppError):   # 图谱不存在的写作编码 → 拒绝
        await qas.confirm_analysis(db_session, question_id=qid,
                                   analysis={**good, "wr_codes": ["wr-99-99"]},
                                   admin_id=uuid.uuid4())


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


def test_validate_grammar_mc_analysis():
    ok = {"kp_codes": ["jf-1-1"], "answer_reason": "一般现在时第三人称加 s",
          "distractors": {"A": {"meaning": "原形", "why_wrong": "主语第三人称单数,谓语须加 s"}}}
    assert qas.validate_grammar_mc_analysis(ok) == []
    # 非 cf-/jf- 编码 → 拒
    assert any("cf-" in e or "jf-" in e for e in qas.validate_grammar_mc_analysis(
        {**ok, "kp_codes": ["rc-1-1"]}))
    # kp_codes 空 / 答案依据空 / 干扰项半空
    assert any("kp_codes" in e for e in qas.validate_grammar_mc_analysis({**ok, "kp_codes": []}))
    assert any("answer_reason" in e for e in qas.validate_grammar_mc_analysis({**ok, "answer_reason": " "}))
    assert any("违规机制" in e or "meaning" in e for e in qas.validate_grammar_mc_analysis(
        {**ok, "distractors": {"A": {"meaning": "原形", "why_wrong": " "}}}))


async def _seed_grammar_mc(s, *, answer="B") -> uuid.UUID:
    r = await pqs.import_real_question(
        s, stem="He ____ to school every day.", answer=answer,
        options=["A. go", "B. goes", "C. going", "D. gone"],
        question_type="单选", section="单项选择", status="published")
    await s.flush()
    return r.question_id


@pytest.mark.asyncio
async def test_suggest_dispatch_grammar_mc(db_session):
    """分发:语法单选(单选·非阅读/听力段)走 grammar_mc 建议(cf/jf 考点 + 干扰项违规机制),不写库。"""
    qid = await _seed_grammar_mc(db_session)
    items = await qas.suggest_analysis(db_session, question_ids=[qid])
    ana = items[0]["analysis"]
    assert ana and ana.get("kp_codes") and ana.get("distractors")   # grammar_mc 形态(非 rc_code/clue_type/genre)
    assert "rc_code" not in ana and "clue_type" not in ana
    q = (await db_session.execute(
        select(PlatformQuestion).where(PlatformQuestion.id == qid))).scalar_one()
    assert not (q.meta or {}).get("analysis")


@pytest.mark.asyncio
async def test_confirm_grammar_mc_writes_and_attaches_kp(db_session):
    qid = await _seed_grammar_mc(db_session)
    good = {"kp_codes": ["jf-1-1"], "answer_reason": "第三人称单数谓语加 s",
            "distractors": {"A": {"meaning": "动词原形", "why_wrong": "主语 He 为三单,谓语须加 s"}}}
    saved = await qas.confirm_analysis(db_session, question_id=qid, analysis=good, admin_id=uuid.uuid4())
    assert saved["kind"] == "grammar_mc" and saved["confirmed_at"]
    from app.models.d15_knowledge_graph import KnowledgeNode
    from app.models.d16_question_domain import PlatformQuestionKp
    codes = (await db_session.execute(
        select(KnowledgeNode.code).join(PlatformQuestionKp, PlatformQuestionKp.node_id == KnowledgeNode.id)
        .where(PlatformQuestionKp.question_id == qid))).scalars().all()
    assert "jf-1-1" in codes       # 确认即自动挂 cf/jf 考点边


def test_validate_word_fill_analysis():
    ok = {"given": "divide", "target_form": "was dividing", "change_type": "过去进行时",
          "kp_codes": ["jf-3-1-3"], "answer_reason": "据 when 从句定过去进行时"}
    assert qas.validate_word_fill_analysis(ok) == []
    assert any("cf-" in e or "jf-" in e for e in qas.validate_word_fill_analysis({**ok, "kp_codes": ["rc-1-1"]}))
    assert any("change_type" in e for e in qas.validate_word_fill_analysis({**ok, "change_type": " "}))
    assert any("answer_reason" in e for e in qas.validate_word_fill_analysis({**ok, "answer_reason": " "}))


async def _seed_word_fill(s) -> uuid.UUID:
    r = await pqs.import_real_question(
        s, stem="I had my finger cut when I _____ (divide) the apple.", answer="was dividing",
        options=None, question_type="填空", section="词汇运用", status="published")
    await s.flush()
    return r.question_id


@pytest.mark.asyncio
async def test_suggest_dispatch_word_fill(db_session):
    """分发:填空词形类(词汇运用段)走 word_fill(change_type + cf/jf 考点),不写库。"""
    qid = await _seed_word_fill(db_session)
    items = await qas.suggest_analysis(db_session, question_ids=[qid])
    ana = items[0]["analysis"]
    assert ana and ana.get("change_type") and ana.get("kp_codes")
    assert "distractors" not in ana and "rc_code" not in ana


@pytest.mark.asyncio
async def test_confirm_word_fill_writes_and_attaches_kp(db_session):
    qid = await _seed_word_fill(db_session)
    good = {"given": "divide", "target_form": "was dividing", "change_type": "过去进行时",
            "kp_codes": ["jf-1-1"], "answer_reason": "据 when 引导的时间状语从句定过去进行时"}
    saved = await qas.confirm_analysis(db_session, question_id=qid, analysis=good, admin_id=uuid.uuid4())
    assert saved["kind"] == "word_fill" and saved["confirmed_at"]
    from app.models.d15_knowledge_graph import KnowledgeNode
    from app.models.d16_question_domain import PlatformQuestionKp
    codes = (await db_session.execute(
        select(KnowledgeNode.code).join(PlatformQuestionKp, PlatformQuestionKp.node_id == KnowledgeNode.id)
        .where(PlatformQuestionKp.question_id == qid))).scalars().all()
    assert "jf-1-1" in codes


@pytest.mark.asyncio
async def test_confirm_batch_partitions_pass_fail(db_session):
    """批量确认:通过项写库、失败项带原因不写、不影响其余(降人工一键采纳的核心)。"""
    qid_ok = await _seed_reading(db_session)
    qid_bad = await _seed_reading(db_session)
    items = [
        {"question_id": str(qid_ok), "analysis": {
            "rc_code": "rc-1-1", "evidence": "He runs for half an hour and then has breakfast.",
            "answer_reason": "then 表先后。",
            "distractors": {"B": {"meaning": "放学后跑步", "why_wrong": "与定位句时间冲突"}}}},
        {"question_id": str(qid_bad), "analysis": {   # 幻觉定位句 → 失败
            "rc_code": "rc-1-1", "evidence": "made-up sentence not in passage.",
            "answer_reason": "x", "distractors": {}}},
    ]
    res = await qas.confirm_analysis_batch(db_session, items=items, admin_id=uuid.uuid4())
    assert res["confirmed"] == [str(qid_ok)]
    assert len(res["failed"]) == 1 and res["failed"][0]["question_id"] == str(qid_bad)
    ok = (await db_session.execute(select(PlatformQuestion).where(PlatformQuestion.id == qid_ok))).scalar_one()
    bad = (await db_session.execute(select(PlatformQuestion).where(PlatformQuestion.id == qid_bad))).scalar_one()
    assert (ok.meta or {}).get("analysis") and not (bad.meta or {}).get("analysis")


@pytest.mark.asyncio
async def test_confirm_writes_and_rejects_invalid(db_session):
    qid = await _seed_reading(db_session)
    admin_id = uuid.uuid4()
    good = {"rc_code": "rc-1-1", "evidence": "He runs for half an hour and then has breakfast.",
            "answer_reason": "then 表先后,跑步在早餐前。",
            "distractors": {"B": {"meaning": "放学后跑步", "why_wrong": "与定位句时间冲突"}}}
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


@pytest.mark.asyncio
async def test_confirm_force_ignores_validation(db_session):
    """人工判定校验误报 → force=True 忽略校验强制写库,并记 validation_skipped 审计。"""
    qid = await _seed_reading(db_session)
    bad = {"rc_code": "rc-1-1", "evidence": "made-up sentence not in passage.",
           "answer_reason": "人工判定定位句其实对(子串过严)。", "distractors": {}}
    from app.core.exceptions import AppError
    with pytest.raises(AppError):                     # 不 force → 仍拒绝
        await qas.confirm_analysis(db_session, question_id=qid, analysis=bad, admin_id=uuid.uuid4())
    saved = await qas.confirm_analysis(               # force → 写库 + 留审计
        db_session, question_id=qid, analysis=bad, admin_id=uuid.uuid4(), force=True)
    assert saved["confirmed_at"] and saved.get("validation_skipped")
    assert any("幻觉" in e for e in saved["validation_skipped"])
    q = (await db_session.execute(
        select(PlatformQuestion).where(PlatformQuestion.id == qid))).scalar_one()
    assert (q.meta or {}).get("analysis", {}).get("validation_skipped")
