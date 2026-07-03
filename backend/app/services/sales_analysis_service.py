"""电销 CRM 意向分析(P1):通话/会话转写 → LLM → 意向分析 schema → 回填。

打分结构复刻 Gong(会话信号 + 行为信号)与循环智能质检维度(见 docs/电销CRM-方案设计.md §4)。
电话与企微(P2)共用本分析入口(纯文本进);ASR/呼叫中心签约前:直接传 transcript 也能跑,
未配 LLM(dev-mock)时走关键词启发式,保证管道可测。
"""
from __future__ import annotations

import logging
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d23_sales_crm import SalesLead, SalesLeadActivity
from app.services import sales_crm_service as crm
from app.services.llm_provider import complete_json, fast_model, is_llm_dev_mode

_log = logging.getLogger(__name__)

_SYS = (
    "你是资深电销会话分析师。给你一段销售与商家/机构客户的通话或微信会话转写,"
    "判断客户的成交意向并抽取产品意见。严格输出 JSON,字段:\n"
    "intent_score(0-100 整数,越高越可能成交,综合客户是否问价/问合作细节/态度积极等信号),\n"
    "signals:{asked_price(bool 客户是否主动问价),asked_next_step(bool 是否问合作/下一步),"
    "competitor_mentioned(string[] 提及的竞品/其他机构),objections(string[] 异议),"
    "red_flags(string[] 明确拒绝/已有供应商等负面信号)},\n"
    "product_feedback(string[] 客户对产品的具体意见/需求),\n"
    "summary(一句话通话摘要),next_action(建议的下一步),\n"
    "compliance:{violations(string[] 座席违规话术,如保过/包提分等夸大承诺,无则空数组)}。\n"
    "只输出 JSON,不要多余文字。"
)

_EMPTY = {
    "intent_score": 0,
    "signals": {"asked_price": False, "asked_next_step": False,
                "competitor_mentioned": [], "objections": [], "red_flags": []},
    "product_feedback": [], "summary": "", "next_action": "",
    "compliance": {"violations": []},
}


def _mock_analyze(text: str) -> dict:
    """dev-mock:关键词启发式,保证无 LLM 也能跑通管道(仅供开发/自测)。"""
    t = text or ""
    asked_price = any(k in t for k in ("价", "多少钱", "费用", "报价", "price"))
    asked_next = any(k in t for k in ("合作", "怎么", "下一步", "签", "试用"))
    objections = [o for o, k in (("价格高", "贵"), ("要再考虑", "考虑"),
                                 ("要开会讨论", "讨论")) if k in t]
    red = [r for r, k in (("已有供应商", "已经有"), ("明确拒绝", "不需要")) if k in t]
    fb = [seg.strip() for kw in ("希望", "想要", "能不能", "支持")
          for seg in t.split("。") if kw in seg][:5]
    score = min(100, 30 + 30 * asked_price + 25 * asked_next
                - 15 * len(red) - 5 * len(objections))
    score = max(0, score)
    return {
        "intent_score": int(score),
        "signals": {"asked_price": asked_price, "asked_next_step": asked_next,
                    "competitor_mentioned": [], "objections": objections, "red_flags": red},
        "product_feedback": fb,
        "summary": (t[:40] + "…") if len(t) > 40 else t,
        "next_action": "3 天内跟进" if score >= 50 else "转培育",
        "compliance": {"violations": []},
    }


def _valid(d: dict) -> bool:
    return isinstance(d, dict) and isinstance(d.get("intent_score"), (int, float))


def grade_from_score(score: int, thresholds: dict) -> str:
    if score >= thresholds.get("A", 80):
        return "A"
    if score >= thresholds.get("B", 60):
        return "B"
    if score >= thresholds.get("C", 40):
        return "C"
    return "D"


