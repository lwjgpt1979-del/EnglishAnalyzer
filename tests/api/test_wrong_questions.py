from app.core.config import settings


def test_settings_has_anthropic_api_key():
    """settings 必须有 anthropic_api_key 字段（值可为 placeholder）。"""
    assert hasattr(settings, "anthropic_api_key")
    assert isinstance(settings.anthropic_api_key, str)


import uuid
from datetime import datetime, timezone

from app.schemas.wrong_questions import (
    AiAnalysisOut,
    MarkMasteredRequest,
    WrongQuestionCreate,
    WrongQuestionListOut,
    WrongQuestionOut,
)


def test_wrong_question_create_requires_source_image_url():
    wq = WrongQuestionCreate(source_image_url="https://cdn.example.com/img.jpg")
    assert wq.source_image_url == "https://cdn.example.com/img.jpg"
    assert wq.question_text is None
    assert wq.tags is None


def test_wrong_question_out_serializes():
    now = datetime.now(timezone.utc)
    out = WrongQuestionOut(
        id=str(uuid.uuid4()),
        student_id=str(uuid.uuid4()),
        source_image_url="https://cdn.example.com/img.jpg",
        question_text="What is the correct tense here?",
        student_answer="I go to school yesterday",
        correct_answer="I went to school yesterday",
        question_type="单选",
        difficulty=2,
        tags=["时态", "过去式"],
        is_mastered=False,
        mastered_at=None,
        created_at=now,
        updated_at=now,
    )
    assert out.is_mastered is False
    assert out.tags == ["时态", "过去式"]


def test_ai_analysis_out_serializes():
    now = datetime.now(timezone.utc)
    out = AiAnalysisOut(
        id=str(uuid.uuid4()),
        wrong_question_id=str(uuid.uuid4()),
        llm_provider="claude",
        error_types=["时态错误"],
        knowledge_points=["一般过去时"],
        diagnosis="学生混淆了一般现在时和一般过去时。",
        suggestions="加强时态练习，重点复习过去时标志词。",
        confidence_score=0.92,
        tokens_used=312,
        created_at=now,
    )
    assert out.llm_provider == "claude"
    assert out.confidence_score == 0.92
