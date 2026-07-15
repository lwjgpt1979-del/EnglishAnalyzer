"""整卷错题只读视图。

拍照单题(旧 wrong_questions ①)已下线;本模块只保留「整卷错题」列表(读 ② user_paper_questions)。
统一错题中枢是 wrong_record(见 wrong_center_service);「我的错题」走 /wrong-center/list。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class PaperWrongItem:
    """整卷错题的简化视图（来自 user_paper_questions.is_wrong=True）。"""
    id: uuid.UUID
    stem: str | None
    question_type: str | None
    is_mastered: bool = False
    source_label: str = "整卷"
    kp_kind: str | None = None   # 'grammar'=考语法 / 'vocab'=考词汇
    kp_name: str | None = None


async def list_paper_wrongs(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[PaperWrongItem], int]:
    """查询整卷错题（user_paper_questions.is_wrong=True），返回 (items, total)。

    只返回属于当前学生整卷（via user_uploaded_papers.student_id）中答错的题。
    """
    from app.models.d13_v2_user_papers import UserPaperQuestion, UserUploadedPaper

    base_conds = [
        UserUploadedPaper.student_id == student_id,
        UserPaperQuestion.is_wrong == True,  # noqa: E712
    ]
    total_result = await db.execute(
        select(func.count())
        .select_from(UserPaperQuestion)
        .join(UserUploadedPaper, UserUploadedPaper.id == UserPaperQuestion.user_paper_id)
        .where(*base_conds)
    )
    total: int = total_result.scalar_one()

    rows = (await db.execute(
        select(UserPaperQuestion)
        .join(UserUploadedPaper, UserUploadedPaper.id == UserPaperQuestion.user_paper_id)
        .where(*base_conds)
        .order_by(UserPaperQuestion.id)
        .offset(skip)
        .limit(limit)
    )).scalars().all()

    # 语法/词汇标签:统一走 user_paper_service.kp_kind_of
    from app.models.d15_knowledge_graph import KnowledgeNode
    from app.services.user_paper_service import kp_kind_of
    node_ids = [r.node_id for r in rows if r.node_id]
    codes = {}
    if node_ids:
        codes = {nid: code for nid, code in (await db.execute(
            select(KnowledgeNode.id, KnowledgeNode.code).where(KnowledgeNode.id.in_(node_ids)))).all()}

    return [
        PaperWrongItem(
            id=r.id,
            stem=r.stem,
            question_type=r.question_type,
            kp_kind=kp_kind_of(r.kp_key, codes.get(r.node_id) if r.node_id else None),
            kp_name=r.kp_key,
        )
        for r in rows
    ], total
