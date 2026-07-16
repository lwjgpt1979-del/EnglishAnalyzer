"""阅读理解精讲(作业精讲的「阅读理解」模块)取数。

学生上传作业里 section_type='reading' 的板块 → 按【卷=批次】归组;
每卷下按 block_key(短文)分组:短文 + 该短文的小题(题干/作答/答案/解析)。
**手动加入**:仅显示学生在作业详情点过「加入阅读理解精讲」(in_reading_intensive=true)的卷,不自动加入。
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
               UserPaperSection.section_type == "reading",
               UserPaperSection.in_reading_intensive.is_(True))   # 仅手动加入的
        .group_by(UserUploadedPaper.id, UserUploadedPaper.title, UserUploadedPaper.created_at)
        .order_by(UserUploadedPaper.created_at.desc()))).all()
    return [{"paper_id": str(pid), "title": title or "未命名作业",
             "date": ca.strftime("%Y-%m-%d") if ca else "", "count": int(cnt)}
            for pid, title, ca, cnt in rows]


async def question_analysis(db: AsyncSession, *, student_id: uuid.UUID,
                            question_id: uuid.UUID) -> dict | None:
    """阅读理解精讲·题目层解析(方案D 第2步):题型 rc + 定位句 evidence(逐字原文)+
    为何对 answer_reason + 干扰项 distractors(义项 + 错因)。按题 md5 全局缓存,不二次付费。
    非本人 → None。"""
    import hashlib
    import json as _json
    from app.models.d13_v2_user_papers import ReadingAnalysisCache
    from app.services import question_analysis_service as qa
    from app.services.llm_provider import complete_json, fast_model, is_llm_dev_mode

    q = await db.get(UserPaperQuestion, question_id)
    if q is None:
        return None
    paper = await db.get(UserUploadedPaper, q.user_paper_id)
    if paper is None or paper.student_id != student_id:
        return None
    q_options = getattr(q, "options", None)   # 上传作业题选项内嵌题干,通常无独立 options 列
    context = (q.passage or q.stem or "").strip()
    key = f"{context}||{q.stem or ''}||{_json.dumps(q_options or [], ensure_ascii=False)}||{q.correct_answer or ''}"
    q_md5 = hashlib.md5(key.encode("utf-8")).hexdigest()   # noqa: S324
    hit = await db.get(ReadingAnalysisCache, q_md5)
    if hit is not None:
        return hit.analysis
    # 生成(复用真题阅读解析 prompt/校验;定位句必须逐字原文,防幻觉)
    opts = _json.dumps(q_options, ensure_ascii=False) if q_options else "(选项见题干)"
    user = (f"【原文】\n{context[:3500]}\n\n【题目】{q.stem}\n【选项】{opts}\n"
            f"【正确答案】{q.correct_answer or '未知'}")
    if is_llm_dev_mode():
        ana = {"rc_code": "rc-detail", "evidence": context[:60],
               "answer_reason": "(dev)据定位句得正确项", "distractors": {}}
    else:
        try:
            # 关思考+快档:结构化抽取(定位句+干扰项),开思考会烧 token 截断致空(见真题路径 46s 截断)
            ana = await complete_json(
                system_prompt=qa._SYSTEM_PROMPT, user_prompt=user,
                model=fast_model(), disable_thinking=True, max_tokens=3072,
                escalate_ceiling=4096, validate=lambda d: bool((d.get("evidence") or "").strip()),
                feature="reading_analysis") or {}
        except Exception:  # noqa: BLE001
            return {"error": "解析暂时不可用,请稍后再试"}
    errs = qa.validate_reading_analysis(ana, context_text=context)
    ana["_warnings"] = errs        # 定位句非原文子串等,前端可弱提示(不阻断展示)
    db.add(ReadingAnalysisCache(q_md5=q_md5, analysis=ana))
    await db.commit()
    return ana


async def add_reading_intensive(db: AsyncSession, *, student_id: uuid.UUID,
                                section_id: uuid.UUID) -> dict | None:
    """学生手动把某作业的阅读理解板块加入「作业精讲·阅读理解精讲」。非本人/非阅读 → None。幂等。"""
    sec = await db.get(UserPaperSection, section_id)
    if sec is None:
        return None
    paper = await db.get(UserUploadedPaper, sec.user_paper_id)
    if paper is None or paper.student_id != student_id:
        return None
    if sec.section_type != "reading":
        return {"added": False, "reason": "非阅读理解板块"}
    sec.in_reading_intensive = True
    await db.commit()
    return {"added": True}


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
            "id": str(qq.id),
            "no": qq.question_no, "type": qq.question_type, "stem": qq.stem,
            "options": qq.options if isinstance(getattr(qq, "options", None), list) else None,
            "student_answer": qq.student_answer, "correct_answer": qq.correct_answer,
            "explanation": qq.explanation, "is_wrong": bool(qq.is_wrong)})
    return [blocks[k] for k in order]
