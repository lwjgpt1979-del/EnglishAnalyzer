"""完形填空精讲(作业精讲的「完形填空」模块)取数。

短文挖空族(方案1·宽口径,不改拆卷 section_type 真值):
- 恒纳入:cloze / passage_fill / reading_fill
- 有语篇才纳入:vocab_use / verb_fill(单句词形不进)
空形态(所给词变形/首字母/中文提示/四选一/纯空)只影响题卡,不改模块归属。
**手动加入**:仅显示点过「加入完形填空精讲」(in_cloze_intensive=true)的卷。
解析为双轴(线索类型/线索句/为何对/干扰错因/载体槽),按题 md5 全局缓存。
"""
from __future__ import annotations

import hashlib
import json as _json
import uuid

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d13_v2_user_papers import (
    UserUploadedPaper, UserPaperSection, UserPaperQuestion,
    ClozeAnalysisCache, ClozePracticeCache, ClozeQuestionStudied,
)

# 短文挖空族·恒纳入(拆卷键保持原值,精讲侧宽口径)
_CLOZE_FAMILY_ALWAYS = frozenset({"cloze", "passage_fill", "reading_fill", "fill"})
# 仅当大题下小题带语篇/block 才算完形变种(加入时闸门;列表 SQL 用并集简化)
_CLOZE_FAMILY_IF_PASSAGE = frozenset({"vocab_use", "verb_fill"})
_CLOZE_FAMILY_SQL = frozenset(_CLOZE_FAMILY_ALWAYS | _CLOZE_FAMILY_IF_PASSAGE)


def _cloze_section_sql():
    """SQL:短文挖空族板块(按 section_type;语篇闸门只在 add 时做,避免 EXISTS 与外层 join 自相关炸编译)。"""
    return UserPaperSection.section_type.in_(tuple(_CLOZE_FAMILY_SQL))


async def _section_is_cloze_family(db: AsyncSession, sec: UserPaperSection) -> bool:
    """Python 侧判定:可否加入完形精讲。"""
    st = (sec.section_type or "").strip()
    if st in _CLOZE_FAMILY_ALWAYS:
        return True
    if st not in _CLOZE_FAMILY_IF_PASSAGE:
        return False
    row = (await db.execute(
        select(UserPaperQuestion.id)
        .where(
            UserPaperQuestion.section_id == sec.id,
            or_(
                and_(UserPaperQuestion.passage.isnot(None), UserPaperQuestion.passage != ""),
                and_(UserPaperQuestion.block_key.isnot(None), UserPaperQuestion.block_key != ""),
            ),
        )
        .limit(1))).first()
    return row is not None

_CLUE_TYPES = (
    "句内固定搭配", "句内语法约束", "跨句逻辑关系", "跨句词汇复现",
    "全篇情感基调", "指代与人物追踪", "情景交际惯用",
)

_CLOZE_ANALYSIS_SYS = (
    "你是中小学英语完形填空精讲老师。对给定空做「双轴解析」,只返回 JSON:"
    '{"clue_type":"线索类型(必须是以下之一:' + "/".join(_CLUE_TYPES) + ')",'
    '"clue":"决定答案的原文线索句(必须逐字摘自语篇,不改写)",'
    '"answer_reason":"为何正确项对(1-2句中文)",'
    '"distractor_why":"学生错选(若有)或主要干扰项的错因中文(张冠李戴/以偏概全/近似词误配等)",'
    '"slot":"载体槽:名词/动词/动词短语/形容词/副词/连词/介词/代词/交际用语/其它"}。'
    "**除 clue(逐字原文)外,所有解析文字一律用中文。**"
    "clue 必须是语篇子串;凑不出原文子串会判幻觉。"
)

_CLOZE_PRACTICE_SYS = (
    "你是中小学英语完形命题老师。根据给定【语篇片段】与【线索类型】出 {count} 道**单选选择题**,"
    "考查同类语境线索捕捉(不是孤立背词)。每题 4 个选项。"
    "题干句除目标考点词外其余用词要简单常见。"
    "只返回 JSON:"
    '{{"questions":[{{"stem":"题干(英文,可挖空)","options":["A. …","B. …","C. …","D. …"],'
    '"answer":"正确选项全文或字母","explanation":"中文解析"}}]}}。'
    "**explanation 一律用中文,即使题干/选项是英文。**"
)


