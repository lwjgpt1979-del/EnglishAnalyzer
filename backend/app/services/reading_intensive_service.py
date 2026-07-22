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

# 方案B 四件套:题型(中文)→定位证据→为什么对→干扰项为什么错→该题型通用技巧
_READING_INTENSIVE_SYS = (
    "你是中小学英语阅读理解精讲老师。对给定的阅读小题做「解题精讲」,只返回 JSON:"
    '{"rc_code":"rc-x-x 阅读技能编码",'
    '"skill":"该题的题型中文名(细节理解/主旨大意/推理判断/词义猜测/作者态度/指代关系/图表数字 之一或更贴切的)",'
    '"evidence":"答案定位句(必须逐字摘自原文,不改写不翻译)",'
    '"answer_reason":"由定位句到正确项的推理(1-2句)",'
    '"distractors":{"A":{"meaning":"该选项的主张/义项(中文)","why_wrong":"为何是干扰项——与原文哪处冲突,点明错因类型"},...},'
    '"skill_tip":"该题型的通用解题技巧(1-2句,可迁移到同类题;如『细节题先定位关键词回原文比对』)"}。'
    "distractors 只列**非正确项**(正确项不出现),每项都要给 meaning + why_wrong。"
    "evidence 会用程序在原文里做子串比对,凑不出原文子串会判幻觉,务必逐字摘抄。"
    "**除 evidence(逐字原文)外,所有解析文字(answer_reason/meaning/why_wrong/skill_tip)一律用中文。**"
)


async def homework_batches(db: AsyncSession, *, student_id: uuid.UUID) -> list[dict]:
    """学生上传作业里含阅读理解的卷,按卷(批次)归组。年月日倒序。
    带 studied(该卷已看解析/练过同类的题数)供前端算 未学/学习中/已学。"""
    from app.models.d13_v2_user_papers import ReadingQuestionStudied
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
    # 每卷已精讲题数(看解析/练同类记录)
    st_rows = (await db.execute(
        select(UserUploadedPaper.id,
               func.count(func.distinct(ReadingQuestionStudied.question_id)))
        .join(UserPaperSection, UserPaperSection.user_paper_id == UserUploadedPaper.id)
        .join(UserPaperQuestion, UserPaperQuestion.section_id == UserPaperSection.id)
        .join(ReadingQuestionStudied,
              (ReadingQuestionStudied.question_id == UserPaperQuestion.id)
              & (ReadingQuestionStudied.student_id == student_id))
        .where(UserUploadedPaper.student_id == student_id,
               UserPaperSection.section_type == "reading",
               UserPaperSection.in_reading_intensive.is_(True))
        .group_by(UserUploadedPaper.id))).all()
    studied = {pid: int(c) for pid, c in st_rows}
    return [{"paper_id": str(pid), "title": title or "未命名作业",
             "date": ca.strftime("%Y-%m-%d") if ca else "", "count": int(cnt),
             "studied": studied.get(pid, 0)}
            for pid, title, ca, cnt in rows]


