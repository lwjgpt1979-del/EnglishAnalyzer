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

# ── 完形填空:双轴解析(载体槽=形式,线索类型=真构念;Bachman 完形约束跨度分类)────
# 线索类型封闭枚举——决定学情归因与仿真变式("同线索类型"),载体(词性)区分度≈0
CLUE_TYPES = ("句内固定搭配", "句内语法约束", "跨句逻辑关系", "跨句词汇复现",
              "全篇情感基调", "指代与人物追踪", "情景交际惯用")
SLOT_TYPES = ("副词槽", "连词槽", "介词槽", "代词槽", "交际用语槽", "动词形式槽", "名词槽", "形容词槽")

_OPT_PREFIX = re.compile(r"^[A-DＡ-Ｄ][.、．)]\s*")
_OPT_SPLIT = re.compile(r"\s*[A-DＡ-Ｄ][.、．)]\s*")


def parse_options_from_stem(stem: str) -> list[str] | None:
    """从题干解析嵌入式选项(切题器常把 'A. x  B. y  C. z  D. w' 留在 stem、options 列为空)。
    解析出 3-4 项才认,否则 None(宁缺勿错)。"""
    parts = [p.strip().strip("\t").strip() for p in _OPT_SPLIT.split(stem or "")]
    opts = [p for p in parts[1:] if p]      # parts[0] 是题号等前缀
    return opts if 3 <= len(opts) <= 4 else None


_CONJS = {"but", "and", "so", "or", "because", "though", "although", "while", "until",
          "unless", "if", "when", "before", "after", "since", "as", "however", "besides"}
_PREPS = {"in", "on", "at", "for", "with", "by", "from", "of", "to", "about", "under",
          "over", "through", "during", "between", "among", "behind", "above", "below",
          "near", "inside", "outside", "without", "against", "across", "towards"}
_PRONS = {"he", "him", "his", "himself", "she", "her", "hers", "herself", "they", "them",
          "their", "theirs", "themselves", "it", "its", "itself", "we", "us", "our",
          "ours", "ourselves", "you", "your", "yours", "yourself", "i", "me", "my", "mine", "myself"}
_COMMS = {"thanks", "sorry", "excuse me", "please", "congratulations", "well done",
          "good idea", "no problem", "you're welcome", "never mind", "cheer up",
          "good luck", "come on", "pardon"}
_VERB_SUFFIX = {"", "s", "es", "d", "ed", "ing", "en", "ne"}


def classify_cloze_slot(options: list | None) -> str | None:
    """载体槽确定性判定:完形四选项同词性即定槽(区分度=0 的形式轴,程序判,零 LLM)。
    拿不准返回 None(交 LLM/人工)。"""
    if not options or len(options) < 2:
        return None
    words = [_OPT_PREFIX.sub("", str(o)).strip().lower() for o in options]
    if any(not w for w in words):
        return None
    if all(w.endswith("ly") and " " not in w for w in words):
        return "副词槽"
    if all(w in _CONJS for w in words):
        return "连词槽"
    if all(w in _PREPS for w in words):
        return "介词槽"
    if all(w in _PRONS for w in words):
        return "代词槽"
    if all(w in _COMMS for w in words):
        return "交际用语槽"
    # 动词形式槽:同一词干的不同形态(goes/going/gone)——共同前缀≥2 且余部是屈折后缀
    prefix = words[0]
    for w in words[1:]:
        while prefix and not w.startswith(prefix):
            prefix = prefix[:-1]
    if len(prefix) >= 2 and all(w[len(prefix):] in _VERB_SUFFIX for w in words):
        return "动词形式槽"
    return None

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


def validate_cloze_analysis(analysis: dict, *, context_text: str) -> list[str]:
    """校验一份完形逐空解析;返回错误列表(空=通过)。"""
    errs: list[str] = []
    clue = (analysis.get("clue") or "").strip()
    if not clue:
        errs.append("缺少线索句 clue")
    elif _norm(clue) not in _norm(context_text):
        errs.append("线索句不是原文子串(疑似幻觉)")
    if analysis.get("clue_type") not in CLUE_TYPES:
        errs.append("clue_type 不在枚举内")
    slot = analysis.get("slot")
    if slot and slot not in SLOT_TYPES:
        errs.append(f"载体槽非法:{slot}")
    codes = analysis.get("kp_codes") or []
    if not isinstance(codes, list) or not codes or not all(isinstance(c, str) and c.strip() for c in codes):
        errs.append("kp_codes 须为非空编码列表(线索轴为主)")
    # 完形干扰项 = 原义 + 干扰机制(词义本身合理、但与语境线索冲突——与阅读的枚举错因不同)
    dts = analysis.get("distractors") or {}
    if not isinstance(dts, dict):
        errs.append("distractors 须为对象 {选项: {meaning, why_wrong}}")
    else:
        for k, v in dts.items():
            if str(k).upper() not in {"A", "B", "C", "D"}:
                errs.append(f"干扰项键非法:{k}")
            if not isinstance(v, dict) or not (v.get("meaning") or "").strip() \
                    or not (v.get("why_wrong") or "").strip():
                errs.append(f"干扰项 {k} 须含 原义(meaning)+干扰机制(why_wrong)")
    return errs


