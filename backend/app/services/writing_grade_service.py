"""书面表达(写作)AI 5 维评分 service(W2)。

对照「写作解析(要点/范文/目标句型/体裁·主时态)」批改学生作文,产出:
- 内容:逐要点命中 checklist(wr-1,客观锚,漏要点=第一失分源);
- 语言准确:错因逐条标注(wr-2);语言丰富:用了几个目标句型 + 升格建议(wr-3);
- 结构连贯:篇章/连接词(wr-4);+ 整体档(holistic,对齐高考五档)+ 逐句批注。

评分是**形成性反馈**(标注 AI,可教师复核);按 wr-* 各维 log_answer 落 BKT(多维掌握)。
量表满分/权重应读后台配置(system_configs.writing_rubric),本模块常量仅兜底。复用 LLM dev-mock 离线可测。
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.services.llm_provider import complete_json, is_llm_dev_mode

# 五维 → 顶层 wr 维度(BKT 按维记掌握);实际权重/满分见后台配置,此为兜底
_DIM_OF_WR = {"wr-1": "content", "wr-2": "accuracy", "wr-3": "richness", "wr-4": "organization",
              "wr-5": "mechanics", "wr-6": "content"}

# ── 写作评分量表(运营可配置:满分/各维达标线)。system_configs.writing_rubric;此为缺失兜底 ──
_WRITING_RUBRIC_KEY = "writing_rubric"
DEFAULT_WRITING_RUBRIC = {
    "full_score": 20,               # 满分(中考 20;高考可配 25 等)
    "accuracy_pass_ratio": 0.7,     # 语言准确达标线:score/full ≥ 此比例
    "organization_pass_ratio": 0.6, # 结构连贯达标线
    "richness_min_targets": 1,      # 语言丰富达标:至少命中的目标句型数
}


async def get_writing_rubric(db: AsyncSession) -> dict:
    """读 system_configs.writing_rubric(满分/各维达标线)。缺失/缺字段用默认兜底。"""
    from app.models.d9_system import SystemConfig
    cfg = (await db.execute(
        sa.select(SystemConfig).where(SystemConfig.key == _WRITING_RUBRIC_KEY))).scalar_one_or_none()
    data = (cfg.value if isinstance(cfg.value, dict) else {}) if cfg else {}
    return {**DEFAULT_WRITING_RUBRIC, **data}


async def update_writing_rubric(db: AsyncSession, *, rubric: dict, updated_by) -> dict:
    """运营改写作评分量表:upsert system_configs.writing_rubric。只接受已知字段,数值兜底。"""
    import uuid as _uuid
    from app.models.d9_system import SystemConfig
    merged = {**DEFAULT_WRITING_RUBRIC}
    if isinstance(rubric.get("full_score"), (int, float)):
        merged["full_score"] = max(1, int(rubric["full_score"]))
    for k in ("accuracy_pass_ratio", "organization_pass_ratio"):
        if isinstance(rubric.get(k), (int, float)):
            merged[k] = min(1.0, max(0.0, float(rubric[k])))
    if isinstance(rubric.get("richness_min_targets"), (int, float)):
        merged["richness_min_targets"] = max(0, int(rubric["richness_min_targets"]))
    cfg = (await db.execute(
        sa.select(SystemConfig).where(SystemConfig.key == _WRITING_RUBRIC_KEY))).scalar_one_or_none()
    if cfg is None:
        db.add(SystemConfig(id=_uuid.uuid4(), key=_WRITING_RUBRIC_KEY, value=merged,
                            description="书面表达评分量表(满分/各维达标线)", updated_by=updated_by))
    else:
        cfg.value = merged
        cfg.updated_by = updated_by
    await db.flush()
    return merged

_SYSTEM_PROMPT = (
    "你是中小学英语书面表达阅卷老师兼写作教练。对照【写作解析】(要点/范文/目标句型/体裁·主时态)批改学生作文,"
    "宽松合理、面向提分。只返回 JSON,键:\n"
    "points(list of {id,point,hit,comment} 逐个要点是否命中——意思到位即命中,不苛求字面)、\n"
    "content_score(int)、content_full(int)、\n"
    "accuracy(dict:{score,full,errors:[{span,type,fix}] 语法/拼写/时态错因逐条})、\n"
    "richness(dict:{score,full,used_targets:[命中的目标句型],suggestions:[升格建议:把学生某句升格为高级句型]})、\n"
    "organization(dict:{score,full,comment 篇章结构/连接词})、\n"
    "band(str 整体档:A优/B良/C中/D待提高)、total(int)、full(int)、\n"
    "inline_comments(list of {sentence,comment} 逐句批注,只批需改的句)、feedback(str 总评+下一步)。"
)


def _empty(full: int) -> dict:
    return {"points": [], "content_score": 0, "content_full": full, "accuracy": {"score": 0, "full": full, "errors": []},
            "richness": {"score": 0, "full": full, "used_targets": [], "suggestions": []},
            "organization": {"score": 0, "full": full, "comment": ""}, "band": "D",
            "total": 0, "full": full, "inline_comments": [], "feedback": "未作答,请写完后再提交。"}


def _mock(*, analysis: dict, student_essay: str, full: int) -> dict:
    """dev-mock:要点关键词命中率 + 目标句型命中,确定性,离线可测。"""
    essay = (student_essay or "").lower()
    pts = analysis.get("points") or []
    graded = []
    hit_n = 0
    for i, p in enumerate(pts):
        txt = (p.get("point") if isinstance(p, dict) else str(p)) or ""
        hit = len(essay) >= 20 and (i % 2 == 0)      # 确定性:偶数要点判命中
        hit_n += 1 if hit else 0
        graded.append({"id": (p.get("id") if isinstance(p, dict) else i + 1), "point": txt,
                       "hit": hit, "comment": "dev-mock 判定"})
    used = [t for t in (analysis.get("target_expressions") or []) if t and t.lower() in essay]
    cf = max(1, len(pts))
    return {"points": graded, "content_score": hit_n, "content_full": cf,
            "accuracy": {"score": full - 2, "full": full, "errors": []},
            "richness": {"score": len(used), "full": max(1, len(analysis.get("target_expressions") or [])),
                         "used_targets": used, "suggestions": ["dev-mock:可用 Only by … can we … 升格"]},
            "organization": {"score": 3, "full": 4, "comment": "dev-mock:结构基本清晰"},
            "band": "B" if hit_n >= max(1, len(pts) // 2) else "C",
            "total": full - 2, "full": full,
            "inline_comments": [], "feedback": "[dev-mock] 要点覆盖尚可;注意时态与升级句型。"}


async def grade_writing(*, analysis: dict, student_essay: str, prompt: str = "", full_score: int = 20) -> dict:
    """批改一篇作文:对照写作解析,返回 5 维分 + 整体档 + 逐句批注 + 升格建议。"""
    essay = (student_essay or "").strip()
    if not essay:
        return _empty(full_score)
    if is_llm_dev_mode():
        return _mock(analysis=analysis, student_essay=essay, full=full_score)
    import json
    pts = analysis.get("points") or []
    ana_brief = {
        "genre": analysis.get("genre"), "main_tense": analysis.get("main_tense"),
        "points": [{"id": (p.get("id") if isinstance(p, dict) else i + 1),
                    "point": (p.get("point") if isinstance(p, dict) else str(p))} for i, p in enumerate(pts)],
        "target_expressions": analysis.get("target_expressions") or [],
        "model_essay": analysis.get("model_essay") or "",
    }
    user = (f"【题目】{prompt}\n\n【写作解析(评分依据)】\n{json.dumps(ana_brief, ensure_ascii=False)}\n\n"
            f"【学生作文】\n{essay}\n\n满分:{full_score}")
    # 5 维诊断(要点+错因+升格+逐句批注+总评)输出较大,上限给足避免截断→502
    data = await complete_json(
        system_prompt=_SYSTEM_PROMPT, user_prompt=user, max_tokens=3200, escalate_ceiling=6000,
        validate=lambda d: isinstance(d.get("points"), list), feature="writing_grade")
    if data is None:
        raise AppError(code=502, message="AI 写作批改失败(截断/抖动重试后仍失败),请重试")
    data.setdefault("full", full_score)
    return data


def _dim_passes(result: dict, rubric: dict | None = None) -> dict:
    """5 维各自是否达标 → 供 BKT 多维掌握信号(维度独立,一维弱不否决另一维)。达标线读量表。"""
    r = {**DEFAULT_WRITING_RUBRIC, **(rubric or {})}
    pts = result.get("points") or []
    content = bool(pts) and all(p.get("hit") for p in pts)        # 要点全覆盖(客观锚,不设配置)
    acc = result.get("accuracy") or {}
    accuracy = float(acc.get("score", 0)) >= float(acc.get("full", 1)) * r["accuracy_pass_ratio"]
    rich = result.get("richness") or {}
    richness = len(rich.get("used_targets") or []) >= r["richness_min_targets"]
    org = result.get("organization") or {}
    organization = float(org.get("score", 0)) >= float(org.get("full", 1)) * r["organization_pass_ratio"]
    return {"content": content, "accuracy": accuracy, "richness": richness,
            "organization": organization, "mechanics": accuracy}


async def grade_platform_writing_question(
    db: AsyncSession, *, student_id: uuid.UUID, question_id: uuid.UUID,
    student_essay: str, full_score: int | None = None,
) -> dict:
    """批改平台书面表达题并落 BKT:解析(要点/范文)由服务端从题 meta 取(不下发前端 → 防作弊)。

    按题目挂的 wr-* 节点、以「该节点所属维度是否达标」为 is_correct,逐维 log_answer(多维掌握)。
    题未挂 KP 时,退化为按解析里的 wr_codes 解析节点记。
    """
    from app.models.d15_knowledge_graph import KnowledgeNode
    from app.models.d16_question_domain import PlatformQuestion, PlatformQuestionKp
    from app.services import mastery_judge_service

    q = (await db.execute(
        sa.select(PlatformQuestion).where(PlatformQuestion.id == question_id)
    )).scalar_one_or_none()
    if q is None:
        raise AppError(code=404, message="题目不存在")
    analysis = (q.meta or {}).get("analysis") or {}
    if not analysis.get("points"):
        raise AppError(code=400, message="该题尚无写作解析(要点/范文),请先在后台完成解析确认")

    rubric = await get_writing_rubric(db)          # 满分/达标线读后台配置(铁律:运营可配置不写死)
    result = await grade_writing(
        analysis=analysis, student_essay=student_essay, prompt=q.stem or "",
        full_score=full_score or rubric["full_score"])
    passes = _dim_passes(result, rubric)

    # 题挂的 wr-* 节点(code→维度);没有则用解析 wr_codes 解析
    rows = (await db.execute(
        sa.select(PlatformQuestionKp.node_id, KnowledgeNode.code)
        .join(KnowledgeNode, KnowledgeNode.id == PlatformQuestionKp.node_id)
        .where(PlatformQuestionKp.question_id == question_id))).all()
    if not rows and analysis.get("wr_codes"):
        rows = (await db.execute(
            sa.select(KnowledgeNode.id, KnowledgeNode.code)
            .where(KnowledgeNode.code.in_(analysis["wr_codes"])))).all()

    logged = 0
    for node_id, code in rows:
        dim = _DIM_OF_WR.get((code or "")[:4], "content")       # wr-1-2 → wr-1 → content
        await mastery_judge_service.log_answer(
            db, student_id=student_id, q_scope="platform", question_id=question_id,
            node_id=node_id, is_correct=bool(passes.get(dim, False)), feature="writing")
        logged += 1
    if not logged:      # 无任何可挂节点 → 记一条总体(内容维)信号
        await mastery_judge_service.log_answer(
            db, student_id=student_id, q_scope="platform", question_id=question_id,
            node_id=None, is_correct=passes["content"], feature="writing")

    result["dim_passes"] = passes
    result["is_ai_graded"] = True       # 形成性:前端标注「AI 评分」,可教师复核
    result["model_essay"] = analysis.get("model_essay") or ""   # 批改后才给范文(S4 对照,已提交无作弊风险)
    result["point_map"] = analysis.get("point_map") or {}       # 要点↔范文句映射
    result["target_expressions"] = analysis.get("target_expressions") or []
    return result


async def list_writing_practice_questions(
    db: AsyncSession, *, limit: int = 10, node_id: uuid.UUID | None = None,
) -> list[dict]:
    """列可练的书面表达题(真题/仿真,已有解析)。**下发要点+结构套路(S1 脚手架),不下发范文**(防抄)。

    返回 [{id, stem, genre, strategy, points, structure, full_score}]。
    """
    from app.models.d16_question_domain import PlatformQuestion, PlatformQuestionKp

    stmt = (
        sa.select(PlatformQuestion.id, PlatformQuestion.stem, PlatformQuestion.meta)
        .where(PlatformQuestion.question_type == "写作",
               PlatformQuestion.status == "published",
               PlatformQuestion.deprecated_at.is_(None),
               PlatformQuestion.meta["analysis"].isnot(None))
    )
    if node_id is not None:
        stmt = stmt.join(
            PlatformQuestionKp, PlatformQuestionKp.question_id == PlatformQuestion.id
        ).where(PlatformQuestionKp.node_id == node_id)
    rows = (await db.execute(
        stmt.order_by(PlatformQuestion.created_at.desc()).limit(limit))).all()
    full_score = (await get_writing_rubric(db))["full_score"]      # 满分读后台配置
    out = []
    for r in rows:
        a = (r.meta or {}).get("analysis") or {}
        out.append({
            "id": str(r.id), "stem": r.stem, "genre": a.get("genre"),
            "main_tense": a.get("main_tense"), "strategy": a.get("strategy"),
            "points_count": len(a.get("points") or []),      # 审题小测:要点条数(前置门,先不给要点文本)
            "points": [{"id": (p.get("id") if isinstance(p, dict) else i + 1),
                        "point": (p.get("point") if isinstance(p, dict) else str(p))}
                       for i, p in enumerate(a.get("points") or [])],
            "structure": a.get("structure") or [],       # S1 搭框架脚手架
            "full_score": full_score,
        })
    return out