async def mark_question_studied(db: AsyncSession, *, student_id: uuid.UUID,
                                question_id: uuid.UUID) -> None:
    """标记某阅读题「已精讲」(看解析/练同类即算学过);(student,question) 幂等。
    仅本人的题才记(调用方已校验归属)。"""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.models.d13_v2_user_papers import ReadingQuestionStudied
    await db.execute(pg_insert(ReadingQuestionStudied)
                     .values(student_id=student_id, question_id=question_id)
                     .on_conflict_do_nothing(index_elements=["student_id", "question_id"]))
    await db.commit()


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
        ana = {"rc_code": "rc-detail", "skill": "细节理解", "evidence": context[:60],
               "answer_reason": "(dev)据定位句得正确项", "distractors": {},
               "skill_tip": "(dev)细节题先圈关键词回原文比对"}
    else:
        try:
            # 关思考+快档:结构化抽取(定位句+干扰项),开思考会烧 token 截断致空(见真题路径 46s 截断)
            ana = await complete_json(
                system_prompt=_READING_INTENSIVE_SYS, user_prompt=user,
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


_READING_PRACTICE_SYS = (
    "你是中小学英语阅读命题老师。根据给定【短文】出 {count} 道**阅读理解选择题**,"
    "考查对**这篇文章**的理解(细节/推断/主旨/词义猜测/作者态度等,题型可多样),难度贴近中学。"
    "每题 4 个选项。只返回 JSON 对象:"
    '{{"questions":[{{"stem":"题干(英文)","options":["A. …","B. …","C. …","D. …"],'
    '"answer":"正确选项字母(A/B/C/D)","explanation":"中文解析:回原文定位 + 为什么对"}}]}}。'
    "★铁律:题目必须**能由短文本身回答**,不考查文章外的知识;选项含字母前缀;answer 为字母;干扰项要有迷惑性但可被原文排除。"
)


async def practice_similar(db: AsyncSession, *, student_id: uuid.UUID,
                           question_id: uuid.UUID, count: int = 5) -> dict | None:
    """阅读理解「练同类」:基于本题所在**短文**生成 count 道理解新题(非语法题)。
    按(短文+数量)md5 全局缓存,同篇不二次付费。返回 {questions:[{id,stem,options,answer,explanation}]}。非本人 → None。"""
    import hashlib
    import json as _json
    import uuid as _uuid
    from app.models.d13_v2_user_papers import ReadingPracticeCache
    from app.services.llm_provider import complete_json, fast_model, is_llm_dev_mode

    q = await db.get(UserPaperQuestion, question_id)
    if q is None:
        return None
    paper = await db.get(UserUploadedPaper, q.user_paper_id)
    if paper is None or paper.student_id != student_id:
        return None
    passage = (q.passage or "").strip()
    if not passage:
        return {"questions": []}
    cache_md5 = hashlib.md5(f"{passage}||{count}".encode("utf-8")).hexdigest()   # noqa: S324
    hit = await db.get(ReadingPracticeCache, cache_md5)
    if hit is not None:
        qs = hit.questions
    else:
        user = f"【短文】\n{passage[:3500]}"
        if is_llm_dev_mode():
            qs = [{"stem": f"According to the passage, statement {i+1}?",
                   "options": ["A. mock1", "B. mock2", "C. mock3", "D. mock4"],
                   "answer": "A", "explanation": "(dev)据原文定位"} for i in range(count)]
        else:
            try:
                data = await complete_json(
                    system_prompt=_READING_PRACTICE_SYS.format(count=count), user_prompt=user,
                    model=fast_model(), disable_thinking=True, max_tokens=3072, escalate_ceiling=4096,
                    validate=lambda d: isinstance(d.get("questions"), list) and len(d["questions"]) > 0,
                    feature="reading_practice")
            except Exception:  # noqa: BLE001
                return {"questions": [], "error": "出题暂时不可用,请稍后再试"}
            qs = (data or {}).get("questions") or []
            qs = [x for x in qs if isinstance(x, dict) and x.get("stem") and x.get("options")][:count]
            if qs:
                db.add(ReadingPracticeCache(cache_md5=cache_md5, questions=qs))
                await db.commit()
    # 稳定 id(缓存命中也一致):按内容派生
    out = [{"id": str(_uuid.uuid5(_uuid.NAMESPACE_OID, f"{cache_md5}:{i}")),
            "stem": x.get("stem"), "options": x.get("options"),
            "answer": x.get("answer"), "explanation": x.get("explanation")}
           for i, x in enumerate(qs)]
    return {"questions": out}


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
    from app.models.d13_v2_user_papers import ReadingQuestionStudied
    rows = (await db.execute(
        select(UserPaperQuestion)
        .join(UserPaperSection, UserPaperSection.id == UserPaperQuestion.section_id)
        .where(UserPaperQuestion.user_paper_id == paper_id,
               UserPaperSection.section_type == "reading")
        .order_by(UserPaperQuestion.sort_order))).scalars().all()
    studied_ids = set((await db.execute(
        select(ReadingQuestionStudied.question_id)
        .where(ReadingQuestionStudied.student_id == student_id,
               ReadingQuestionStudied.question_id.in_([q.id for q in rows] or [None])))).scalars().all())
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
            "explanation": qq.explanation, "is_wrong": bool(qq.is_wrong),
            "studied": qq.id in studied_ids})
    return [blocks[k] for k in order]
