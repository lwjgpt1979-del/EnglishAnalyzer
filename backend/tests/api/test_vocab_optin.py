"""R5 收尾:通用词库 opt-in 学生设置 → 背词新词来源加入通用词库(P4,最低优先)。"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from app.core.database import _async_session_factory
from app.models.d1_users import User
from app.models.d5_learning import VocabularyWord
from app.models.d18_vocab_kg import VocabList, VocabListItem
from app.services import vocabulary_service as vs

_TAG = "voptin"


async def _cleanup(student, list_id):
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM student_vocab_settings WHERE student_id = :s"), {"s": str(student)})
        await db.execute(text("DELETE FROM vocab_list_item WHERE list_id = :l"), {"l": str(list_id)})
        await db.execute(text("DELETE FROM vocab_list WHERE name LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM vocabulary_words WHERE word LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM users WHERE id = :s"), {"s": str(student)})
        await db.commit()


@pytest.mark.asyncio
async def test_optin_includes_general_vocab():
    student, list_id, word_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(User(id=student, openid=f"{_TAG}_{student.hex[:8]}", role="student"))
        db.add(VocabularyWord(id=word_id, word=f"{_TAG}abandon", definitions=[{"pos": "v", "meaning": "放弃"}],
                              difficulty=3, type="word", source="import"))
        db.add(VocabList(id=list_id, name=f"{_TAG}高考3500", status="published"))
        await db.flush()
        db.add(VocabListItem(list_id=list_id, word_id=word_id, rank=1, star=5))
        await db.commit()
    try:
        # 默认关:通用词库词不进新词来源
        async with _async_session_factory() as db:
            user = (await db.execute(select(User).where(User.id == student))).scalar_one()
            words = await vs._ordered_new_words(db, student=user, limit=50)
            assert word_id not in {w.id for w in words}

        # 开 opt-in 指定该词库
        async with _async_session_factory() as db:
            s = await vs.set_vocab_settings(db, student_id=student, words_per_group=5, reps_per_group=1,
                                            include_general_vocab=True, general_vocab_list_id=list_id)
            await db.commit()
            assert s["include_general_vocab"] is True and s["general_vocab_list_id"] == str(list_id)

        # 开后:通用词库词进入新词来源
        async with _async_session_factory() as db:
            user = (await db.execute(select(User).where(User.id == student))).scalar_one()
            words = await vs._ordered_new_words(db, student=user, limit=50)
            assert word_id in {w.id for w in words}
    finally:
        await _cleanup(student, list_id)
