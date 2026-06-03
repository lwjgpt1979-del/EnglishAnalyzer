"""词力通媒体 service 测试（P1 / D-101）。"""
import uuid

import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.models.d5_learning import VocabularyWord
from app.services import vocab_media_service


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _seed_word(s) -> uuid.UUID:
    w = VocabularyWord(
        id=uuid.uuid4(), word=f"media_{uuid.uuid4().hex[:6]}", phonetic="t",
        definitions=[{"pos": "n.", "meaning": "测试"}], examples=None, difficulty=1,
    )
    s.add(w)
    await s.flush()
    return w.id


@pytest.mark.asyncio
async def test_generate_writes_all_media_draft(db_session):
    wid = await _seed_word(db_session)
    w = await vocab_media_service.generate_for_word(db_session, word_id=wid)
    assert w.image_urls and len(w.image_urls) >= 1
    assert w.en_description
    assert w.word_audio_url and w.en_desc_audio_url
    assert w.media_status == "draft"


@pytest.mark.asyncio
async def test_review_approve_publishes(db_session):
    wid = await _seed_word(db_session)
    await vocab_media_service.generate_for_word(db_session, word_id=wid)
    w = await vocab_media_service.review_word_media(db_session, word_id=wid, approve=True)
    assert w.media_status == "published"


@pytest.mark.asyncio
async def test_review_reject_retires(db_session):
    wid = await _seed_word(db_session)
    await vocab_media_service.generate_for_word(db_session, word_id=wid)
    w = await vocab_media_service.review_word_media(db_session, word_id=wid, approve=False)
    assert w.media_status == "retired"


@pytest.mark.asyncio
async def test_update_media_edits_fields(db_session):
    wid = await _seed_word(db_session)
    await vocab_media_service.generate_for_word(db_session, word_id=wid)
    w = await vocab_media_service.update_word_media(
        db_session, word_id=wid, en_description="edited desc", image_urls=["https://x/y.png"],
    )
    assert w.en_description == "edited desc"
    assert w.image_urls == ["https://x/y.png"]


@pytest.mark.asyncio
async def test_list_for_review_filters_status(db_session):
    wid = await _seed_word(db_session)
    await vocab_media_service.generate_for_word(db_session, word_id=wid)
    await db_session.flush()
    rows, total = await vocab_media_service.list_words_for_media_review(
        db_session, media_status="draft", limit=10000,
    )
    assert total >= 1 and any(r.id == wid for r in rows)


@pytest.mark.asyncio
async def test_generate_missing_word_raises(db_session):
    from app.core.exceptions import AppError
    with pytest.raises(AppError):
        await vocab_media_service.generate_for_word(db_session, word_id=uuid.uuid4())
