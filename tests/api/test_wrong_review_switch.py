"""前台读取切换:旧 /wrong-questions/review-queue + {id}/review 直接读写 wrong_record(新表)。"""
import datetime as _dt
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from unittest.mock import AsyncMock, patch

from app.core.database import _async_session_factory
from app.main import app
from app.models.d1_users import User
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import UploadedQuestion, WrongRecord

_TAG = "wrsw"


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _login(client, openid):
    with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as m:
        m.return_value = {"openid": openid}
        r = await client.post("/api/v1/auth/wx-login", json={"code": "x"})
    token = r.json()["data"]["access_token"]
    async with _async_session_factory() as s:
        uid = (await s.execute(select(User.id).where(User.openid == openid))).scalar_one()
    return {"Authorization": f"Bearer {token}"}, uid


async def _cleanup(uid, node_id):
    async with _async_session_factory() as db:
        await db.execute(text("DELETE FROM wrong_record WHERE student_id = :s"), {"s": str(uid)})
        await db.execute(text("DELETE FROM uploaded_question WHERE owner_id = :s"), {"s": str(uid)})
        await db.execute(text("DELETE FROM knowledge_nodes WHERE code LIKE :p"), {"p": f"{_TAG}%"})
        await db.commit()


@pytest.mark.asyncio
async def test_review_queue_and_submit_from_wrong_record(client):
    headers, uid = await _login(client, f"{_TAG}_{uuid.uuid4().hex[:8]}")
    node_id, uq_id, wr_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with _async_session_factory() as db:
        db.add(KnowledgeNode(id=node_id, axis="knowledge", node_kind="句法", name=f"{_TAG}定从",
                             code=f"{_TAG}-n", status="active", source="seed"))
        db.add(UploadedQuestion(id=uq_id, owner_scope="student", owner_id=uid, question_no="3",
                                stem="The book ___ I read.", student_answer="who",
                                correct_answer="which", is_wrong=True))
        await db.flush()
        db.add(WrongRecord(id=wr_id, student_id=uid, q_scope="uploaded", question_id=uq_id,
                           node_id=node_id, status="open", next_review_at=_dt.date.today()))
        await db.commit()
    try:
        # 旧端点 review-queue → 直接读 wrong_record(含 uploaded_question 内容 + node 名 tags)
        r = await client.get("/api/v1/wrong-questions/review-queue", headers=headers)
        assert r.status_code == 200, r.text
        items = r.json()["data"]["due_items"]
        mine = [it for it in items if it["id"] == str(wr_id)]
        assert len(mine) == 1
        assert mine[0]["question_text"].startswith("The book") and mine[0]["correct_answer"] == "which"
        assert mine[0]["tags"] == [f"{_TAG}定从"]
        assert r.json()["data"]["stats"]["total_unmastered"] >= 1

        # 旧端点 {id}/review → 直接写 wrong_record SM-2
        r = await client.post(f"/api/v1/wrong-questions/{wr_id}/review",
                              json={"quality": 5}, headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["data"]["review_count"] == 1
        async with _async_session_factory() as db:
            wr = (await db.execute(select(WrongRecord).where(WrongRecord.id == wr_id))).scalar_one()
            assert wr.review_count == 1 and wr.next_review_at > _dt.date.today()
    finally:
        await _cleanup(uid, node_id)
