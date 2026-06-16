"""整卷上传 service（D-089 / M4）：建卷 / 列表 / 详情 / 后台 OCR 拆题管线。

后台管线沿用 ocr.py 已验证的「BackgroundTasks + 独立 async_session_factory」模式：
管线内部开独立 session 提交，避免与请求 session 串扰。
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d13_v2_user_papers import UserPaperQuestion, UserUploadedPaper
from app.schemas.user_papers import (
    UserPaperDetailOut,
    UserPaperOut,
    UserPaperQuestionOut,
)


def _is_wrong(student_answer: str | None, correct_answer: str | None) -> bool:
    """学生答案与正确答案都存在且归一化后不同 → 判错；否则 False（无法判定不算错）。"""
    if not student_answer or not correct_answer:
        return False
    return student_answer.strip().lower() != correct_answer.strip().lower()


async def create_paper(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    source_image_urls: list[str],
    title: str | None,
) -> UserUploadedPaper:
    """创建整卷记录，ocr_status=pending（后台管线随后处理）。"""
    paper = UserUploadedPaper(
        student_id=student_id,
        title=title,
        source_image_urls=source_image_urls,
        ocr_status="pending",
    )
    db.add(paper)
    await db.flush()
    await db.refresh(paper)
    return paper


async def run_paper_pipeline(paper_id: uuid.UUID) -> None:
    """后台任务：整卷图片 → 豆包Vision拆题 → DeepSeek KP归类 → 落库 + 台账写入（M40）。

    用独立 session（async_session_factory），与触发请求的 session 解耦。
    """
    from app.core.database import async_session_factory as _async_session_factory
    from app.services.ocr_service import OcrResult, run_ocr
    from app.services.paper_split_service import split_paper_questions
    from app.services.kp_classifier_service import classify_kps
    from app.services.kp_mastery_service import upsert_mastery

    async with _async_session_factory() as db:
        paper: UserUploadedPaper | None = await db.get(UserUploadedPaper, paper_id)
        if paper is None:
            return

        paper.ocr_status = "processing"
        await db.commit()

        try:
            # Step 1: 豆包Vision看图拆题（每张图独立处理，多页合并）
            printed_parts: list[str] = []
            handwritten_parts: list[str] = []
            for url in paper.source_image_urls:
                ocr = await run_ocr(url)
                if ocr.printed_text:
                    printed_parts.append(ocr.printed_text)
                if ocr.handwritten_text:
                    handwritten_parts.append(ocr.handwritten_text)

            merged = OcrResult(
                printed_text="\n".join(printed_parts),
                handwritten_text="\n".join(handwritten_parts),
            )
            parsed = await split_paper_questions(merged)

            # Step 2: DeepSeek 批量归类 KP（M40 新增）
            kp_map: dict[str, str] = await classify_kps(parsed)

            # Step 3: 落库题目 + 题目↔知识点关联 + 写入 student_kp_mastery
            from app.services.practice_service import get_or_create_knowledge_point
            from app.models.d13_v2_user_papers import UserPaperQuestionKnowledgePoint
            for pq in parsed:
                is_wrong = _is_wrong(pq.student_answer, pq.correct_answer)
                q = UserPaperQuestion(
                    user_paper_id=paper.id,
                    question_no=pq.question_no,
                    question_type=pq.question_type,
                    stem=pq.stem,
                    student_answer=pq.student_answer,
                    correct_answer=pq.correct_answer,
                    explanation=pq.explanation,
                    is_wrong=is_wrong,
                )
                db.add(q)
                await db.flush()   # 取 q.id 以建关联

                # 知识点：归类名 → 标准 KP（get_or_create），建题目↔KP关联 + 写台账
                qno = pq.question_no or ""
                kp_key = kp_map.get(qno)
                if kp_key:
                    kp = await get_or_create_knowledge_point(db, name=kp_key)
                    db.add(UserPaperQuestionKnowledgePoint(
                        user_paper_question_id=q.id, knowledge_point_id=kp.id))
                    await upsert_mastery(
                        db,
                        student_id=paper.student_id,
                        kp_key=kp_key,
                        kp_id=kp.id,     # 关联标准 KP UUID（M4 深化）
                        is_correct=not is_wrong,
                        source="paper_upload",
                    )

            # P2：整卷题干里命中词典的生词 → 该生词力通候选池（best-effort）
            try:
                from app.services import vocabulary_service
                stems_text = " ".join((pq.stem or "") for pq in parsed)
                await vocabulary_service.add_source_candidates(
                    db, student_id=paper.student_id, text=stems_text, source="paper")
            except Exception:  # noqa: BLE001
                pass

            paper.ocr_status = "completed"
        except Exception:
            paper.ocr_status = "failed"

        await db.commit()


async def _question_count(db: AsyncSession, paper_id: uuid.UUID) -> int:
    return int(
        (await db.execute(
            select(func.count(UserPaperQuestion.id)).where(
                UserPaperQuestion.user_paper_id == paper_id
            )
        )).scalar_one()
    )


async def list_papers(
    db: AsyncSession, *, student_id: uuid.UUID, limit: int = 50
) -> list[UserPaperOut]:
    """列出某学生的全部整卷（倒序），含每卷题目数。"""
    rows = (await db.execute(
        select(UserUploadedPaper)
        .where(UserUploadedPaper.student_id == student_id)
        .order_by(UserUploadedPaper.created_at.desc())
        .limit(limit)
    )).scalars().all()

    out: list[UserPaperOut] = []
    for p in rows:
        out.append(
            UserPaperOut(
                id=p.id,
                title=p.title,
                source_image_urls=list(p.source_image_urls or []),
                ocr_status=p.ocr_status,
                question_count=await _question_count(db, p.id),
                created_at=p.created_at,
            )
        )
    return out


async def get_paper_detail(
    db: AsyncSession, *, paper_id: uuid.UUID, student_id: uuid.UUID
) -> UserPaperDetailOut | None:
    """整卷详情（含题目列表）。非本人持有 → None。"""
    paper = await db.get(UserUploadedPaper, paper_id)
    if paper is None or paper.student_id != student_id:
        return None

    qs = (await db.execute(
        select(UserPaperQuestion)
        .where(UserPaperQuestion.user_paper_id == paper_id)
        .order_by(UserPaperQuestion.created_at.asc())
    )).scalars().all()

    questions = [
        UserPaperQuestionOut(
            id=q.id,
            question_no=q.question_no,
            question_type=q.question_type,
            stem=q.stem,
            student_answer=q.student_answer,
            correct_answer=q.correct_answer,
            explanation=q.explanation,
            is_wrong=q.is_wrong,
        )
        for q in qs
    ]

    return UserPaperDetailOut(
        id=paper.id,
        title=paper.title,
        source_image_urls=list(paper.source_image_urls or []),
        ocr_status=paper.ocr_status,
        question_count=len(questions),
        created_at=paper.created_at,
        questions=questions,
    )


async def paper_kp_summary(
    db: AsyncSession, *, paper_id: uuid.UUID, student_id: uuid.UUID
) -> dict | None:
    """本卷错题按知识点归集（M4 深化）：每个涉及知识点的 总题/错题 数 + 薄弱标。

    非本人持有 → None。薄弱（weak）= 该 KP 本卷有错题，优先排前。
    """
    from app.models.d13_v2_user_papers import UserPaperQuestionKnowledgePoint as _Link
    from app.models.d4_knowledge import KnowledgePoint

    paper = await db.get(UserUploadedPaper, paper_id)
    if paper is None or paper.student_id != student_id:
        return None

    rows = (await db.execute(
        select(
            KnowledgePoint.id, KnowledgePoint.name,
            func.count(UserPaperQuestion.id),
            func.count().filter(UserPaperQuestion.is_wrong.is_(True)),
        )
        .select_from(UserPaperQuestion)
        .join(_Link, _Link.user_paper_question_id == UserPaperQuestion.id)
        .join(KnowledgePoint, KnowledgePoint.id == _Link.knowledge_point_id)
        .where(UserPaperQuestion.user_paper_id == paper_id)
        .group_by(KnowledgePoint.id, KnowledgePoint.name)
    )).all()

    items = [
        {"kp_id": str(kp_id), "kp_name": name, "total": int(total),
         "wrong": int(wrong), "weak": int(wrong) > 0}
        for kp_id, name, total, wrong in rows
    ]
    items.sort(key=lambda x: (not x["weak"], -x["wrong"], x["kp_name"]))
    return {"paper_id": str(paper_id), "items": items}


async def practice_for_question(
    db: AsyncSession, *, question_id: uuid.UUID, student_id: uuid.UUID,
    count: int = 5, difficulty: int = 3,
):
    """错题「练同类」：取该题知识点，生成同类仿真练习（M4 深化）。

    校验题目归属（题→卷→学生）；无关联知识点 → AppError。
    """
    from app.core.exceptions import AppError
    from app.models.d13_v2_user_papers import UserPaperQuestionKnowledgePoint as _Link
    from app.models.d4_knowledge import KnowledgePoint
    from app.services import practice_service

    # 校验归属
    owned = await db.scalar(
        select(func.count()).select_from(UserPaperQuestion)
        .join(UserUploadedPaper, UserUploadedPaper.id == UserPaperQuestion.user_paper_id)
        .where(UserPaperQuestion.id == question_id,
               UserUploadedPaper.student_id == student_id))
    if not owned:
        raise AppError(code=404, message="题目不存在或无权访问")

    kp_name = await db.scalar(
        select(KnowledgePoint.name)
        .join(_Link, _Link.knowledge_point_id == KnowledgePoint.id)
        .where(_Link.user_paper_question_id == question_id).limit(1))
    if not kp_name:
        raise AppError(code=400, message="该题暂无关联知识点，无法生成同类练习")

    questions = await practice_service.generate_practice_questions(
        db, student_id=student_id, knowledge_point=kp_name, count=count, difficulty=difficulty)
    return {"knowledge_point": kp_name, "questions": questions}
