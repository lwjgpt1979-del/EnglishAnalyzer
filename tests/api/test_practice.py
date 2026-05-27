"""AI 练习模块测试。"""
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch

from app.main import app
from app.schemas.practice import (
    GenerateQuestionsRequest,
    PracticeQuestionOut,
    PracticeRecordOut,
    PracticeStatsOut,
    SubmitAnswerRequest,
    SubmitAnswerResult,
)


# ── Schema 单元测试 ────────────────────────────────────────────────────────────


def test_generate_request_defaults():
    req = GenerateQuestionsRequest()
    assert req.knowledge_point is None
    assert req.count == 5
    assert req.difficulty == 3


def test_generate_request_clamps_count_via_validation():
    req = GenerateQuestionsRequest(knowledge_point="一般现在时", count=3, difficulty=2)
    assert req.count == 3
    assert req.knowledge_point == "一般现在时"


def test_practice_question_out_has_no_answer_field():
    out = PracticeQuestionOut(
        id=uuid.uuid4(),
        knowledge_point_id=uuid.uuid4(),
        knowledge_point_name="一般现在时",
        question_type="单选",
        difficulty=2,
        stem="She ___ to school every day.",
        options=["go", "goes", "going", "went"],
    )
    dumped = out.model_dump()
    assert "answer" not in dumped
    assert "explanation" not in dumped
    assert dumped["options"] == ["go", "goes", "going", "went"]


def test_submit_answer_request_schema():
    req = SubmitAnswerRequest(question_id=uuid.uuid4(), answer="goes", time_spent_sec=12)
    assert req.answer == "goes"
    assert req.time_spent_sec == 12


def test_submit_answer_result_schema():
    res = SubmitAnswerResult(
        record_id=uuid.uuid4(),
        question_id=uuid.uuid4(),
        is_correct=True,
        correct_answer="goes",
        explanation="主语第三人称单数。",
    )
    assert res.is_correct is True
    assert res.correct_answer == "goes"


def test_practice_stats_out_schema():
    out = PracticeStatsOut(
        total_practiced=10,
        total_correct=7,
        correct_rate=0.7,
        by_knowledge_point={"一般现在时": {"practiced": 5, "correct": 3}},
    )
    assert out.correct_rate == 0.7
    assert out.by_knowledge_point["一般现在时"]["correct"] == 3