async def analyze_transcript(text: str, *, source: str = "call") -> dict:
    """转写文本 → 意向分析 schema(不落库)。无 LLM/失败 → 启发式兜底。"""
    if not (text or "").strip():
        return dict(_EMPTY)
    if is_llm_dev_mode():
        return _mock_analyze(text)
    data = await complete_json(
        system_prompt=_SYS,
        user_prompt=f"渠道:{source}\n转写:\n{text}",
        max_tokens=1200, escalate_ceiling=2400, model=fast_model(),
        validate=_valid, feature="sales_intent")
    if data is None:
        _log.warning("intent analyze fell back to heuristic")
        return _mock_analyze(text)
    # 归一 + 补齐缺省字段
    out = dict(_EMPTY)
    out.update({k: data.get(k, out[k]) for k in _EMPTY})
    out["intent_score"] = max(0, min(100, int(out.get("intent_score") or 0)))
    return out


async def analyze_activity(db: AsyncSession, *, activity_id: uuid.UUID) -> SalesLeadActivity:
    """对一条已有转写(asr_text,缺则用 content)的跟进记录跑分析,回填到 activity + 线索。"""
    act = await db.get(SalesLeadActivity, activity_id)
    if act is None:
        raise AppError(code=404, message="跟进记录不存在")
    text = act.asr_text or act.content or ""
    analysis = await analyze_transcript(text, source=act.channel or "call")
    score = int(analysis.get("intent_score") or 0)
    act.analysis = analysis
    act.intent_score = score
    await _rollup_to_lead(db, lead_id=act.lead_id, score=score, analysis=analysis)
    await db.flush()
    return act


async def transcribe_and_analyze(db: AsyncSession, *, activity_id: uuid.UUID) -> SalesLeadActivity:
    """录音 → ASR 转写 → 意向分析。用于「有录音无转写」的跟进(呼叫中心回传录音后)。

    转写可能耗数十秒(腾讯录音文件识别是异步任务),生产建议放后台任务调用本函数。
    """
    from app.services import asr_service
    act = await db.get(SalesLeadActivity, activity_id)
    if act is None:
        raise AppError(code=404, message="跟进记录不存在")
    if not (act.recording_url or "").strip():
        raise AppError(code=400, message="该跟进没有录音,无法转写")
    act.asr_text = await asr_service.transcribe(act.recording_url, source=act.channel or "call")
    await db.flush()
    return await analyze_activity(db, activity_id=activity_id)


async def _rollup_to_lead(db: AsyncSession, *, lead_id: uuid.UUID,
                          score: int, analysis: dict) -> None:
    """把最新一次分析汇总到线索:意向分/分层 + 合并产品意见(去重保序)。"""
    lead = await db.get(SalesLead, lead_id)
    if lead is None:
        return
    cfg = await crm.get_config(db)
    lead.intent_score = score
    lead.intent_grade = grade_from_score(score, cfg["intent_grade_thresholds"])
    new_fb = [f for f in (analysis.get("product_feedback") or []) if f]
    if new_fb:
        merged = list(lead.product_feedback or [])
        for f in new_fb:
            if f not in merged:
                merged.append(f)
        lead.product_feedback = merged[:50]


async def ingest_call_record(
    db: AsyncSession, *, lead_id: uuid.UUID, admin_id: uuid.UUID | None,
    recording_url: str | None = None, asr_text: str | None = None,
    call_duration_sec: int | None = None, direction: str | None = "out",
    outcome: str | None = None, content: str | None = None,
) -> SalesLeadActivity:
    """呼叫中心接入位:落一条 call 跟进(挂录音/时长),有转写就顺带跑意向分析并回填。

    ASR 未接时可只传 recording_url(分析留空,后续补 asr_text 再 analyze_activity)。
    """
    lead = await crm.get_lead(db, lead_id)
    act = SalesLeadActivity(
        id=uuid.uuid4(), lead_id=lead_id, admin_id=admin_id, channel="call",
        direction=direction, outcome=outcome, content=content,
        recording_url=recording_url, asr_text=asr_text, call_duration_sec=call_duration_sec)
    db.add(act)
    from datetime import datetime, timezone
    lead.last_contacted_at = datetime.now(timezone.utc)
    if lead.status == "new":
        lead.status = "contacted"
    await db.flush()
    if asr_text:
        await analyze_activity(db, activity_id=act.id)
    return act
