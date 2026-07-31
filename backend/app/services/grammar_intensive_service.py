"""语法精讲(作业精讲/课程精讲 的「语法精讲」模块)取数。

- 作业:学生「加入待学习」的语法点(student_kp_target,带 source_paper_id)→ 按【卷=批次】归组;
- 课程:本单元已挂靠的 grammar section(含 cf/jf/m-*)→ 按【年级→册→单元】归组;
  清单主名优先用挂靠点 point_name(与后台一致),缺则回退图谱 display_label;未挂不进清单;
- 作业 D1:目标可挂 source_question_id,points 带回原题 stem/作答/解析,按原题切点学习。
"""
from __future__ import annotations

import uuid

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d1_users import User
from app.models.d4_knowledge import CurriculumUnit
from app.models.d13_v2_user_papers import UserPaperQuestion, UserUploadedPaper
from app.models.d15_knowledge_graph import KnowledgeNode
from app.services.kp_title_rewrite_service import display_label
from app.models.d17_curriculum_kg import UnitNode
from app.models.d26_kp_target import StudentKpTarget

_GRAMMAR = (KnowledgeNode.code.ilike("cf%")) | (KnowledgeNode.code.ilike("jf%"))


def _pt(nid, name, code) -> dict:
    return {"node_id": str(nid), "name": name, "code": code, "personal": False}


def _mastery(has_row, recog, det, prod, transfer) -> dict | None:
    """四维掌握度(识别/纠错/产出 各 0–1 + 迁移布尔);无 student_grammar_mastery 行(未学)返回 None。"""
    if not has_row:
        return None
    return {"recognize": float(recog or 0), "detect": float(det or 0),
            "produce": float(prod or 0), "transfer": bool(transfer)}


async def _q_payload(db: AsyncSession, q: UserPaperQuestion | None,
                     *, student_id: uuid.UUID) -> dict | None:
    """原题摘要字段(D1 合一页:题干/作答/解析 + 错题关系网 id)。"""
    if q is None:
        return None
    opts = q.options if isinstance(q.options, list) else None
    qtype = getattr(q, "question_type", None)
    qtype_s = str(qtype) if qtype else None
    # 挂错题关系网:同生 uploaded 题 → wrong_record
    wr_id = None
    if q.is_wrong:
        from app.models.d16_question_domain import WrongRecord
        wr_id = (await db.execute(
            select(WrongRecord.id).where(
                WrongRecord.student_id == student_id,
                WrongRecord.q_scope == "uploaded",
                WrongRecord.question_id == q.id).limit(1))).scalar_one_or_none()
    return {
        "id": str(q.id),
        "question_no": q.question_no,
        "stem": q.stem,
        "options": opts,
        "question_type": qtype_s,
        "student_answer": q.student_answer,
        "correct_answer": q.correct_answer,
        "explanation": q.explanation,
        "is_wrong": bool(q.is_wrong),
        "wrong_record_id": str(wr_id) if wr_id else None,
    }