async def homework_batches(db: AsyncSession, *, student_id: uuid.UUID) -> list[dict]:
    """含短文挖空族且已手动加入精讲的卷;带 studied。"""
    fam = _cloze_section_sql()
    rows = (await db.execute(
        select(UserUploadedPaper.id, UserUploadedPaper.title, UserUploadedPaper.created_at,
               func.count(UserPaperQuestion.id))
        .join(UserPaperSection, UserPaperSection.user_paper_id == UserUploadedPaper.id)
        .join(UserPaperQuestion, UserPaperQuestion.section_id == UserPaperSection.id)
        .where(UserUploadedPaper.student_id == student_id,
               UserUploadedPaper.ocr_status == "completed",
               fam,
               UserPaperSection.in_cloze_intensive.is_(True))
        .group_by(UserUploadedPaper.id, UserUploadedPaper.title, UserUploadedPaper.created_at)
        .order_by(UserUploadedPaper.created_at.desc()))).all()
    st_rows = (await db.execute(
        select(UserUploadedPaper.id,
               func.count(func.distinct(ClozeQuestionStudied.question_id)))
        .join(UserPaperSection, UserPaperSection.user_paper_id == UserUploadedPaper.id)
        .join(UserPaperQuestion, UserPaperQuestion.section_id == UserPaperSection.id)
        .join(ClozeQuestionStudied,
              (ClozeQuestionStudied.question_id == UserPaperQuestion.id)
              & (ClozeQuestionStudied.student_id == student_id))
        .where(UserUploadedPaper.student_id == student_id,
               fam,
               UserPaperSection.in_cloze_intensive.is_(True))
        .group_by(UserUploadedPaper.id))).all()
    studied = {pid: int(c) for pid, c in st_rows}
    return [{"paper_id": str(pid), "title": title or "未命名作业",
             "date": ca.strftime("%Y-%m-%d") if ca else "", "count": int(cnt),
             "studied": studied.get(pid, 0)}
            for pid, title, ca, cnt in rows]


async def mark_question_studied(db: AsyncSession, *, student_id: uuid.UUID,
                                question_id: uuid.UUID) -> None:
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    await db.execute(pg_insert(ClozeQuestionStudied)
                     .values(student_id=student_id, question_id=question_id)
                     .on_conflict_do_nothing(index_elements=["student_id", "question_id"]))
    await db.commit()


async def add_cloze_intensive(db: AsyncSession, *, student_id: uuid.UUID,
                              section_id: uuid.UUID) -> dict | None:
    """手动加入完形精讲。非本人/非短文挖空族 → None / reason。"""
    sec = await db.get(UserPaperSection, section_id)
    if sec is None:
        return None
    paper = await db.get(UserUploadedPaper, sec.user_paper_id)
    if paper is None or paper.student_id != student_id:
        return None
    if not await _section_is_cloze_family(db, sec):
        return {"added": False, "reason": "非完形/短文填空类板块"}
    sec.in_cloze_intensive = True
    await db.commit()
    return {"added": True}


async def homework_passages(db: AsyncSession, *, student_id: uuid.UUID,
                            paper_id: uuid.UUID) -> list[dict]:
    """某卷短文挖空族:按 block_key 组语篇 + 空题。"""
    paper = await db.get(UserUploadedPaper, paper_id)
    if paper is None or paper.student_id != student_id:
        return []
    rows = (await db.execute(
        select(UserPaperQuestion)
        .join(UserPaperSection, UserPaperSection.id == UserPaperQuestion.section_id)
        .where(UserPaperQuestion.user_paper_id == paper_id,
               _cloze_section_sql())
        .order_by(UserPaperQuestion.sort_order))).scalars().all()
    studied_ids = set((await db.execute(
        select(ClozeQuestionStudied.question_id)
        .where(ClozeQuestionStudied.student_id == student_id,
               ClozeQuestionStudied.question_id.in_([q.id for q in rows] or [None])))).scalars().all())
    blocks: dict[str, dict] = {}
    order: list[str] = []
    for qq in rows:
        bk = qq.block_key or f"__solo_{qq.id}"
        if bk not in blocks:
            blocks[bk] = {
                "block_key": qq.block_key or "",
                "block_label": (f" · {qq.block_key}" if qq.block_key else ""),
                "passage": qq.passage or "", "questions": [],
            }
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
            "studied": qq.id in studied_ids,
        })
    return [blocks[k] for k in order]


def _clue_in_passage(clue: str, passage: str) -> bool:
    """线索句须为语篇子串(空白归一)。"""
    import re
    def _n(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "").strip().lower())
    c, p = _n(clue), _n(passage)
    return bool(c) and c in p


