"""书面表达 5 维评分 service 测试:dev-mock 结构、维度达标判定、练习列表脱敏(不下发范文)。"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.database import _async_session_factory
from app.models.d16_question_domain import PlatformQuestion
from app.services import platform_question_service as pqs
from app.services import writing_grade_service as wgs

_ANALYSIS = {
    "kind": "writing", "genre": "应用文", "sub_format": "演讲稿", "main_tense": "一般现在时",
    "points": [{"id": 1, "point": "懂感恩"}, {"id": 2, "point": "亲自然"}],
    "wr_codes": ["wr-1-2", "wr-4-1"], "strategy": "三段式",
    "structure": [{"role": "开头", "guide": "问候引题"}],
    "model_essay": "Only by working hard can we grow. I am grateful to my parents.",
    "target_expressions": ["Only by working hard can we grow"],
}


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


@pytest.mark.asyncio
async def test_grade_writing_mock_structure():
    r = await wgs.grade_writing(analysis=_ANALYSIS, student_essay="", full_score=20)
    assert r["total"] == 0 and "未作答" in r["feedback"]        # 空作答
    essay = "Only by working hard can we grow. I love nature and my family very much."
    g = await wgs.grade_writing(analysis=_ANALYSIS, student_essay=essay, full_score=20)
    assert isinstance(g["points"], list) and len(g["points"]) == 2  # 逐要点
    assert "accuracy" in g and "richness" in g and "organization" in g and g["band"]
    # 目标句型逐字出现 → 命中 richness.used_targets
    assert "Only by working hard can we grow" in g["richness"]["used_targets"]


def test_dim_passes():
    # 全要点命中 + 用了目标句型 + 结构达标 → content/richness/organization 通过
    res = {"points": [{"hit": True}, {"hit": True}],
           "accuracy": {"score": 8, "full": 10}, "richness": {"used_targets": ["x"]},
           "organization": {"score": 3, "full": 4}}
    p = wgs._dim_passes(res)
    assert p["content"] and p["accuracy"] and p["richness"] and p["organization"]
    # 漏要点 → content 不过;没用目标句型 → richness 不过
    res2 = {"points": [{"hit": True}, {"hit": False}],
            "accuracy": {"score": 5, "full": 10}, "richness": {"used_targets": []},
            "organization": {"score": 1, "full": 4}}
    p2 = wgs._dim_passes(res2)
    assert not p2["content"] and not p2["accuracy"] and not p2["richness"] and not p2["organization"]


def test_dim_passes_uses_rubric():
    # 准确 7/10:默认 0.7 达标;若量表调到 0.8 则不达标(达标线可配)
    res = {"points": [{"hit": True}], "accuracy": {"score": 7, "full": 10},
           "richness": {"used_targets": ["x"]}, "organization": {"score": 3, "full": 4}}
    assert wgs._dim_passes(res)["accuracy"] is True
    assert wgs._dim_passes(res, {"accuracy_pass_ratio": 0.8})["accuracy"] is False
    # 丰富达标线可配:要求 2 个目标句型时,只用 1 个不达标
    assert wgs._dim_passes(res, {"richness_min_targets": 2})["richness"] is False


@pytest.mark.asyncio
async def test_writing_rubric_config_roundtrip(db_session):
    r0 = await wgs.get_writing_rubric(db_session)
    assert r0["full_score"] == 20 and r0["accuracy_pass_ratio"] == 0.7   # 默认兜底
    saved = await wgs.update_writing_rubric(       # updated_by 可空(自动流程无操作人);端点传真 admin.id
        db_session, rubric={"full_score": 25, "accuracy_pass_ratio": 0.8}, updated_by=None)
    assert saved["full_score"] == 25 and saved["accuracy_pass_ratio"] == 0.8
    r1 = await wgs.get_writing_rubric(db_session)      # 读回持久化值 + 未改字段仍兜底
    assert r1["full_score"] == 25 and r1["organization_pass_ratio"] == 0.6


async def _seed_writing_q(s, *, status="published", with_analysis=True) -> uuid.UUID:
    r = await pqs.import_real_question(
        s, stem="以 To be a better self 为题写一篇演讲稿。", answer=None, options=None,
        question_type="写作", section="书面表达", status=status)
    await s.flush()
    q = await s.get(PlatformQuestion, r.question_id)
    if with_analysis:
        q.meta = {"analysis": _ANALYSIS}
    await s.flush()
    return r.question_id


@pytest.mark.asyncio
async def test_list_practice_hides_model_essay(db_session):
    await _seed_writing_q(db_session)
    items = await wgs.list_writing_practice_questions(db_session, limit=10)
    assert len(items) >= 1
    it = next(i for i in items if i["genre"] == "应用文")
    assert it["points"] and it["strategy"] == "三段式" and it["structure"]  # 下发脚手架
    assert "model_essay" not in it and "target_expressions" not in it       # 不下发范文/答案


@pytest.mark.asyncio
async def test_grade_platform_requires_analysis(db_session):
    qid = await _seed_writing_q(db_session, with_analysis=False)
    from app.core.exceptions import AppError
    with pytest.raises(AppError):   # 无解析 → 拒绝批改
        await wgs.grade_platform_writing_question(
            db_session, student_id=uuid.uuid4(), question_id=qid, student_essay="hi there friend")
