"""加权掌握度(m139):公式 + 首答计数(fa_correct/fa_wrong)去重/排除订正。

裸正确率误导(3对3=100%);加权后基数下限 10、错罚重。首答只计一次(同题重刷不重复),
订正(feature='review')不计首答。订正对/错(corrected/redo_wrong)由 wrong_review 记,
其 redo 集成见 test_wrong_review。
"""
from __future__ import annotations

import datetime as _dt
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.core.database import _async_session_factory
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import StudentKp, WrongRecord
from app.services import kp_mastery_service as kms
from app.services import mastery_judge_service
from app.services import wrong_review_service as wr


def test_weighted_mastery_matches_spec():
    assert kms.weighted_mastery(3, 0, 0, 0) == (0.3, 3)      # 3对3 → 30%(裸算是100%)
    assert kms.weighted_mastery(7, 3, 0, 0) == (0.25, 10)    # 7对3错 → 25%(裸算70%)
    assert kms.weighted_mastery(7, 3, 3, 0) == (0.2615, 13)  # 全订正对
    assert kms.weighted_mastery(7, 3, 1, 1) == (0.2083, 12)  # 1题先错后对
    assert kms.weighted_mastery(10, 0, 0, 0) == (1.0, 10)    # 全对封顶 1
    assert kms.weighted_mastery(0, 0, 0, 0) == (0.0, 0)      # 空
    assert kms.weighted_mastery(0, 5, 0, 0)[0] == 0.0        # 负分截 0


@pytest_asyncio.fixture
async def db_session():
    async with _async_session_factory() as s:
        yield s
        await s.rollback()


async def _seed_node(db) -> uuid.UUID:
    nid = uuid.uuid4()
    db.add(KnowledgeNode(id=nid, axis="knowledge", name=f"wm-{nid.hex[:6]}",
                         code=f"wm-{nid.hex[:8]}", status="active", source="seed"))
    await db.flush()
    return nid


async def _sk(db, sid, nid):
    """读原始列值(避免 ORM 身份映射缓存导致读到旧对象)。"""
    return (await db.execute(
        select(StudentKp.practice_count, StudentKp.fa_correct, StudentKp.fa_wrong,
               StudentKp.corrected_count, StudentKp.redo_wrong_count)
        .where(StudentKp.student_id == sid, StudentKp.node_id == nid)
    )).one()


@pytest.mark.asyncio
async def test_first_attempt_counts_once_and_excludes_review(db_session):
    db = db_session
    sid, nid = uuid.uuid4(), await _seed_node(db)
    q1 = uuid.uuid4()

    async def log(qid, correct, feature="practice"):
        await mastery_judge_service.log_answer(
            db, student_id=sid, q_scope="platform", question_id=qid,
            node_id=nid, is_correct=correct, feature=feature)

    # 首答对 → fa_correct=1
    await log(q1, True)
    sk = await _sk(db, sid, nid)
    assert (sk.fa_correct, sk.fa_wrong) == (1, 0)

    # 同题重刷 → 首答不再计,但总次数(practice_count)照加
    await log(q1, True)
    sk = await _sk(db, sid, nid)
    assert (sk.fa_correct, sk.fa_wrong) == (1, 0)
    assert sk.practice_count == 2

    # 另一题首答错 → fa_wrong=1
    await log(uuid.uuid4(), False)
    sk = await _sk(db, sid, nid)
    assert (sk.fa_correct, sk.fa_wrong) == (1, 1)

    # 订正/复习(feature='review')不计首答
    await log(uuid.uuid4(), True, feature="review")
    sk = await _sk(db, sid, nid)
    assert (sk.fa_correct, sk.fa_wrong) == (1, 1)

    # 掌握度 = weighted(1,1,0,0) → S=1-1.5=-0.5<0 → 0%
    assert kms.weighted_mastery(sk.fa_correct, sk.fa_wrong,
                                sk.corrected_count, sk.redo_wrong_count)[0] == 0.0


