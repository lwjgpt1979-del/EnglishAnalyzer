"""解析护栏:阅读与表达题的短文若被别的大题共用(徐州式错挂)→ 记警告。"""
import pytest
import pytest_asyncio

from app.core.database import _async_session_factory
from app.services import platform_question_service as pqs


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _q(s, *, paper_id, section, block_id):
    r = await pqs.import_real_question(
        s, stem="Q?", answer="a", question_type="阅读", section=section,
        block_id=block_id, paper_id=paper_id, status="draft")
    await s.flush()
    return r.question_id


@pytest.mark.asyncio
async def test_guardrail_flags_shared_passage(db_session):
    pid = await pqs.create_paper(db_session, name="护栏测试卷", meta={})
    block = await pqs.create_passage(db_session, text="Some reading passage.")
    # 阅读与表达 + 阅读理解 共用同一短文 → 命中错挂
    await _q(db_session, paper_id=pid, section="阅读与表达", block_id=block)
    await _q(db_session, paper_id=pid, section="阅读理解", block_id=block)
    warn = await pqs._reading_expr_passage_warning(db_session, pid)
    assert warn and "短文" in warn


@pytest.mark.asyncio
async def test_guardrail_ok_when_own_passage(db_session):
    pid = await pqs.create_paper(db_session, name="护栏测试卷2", meta={})
    b1 = await pqs.create_passage(db_session, text="Reading-expr passage.")
    b2 = await pqs.create_passage(db_session, text="Reading-comp passage.")
    await _q(db_session, paper_id=pid, section="阅读与表达", block_id=b1)   # 独立短文
    await _q(db_session, paper_id=pid, section="阅读理解", block_id=b2)
    assert await pqs._reading_expr_passage_warning(db_session, pid) is None


@pytest.mark.asyncio
async def test_guardrail_no_reading_expr(db_session):
    pid = await pqs.create_paper(db_session, name="护栏测试卷3", meta={})
    b = await pqs.create_passage(db_session, text="Only reading comp.")
    await _q(db_session, paper_id=pid, section="阅读理解", block_id=b)      # 没有阅读与表达 → 不触发
    assert await pqs._reading_expr_passage_warning(db_session, pid) is None