# ── 作业精讲 · 语法:按卷(批次)──────────────────────────────────────────────
async def homework_batches(db: AsyncSession, *, student_id: uuid.UUID) -> list[dict]:
    """学生作业里的语法点,按来源卷(批次)归组。年月日倒序。
    含两类:①匹配上图谱的语法(student_kp_target,cf/jf);②没匹配上的个人语法(挂个人树)。
    count/studied 按「目标行」计(有来源题则一题一行,对齐 D1 切点)。"""
    from app.models.d27_student_grammar import StudentGrammarNode
    from app.models.d4_knowledge import StudentGrammarMastery
    kp = (await db.execute(
        select(StudentKpTarget.source_paper_id, func.count(StudentKpTarget.id),
               # 已学过的目标行(该生该点有 student_grammar_mastery 行)= studied
               func.count(case(
                   (StudentGrammarMastery.id.isnot(None), StudentKpTarget.id))),
               UserUploadedPaper.title, UserUploadedPaper.created_at)
        .join(KnowledgeNode, KnowledgeNode.id == StudentKpTarget.node_id)
        .join(UserUploadedPaper, UserUploadedPaper.id == StudentKpTarget.source_paper_id)
        .outerjoin(StudentGrammarMastery,
                   (StudentGrammarMastery.kp_id == StudentKpTarget.node_id)
                   & (StudentGrammarMastery.student_id == student_id))
        .where(StudentKpTarget.student_id == student_id,
               StudentKpTarget.source_paper_id.isnot(None), _GRAMMAR)
        .group_by(StudentKpTarget.source_paper_id, UserUploadedPaper.title, UserUploadedPaper.created_at))).all()
    pers = (await db.execute(
        select(StudentGrammarNode.source_paper_id, func.count(StudentGrammarNode.id),
               func.count(StudentGrammarNode.studied_at),   # 已练(studied_at 非空)= 已学
               UserUploadedPaper.title, UserUploadedPaper.created_at)
        .join(UserUploadedPaper, UserUploadedPaper.id == StudentGrammarNode.source_paper_id)
        .where(StudentGrammarNode.student_id == student_id,
               StudentGrammarNode.source_paper_id.isnot(None),
               StudentGrammarNode.ref_node_id.is_(None))   # 未匹配图谱的个人语法
        .group_by(StudentGrammarNode.source_paper_id, UserUploadedPaper.title, UserUploadedPaper.created_at))).all()
    merged: dict = {}
    for pid, cnt, studied, title, ca in kp:
        m = merged.setdefault(pid, {"title": title, "ca": ca, "count": 0, "studied": 0})
        m["count"] += int(cnt); m["studied"] += int(studied)
    for pid, cnt, studied, title, ca in pers:   # 个人语法:练过(studied_at)才计已学
        m = merged.setdefault(pid, {"title": title, "ca": ca, "count": 0, "studied": 0})
        m["count"] += int(cnt); m["studied"] += int(studied)
    out = [{"paper_id": str(pid), "title": m["title"] or "未命名作业",
            "date": m["ca"].strftime("%Y-%m-%d") if m["ca"] else "",
            "count": m["count"], "studied": m["studied"]}
           for pid, m in merged.items()]
    out.sort(key=lambda x: x["date"], reverse=True)
    return out


async def homework_points(db: AsyncSession, *, student_id: uuid.UUID,
                          paper_id: uuid.UUID) -> list[dict]:
    """某批次(卷)里的语法学习项:匹配图谱的 + 个人语法。
    有 source_question_id 的带回原题字段;旧目标无题 id 时按本卷同 node/kp 题回填展开。"""
    from app.models.d27_student_grammar import StudentGrammarNode
    from app.models.d4_knowledge import StudentGrammarMastery

    # 本卷全部小题,供挂题 / 存量回填
    qrows = (await db.execute(
        select(UserPaperQuestion).where(UserPaperQuestion.user_paper_id == paper_id)
        .order_by(UserPaperQuestion.sort_order, UserPaperQuestion.created_at))).scalars().all()
    q_by_id = {q.id: q for q in qrows}
    qs_by_node: dict[uuid.UUID, list] = {}
    qs_by_kp: dict[str, list] = {}
    for q in qrows:
        if q.node_id:
            qs_by_node.setdefault(q.node_id, []).append(q)
        if q.kp_key:
            qs_by_kp.setdefault((q.kp_key or "").strip().lower(), []).append(q)

    rows = (await db.execute(
        select(StudentKpTarget.id, StudentKpTarget.source_question_id,
               KnowledgeNode.id, KnowledgeNode.name, KnowledgeNode.code,
               KnowledgeNode.description,
               StudentGrammarMastery.id.isnot(None),
               StudentGrammarMastery.mastery_recognize, StudentGrammarMastery.mastery_detect,
               StudentGrammarMastery.mastery_produce, StudentGrammarMastery.transfer_ok)
        .join(KnowledgeNode, KnowledgeNode.id == StudentKpTarget.node_id)
        .outerjoin(StudentGrammarMastery,
                   (StudentGrammarMastery.kp_id == KnowledgeNode.id)
                   & (StudentGrammarMastery.student_id == student_id))
        .where(StudentKpTarget.student_id == student_id,
               StudentKpTarget.source_paper_id == paper_id, _GRAMMAR)
        .order_by(KnowledgeNode.code, StudentKpTarget.created_at))).all()

    out: list[dict] = []
    seen_q: set[str] = set()  # 避免存量回填与显式挂题重复

    async def _emit_kp(nid, name, desc, code, st, recog, det, prod, tr, q: UserPaperQuestion | None):
        if q:
            key = f"n:{nid}:{q.id}"
            if key in seen_q:
                return
            seen_q.add(key)
        out.append({**_pt(nid, display_label(name, desc), code), "studied": bool(st),
                    "mastery": _mastery(st, recog, det, prod, tr),
                    "source_question_id": str(q.id) if q else None,
                    "question": await _q_payload(db, q, student_id=student_id)})

    for _tid, sqid, nid, name, code, desc, st, recog, det, prod, tr in rows:
        if sqid and sqid in q_by_id:
            await _emit_kp(nid, name, desc, code, st, recog, det, prod, tr, q_by_id[sqid])
        elif sqid is None:
            matched = qs_by_node.get(nid) or []
            if matched:
                for q in matched:
                    await _emit_kp(nid, name, desc, code, st, recog, det, prod, tr, q)
            else:
                await _emit_kp(nid, name, desc, code, st, recog, det, prod, tr, None)
        else:
            await _emit_kp(nid, name, desc, code, st, recog, det, prod, tr, None)

    pers = (await db.execute(
        select(StudentGrammarNode.id, StudentGrammarNode.name,
               StudentGrammarNode.source_question_id,
               StudentGrammarNode.studied_at, StudentGrammarNode.last_correct,
               StudentGrammarNode.last_total)
        .where(StudentGrammarNode.student_id == student_id,
               StudentGrammarNode.source_paper_id == paper_id,
               StudentGrammarNode.ref_node_id.is_(None))
        .order_by(StudentGrammarNode.name, StudentGrammarNode.created_at))).all()

    async def _emit_pers(sgn_id, pname, st_at, lc, lt, q: UserPaperQuestion | None):
        if q:
            key = f"p:{pname.lower()}:{q.id}"
            if key in seen_q:
                return
            seen_q.add(key)
        out.append({"node_id": None, "name": pname, "code": None, "personal": True,
                    "sgn_id": str(sgn_id), "studied": st_at is not None, "mastery": None,
                    "practice": ({"correct": int(lc or 0), "total": int(lt or 0)}
                                 if st_at is not None else None),
                    "source_question_id": str(q.id) if q else None,
                    "question": await _q_payload(db, q, student_id=student_id)})

    for sgn_id, pname, sqid, st_at, lc, lt in pers:
        if sqid and sqid in q_by_id:
            await _emit_pers(sgn_id, pname, st_at, lc, lt, q_by_id[sqid])
        elif sqid is None:
            matched = qs_by_kp.get((pname or "").strip().lower()) or []
            if matched:
                for q in matched:
                    await _emit_pers(sgn_id, pname, st_at, lc, lt, q)
            else:
                await _emit_pers(sgn_id, pname, st_at, lc, lt, None)
        else:
            await _emit_pers(sgn_id, pname, st_at, lc, lt, None)

    # 有原题的排前(按题号),无原题的 KP 殿后
    def _sort_key(it: dict):
        q = it.get("question") or {}
        no = str(q.get("question_no") or "")
        return (0 if q else 1, no, it.get("name") or "")
    out.sort(key=_sort_key)
    return out


