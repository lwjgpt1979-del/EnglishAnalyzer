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


def _tag_reading_skill(q, analysis) -> bool:
    """P1:把精讲产出的题型 skill 归一后落到题上(仅当尚未标)。返回是否改动。
    不 commit——由调用处随其事务提交。"""
    if getattr(q, "reading_skill", None):
        return False
    from app.services.reading_qtype_service import normalize_skill
    q.reading_skill = normalize_skill((analysis or {}).get("skill"))
    return True


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
        if _tag_reading_skill(q, hit.analysis):   # P1:顺手把题型落到题上
            await db.commit()
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
    _tag_reading_skill(q, ana)   # P1:顺手把题型落到题上(随下方 commit 一并持久)
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
        stem, opts = qq.stem, (qq.options if isinstance(getattr(qq, "options", None), list) else None)
        if not opts and stem:
            from app.services.stem_options import parse_inline_options
            clean, parsed = parse_inline_options(stem)
            if parsed:
                stem, opts = clean, parsed
        blocks[bk]["questions"].append({
            "id": str(qq.id),
            "no": qq.question_no, "type": qq.question_type, "stem": stem,
            "options": opts,
            "student_answer": qq.student_answer, "correct_answer": qq.correct_answer,
            "explanation": qq.explanation, "is_wrong": bool(qq.is_wrong),
            "studied": qq.id in studied_ids})
    return [blocks[k] for k in order]


def _answer_letter(s: str | None) -> str | None:
    """从作答/答案文本里取选项字母 A/B/C/D(取首个命中)。取不到 → None(无法判分)。"""
    for ch in (s or "").upper():
        if ch in "ABCD":
            return ch
    return None


async def record_reading_answer(db: AsyncSession, *, student_id: uuid.UUID,
                                question_id: uuid.UUID, chosen: str) -> dict | None:
    """P3 学生在精讲里主动作答某阅读题 → 记 reading_answer_log(留痕,可重做多次)。
    与 correct_answer 字母比对得 is_correct(取不到答案 → None)。非本人题 → None。"""
    from app.models.d13_v2_user_papers import ReadingAnswerLog
    q = await db.get(UserPaperQuestion, question_id)
    if q is None:
        return None
    paper = await db.get(UserUploadedPaper, q.user_paper_id)
    if paper is None or paper.student_id != student_id:
        return None
    pick = _answer_letter(chosen)
    correct = _answer_letter(q.correct_answer)
    is_correct = (pick == correct) if (pick and correct) else None
    db.add(ReadingAnswerLog(student_id=student_id, question_id=question_id,
                            chosen=pick or (chosen or "")[:8], is_correct=is_correct))
    await db.commit()
    return {"chosen": pick, "correct_answer": correct, "is_correct": is_correct}


async def _paper_weak_exam_vocab(db: AsyncSession, *, student_id: uuid.UUID,
                                 paper_id: uuid.UUID) -> dict:
    """P4 词汇探头:与阅读精讲原文高亮同一口径——理解向难词(F+E+A)。
    逐短文抽 → 按 score 合并去重 → Top12。tag 带考纲/频档或「超纲·关键」。"""
    from app.services import user_paper_service as ups
    passages, stems = await ups._paper_texts(db, paper_id)
    if not passages:
        return {"weak_count": 0, "weak": []}
    stem_blob = " ".join(stems) if stems else None
    best: dict[str, dict] = {}   # word → {word, tag, _score}
    for i, p in enumerate(passages):
        others = passages[:i] + passages[i + 1:]
        picked = await ups.comprehension_hard_words(
            db, text=p, student_id=student_id,
            stem_text=stem_blob, other_passages=others, limit=ups._COMP_WORD_TOP)
        for c in picked:
            w = c["word"]
            prev = best.get(w)
            if prev is None or c["score"] > prev["_score"]:
                best[w] = {"word": w, "tag": c.get("exam_tag") or "", "_score": c["score"]}
    weak = sorted(best.values(), key=lambda x: -x["_score"])
    for x in weak:
        x.pop("_score", None)
    weak = weak[:12]
    return {"weak_count": len(weak), "weak": weak}


async def _paper_stuck_sentences(db: AsyncSession, *, student_id: uuid.UUID,
                                 paper_id: uuid.UUID) -> dict:
    """P4 长难句探头:本卷长难句(source_paper_id)里「卡」= 已起学(认成分/重点词)但语法未掌握
    (did_gram=false);不含未学句。卡句的语法结构名(analysis_json.grammar_points)聚合计数。"""
    from collections import Counter
    from app.models.d20_long_sentence import StudentLongSentence
    rows = (await db.execute(
        select(StudentLongSentence.did_comp, StudentLongSentence.did_gram,
               StudentLongSentence.did_word, StudentLongSentence.analysis_json)
        .where(StudentLongSentence.owner_id == student_id,
               StudentLongSentence.source_paper_id == paper_id))).all()
    struct: Counter = Counter()
    stuck = 0
    for did_comp, did_gram, did_word, ana in rows:
        if (did_comp or did_word) and not did_gram:   # 起了学、语法没掌握 = 卡(排除未学)
            stuck += 1
            for gp in ((ana or {}).get("grammar_points") or []):
                nm = (gp or {}).get("name")
                if nm:
                    struct[nm] += 1
    return {"total": len(rows), "stuck": stuck,
            "structures": [{"name": n, "count": c} for n, c in struct.most_common(6)]}


