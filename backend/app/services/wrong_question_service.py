"""错题 CRUD 业务逻辑。

所有函数使用 db.flush()，由 endpoint 层控制 commit。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d3_wrong_questions import AiAnalysis, WrongQuestion
from app.schemas.wrong_questions import WrongQuestionCreate


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


async def create_wrong_question(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    data: WrongQuestionCreate,
) -> WrongQuestion:
    """创建错题记录，返回已 flush 的 ORM 对象（调用方需 commit）。"""
    wq = WrongQuestion(
        id=uuid.uuid4(),
        student_id=student_id,
        source_image_url=data.source_image_url,
        question_text=data.question_text,
        student_answer=data.student_answer,
        correct_answer=data.correct_answer,
        question_type=data.question_type,
        difficulty=data.difficulty,
        tags=data.tags,
    )
    db.add(wq)
    await db.flush()
    # P2：把错题题干里命中词典的生词加入该生词力通候选池（best-effort，不影响主流程）
    try:
        from app.services import vocabulary_service
        await vocabulary_service.add_source_candidates(
            db, student_id=student_id, text=data.question_text or "", source="wrong_question")
    except Exception:  # noqa: BLE001
        pass
    return wq


async def get_wrong_question(
    db: AsyncSession,
    *,
    wq_id: uuid.UUID,
    student_id: uuid.UUID,
) -> WrongQuestion | None:
    """按 id + student_id 查询（student_id 防止越权访问）。"""
    result = await db.execute(
        select(WrongQuestion)
        .where(WrongQuestion.id == wq_id)
        .where(WrongQuestion.student_id == student_id)
    )
    return result.scalar_one_or_none()


def _source_filter(source: str | None):
    """来源过滤：assignment=作业（assignment://），upload=非作业。"""
    if source == "assignment":
        return [WrongQuestion.source_image_url.like("assignment://%")]
    if source == "upload":
        return [~WrongQuestion.source_image_url.like("assignment://%")]
    return []


async def list_wrong_questions(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    skip: int = 0,
    limit: int = 20,
    source: str | None = None,
    tag: str | None = None,
) -> tuple[list[WrongQuestion], int]:
    """分页查询当前学生的错题，按创建时间倒序，返回 (items, total)。source/tag 可过滤。"""
    from sqlalchemy.dialects.postgresql import JSONB as _JSONB
    conds = [WrongQuestion.student_id == student_id, *_source_filter(source)]
    if tag:
        # JSONB @> 包含查询：右侧把 JSON 字符串转为 JSONB
        import json as _json
        from sqlalchemy import cast as _cast, literal as _lit
        conds.append(
            WrongQuestion.tags.op("@>")(_cast(_lit(_json.dumps([tag])), _JSONB))
        )
    count_result = await db.execute(
        select(func.count()).select_from(WrongQuestion).where(*conds)
    )
    total: int = count_result.scalar_one()

    rows = await db.execute(
        select(WrongQuestion)
        .where(*conds)
        .order_by(WrongQuestion.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(rows.scalars().all()), total


# R8 Phase6b 已退役 list_wrong_questions_by_kp:原 join wrong_question_knowledge_points(硬 FK→
# knowledge_points)按 KP 查错题。已被节点化 wrong_center_service.list_by_node 取代(见 API
# /wrong-questions/by-kp,直读 wrong_record),本函数无调用方,一并删除。


async def mark_mastered(
    db: AsyncSession,
    *,
    wq: WrongQuestion,
    is_mastered: bool,
) -> WrongQuestion:
    """切换已掌握状态；is_mastered=True 时记录 mastered_at。"""
    wq.is_mastered = is_mastered
    wq.mastered_at = datetime.now(timezone.utc) if is_mastered else None
    wq.mastery_source = "manual" if is_mastered else None  # 用户手动标记（§5.5 复盘率拆分）
    await db.flush()
    return wq


async def list_analyses(
    db: AsyncSession,
    *,
    wrong_question_id: uuid.UUID,
) -> list[AiAnalysis]:
    """查询某道错题的全部 AI 分析记录，按创建时间倒序。"""
    rows = await db.execute(
        select(AiAnalysis)
        .where(AiAnalysis.wrong_question_id == wrong_question_id)
        .order_by(AiAnalysis.created_at.desc())
    )
    return list(rows.scalars().all())


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
        UserPaperQuestion.is_wrong == True,
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

    # 语法/词汇标签:命中语法节点(cf/jf)或归类名是语法概念 → 语法;有归类名但非语法 → 词汇
    from app.models.d15_knowledge_graph import KnowledgeNode
    from app.services.grammar_progress_service import _grammar_anchor
    from app.services.kp_lecture_service import kp_type_of
    node_ids = [r.node_id for r in rows if r.node_id]
    codes = {}
    if node_ids:
        codes = {nid: code for nid, code in (await db.execute(
            select(KnowledgeNode.id, KnowledgeNode.code).where(KnowledgeNode.id.in_(node_ids)))).all()}

    def _kind(r):
        if (r.node_id and kp_type_of(codes.get(r.node_id)) == "grammar") or (r.kp_key and _grammar_anchor(r.kp_key)):
            return "grammar"
        return "vocab" if r.kp_key else None

    return [
        PaperWrongItem(
            id=r.id,
            stem=r.stem,
            question_type=r.question_type,
            kp_kind=_kind(r),
            kp_name=r.kp_key,
        )
        for r in rows
    ], total


# ── M38 自动打标 ───────────────────────────────────────────────────────────────

def _merge_tags(existing: list | None, new_tags: list[str]) -> list[str]:
    """合并已有 tags 与新 tags，去重，保持顺序。"""
    combined = list(existing or [])
    seen = set(combined)
    for t in new_tags:
        if t and t not in seen:
            combined.append(t)
            seen.add(t)
    return combined


def apply_tags_from_analysis(wq: WrongQuestion, knowledge_points: list[str]) -> None:
    """将 AI 分析的 knowledge_points 合并到 wq.tags（不 commit，由调用方负责）。"""
    if not knowledge_points:
        return
    wq.tags = _merge_tags(wq.tags, knowledge_points)


async def auto_tag_all(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
) -> int:
    """批量补标：找当前学生所有有 AI 分析但缺 tags 的错题，用最新分析的 knowledge_points 填充。

    返回处理条数（processed）。不 commit，由 endpoint 层负责。
    """
    # 1. 找所有 tags 为空/null 的错题
    wqs_result = await db.execute(
        select(WrongQuestion)
        .where(
            WrongQuestion.student_id == student_id,
            (WrongQuestion.tags == None) | (WrongQuestion.tags == []),  # noqa: E711
        )
    )
    wqs: list[WrongQuestion] = list(wqs_result.scalars().all())
    if not wqs:
        return 0

    wq_ids = [wq.id for wq in wqs]

    # 2. 取每道错题最新一条 AI 分析
    analyses_result = await db.execute(
        select(AiAnalysis)
        .where(AiAnalysis.wrong_question_id.in_(wq_ids))
        .order_by(AiAnalysis.created_at.desc())
    )
    analyses: list[AiAnalysis] = list(analyses_result.scalars().all())

    # 按 wrong_question_id → 最新分析
    latest: dict[uuid.UUID, AiAnalysis] = {}
    for a in analyses:
        if a.wrong_question_id not in latest:
            latest[a.wrong_question_id] = a

    processed = 0
    for wq in wqs:
        analysis = latest.get(wq.id)
        if analysis and analysis.knowledge_points:
            apply_tags_from_analysis(wq, list(analysis.knowledge_points))
            processed += 1

    return processed
