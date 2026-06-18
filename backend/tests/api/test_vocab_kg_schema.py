"""R5.1 词汇接入 schema smoke:词扩字段 + 词↔KP/真题/错题边 + 通用词库。"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from app.core.database import _async_session_factory
from app.models.d5_learning import VocabularyWord
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import WrongRecord
from app.models.d18_vocab_kg import (
    VocabNode, VocabQuestion, VocabWrong, VocabList, VocabListItem,
)

_TAG = "vkgsc"


async def _cleanup(word_id, node_id):
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM vocab_list_item WHERE word_id = :w"), {"w": str(word_id)})
        await db.execute(text("DELETE FROM vocab_list WHERE name LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM vocab_wrong WHERE word_id = :w"), {"w": str(word_id)})
        await db.execute(text("DELETE FROM vocab_question WHERE word_id = :w"), {"w": str(word_id)})
        await db.execute(text("DELETE FROM vocab_node WHERE word_id = :w"), {"w": str(word_id)})
        await db.execute(text("DELETE FROM wrong_record WHERE node_id = :n"), {"n": str(node_id)})
        await db.execute(text("DELETE FROM vocabulary_words WHERE word LIKE :p"), {"p": f"{_TAG}%"})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.commit()


@pytest.mark.asyncio
async def test_vocab_kg_tables():
    word_id, node_id, wr_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    list_id = uuid.uuid4()
    try:
        async with _async_session_factory() as db:
            db.add(VocabularyWord(id=word_id, word=f"{_TAG}abandon", definitions=[{"pos": "v", "meaning": "放弃"}],
                                  difficulty=3, type="word", source="import", frequency=500, star=4))
            db.add(KnowledgeNode(id=node_id, axis="knowledge", node_kind="词汇", name=f"{_TAG}KP",
                                 code=f"{_TAG}-n", status="active", source="seed"))
            db.add(WrongRecord(id=wr_id, student_id=uuid.uuid4(), q_scope="platform",
                               question_id=uuid.uuid4(), node_id=node_id, status="open"))
            await db.flush()
            # 三种边
            db.add(VocabNode(word_id=word_id, node_id=node_id, source="textbook"))
            db.add(VocabQuestion(word_id=word_id, q_scope="platform", question_id=uuid.uuid4(), source="stem"))
            db.add(VocabWrong(word_id=word_id, wrong_record_id=wr_id))
            # 通用词库
            db.add(VocabList(id=list_id, name=f"{_TAG}高考3500", exam_level="senior",
                             source_type="official_syllabus", status="published"))
            await db.flush()
            db.add(VocabListItem(list_id=list_id, word_id=word_id, rank=500, frequency=120, star=4, verified=True))
            await db.commit()

        async with _async_session_factory() as db:
            w = (await db.execute(select(VocabularyWord).where(VocabularyWord.id == word_id))).scalar_one()
            assert w.type == "word" and w.source == "import" and w.frequency == 500 and w.star == 4
            assert (await db.execute(select(VocabNode.node_id).where(VocabNode.word_id == word_id))).scalar_one() == node_id
            assert (await db.execute(select(VocabWrong.wrong_record_id).where(VocabWrong.word_id == word_id))).scalar_one() == wr_id
            item = (await db.execute(select(VocabListItem).where(VocabListItem.list_id == list_id))).scalar_one()
            assert item.rank == 500 and item.star == 4 and item.verified is True
    finally:
        await _cleanup(word_id, node_id)
