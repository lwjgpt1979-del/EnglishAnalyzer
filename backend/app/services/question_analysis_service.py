"""真题「题目层科学解析」service(试点:阅读理解;见 docs/AI整卷匹配-分题型科学解析)。

铁律:**AI 只出建议,人工逐题确认后才写库**(confirm_analysis 是唯一写入口)。
防胡说机制(程序一票否决,不合格建议直接标 invalid,不进人工队列):
- 定位句 evidence 必须是原文(短文;无短文则题干)的子串——空白归一后比对;
- 干扰项错因必须在封闭枚举内;rc_code 必须是图谱既有 rc-* 节点。
解析存 platform_question.meta["analysis"](JSONB,免迁移)。
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import PlatformQuestion, Passage
from app.services.kp_suggest_service import classify_reading_skill
from app.services.llm_provider import chat_completion, is_llm_dev_mode

# 干扰项错因封闭枚举(干扰项理据分析 distractor rationale 的常用分类)
DISTRACTOR_TYPES = ("原文近似词误配", "以偏概全", "过度推断", "无中生有", "张冠李戴", "因果倒置")

_SYSTEM_PROMPT = (
    "你是中小学英语阅读测评专家。对给定的阅读理解小题做「题目层解析」,只返回 JSON:"
    '{"rc_code":"rc-x-x 技能编码","evidence":"答案定位句(必须逐字摘自原文)",'
    '"answer_reason":"由定位句到正确项的推理(1-2句)",'
    '"distractor_types":{"A":"错因",...}}。'
    "错因只能取:" + "、".join(DISTRACTOR_TYPES) + "。正确项不出现在 distractor_types 里。"
)


def _norm(s: str) -> str:
    """空白归一(OCR 换行/多空格不应影响子串比对)。"""
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def validate_reading_analysis(analysis: dict, *, context_text: str) -> list[str]:
    """校验一份阅读题目层解析;返回错误列表(空=通过)。"""
    errs: list[str] = []
    ev = (analysis.get("evidence") or "").strip()
    if not ev:
        errs.append("缺少定位句 evidence")
    elif _norm(ev) not in _norm(context_text):
        errs.append("定位句不是原文子串(疑似幻觉)")
    code = (analysis.get("rc_code") or "").strip()
    if not code.startswith("rc-"):
        errs.append("rc_code 缺失或不合法")
    dts = analysis.get("distractor_types") or {}
    if not isinstance(dts, dict):
        errs.append("distractor_types 须为对象")
    else:
        for k, v in dts.items():
            if str(k).upper() not in {"A", "B", "C", "D"}:
                errs.append(f"干扰项键非法:{k}")
            if v not in DISTRACTOR_TYPES:
                errs.append(f"干扰项错因不在枚举内:{v}")
    if not (analysis.get("answer_reason") or "").strip():
        errs.append("缺少 answer_reason")
    return errs


async def _rc_code_exists(db: AsyncSession, code: str) -> bool:
    return (await db.execute(
        sa.select(KnowledgeNode.id).where(KnowledgeNode.code == code).limit(1)
    )).first() is not None


async def _load_with_context(
    db: AsyncSession, question_ids: list[uuid.UUID]
) -> list[tuple[PlatformQuestion, str]]:
    """加载题目 + 其上下文正文(题组短文;无短文用题干,微题短文内嵌 stem)。"""
    qs = list((await db.execute(
        sa.select(PlatformQuestion).where(PlatformQuestion.id.in_(question_ids))
    )).scalars().all())
    block_ids = {q.block_id for q in qs if q.block_id}
    pmap: dict = {}
    if block_ids:
        pmap = {pid: txt for pid, txt in (await db.execute(
            sa.select(Passage.id, Passage.text).where(Passage.id.in_(block_ids)))).all()}
    out = []
    for q in qs:
        passage = pmap.get(q.block_id) if q.block_id else None
        # 定位句可来自短文或题干(自含微题);校验语境 = 两者拼接
        out.append((q, f"{passage or ''}\n{q.stem or ''}"))
    return out


def _mock_suggestion(q: PlatformQuestion, context: str) -> dict:
    """dev-mock:确定性建议(取语境第一句为定位句),离线可测。"""
    first = re.split(r"(?<=[.!?])\s+", context.strip())[0][:200]
    return {
        "rc_code": classify_reading_skill(q.stem or "") or "rc-1-1",
        "evidence": first,
        "answer_reason": "dev-mock:据第一句可定位答案。",
        "distractor_types": {},
    }


async def _llm_suggestion(q: PlatformQuestion, context: str, rc_catalog: str) -> dict:
    opts = json.dumps(q.options, ensure_ascii=False) if q.options else "(无选项)"
    user = (f"【rc 技能目录】\n{rc_catalog}\n\n【原文】\n{context[:3500]}\n\n"
            f"【题目】{q.stem}\n【选项】{opts}\n【正确答案】{q.answer or '未知'}")
    resp = await chat_completion(system_prompt=_SYSTEM_PROMPT, user_prompt=user,
                                 max_tokens=1024, response_format={"type": "json_object"})
    return json.loads((resp.choices[0].message.content or "{}").strip())


async def suggest_reading_analysis(
    db: AsyncSession, *, question_ids: list[uuid.UUID]
) -> list[dict]:
    """为阅读小题生成「题目层解析」**建议**(不写库)。逐条带校验结果,invalid 的直接标明错误。"""
    pairs = await _load_with_context(db, question_ids)
    rc_catalog = "\n".join(
        f"{c} {n}" for c, n in (await db.execute(
            sa.select(KnowledgeNode.code, KnowledgeNode.name)
            .where(KnowledgeNode.code.like("rc-%")).order_by(KnowledgeNode.code))).all())
    out = []
    for q, context in pairs:
        existing = (q.meta or {}).get("analysis")
        try:
            ana = _mock_suggestion(q, context) if is_llm_dev_mode() \
                else await _llm_suggestion(q, context, rc_catalog)
        except Exception as exc:  # noqa: BLE001 —— 单题失败不拖垮整批
            out.append({"question_id": str(q.id), "analysis": None,
                        "errors": [f"生成失败:{exc}"], "existing": existing})
            continue
        errs = validate_reading_analysis(ana, context_text=context)
        if not errs and not await _rc_code_exists(db, ana.get("rc_code", "")):
            errs = [f"rc_code 不在图谱:{ana.get('rc_code')}"]
        out.append({"question_id": str(q.id), "analysis": ana,
                    "errors": errs, "existing": existing})
    return out


async def confirm_analysis(
    db: AsyncSession, *, question_id: uuid.UUID, analysis: dict, admin_id: uuid.UUID,
) -> dict:
    """人工确认后写库(唯一写入口):服务端重校验 → meta.analysis(带确认者/时间)。"""
    q = (await db.execute(
        sa.select(PlatformQuestion).where(PlatformQuestion.id == question_id)
    )).scalar_one_or_none()
    if q is None:
        raise AppError(code=404, message="题目不存在")
    pairs = await _load_with_context(db, [question_id])
    context = pairs[0][1]
    errs = validate_reading_analysis(analysis, context_text=context)
    if not errs and not await _rc_code_exists(db, analysis.get("rc_code", "")):
        errs = [f"rc_code 不在图谱:{analysis.get('rc_code')}"]
    if errs:
        raise AppError(code=400, message="解析未通过校验:" + ";".join(errs))
    saved = {**analysis,
             "confirmed_by": str(admin_id),
             "confirmed_at": _dt.datetime.now(_dt.timezone.utc).isoformat()}
    q.meta = {**(q.meta or {}), "analysis": saved}
    await db.flush()
    return saved
