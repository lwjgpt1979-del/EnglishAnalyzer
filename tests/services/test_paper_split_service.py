"""整卷拆题服务测试（D-089 / M4）。dev mock 确定性返回 2 题。"""
from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.ocr_service import OcrResult, _MOCK_PRINTED, _MOCK_HANDWRITTEN
from app.services.paper_split_service import split_paper_questions, ParsedPaperQuestion


@pytest.fixture(autouse=True)
def force_dev_mode(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-placeholder-for-test")


@pytest.mark.asyncio
async def test_split_dev_mock_returns_two_questions():
    ocr = OcrResult(printed_text=_MOCK_PRINTED, handwritten_text=_MOCK_HANDWRITTEN)
    questions = await split_paper_questions(ocr)

    assert isinstance(questions, list)
    assert len(questions) == 2
    assert all(isinstance(q, ParsedPaperQuestion) for q in questions)

    q27, q28 = questions
    assert q27.question_no == "27"
    assert q27.question_type == "单选"
    assert q27.student_answer == "B"
    assert q27.stem and "hand in" in q27.stem

    assert q28.question_no == "28"
    assert q28.student_answer == "B"


@pytest.mark.asyncio
async def test_split_empty_ocr_returns_empty_list():
    ocr = OcrResult(printed_text="", handwritten_text="")
    questions = await split_paper_questions(ocr)
    assert questions == []
