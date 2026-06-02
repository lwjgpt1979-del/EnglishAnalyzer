"""词力通 vocabulary_service + schemas 测试（P1 / D-100）。"""
import uuid

import pytest
import pytest_asyncio

from app.core.database import _async_session_factory


# ─── Task 1: schema 冒烟 ──────────────────────────────────────────────

def test_schemas_construct():
    from app.schemas.vocabulary import (
        WordCardOut, DailyTaskOut, VocabAnswerIn, VocabAnswerResult,
    )
    card = WordCardOut(
        word_id=uuid.uuid4(), word="frequently", phonetic="ˈfriːkwəntli",
        definitions=[{"pos": "adv.", "meaning": "频繁地"}], examples=None,
        difficulty=3, level="new", is_new=True,
    )
    task = DailyTaskOut(
        new_words=[card], review_words=[], new_count=1, review_count=0, new_limit=5,
    )
    assert task.new_count == 1 and task.new_limit == 5
    ans_in = VocabAnswerIn(word_id=card.word_id, correct=True)
    assert ans_in.hesitant is False
    res = VocabAnswerResult(
        word_id=card.word_id, level="learning", repetitions=1,
        interval_days=1, next_review_at="2026-06-04T00:00:00+00:00",
    )
    assert res.repetitions == 1