@pytest.mark.asyncio
async def test_trend_reconstructs_from_answer_log(db_session):
    """趋势:从 answer_log 重放 首答/订正 → 当日日末掌握度。校验 fa/Kc/Kf 分支。"""
    db = db_session
    sid, nid = uuid.uuid4(), await _seed_node(db)
    q2 = uuid.uuid4()

    async def log(qid, correct, feature="practice"):
        await mastery_judge_service.log_answer(
            db, student_id=sid, q_scope="platform", question_id=qid,
            node_id=nid, is_correct=correct, feature=feature)

    await log(uuid.uuid4(), True)                     # 首答对 → fa_c=1
    await log(q2, False)                              # 首答错 → fa_w=1
    await log(q2, True, feature="review")             # 该题首次订正对 → Kc=1
    await log(uuid.uuid4(), False, feature="review")  # 首事件即订正错 → Kf=1(不计首答)

    pts = await kms.get_kp_mastery_trend(db, student_id=sid, node_id=nid, days=30)
    assert len(pts) == 1                              # 同一天 → 一个日末点
    # weighted(1,1,1,1): S=1-1.5+0.3-0.3=-0.5<0 → 0.0;C=4
    assert pts[0]["mastery"] == 0.0 and pts[0]["mastery_events"] == 4


async def _seed_wrong(db, sid, nid, answer="B") -> uuid.UUID:
    """建一道 platform_question(答案 B/单选)+ 指向它、挂 node 的 open wrong_record。"""
    qid, rid = uuid.uuid4(), uuid.uuid4()
    await db.execute(text(
        "INSERT INTO platform_question (id, type, is_fallback, question_type, stem, options, answer, status) "
        "VALUES (:id,'sim',true,'单选',:stem,CAST(:opts AS jsonb),:ans,'published')"),
        {"id": qid, "stem": "wm redo", "opts": '["A. x", "B. y"]', "ans": answer})
    db.add(WrongRecord(
        id=rid, student_id=sid, q_scope="platform", question_id=qid, node_id=nid,
        status="open", review_count=0, review_interval_days=1,
        easiness_factor=Decimal("2.50"), next_review_at=_dt.date.today()))
    await db.flush()
    return rid


@pytest.mark.asyncio
async def test_redo_records_corrected_and_redo_wrong():
    """错题订正:重做答对 → corrected_count(每题首次);重做答错 → redo_wrong_count(每次)。
    订正不计首答(fa_* 不变)。复现用户场景(错题详情做对/做错 → 掌握度计数)。"""
    sid = uuid.uuid4()
    async with _async_session_factory() as db:
        nid = await _seed_node(db)
        r_ok = await _seed_wrong(db, sid, nid)     # 将答对
        r_bad = await _seed_wrong(db, sid, nid)    # 将答错
        await db.commit()
    try:
        async with _async_session_factory() as db:
            res_ok = await wr.redo(db, student_id=sid, wrong_record_id=r_ok, user_answer="B")
            res_bad = await wr.redo(db, student_id=sid, wrong_record_id=r_bad, user_answer="X")
            await db.commit()
            assert res_ok["is_correct"] is True and res_bad["is_correct"] is False
        async with _async_session_factory() as db:
            row = (await db.execute(
                select(StudentKp.corrected_count, StudentKp.redo_wrong_count,
                       StudentKp.fa_correct, StudentKp.fa_wrong)
                .where(StudentKp.student_id == sid, StudentKp.node_id == nid))).one()
            assert row.corrected_count == 1     # 订正做对一次
            assert row.redo_wrong_count == 1    # 订正做错一次
            assert (row.fa_correct, row.fa_wrong) == (0, 0)   # 订正不计首答
            assert kms.weighted_mastery(0, 0, row.corrected_count, row.redo_wrong_count) == (0.0, 2)
    finally:
        async with _async_session_factory() as db:
            await db.execute(text(
                "DELETE FROM platform_question WHERE id IN "
                "(SELECT question_id FROM wrong_record WHERE student_id=:s)"), {"s": str(sid)})
            await db.execute(text("DELETE FROM wrong_record WHERE student_id=:s"), {"s": str(sid)})
            await db.execute(text("DELETE FROM answer_log WHERE student_id=:s"), {"s": str(sid)})
            await db.execute(text("DELETE FROM student_kp WHERE student_id=:s"), {"s": str(sid)})
            await db.execute(text("DELETE FROM knowledge_nodes WHERE id=:n"), {"n": str(nid)})
            await db.commit()
