"""question_ai_service dev mock 测试。"""
from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.question_ai_service import generate_questions


@pytest.fixture(autouse=True)
def force_dev_mode(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-placeholder-for-test")


@pytest.mark.asyncio
async def test_mock_returns_all_7_types_at_count_9():
    """dev mock count=9 必须包含全部 7 种题型。"""
    qs = await generate_questions(
        kp_name="There be 句型",
        kp_category="grammar",
        kp_description="表示存在",
        count=9,
    )
    assert len(qs) == 9
    types = {q.question_type for q in qs}
    assert types == {"单选", "填空", "判断", "完型", "阅读", "写作", "连线"}

    for q in qs:
        if q.question_type in ("单选", "完型", "阅读"):
            assert q.options is not None
            assert len(q.options) == 4
            assert q.answer in ["A", "B", "C", "D"]
        elif q.question_type == "填空":
            assert q.options is None
            assert q.answer
        elif q.question_type == "判断":
            assert q.options is None
            assert q.answer in ["对", "错"]
        elif q.question_type == "写作":
            assert q.options is None
            assert len(q.answer) >= 50  # 范文应较长
        elif q.question_type == "连线":
            assert q.options is None
            assert "|" in q.answer and "-" in q.answer
        assert q.explanation
        assert 1 <= q.difficulty <= 5


@pytest.mark.asyncio
async def test_mock_deterministic_per_kp_name():
    """同名 KP 多次调用应该至少 type 分布一致（便于幂等 upsert）。"""
    q1 = await generate_questions(kp_name="X", kp_category="grammar", kp_description="d", count=5)
    q2 = await generate_questions(kp_name="X", kp_category="grammar", kp_description="d", count=5)
    assert sorted([q.question_type for q in q1]) == sorted([q.question_type for q in q2])
