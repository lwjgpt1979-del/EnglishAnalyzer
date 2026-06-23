"""R7 统一上传/错题接入(KP-First 收官):上传拆题 → 挂 KP → 错题收口 的公共原子。

两入口,各渠道复用:
  - ingest_parsed:OCR/上传拆出的题 → uploaded_question + match_kp 挂 node/落候选 +
    错题 record_wrong + add_source。供 单题拍照 / 作业上传 / 整卷 复用。
  - record_wrong_answer:答错事件(无 OCR)→ match_kp(kp 名)→node + record_wrong + add_source。
    供 听力 / 口语 / 作业答题 复用。
不破坏旧表(WrongQuestion/UserPaperQuestion 等);新口径统一进 wrong_record + uploaded_question。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d16_question_domain import UploadedQuestion, UploadedQuestionKp
from app.services import wrong_center_service
from app.services.kp_match_service import match_kp


@dataclass
class IngestItem:
    question_no: str | None = None
    question_type: str | None = None
    stem: str | None = None
    student_answer: str | None = None
    correct_answer: str | None = None
    explanation: str | None = None
    is_wrong: bool = False
    kp_name: str | None = None       # 该题知识点名(classify_kps 给出),供 match_kp


@dataclass
class IngestResult:
    question_id: uuid.UUID
    node_id: uuid.UUID | None = None
    candidate_id: uuid.UUID | None = None
    wrong_record_id: uuid.UUID | None = None


async def _attach_uploaded_kp(db: AsyncSession, question_id: uuid.UUID, node_id: uuid.UUID) -> None:
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    await db.execute(
        pg_insert(UploadedQuestionKp)
        .values(question_id=question_id, node_id=node_id)
        .on_conflict_do_nothing(index_elements=["question_id", "node_id"])
    )


async def ingest_parsed(
    db: AsyncSession, *, owner_scope: str, owner_id: uuid.UUID,
    items: list[IngestItem], source_type: str = "uploaded_student",
    paper_id: uuid.UUID | None = None, stage_hint: str | None = None,
) -> list[IngestResult]:
    """拆好的题统一入库:uploaded_question + 挂 node/候选 + 错题收口。owner_scope ∈ {student, institution}。"""
    out: list[IngestResult] = []
    for it in items:
        uq = UploadedQuestion(
            id=uuid.uuid4(), owner_scope=owner_scope, owner_id=owner_id, paper_id=paper_id,
            question_no=it.question_no, question_type=it.question_type, stem=it.stem,
            student_answer=it.student_answer, correct_answer=it.correct_answer,
            explanation=it.explanation, is_wrong=it.is_wrong,
        )
        db.add(uq)
        await db.flush()
        res = IngestResult(question_id=uq.id)

        node_id = None
        if it.kp_name and it.kp_name.strip():
            m = await match_kp(db, raw_name=it.kp_name, axis_hint="knowledge",
                               stage_hint=stage_hint, source_type=source_type)
            node_id = m.node_id
            res.node_id, res.candidate_id = m.node_id, m.candidate_id
            if node_id is not None:
                await _attach_uploaded_kp(db, uq.id, node_id)

        if it.is_wrong and owner_scope == "student":
            res.wrong_record_id = await wrong_center_service.record_wrong(
                db, student_id=owner_id, q_scope="uploaded", question_id=uq.id, node_id=node_id)

        # 学生上传作业时抽长难句 → 个人独立表(本人可见);best-effort,失败不影响入库
        if owner_scope == "student" and it.stem:
            try:
                from app.services import long_sentence_service as lss
                await lss.extract_student_for_question(
                    db, owner_id=owner_id, question_id=uq.id, text=it.stem)
            except Exception:  # noqa: BLE001
                pass
        out.append(res)
    await db.flush()
    return out


async def record_wrong_answer(
    db: AsyncSession, *, student_id: uuid.UUID, q_scope: str, question_id: uuid.UUID,
    kp_name: str | None = None, source_type: str = "uploaded_student",
) -> uuid.UUID | None:
    """答错事件统一收口:match_kp(kp 名)→node(可空)→ record_wrong + add_source。返回 wrong_record id。"""
    node_id = None
    if kp_name and kp_name.strip():
        m = await match_kp(db, raw_name=kp_name, axis_hint="knowledge", source_type=source_type)
        node_id = m.node_id
    return await wrong_center_service.record_wrong(
        db, student_id=student_id, q_scope=q_scope, question_id=question_id, node_id=node_id)