async def paper_reading_summary(db: AsyncSession, *, student_id: uuid.UUID,
                                paper_id: uuid.UUID) -> dict | None:
    """单篇读后小结·三块(提问/词汇/长难句):该卷阅读题按「题型」聚合对错 + 一句话诊断。
    题型先按需补标(P1,查看即生成)。对错口径:优先取学生「精讲里主动作答」的最新一次
    (P3 reading_answer_log,治 OCR 抓不到卷面圈选),回落 OCR is_wrong;都没有 → 未作答。
    非本人卷 → None。"""
    from collections import defaultdict
    from app.models.d13_v2_user_papers import ReadingAnswerLog
    from app.services import reading_qtype_service as qsvc

    paper = await db.get(UserUploadedPaper, paper_id)
    if paper is None or paper.student_id != student_id:
        return None
    await qsvc.ensure_paper_tagged(db, paper_id=paper_id)   # 回填+少量补跑,零运营
    rows = (await db.execute(
        select(UserPaperQuestion.id, UserPaperQuestion.reading_skill,
               UserPaperQuestion.is_wrong, UserPaperQuestion.student_answer)
        .join(UserPaperSection, UserPaperSection.id == UserPaperQuestion.section_id)
        .where(UserPaperSection.section_type == "reading",
               UserPaperQuestion.user_paper_id == paper_id))).all()
    qids = [r.id for r in rows]
    # 每题最新一次「已判」作答(升序遍历,后者即更新)
    fresh: dict[uuid.UUID, bool] = {}
    if qids:
        logs = (await db.execute(
            select(ReadingAnswerLog.question_id, ReadingAnswerLog.is_correct)
            .where(ReadingAnswerLog.student_id == student_id,
                   ReadingAnswerLog.question_id.in_(qids))
            .order_by(ReadingAnswerLog.created_at))).all()
        for qid, ic in logs:
            if ic is not None:
                fresh[qid] = bool(ic)
    agg: dict[str, dict] = defaultdict(lambda: {"total": 0, "wrong": 0})
    answered = wrong = 0
    for qid, sk, is_wrong, stu_ans in rows:
        if qid in fresh:                       # ① 主动作答(最优)
            correct = fresh[qid]
        elif stu_ans:                          # ② OCR 抓到的卷面作答
            correct = not is_wrong
        else:                                  # ③ 未作答 → 不计正确率
            continue
        cell = agg[sk or "其他"]
        cell["total"] += 1
        answered += 1
        if not correct:
            cell["wrong"] += 1
            wrong += 1
    by_skill = sorted(
        ({"skill": k, "total": v["total"], "wrong": v["wrong"]} for k, v in agg.items()),
        key=lambda x: (-x["wrong"], -x["total"]))
    worst = next((s for s in by_skill if s["wrong"] > 0), None)
    if not answered:
        diagnosis = "本篇还没作答,点题目下方 A/B/C/D 作答后即出小结。"
    elif worst:
        diagnosis = f"本篇薄弱题型:{worst['skill']}(错 {worst['wrong']}/{worst['total']})"
    else:
        diagnosis = "本篇全对,读得不错。"
    sentences = await _paper_stuck_sentences(db, student_id=student_id, paper_id=paper_id)
    return {"total": len(rows), "answered": answered, "unanswered": len(rows) - answered,
            "wrong": wrong, "by_skill": by_skill, "diagnosis": diagnosis,
            "sentences": sentences}


# ── P5 阶段薄弱点聚合(跨卷 + 时间窗)─────────────────────────────────────────
# 判弱阈值走 reading_analytics_config_service(system_configs,运营可配 + 后台入口)


