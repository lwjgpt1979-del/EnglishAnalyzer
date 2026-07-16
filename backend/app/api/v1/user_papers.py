"""整卷上传 OCR 拆题 API（D-089 / M4）。

POST /user-papers          建卷 + 触发后台 OCR 拆题管线
GET  /user-papers          列出本人整卷
GET  /user-papers/{id}     整卷详情（含拆出的题目）
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.exceptions import AppError
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import make_ok
from app.schemas.user_papers import UserPaperCreate, UserPaperListOut, SectionUpdateIn, AnalyzeSentenceIn
from app.services import user_paper_service

router = APIRouter(prefix="/user-papers", tags=["user-papers"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.post("")
async def create_user_paper(
    body: UserPaperCreate,
    background_tasks: BackgroundTasks,
    db: DbDep,
    current_user: UserDep,
):
    """建卷并异步触发 OCR 拆题。"""
    await get_rls_db(db, str(current_user.id))
    from app.services import entitlement_service
    await entitlement_service.require_feature(db, user_id=current_user.id, key="paper.upload")
    paper, reused = await user_paper_service.create_paper(
        db,
        student_id=current_user.id,
        source_image_urls=body.source_image_urls,
        title=body.title,
    )
    if reused:
        # 问题1:同图已解析过 → 直接复用,不重复扣费、不重复解析
        return make_ok({"id": str(paper.id), "title": paper.title,
                        "ocr_status": paper.ocr_status, "reused": True})

    await entitlement_service.consume(db, user_id=current_user.id, key="paper.upload")
    await db.commit()

    background_tasks.add_task(user_paper_service.run_paper_pipeline, paper.id)

    return make_ok(
        {
            "id": str(paper.id),
            "title": paper.title,
            "ocr_status": paper.ocr_status,
            "reused": False,
        }
    )


@router.get("")
async def list_user_papers(
    db: DbDep,
    current_user: UserDep,
):
    """列出本人整卷。"""
    items = await user_paper_service.list_papers(db, student_id=current_user.id)
    out = UserPaperListOut(items=items, total=len(items))
    return make_ok(out.model_dump(mode="json"))


@router.get("/{paper_id}")
async def get_user_paper(
    paper_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
):
    """整卷详情（含题目）。"""
    detail = await user_paper_service.get_paper_detail(
        db, paper_id=paper_id, student_id=current_user.id
    )
    if detail is None:
        raise AppError(code=404, message="试卷不存在或无权访问")
    return make_ok(detail.model_dump(mode="json"))


@router.get("/{paper_id}/grammar-status")
async def get_paper_grammar_status(
    paper_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
):
    """P1:本卷语法点对照学生掌握度 → 已学 / 薄弱 / 未学(未学可一键去学)。"""
    r = await user_paper_service.paper_grammar_status(
        db, paper_id=paper_id, student_id=current_user.id)
    if r is None:
        raise AppError(code=404, message="试卷不存在或无权访问")
    return make_ok(r)


@router.get("/{paper_id}/vocab")
async def get_paper_vocab(
    paper_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
    section_id: uuid.UUID | None = Query(None, description="给定→只取该题型的生词(本题型级)"),
):
    """P2:本卷原文里的『生词』(未学/接收度低),可挑选加入词力通优先学(走 /vocabulary/pins)。"""
    r = await user_paper_service.paper_vocab_candidates(
        db, paper_id=paper_id, student_id=current_user.id, section_id=section_id)
    if r is None:
        raise AppError(code=404, message="试卷不存在或无权访问")
    return make_ok(r)


@router.get("/{paper_id}/long-sentences")
async def get_paper_long_sentences(
    paper_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
    section_id: uuid.UUID | None = Query(None, description="给定→只取该题型的长难句(本题型级)"),
):
    """P3:从本卷短文拆出的长难句,可逐句解析。"""
    r = await user_paper_service.paper_long_sentences(
        db, paper_id=paper_id, student_id=current_user.id, section_id=section_id)
    if r is None:
        raise AppError(code=404, message="试卷不存在或无权访问")
    return make_ok(r)


@router.post("/analyze-sentence")
async def analyze_sentence(
    body: AnalyzeSentenceIn,
    db: DbDep,
    current_user: UserDep,
):
    """P3:按需解析一句长难句(结构切分 + 释义),带暂存复用。"""
    return make_ok(await user_paper_service.analyze_paper_sentence(db, body.sentence))


@router.post("/save-sentence")
async def save_sentence(
    body: AnalyzeSentenceIn,
    db: DbDep,
    current_user: UserDep,
):
    """学生把一句长难句「加入学习」——打包:该句 + 句中单词 + 句中语法点 一起进作业精讲的
    长难句/单词/语法(同一来源卷=同一批次)。返回三项计数。"""
    from app.services import long_sentence_service
    r = await long_sentence_service.add_paper_sentence_bundle(
        db, owner_id=current_user.id, text=body.sentence, source_paper_id=body.paper_id)
    # 兼容旧字段 added(句是否新增)
    return make_ok({"added": r["sentence_added"], **r})


@router.post("/{paper_id}/add-to-plan")
async def add_paper_to_plan(
    paper_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
):
    """P4 闭环:把本卷「未学 + 薄弱」语法一键加入学习目标 → 今日计划带出「去学/去练」。"""
    r = await user_paper_service.add_paper_grammar_to_plan(
        db, paper_id=paper_id, student_id=current_user.id)
    if r is None:
        raise AppError(code=404, message="试卷不存在或无权访问")
    return make_ok(r)


@router.put("/{paper_id}/title")
async def rename_paper(
    paper_id: uuid.UUID,
    body: dict,
    db: DbDep,
    current_user: UserDep,
):
    """重命名作业标题(用户可自己修改自动生成的名字)。"""
    title = str((body or {}).get("title") or "").strip()
    if not title:
        raise AppError(code=422, message="标题不能为空")
    r = await user_paper_service.rename_paper(
        db, paper_id=paper_id, student_id=current_user.id, title=title[:100])
    if r is None:
        raise AppError(code=404, message="作业不存在或无权访问")
    return make_ok({"title": r})


@router.put("/sections/{section_id}")
async def update_paper_section(
    section_id: uuid.UUID,
    body: SectionUpdateIn,
    db: DbDep,
    current_user: UserDep,
):
    """学生修改某大题的题型分类(AI 建议不准时可改;改后不再标「建议」)。"""
    ok = await user_paper_service.update_section(
        db, section_id=section_id, student_id=current_user.id, label=body.label)
    if not ok:
        raise AppError(code=404, message="大题不存在或无权访问")
    return make_ok({"updated": True, "label": body.label.strip()})


@router.get("/wrongs")
async def list_paper_wrong_questions(
    db: DbDep,
    current_user: UserDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    """整卷错题列表（is_wrong=True）。供前端错题本"整卷"tab 调用。"""
    from app.services.wrong_question_service import list_paper_wrongs
    items, total = await list_paper_wrongs(
        db, student_id=current_user.id, skip=skip, limit=limit
    )
    return make_ok({
        "items": [
            {
                "id": str(i.id),
                "stem": i.stem,
                "question_type": i.question_type,
                "is_mastered": i.is_mastered,
                "source_label": i.source_label,
                "kp_kind": i.kp_kind,
                "kp_name": i.kp_name,
            }
            for i in items
        ],
        "total": total,
    })


@router.get("/{paper_id}/kp-summary")
async def paper_kp_summary_api(paper_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """本卷错题按知识点归集（M4 深化）：每个知识点 总/错 数 + 薄弱标，薄弱优先。"""
    await get_rls_db(db, str(current_user.id))
    res = await user_paper_service.paper_kp_summary(
        db, paper_id=paper_id, student_id=current_user.id)
    if res is None:
        raise AppError(code=404, message="试卷不存在或无权访问")
    return make_ok(res)


@router.post("/questions/{question_id}/add-grammar")
async def add_question_grammar_api(question_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """单题「加入语法学习」→ 作业精讲·语法(命中图谱)或个人语法树(未命中)。"""
    r = await user_paper_service.add_question_grammar(
        db, question_id=question_id, student_id=current_user.id)
    if r is None:
        raise AppError(code=404, message="题目不存在或无权访问")
    return make_ok(r)


@router.post("/questions/{question_id}/add-vocab")
async def add_question_vocab_api(question_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """单题「加入作业精讲·单词」→ 从题干抽词典命中的词加入作业精讲·单词候选。"""
    r = await user_paper_service.add_question_vocab(
        db, question_id=question_id, student_id=current_user.id)
    if r is None:
        raise AppError(code=404, message="题目不存在或无权访问")
    return make_ok(r)


@router.post("/questions/{question_id}/add-wrong")
async def add_question_to_wrong_api(question_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """手动把某道题加入「我的错题」(答对想复习该考点的兜底;错题已自动进)。"""
    r = await user_paper_service.add_question_to_wrong(
        db, question_id=question_id, student_id=current_user.id)
    if r is None:
        raise AppError(code=404, message="题目不存在或无权访问")
    return make_ok(r)


@router.post("/sections/{section_id}/add-reading-intensive")
async def add_reading_intensive_api(section_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """手动把某作业的阅读理解板块加入「作业精讲·阅读理解精讲」(不自动加入)。"""
    from app.services import reading_intensive_service
    r = await reading_intensive_service.add_reading_intensive(
        db, student_id=current_user.id, section_id=section_id)
    if r is None:
        raise AppError(code=404, message="板块不存在或无权访问")
    return make_ok(r)


@router.get("/questions/{question_id}/reading-analysis")
async def reading_analysis_api(question_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """阅读理解精讲·题目层解析(题型/定位句/为何对/干扰项),缓存复用。"""
    from app.services import reading_intensive_service
    r = await reading_intensive_service.question_analysis(
        db, student_id=current_user.id, question_id=question_id)
    if r is None:
        raise AppError(code=404, message="题目不存在或无权访问")
    return make_ok(r)


@router.post("/questions/{question_id}/practice")
async def practice_for_question_api(question_id: uuid.UUID, db: DbDep, current_user: UserDep):
    """错题「练同类」：按该题知识点生成同类仿真练习（计入 practice.generate 配额）。"""
    await get_rls_db(db, str(current_user.id))
    from app.services import entitlement_service
    await entitlement_service.require_feature(db, user_id=current_user.id, key="practice.generate")
    res = await user_paper_service.practice_for_question(
        db, question_id=question_id, student_id=current_user.id)
    await entitlement_service.consume(db, user_id=current_user.id, key="practice.generate")
    await db.commit()
    qs = res["questions"]
    kp_name = res["knowledge_point"]
    return make_ok({
        "knowledge_point": kp_name,
        "questions": [
            {
                "id": str(q.id),
                "knowledge_point_name": kp_name, "question_type": str(q.question_type),
                "difficulty": q.difficulty, "stem": (q.content or {}).get("stem", ""),
                "options": (q.content or {}).get("options"),
                "answer": (q.content or {}).get("answer"),
                "explanation": (q.content or {}).get("explanation"),
            } for q in qs
        ],
    })


@router.post("/questions/{question_id}/practice-result")
async def paper_practice_result(
    question_id: uuid.UUID, body: dict, db: DbDep, current_user: UserDep,
):
    """作业详情练同类结算:回写对应错题的 practice + 语法推进 SM-2。body: {total, correct}"""
    await get_rls_db(db, str(current_user.id))
    from app.services import wrong_center_service
    r = await wrong_center_service.record_practice_for_question(
        db, student_id=current_user.id, question_id=question_id,
        total=int(body.get("total", 0)), correct=int(body.get("correct", 0)))
    await db.commit()
    return make_ok(r)