async def question_analysis(db: AsyncSession, *, student_id: uuid.UUID,
                            question_id: uuid.UUID) -> dict | None:
    """完形双轴解析;按题 md5 全局缓存。非本人 → None。"""
    from app.services.llm_provider import complete_json, fast_model, is_llm_dev_mode

    q = await db.get(UserPaperQuestion, question_id)
    if q is None:
        return None
    paper = await db.get(UserUploadedPaper, q.user_paper_id)
    if paper is None or paper.student_id != student_id:
        return None
    q_options = getattr(q, "options", None)
    context = (q.passage or q.stem or "").strip()
    key = (f"{context}||{q.stem or ''}||{_json.dumps(q_options or [], ensure_ascii=False)}"
           f"||{q.correct_answer or ''}||{q.student_answer or ''}")
    q_md5 = hashlib.md5(key.encode("utf-8")).hexdigest()  # noqa: S324
    hit = await db.get(ClozeAnalysisCache, q_md5)
    if hit is not None:
        return hit.analysis

    opts = _json.dumps(q_options, ensure_ascii=False) if q_options else "(无选项·填空)"
    user = (f"【语篇】\n{context[:3500]}\n\n【本题】{q.stem}\n【选项】{opts}\n"
            f"【正确答案】{q.correct_answer or '未知'}\n"
            f"【学生作答】{q.student_answer or '未识别'}")
    if is_llm_dev_mode():
        ana = {
            "clue_type": "跨句逻辑关系",
            "clue": context[:80] if context else "",
            "answer_reason": "(dev)据语境线索得正确项",
            "distractor_why": "(dev)干扰项与语境不符",
            "slot": "动词短语",
        }
    else:
        try:
            ana = await complete_json(
                system_prompt=_CLOZE_ANALYSIS_SYS, user_prompt=user,
                model=fast_model(), disable_thinking=True, max_tokens=2048,
                escalate_ceiling=3072,
                validate=lambda d: bool((d.get("clue_type") or "").strip()),
                feature="cloze_analysis",
            ) or {}
        except Exception:  # noqa: BLE001
            return {"error": "解析暂时不可用,请稍后再试"}

    ct = (ana.get("clue_type") or "").strip()
    if ct not in _CLUE_TYPES:
        ana["clue_type"] = _CLUE_TYPES[2]  # 默认跨句逻辑
        ana["_warnings"] = list(ana.get("_warnings") or []) + ["clue_type 已归一"]
    clue = (ana.get("clue") or "").strip()
    if clue and context and not _clue_in_passage(clue, context):
        ana["_warnings"] = list(ana.get("_warnings") or []) + ["线索句非原文子串"]
    db.add(ClozeAnalysisCache(q_md5=q_md5, analysis=ana))
    await db.commit()
    return ana


async def practice_similar(db: AsyncSession, *, student_id: uuid.UUID,
                           question_id: uuid.UUID, count: int = 5) -> dict | None:
    """本题巩固:按语篇+线索类型出同类单选;全局缓存。"""
    from app.services.llm_provider import complete_json, fast_model, is_llm_dev_mode

    q = await db.get(UserPaperQuestion, question_id)
    if q is None:
        return None
    paper = await db.get(UserUploadedPaper, q.user_paper_id)
    if paper is None or paper.student_id != student_id:
        return None
    passage = (q.passage or q.stem or "").strip()
    if not passage:
        return {"questions": []}
    # 优先用已缓存双轴的线索类型
    ana = await question_analysis(db, student_id=student_id, question_id=question_id) or {}
    clue_type = (ana.get("clue_type") or "跨句逻辑关系").strip()
    cache_md5 = hashlib.md5(
        f"{passage}||{clue_type}||{count}".encode("utf-8")).hexdigest()  # noqa: S324
    hit = await db.get(ClozePracticeCache, cache_md5)
    if hit is not None:
        qs = hit.questions
    else:
        user = f"【线索类型】{clue_type}\n【语篇】\n{passage[:3000]}"
        if is_llm_dev_mode():
            qs = [{"stem": f"(dev) Cloze clue practice {i+1} ______?",
                   "options": ["A. mock1", "B. mock2", "C. mock3", "D. mock4"],
                   "answer": "A. mock1", "explanation": "(dev)据线索类型练习"}
                  for i in range(count)]
        else:
            try:
                data = await complete_json(
                    system_prompt=_CLOZE_PRACTICE_SYS.format(count=count),
                    user_prompt=user,
                    model=fast_model(), disable_thinking=True, max_tokens=3072,
                    escalate_ceiling=4096,
                    validate=lambda d: isinstance(d.get("questions"), list) and len(d["questions"]) > 0,
                    feature="cloze_practice",
                )
            except Exception:  # noqa: BLE001
                return {"questions": [], "error": "出题暂时不可用,请稍后再试"}
            qs = (data or {}).get("questions") or []
            qs = [x for x in qs if isinstance(x, dict) and x.get("stem")
                  and isinstance(x.get("options"), list) and len(x["options"]) >= 2][:count]
            # answer 必须在 options 内
            cleaned = []
            for x in qs:
                opts = [str(o) for o in x["options"]]
                ans = str(x.get("answer") or "")
                if ans not in opts:
                    # 字母答案
                    if len(ans) == 1 and ans.upper() in "ABCD":
                        i = ord(ans.upper()) - 65
                        if 0 <= i < len(opts):
                            x = {**x, "answer": opts[i]}
                        else:
                            continue
                    else:
                        continue
                cleaned.append({**x, "options": opts})
            qs = cleaned
            if qs:
                db.add(ClozePracticeCache(cache_md5=cache_md5, questions=qs))
                await db.commit()
    out = [{"id": str(uuid.uuid5(uuid.NAMESPACE_OID, f"{cache_md5}:{i}")),
            "stem": x.get("stem"), "options": x.get("options"),
            "answer": x.get("answer"), "explanation": x.get("explanation")}
           for i, x in enumerate(qs)]
    return {"questions": out, "clue_type": clue_type}