# ── 课程精讲 · 语法:按教材单元 ────────────────────────────────────────────────
async def course_units(db: AsyncSession, *, student_id: uuid.UUID,
                       grade: str | None = None, semester: str | None = None) -> dict:
    """学生当前教材某学期的单元(默认聚焦 preferred 当前学期)+ 每单元语法点数/已学数,
    含闯关顺序解锁 + 本学期通关 + 下学期。

    点数口径(D1):本单元 grammar 已挂靠节点(含 m-*),与 course_points 一致。
    """
    from app.models.d4_knowledge import StudentGrammarMastery
    from app.models.d22_unit_structured import UnitSection
    from app.services.course_intensive_util import decorate_units, next_semester, resolve_semester
    student = await db.get(User, student_id)
    tv = student.preferred_textbook_version if student else None
    if not tv:
        return {"version": None, "grade": None, "semester": None, "units": [],
                "semester_done": False, "next_semester": None}
    g, s = await resolve_semester(db, tv, student, grade, semester)
    rows = (await db.execute(
        select(CurriculumUnit.id, CurriculumUnit.grade, CurriculumUnit.semester,
               CurriculumUnit.unit_no, CurriculumUnit.unit_title,
               func.count(func.distinct(UnitSection.node_id)),
               func.count(func.distinct(case(
                   (StudentGrammarMastery.id.isnot(None), UnitSection.node_id)))))
        .join(UnitSection, (UnitSection.unit_id == CurriculumUnit.id)
              & (UnitSection.kind == "grammar")
              & (UnitSection.node_id.isnot(None)))
        .outerjoin(StudentGrammarMastery,
                   (StudentGrammarMastery.kp_id == UnitSection.node_id)
                   & (StudentGrammarMastery.student_id == student_id))
        .where(CurriculumUnit.textbook_version == tv,
               CurriculumUnit.grade == g, CurriculumUnit.semester == s)
        .group_by(CurriculumUnit.id, CurriculumUnit.grade, CurriculumUnit.semester,
                  CurriculumUnit.unit_no, CurriculumUnit.unit_title)
        .order_by(CurriculumUnit.unit_no))).all()
    units = [{"unit_id": str(uid), "grade": gr, "semester": sem, "unit_no": uno,
              "unit_title": title or f"Unit {uno}", "count": int(cnt),
              "total": int(cnt), "studied": int(st)}
             for uid, gr, sem, uno, title, cnt, st in rows]
    done = decorate_units(units)
    return {"version": tv, "grade": g, "semester": s, "units": units,
            "semester_done": done,
            "next_semester": await next_semester(db, tv, g, s) if done else None}


