"""阅读逐问 rc-* 技能确定性归类测试（P1①，dev-mock 离线）。"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.database import _async_session_factory
from app.models.d15_knowledge_graph import KnowledgeNode
from app.services import kp_suggest_service as kss
from app.services import platform_question_service as pqs


def test_classify_reading_skill_patterns():
    c = kss.classify_reading_skill
    assert c("What is the best title for the passage?") == "rc-2-3"
    assert c('The underlined word "it" refers to ___') == "rc-4-3"   # 指代优先于猜词
    assert c('The word "huge" means ___') == "rc-4-1"
    assert c("What can we infer from the passage?") == "rc-3-1"
    assert c("What is the passage mainly about?") == "rc-2-2"
    assert c("What is the author's attitude towards it?") == "rc-5-1"
    assert c("Where would you most probably read this?") == "rc-3-3"
    assert c("What is the purpose of writing this passage?") == "rc-3-2"
    assert c("How many students are there according to the passage?") == "rc-1-1"
    assert c("A plain sentence with no question signal.") is None
    assert c("") is None


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


@pytest.mark.asyncio
async def test_suggest_paper_reading_gets_precise_rc(db_session):
    """整卷匹配(dev-mock):阅读小问按问法确定性打到精确 rc-* 叶子。"""
    pid = await pqs.create_paper(db_session, name="rc-classify-test", meta={"stage": "初"})
    r = await pqs.import_real_question(
        db_session, stem="What is the best title for the passage?", answer="A",
        question_type="阅读", section="阅读理解", paper_id=pid, status="draft")
    await db_session.flush()
    matches, _props = await kss.suggest_kps_for_paper(db_session, pid)
    refs = matches.get(r.question_id, [])
    codes = [ref[2] for ref in refs]
    assert "rc-2-3" in codes
    # 命中的确实是 rc-2-3「标题归纳」节点
    name = (await db_session.execute(
        select(KnowledgeNode.name).where(KnowledgeNode.code == "rc-2-3"))).scalar_one()
    assert any(ref[1] == name for ref in refs)
