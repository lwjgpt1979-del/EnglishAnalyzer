"""阅读理解精讲(作业精讲的「阅读理解」模块)取数。

学生上传作业里 section_type='reading' 的板块 → 按【卷=批次】归组;
每卷下按 block_key(短文)分组:短文 + 该短文的小题(题干/作答/答案/解析)。
数据来自 user_paper_questions(上传作业解析产物),无需额外「加入」动作——上传即在其中。
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d13_v2_user_papers import (
    UserUploadedPaper, UserPaperSection, UserPaperQuestion,
)


async def homework_batches(db: AsyncSession, *, student_id: uuid.UUID) -> list[dict]:
    """学生上传作业里含阅读理解的卷,按卷(批次)归组。年月日倒序。"""
    rows = (await db.execute(
        select(UserUploadedPaper.id, UserUploadedPaper.title, UserUploadedPaper.created_at,
               func.count(UserPaperQuestion.id))
        .join(UserPaperSection, UserPaperSection.user_paper_id == UserUploadedPaper.id)
        .join(UserPaperQuestion, UserPaperQuestion.section_id == UserPaperSection.id)
        .where(UserUploadedPaper.student_id == student_id,
               UserUploadedPaper.ocr_status == "completed",
               UserPaperSection.section_type == "reading")
        .group_by(UserUploadedPaper.id, UserUploadedPaper.title, UserUploadedPaper.created_at)
        .order_by(UserUploadedPaper.created_at.desc()))).all()
    return [{"paper_id": str(pid), "title": title or "未命名作业",
             "date": ca.strftime("%Y-%m-%d") if ca else "", "count": int(cnt)}
            for pid, title, ca, cnt in rows]


async def homework_passages(db: AsyncSession, *, student_id: uuid.UUID,
                            paper_id: uuid.UUID) -> list[dict]:
    """某卷的阅读理解:按短文(block_key)分组 → 短文原文 + 小题。仅本人。"""
    paper = await db.get(UserUploadedPaper, paper_id)
    if paper is None or paper.student_id != student_id:
        return []
    rows = (await db.execute(
        select(UserPaperQuestion)
        .join(UserPaperSection, UserPaperSection.id == UserPaperQuestion.section_id)
        .where(UserPaperQuestion.user_paper_id == paper_id,
               UserPaperSection.section_type == "reading")
        .order_by(UserPaperQuestion.sort_order))).scalars().all()
    blocks: dict[str, dict] = {}
    order: list[str] = []
    for qq in rows:
        bk = qq.block_key or f"__solo_{qq.id}"
        if bk not in blocks:
            blocks[bk] = {"block_label": (f" · {qq.block_key}" if qq.block_key else ""),
                          "passage": qq.passage or "", "questions": []}
            order.append(bk)
        blocks[bk]["questions"].append({
            "no": qq.question_no, "type": qq.question_type, "stem": qq.stem,
            "student_answer": qq.student_answer, "correct_answer": qq.correct_answer,
            "explanation": qq.explanation, "is_wrong": bool(qq.is_wrong)})
    return [blocks[k] for k in order]