def _facet_total_from_json(facets: object) -> int:
    """挂靠点细目条数;无细目名时返回 0。"""
    if not isinstance(facets, list):
        return 0
    return sum(
        1 for f in facets
        if isinstance(f, dict) and (f.get("name") or "").strip()
    )


async def course_points(db: AsyncSession, *, unit_id: uuid.UUID,
                        student_id: uuid.UUID | None = None) -> list[dict]:
    """某教材单元的语法点;传 student_id 则按细目闯关过关计 studied(方案 A,不用四维)。

    D1:数据源=本单元已挂靠的 grammar section(含 m-*,不限 cf/jf);未挂不进清单。
    主名=point_name;同节点多挂靠点取 sort_order 最小者;缺名回退图谱 display_label。
    """
    from app.models.d22_unit_structured import UnitSection

    sec_rows = (await db.execute(
        select(
            UnitSection.node_id, UnitSection.point_name, UnitSection.sort_order,
            UnitSection.facets,
            KnowledgeNode.name, KnowledgeNode.code, KnowledgeNode.description,
        )
        .join(KnowledgeNode, KnowledgeNode.id == UnitSection.node_id)
        .where(
            UnitSection.unit_id == unit_id,
            UnitSection.kind == "grammar",
            UnitSection.node_id.isnot(None),
        )
        .order_by(UnitSection.sort_order, UnitSection.point_name)
    )).all()
    # node 去重:保留首次出现(最小 sort_order)的挂靠点名与节点信息
    ordered: list[tuple] = []
    seen: set[uuid.UUID] = set()
    point_name_by_node: dict[uuid.UUID, str] = {}
    facet_total_by_node: dict[uuid.UUID, int] = {}
    for nid, pname, _ord, facets, kn_name, code, desc in sec_rows:
        if nid is None or nid in seen:
            continue
        seen.add(nid)
        nm = (pname or "").strip()
        if nm:
            point_name_by_node[nid] = nm
        facet_total_by_node[nid] = _facet_total_from_json(facets)
        ordered.append((nid, kn_name, code, desc))

    pass_map: dict[str, int] = {}
    if student_id is not None and ordered:
        from app.models.d28_grammar_facet_quest import StudentGrammarFacetPass
        prows = (await db.execute(
            select(
                StudentGrammarFacetPass.node_id,
                func.count(StudentGrammarFacetPass.id),
            ).where(
                StudentGrammarFacetPass.student_id == student_id,
                StudentGrammarFacetPass.unit_id == unit_id,
                StudentGrammarFacetPass.node_id.in_([r[0] for r in ordered]),
            ).group_by(StudentGrammarFacetPass.node_id)
        )).all()
        pass_map = {str(nid): int(c) for nid, c in prows}

    out = []
    for nid, name, code, desc in ordered:
        label = point_name_by_node.get(nid) or display_label(name, desc)
        total = facet_total_by_node.get(nid, 0)
        passed = pass_map.get(str(nid), 0)
        if total > 0:
            passed = min(passed, total)
        all_done = total > 0 and passed >= total
        out.append({
            **_pt(nid, label, code),
            "studied": all_done,
            "facet_passed": passed,
            "facet_total": total,
            # 课程清单不再展示四维;字段保留兼容旧前端
            "mastery": None,
        })
    return out


# ── 自建语法「练一练」痕迹:标记已学 + 最近成绩(无图谱 node、无四维,用此反馈)──────────
async def mark_personal_practiced(db: AsyncSession, *, student_id: uuid.UUID,
                                  sgn_id: uuid.UUID, correct: int, total: int) -> dict:
    """自建语法练一练做完 → 该个人节点置 studied_at(已学)+ 记最近一轮 correct/total。"""
    import datetime as _dt
    from app.core.exceptions import AppError
    from app.models.d27_student_grammar import StudentGrammarNode
    node = await db.get(StudentGrammarNode, sgn_id)
    if node is None or node.student_id != student_id:
        raise AppError(code=404, message="个人语法不存在")
    node.studied_at = _dt.datetime.now(_dt.timezone.utc)
    node.last_correct = int(max(0, correct))
    node.last_total = int(max(0, total))
    await db.flush()
    return {"studied": True, "correct": node.last_correct, "total": node.last_total}


