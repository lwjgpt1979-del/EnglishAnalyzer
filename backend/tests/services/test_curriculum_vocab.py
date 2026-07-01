"""单元重点单词 ↔ 词力通:get-or-create 复用、新建、列出、解除挂靠。"""
import uuid

import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.models.d4_knowledge import CurriculumUnit
from app.models.d5_learning import VocabularyWord
from app.services import curriculum_vocab_service as cv


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


@pytest.mark.asyncio
async def test_link_reuses_existing_and_creates_missing(db_session):
    tb = f"词版{uuid.uuid4().hex[:6]}"
    sfx = uuid.uuid4().hex[:6]   # 唯一后缀:避开 dev 库种子词,保证「新建」可断言
    w_apple = f"Apple{sfx}"
    w_phrase = f"hit {sfx} road"
    w_banana = f"banana{sfx}"
    uid = uuid.uuid4()
    db_session.add(CurriculumUnit(id=uid, textbook_version=tb, grade="七年级",
                                  semester="上", unit_no=1, unit_title="U1"))
    # 已存在的词条(大小写不同,应被复用而非新建)
    existing = VocabularyWord(id=uuid.uuid4(), word=w_apple, definitions=[{"zh": "苹果"}],
                              difficulty=3, type="word", source="seed")
    db_session.add(existing)
    await db_session.flush()

    res = await cv.link_unit_words(db_session, unit_id=uid, items=[
        {"word": w_apple.lower(), "meaning": "苹果", "type": "word"},   # 复用(忽略大小写)
        {"word": w_phrase, "meaning": "起床", "type": "phrase"},        # 新建词组
        {"word": w_banana, "phonetic": "/bəˈnɑːnə/", "meaning": "n. 香蕉"},  # 新建单词
    ])
    assert res["linked"] == 3
    assert res["created"] == 2          # apple 复用,phrase / banana 新建

    items = await cv.list_unit_words(db_session, unit_id=uid)
    assert {i["word"] for i in items} == {w_apple, w_phrase, w_banana}
    phrase = next(i for i in items if i["word"] == w_phrase)
    assert phrase["type"] == "phrase"
    banana = next(i for i in items if i["word"] == w_banana)
    assert banana["phonetic"] == "/bəˈnɑːnə/" and banana["meaning"] == "n. 香蕉"


@pytest.mark.asyncio
async def test_link_idempotent_and_unlink(db_session):
    tb = f"词版{uuid.uuid4().hex[:6]}"
    uid = uuid.uuid4()
    db_session.add(CurriculumUnit(id=uid, textbook_version=tb, grade="七年级",
                                  semester="上", unit_no=2, unit_title="U2"))
    await db_session.flush()

    await cv.link_unit_words(db_session, unit_id=uid, items=[{"word": "dog", "meaning": "狗"}])
    # 再挂一次同词 → 不重复
    res2 = await cv.link_unit_words(db_session, unit_id=uid, items=[{"word": "dog", "meaning": "狗"}])
    assert res2["linked"] == 0
    items = await cv.list_unit_words(db_session, unit_id=uid)
    assert len(items) == 1

    wid = items[0]["word_id"]
    await cv.unlink_unit_word(db_session, unit_id=uid, word_id=uuid.UUID(wid))
    assert await cv.list_unit_words(db_session, unit_id=uid) == []


@pytest.mark.asyncio
async def test_backfill_phonetic_meaning_on_existing(db_session):
    """已存在但缺音标/释义的词条,挂靠时带了就回填(不覆盖已有)。"""
    bare = VocabularyWord(id=uuid.uuid4(), word=f"orange{uuid.uuid4().hex[:4]}",
                          definitions=[], difficulty=3, type="word", source="seed")
    db_session.add(bare)
    uid = uuid.uuid4()
    db_session.add(CurriculumUnit(id=uid, textbook_version=f"词版{uuid.uuid4().hex[:6]}",
                                  grade="七年级", semester="上", unit_no=3, unit_title="U3"))
    await db_session.flush()

    await cv.link_unit_words(db_session, unit_id=uid, items=[
        {"word": bare.word, "phonetic": "/ˈɒrɪndʒ/", "meaning": "n. 橙子"}])
    await db_session.refresh(bare)
    assert bare.phonetic == "/ˈɒrɪndʒ/"
    assert bare.definitions and bare.definitions[0]["zh"] == "n. 橙子"