def analysis_constraints_text(analysis: dict | None) -> str:
    """解析对象 → 仿真派生 prompt 的约束文本(同线索类型+同载体槽/同技能+同错因策略)。"""
    if not analysis:
        return ""
    lines: list[str] = []
    if analysis.get("clue_type"):                    # 完形
        slot = analysis.get("slot")
        lines.append(f"本空线索类型:{analysis['clue_type']}(变式必须保持同线索类型)")
        if slot:
            lines.append(f"载体槽:{slot}(四个选项保持同词性)")
    if analysis.get("rc_code"):                      # 阅读
        lines.append(f"本题阅读技能:{analysis['rc_code']}(变式必须考同一技能,答案须可回文定位)")
    dts = analysis.get("distractor_types") or {}
    if dts:                                          # 阅读:枚举错因策略
        lines.append("干扰项错因策略(变式按同策略造干扰项):" +
                     "、".join(sorted(set(dts.values()))))
    dss = analysis.get("distractors") or {}
    if dss:                                          # 完形:同干扰机制(原义合理×语境冲突)
        mech = "; ".join(f"{k}:{(v or {}).get('why_wrong', '')}" for k, v in sorted(dss.items()))
        lines.append(f"干扰项设计机制(变式按同机制造干扰项——词义本身合理但与语境线索冲突):{mech[:300]}")
    return ("\n".join(lines) + "\n") if lines else ""


async def _kp_codes_exist(db: AsyncSession, codes: list[str]) -> list[str]:
    """返回图谱里不存在的编码列表(空=全部存在)。"""
    if not codes:
        return []
    found = set((await db.execute(
        sa.select(KnowledgeNode.code).where(KnowledgeNode.code.in_(codes)))).scalars().all())
    return [c for c in codes if c not in found]


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


_CLOZE_SYSTEM = (
    "你是中小学英语完形填空测评专家。完形四选项同词性,词性本身区分度为零;"
    "真正被测的是「语境线索」——干扰项的词义本身合理,错在与语境线索冲突。"
    "对给定空做双轴解析,只返回 JSON:"
    '{"clue_type":"线索类型","clue":"决定答案的线索句(必须逐字摘自原文)",'
    '"answer_letter":"正确项字母(未给答案时按语境推断)",'
    '"kp_codes":["考点编码(从目录挑,线索轴为主)"],'
    '"distractors":{"A":{"meaning":"该词原义(中文)","why_wrong":"为何在本语境是干扰(必须指出与哪条线索冲突)"},...}}。'
    "线索类型只能取:" + "、".join(CLUE_TYPES) + "。"
    "distractors 只列**非正确项**,每项必须给 meaning+why_wrong。"
)


def _effective_options(q: PlatformQuestion) -> list[str] | None:
    """options 列优先;为空则从 stem 解析嵌入式选项(切题器常把选项留在题干)。"""
    if q.options:
        return list(q.options) if isinstance(q.options, list) else None
    return parse_options_from_stem(q.stem or "")


def _mock_cloze_suggestion(q: PlatformQuestion, context: str) -> dict:
    first = re.split(r"(?<=[.!?])\s+", context.strip())[0][:200]
    opts = _effective_options(q) or []
    dss = {chr(65 + i): {"meaning": f"mock 原义{i}", "why_wrong": "mock:与线索句语境冲突"}
           for i, _ in enumerate(opts[:2])}
    return {"slot": classify_cloze_slot(opts),
            "clue_type": "跨句逻辑关系", "clue": first,
            "kp_codes": ["rc-6-1"], "distractors": dss}


async def _llm_cloze_suggestion(q: PlatformQuestion, context: str, clue_catalog: str) -> dict:
    eff = _effective_options(q)
    slot = classify_cloze_slot(eff)
    opts = json.dumps(eff, ensure_ascii=False) if eff else "(无选项)"
    user = (f"【线索轴考点目录】\n{clue_catalog}\n\n【原文(空格即本题)】\n{context[:3500]}\n\n"
            f"【本空题干】{q.stem}\n【选项(A-D 顺序)】{opts}\n【正确答案】{q.answer or '未知(请按语境推断)'}\n"
            f"【载体槽(程序已判)】{slot or '未定'}")
    resp = await chat_completion(system_prompt=_CLOZE_SYSTEM, user_prompt=user,
                                 max_tokens=1400, response_format={"type": "json_object"})
    ana = json.loads((resp.choices[0].message.content or "{}").strip())
    ana["slot"] = slot or ana.get("slot")   # 载体槽以程序判定为准
    return ana