# ── 原题单段解析:查看即生成(正确/错误同等)────────────────────────────────────
def _explain_md5(q: UserPaperQuestion) -> str:
    """题面指纹:题干+选项+正确+学生答案 → 同内容全局复用。"""
    import hashlib
    import json
    opts = q.options if isinstance(q.options, list) else []
    raw = "|".join([
        (q.stem or "").strip(),
        json.dumps(opts, ensure_ascii=False, separators=(",", ":")),
        (q.correct_answer or "").strip(),
        (q.student_answer or "").strip(),
        "1" if q.is_wrong else "0",
    ])
    return hashlib.md5(raw.encode("utf-8")).hexdigest()  # noqa: S324


async def ensure_question_explanation(
    db: AsyncSession, *, student_id: uuid.UUID, question_id: uuid.UUID,
    kp_name: str | None = None,
) -> dict:
    """语法精讲原题解析兜底:已有 explanation 直接返回;否则查全局缓存 → 未命中则 LLM 生成,
    立刻写回 user_paper_questions.explanation + paper_q_explain_cache。正确/错误同等。"""
    from app.core.exceptions import AppError
    from app.models.d13_v2_user_papers import PaperQExplainCache, UserUploadedPaper
    from app.services.llm_provider import complete_json, fast_model, is_llm_dev_mode

    q = await db.get(UserPaperQuestion, question_id)
    if q is None:
        raise AppError(code=404, message="题目不存在")
    paper = await db.get(UserUploadedPaper, q.user_paper_id)
    if paper is None or paper.student_id != student_id:
        raise AppError(code=403, message="无权访问该题")

    existed = (q.explanation or "").strip()
    if existed:
        return {"explanation": existed, "cached": True}

    md5 = _explain_md5(q)
    hit = await db.get(PaperQExplainCache, md5)
    if hit and (hit.explanation or "").strip():
        q.explanation = hit.explanation.strip()
        await db.commit()
        return {"explanation": q.explanation, "cached": True}

    opts = q.options if isinstance(q.options, list) else []
    opt_txt = "\n".join(f"- {o}" for o in opts) if opts else "(无选项·填空/主观)"
    kp = (kp_name or q.kp_key or "").strip() or "本题语法点"
    system = (
        "你是中小学英语语法老师。根据题干、正确答案与学生作答,写一段中文解析(2–5 句)。"
        "无论学生对错都要写解析——全对也要讲清「为什么对」。"
        "规则:\n"
        "1) 填空/多空:按空位说明正确答案(变形/词性/比较级等)为何成立;"
        "若学生答错,再点明错因。\n"
        "2) 单选/多选:说明正确选项为何对;"
        "若学生答错,顺带一句错选项错因;全对则不必展开全部干扰项。\n"
        "一律中文;不要英文解析;不要 markdown。"
        '严格输出 JSON:{"explanation":"……"}'
    )
    user = (
        f"语法点:{kp}\n题干:{q.stem or ''}\n选项:\n{opt_txt}\n"
        f"正确答案:{q.correct_answer or ''}\n学生作答:{q.student_answer or ''}\n"
        f"是否答错:{'是' if q.is_wrong else '否(全对,仍需解析为何正确)'}\n返回 JSON:"
    )
    if is_llm_dev_mode():
        ca = q.correct_answer or "—"
        text = (
            f"(dev)「{kp}」全对解析:正确答案是 {ca}。"
            if not q.is_wrong else
            f"(dev)「{kp}」:正确答案 {ca},学生 {q.student_answer or '—'} 有误。"
        )
    else:
        d = await complete_json(
            system_prompt=system, user_prompt=user, max_tokens=500,
            model=fast_model(), feature="paper_q_explain",
            validate=lambda x: isinstance((x or {}).get("explanation"), str)
            and bool(str((x or {}).get("explanation") or "").strip()),
        ) or {}
        text = str(d.get("explanation") or "").strip()
    if not text:
        raise AppError(code=502, message="解析生成失败,请稍后重试")

    q.explanation = text
    if hit is None:
        db.add(PaperQExplainCache(content_md5=md5, explanation=text))
    else:
        hit.explanation = text
    await db.commit()
    return {"explanation": text, "cached": False}
