"""阅读表达批改 service 测试（P2a，dev-mock 离线确定）。"""
import pytest

from app.services import reading_expression_service as res


@pytest.mark.asyncio
async def test_grade_hit_when_reference_matched():
    r = await res.grade_reading_expression(
        question="When does Tom run?", reference_answer="before breakfast",
        student_answer="He runs before breakfast every morning.", full_score=4)
    assert r["points"] and r["points"][0]["hit"] is True
    assert r["total"] == 4 and r["full"] == 4
    assert r["content_score"] == 4


@pytest.mark.asyncio
async def test_grade_partial_when_short_unmatched():
    r = await res.grade_reading_expression(
        question="Q", reference_answer="a specific long reference point about the plot",
        student_answer="no", full_score=4)
    assert r["points"][0]["hit"] is False
    assert r["total"] == 2  # full - 2


@pytest.mark.asyncio
async def test_grade_empty_answer_returns_zero():
    r = await res.grade_reading_expression(
        question="Q", reference_answer="ref", student_answer="   ", full_score=6)
    assert r["total"] == 0 and r["full"] == 6 and r["points"] == []