async def suggest_cloze_analysis(
    db: AsyncSession, *, question_ids: list[uuid.UUID]
) -> list[dict]:
    """为完形逐空生成双轴解析**建议**(不写库):载体槽程序判,线索类型/线索句 LLM 建议+校验。"""
    pairs = await _load_with_context(db, question_ids)
    clue_catalog = "\n".join(
        f"{c} {n}" for c, n in (await db.execute(
            sa.select(KnowledgeNode.code, KnowledgeNode.name).where(sa.or_(
                KnowledgeNode.code.like("rc-4%"), KnowledgeNode.code.like("rc-6%"),
                KnowledgeNode.name == "情景交际用语",
            )).order_by(KnowledgeNode.code))).all())
    out = []
    for q, context in pairs:
        existing = (q.meta or {}).get("analysis")
        try:
            ana = _mock_cloze_suggestion(q, context) if is_llm_dev_mode() \
                else await _llm_cloze_suggestion(q, context, clue_catalog)
        except Exception as exc:  # noqa: BLE001
            out.append({"question_id": str(q.id), "analysis": None,
                        "errors": [f"生成失败:{exc}"], "existing": existing})
            continue
        errs = validate_cloze_analysis(ana, context_text=context)
        if not errs:
            missing = await _kp_codes_exist(db, ana.get("kp_codes") or [])
            if missing:
                errs = [f"kp_codes 不在图谱:{','.join(missing)}"]
        out.append({"question_id": str(q.id), "analysis": ana,
                    "errors": errs, "existing": existing})
    return out


async def suggest_analysis(
    db: AsyncSession, *, question_ids: list[uuid.UUID]
) -> list[dict]:
    """按题型分发解析建议:完型→双轴(载体槽+线索);阅读→题目层(rc技能+定位句)。
    完型判定 = question_type 为「完型」或 section 含「完形/完型」(与前端 _fine_type 显示一致,防错位)。"""
    qs = (await db.execute(
        sa.select(PlatformQuestion.id, PlatformQuestion.question_type, PlatformQuestion.section)
        .where(PlatformQuestion.id.in_(question_ids)))).all()

    def _is_cloze(qt: str | None, sec: str | None) -> bool:
        return (qt or "") == "完型" or "完形" in (sec or "") or "完型" in (sec or "")

    cloze_ids = [qid for qid, qt, sec in qs if _is_cloze(qt, sec)]
    reading_ids = [qid for qid, qt, sec in qs if not _is_cloze(qt, sec)]
    out: list[dict] = []
    if cloze_ids:
        out += await suggest_cloze_analysis(db, question_ids=cloze_ids)
    if reading_ids:
        out += await suggest_reading_analysis(db, question_ids=reading_ids)
    order = {str(q): i for i, q in enumerate(question_ids)}
    out.sort(key=lambda it: order.get(it["question_id"], 999))
    return out


async def confirm_analysis(
    db: AsyncSession, *, question_id: uuid.UUID, analysis: dict, admin_id: uuid.UUID,
) -> dict:
    """人工确认后写库(唯一写入口):按解析形态分发校验(完形=clue_type;阅读=rc_code)→
    meta.analysis(带确认者/时间)。"""
    q = (await db.execute(
        sa.select(PlatformQuestion).where(PlatformQuestion.id == question_id)
    )).scalar_one_or_none()
    if q is None:
        raise AppError(code=404, message="题目不存在")
    pairs = await _load_with_context(db, [question_id])
    context = pairs[0][1]
    if "clue_type" in analysis:                       # 完形双轴解析
        errs = validate_cloze_analysis(analysis, context_text=context)
        if not errs:
            missing = await _kp_codes_exist(db, analysis.get("kp_codes") or [])
            if missing:
                errs = [f"kp_codes 不在图谱:{','.join(missing)}"]
        analysis = {**analysis, "kind": "cloze"}
    else:                                             # 阅读题目层解析
        errs = validate_reading_analysis(analysis, context_text=context)
        if not errs and not await _rc_code_exists(db, analysis.get("rc_code", "")):
            errs = [f"rc_code 不在图谱:{analysis.get('rc_code')}"]
        analysis = {**analysis, "kind": "reading"}
    if errs:
        raise AppError(code=400, message="解析未通过校验:" + ";".join(errs))
    saved = {**analysis,
             "confirmed_by": str(admin_id),
             "confirmed_at": _dt.datetime.now(_dt.timezone.utc).isoformat()}
    q.meta = {**(q.meta or {}), "analysis": saved}
    await db.flush()
    return saved