async def reading_analytics(db: AsyncSession, *, student_id: uuid.UUID,
                            days: int = 14, paper_cap: int = 20) -> dict:
    """P5 阶段薄弱点:近 days 天(days<=0=全部)多卷聚合 → 多篇理解向重点词 / 反复卡句法 /
    弱题型正确率 + 一句话诊断。纯阈值判弱(可配)。全部复用现成信号,零新增采集。"""
    from datetime import datetime, timezone, timedelta
    from collections import Counter, defaultdict
    from app.models.d13_v2_user_papers import ReadingAnswerLog
    from app.models.d20_long_sentence import StudentLongSentence
    from app.services import reading_analytics_config_service

    th = await reading_analytics_config_service.get_config(db)
    pq = (select(UserUploadedPaper.id)
          .where(UserUploadedPaper.student_id == student_id)
          .order_by(UserUploadedPaper.created_at.desc()))
    if days and days > 0:
        pq = pq.where(UserUploadedPaper.created_at >= datetime.now(timezone.utc) - timedelta(days=days))
    papers = (await db.execute(pq)).scalars().all()
    if not papers:
        return {"days": days, "papers": 0, "skills": [], "weak_skills": [],
                "weak_structures": [], "weak_words": [], "diagnosis": "这段时间还没有阅读作业。"}

    # ① 题型正确率(对错口径同单篇:主动作答 > OCR is_wrong > 未答不计)
    q_rows = (await db.execute(
        select(UserPaperQuestion.id, UserPaperQuestion.reading_skill,
               UserPaperQuestion.is_wrong, UserPaperQuestion.student_answer)
        .join(UserPaperSection, UserPaperSection.id == UserPaperQuestion.section_id)
        .where(UserPaperSection.section_type == "reading",
               UserPaperQuestion.user_paper_id.in_(papers)))).all()
    fresh: dict = {}
    qids = [r.id for r in q_rows]
    if qids:
        for qid, ic in (await db.execute(
            select(ReadingAnswerLog.question_id, ReadingAnswerLog.is_correct)
            .where(ReadingAnswerLog.student_id == student_id,
                   ReadingAnswerLog.question_id.in_(qids))
            .order_by(ReadingAnswerLog.created_at))).all():
            if ic is not None:
                fresh[qid] = bool(ic)
    sk_agg: dict = defaultdict(lambda: {"total": 0, "wrong": 0})
    for qid, sk, is_wrong, stu in q_rows:
        if qid in fresh:
            correct = fresh[qid]
        elif stu:
            correct = not is_wrong
        else:
            continue
        c = sk_agg[sk or "其他"]
        c["total"] += 1
        if not correct:
            c["wrong"] += 1
    skills = sorted(
        ({"skill": k, "total": v["total"], "wrong": v["wrong"],
          "rate": round((v["total"] - v["wrong"]) / v["total"] * 100) if v["total"] else 0}
         for k, v in sk_agg.items()),
        key=lambda x: (x["rate"], -x["total"]))
    weak_skills = [s for s in skills
                   if s["total"] >= th["skill_min_sample"] and s["rate"] < th["skill_weak_rate"]]

    # ② 多篇理解向重点词(出现 ≥N 卷;复用单篇词汇探头,与原文高亮同口径 F+E+A)
    word_papers: dict = defaultdict(set)
    word_tag: dict = {}
    for pid in papers[:paper_cap]:
        vb = await _paper_weak_exam_vocab(db, student_id=student_id, paper_id=pid)
        for w in vb["weak"]:
            word_papers[w["word"]].add(pid)
            word_tag[w["word"]] = w["tag"]
    weak_words = sorted(
        ({"word": w, "tag": word_tag[w], "papers": len(ps)}
         for w, ps in word_papers.items() if len(ps) >= th["weak_word_min_papers"]),
        key=lambda x: (-("频" in (x["tag"] or "")), -x["papers"]))[:12]

    # ③ 反复卡的句法结构(卡 ≥K 次;卡口径同单篇:已起学但 did_gram=false)
    struct: Counter = Counter()
    for dc, dg, dw, ana in (await db.execute(
        select(StudentLongSentence.did_comp, StudentLongSentence.did_gram,
               StudentLongSentence.did_word, StudentLongSentence.analysis_json)
        .where(StudentLongSentence.owner_id == student_id,
               StudentLongSentence.source_paper_id.in_(papers)))).all():
        if (dc or dw) and not dg:
            for gp in ((ana or {}).get("grammar_points") or []):
                nm = (gp or {}).get("name")
                if nm:
                    struct[nm] += 1
    weak_structures = [{"name": n, "count": c} for n, c in struct.most_common()
                       if c >= th["struct_min_stuck"]][:8]

    bits = []
    if weak_skills:
        bits.append(weak_skills[0]["skill"] + "题")
    if weak_structures:
        bits.append(weak_structures[0]["name"])
    if weak_words:
        bits.append(weak_words[0]["word"] + " 类重点词")
    diagnosis = ("近期薄弱:" + " + ".join(bits) + ",建议优先攻这几块。") if bits \
        else "近期没有明显薄弱点,继续保持。"
    return {"days": days, "papers": len(papers), "skills": skills,
            "weak_skills": weak_skills, "weak_structures": weak_structures,
            "weak_words": weak_words, "diagnosis": diagnosis}
