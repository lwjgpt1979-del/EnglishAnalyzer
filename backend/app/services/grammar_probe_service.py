"""R10.1 语法「可解释掌握」· 识别 + 纠错探针 + 四维掌握度(BKT)。

设计见 docs/R10-技术方案-语法掌握判定与分级测验.md。方法论沿用 R9(vocab_probe_service):
- 探针库(KP 级公共复用):ensure_probes 生成并缓存到 KnowledgePoint.grammar_probes_json。
- 四维证据:识别(选择)/ 纠错(改错)/ 产出(造句,R10.2)/ 迁移(新语境,R10.3)。
- 判分 → 各维掌握度走 BKT(复用 mastery_judge_service.bkt_update,天然分离蒙对/手滑)。
- R10.1 落 识别 + 纠错 两维;产出/迁移题料一并生成缓存,留 R10.2/3 暴露。
复用:llm_provider.complete_json(分档/智能重试)、usage_log_service(台账+预算熔断)。
"""
from __future__ import annotations

import logging
import random
import uuid
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d4_knowledge import KnowledgePoint, StudentGrammarMastery
from app.services import mastery_judge_service, usage_log_service
from app.services import grammar_config_service as _cfg
from app.services.llm_provider import complete_json, fast_model, is_llm_dev_mode

_log = logging.getLogger(__name__)

RECOGNIZE_MASTERED = 0.85   # 识别维掌握阈
DETECT_MASTERED = 0.85      # 纠错维掌握阈
PRODUCE_MASTERED = 0.85     # 产出维掌握阈
# 产出造句 rubric 维度(每维 0-2):用对结构 / 句子正确 / 表意通顺
_PROD_DIMS = [("structure", "用对结构"), ("accuracy", "句子正确"), ("meaning", "表意通顺")]
_PROD_PASS = 4              # 总分 ≥4/6 且「用对结构」≥1 视为产出达标
# 间隔复测阶梯(天):四维门槛达成后,隔期用新题复测,通过则间隔拉长(SM2 思路)
_RETAIN_LADDER = [3, 7, 15, 30, 60]
RETAIN_MIN_DAYS = 3        # 至少隔 3 天才复测(破"刷同一套题过拟合")


# ── 探针库(KP 级公共缓存)────────────────────────────────────────────
async def ensure_probes(db: AsyncSession, kp: KnowledgePoint) -> dict:
    """取该语法点探针库;无缓存则 LLM 生成(走 fast 档)并写回 grammar_probes_json。"""
    p = kp.grammar_probes_json or {}
    if p.get("recognize") and p.get("detect"):
        return p
    name = kp.name
    desc = kp.description or ""
    if is_llm_dev_mode():
        p = {
            "recognize": [
                {"stem": f"This is a ___ test of {name}.", "options": ["A", "B", "C", "D"],
                 "answer": "A", "misconception": {"B": "(dev)误区B", "C": "(dev)误区C", "D": "(dev)误区D"}},
                {"stem": f"He ___ ({name}) every day.", "options": ["W", "X", "Y", "Z"],
                 "answer": "W", "misconception": {"X": "(dev)误区X"}},
            ],
            "detect": [
                {"sentence": f"(dev) wrong sentence about {name}.",
                 "options": ["fixA", "fixB", "fixC", "fixD"], "answer": "fixA", "explain": "(dev)错因"},
            ],
            "produce_hint": f"用「{name}」写一句英文(用对结构)",
            "transfer_seed": [],
        }
    else:
        system = (
            "你是初中英语语法命题专家。给定一个语法知识点(名称+说明),生成「识别 + 纠错」检测题料,"
            "面向初中学生,题目地道、误区典型。严格输出 JSON:\n"
            "{\"recognize\":[2-3题 单选,检验能否选对正确形式 "
            "{\"stem\":\"一句带 ___ 的英文(留一空)\",\"options\":[\"4个英文选项\"],"
            "\"answer\":\"正确选项(须在 options 内)\",\"misconception\":{\"错误选项\":\"一句中文错因\"}}],\n"
            " \"detect\":[2题 改错,检验能否发现并改正违例 "
            "{\"sentence\":\"一句含一处该语法点错误的英文\",\"options\":[\"4个完整改写句\"],"
            "\"answer\":\"正确改写(须在 options 内)\",\"explain\":\"一句中文错因\"}],\n"
            " \"produce_hint\":\"一句中文,引导学生用该语法点造句\",\n"
            " \"transfer_seed\":[1题 新语境单选,结构同 recognize,用于迁移检测]}"
        )
        user = f"语法知识点:{name}\n说明:{desc}\n返回 JSON:"
        d = await complete_json(
            system_prompt=system, user_prompt=user, max_tokens=1200,
            model=fast_model(), feature="grammar_probe",
            validate=lambda x: bool(x.get("recognize") and x.get("detect")))
        if not d:
            p = {"recognize": [], "detect": [], "produce_hint": f"用「{name}」造一个句子", "transfer_seed": []}
        else:
            p = {
                "recognize": [r for r in (d.get("recognize") or [])
                              if isinstance(r, dict) and r.get("stem") and r.get("options") and r.get("answer")][:3],
                "detect": [r for r in (d.get("detect") or [])
                           if isinstance(r, dict) and r.get("sentence") and r.get("options") and r.get("answer")][:2],
                "produce_hint": str(d.get("produce_hint") or f"用「{name}」造一个句子"),
                "transfer_seed": [r for r in (d.get("transfer_seed") or [])
                                  if isinstance(r, dict) and r.get("stem") and r.get("options") and r.get("answer")][:2],
            }
    kp.grammar_probes_json = p
    await db.flush()
    return p


# ── 探针组装(不含答案,发给前端)──────────────────────────────────────
async def comprehension_probes(db: AsyncSession, *, student_id: uuid.UUID, kp: KnowledgePoint) -> dict:
    """组装该语法点 R10.1 题面:识别(选择)+ 纠错(改错)。返回题面 + 当前各维掌握度。"""
    await _cfg.get_config(db)   # 预热运营配置(阈值等)
    p = await ensure_probes(db, kp)
    probes = []
    for i, r in enumerate(p.get("recognize") or []):
        probes.append({"key": f"recognize:{i}", "kind": "recognize",
                       "prompt": r["stem"], "options": list(r["options"])})
    for i, r in enumerate(p.get("detect") or []):
        probes.append({"key": f"detect:{i}", "kind": "detect",
                       "prompt": f"找出并改正错误:{r['sentence']}", "options": list(r["options"])})
    m = await _get_mastery(db, student_id, kp.id)
    recog = float(m.mastery_recognize) if m and m.mastery_recognize is not None else 0.0
    detect = float(m.mastery_detect) if m and m.mastery_detect is not None else 0.0
    produce = float(m.mastery_produce) if m and m.mastery_produce is not None else 0.0
    transfer_ok = bool(m.transfer_ok) if m else False
    return {
        "kp_id": str(kp.id), "kp_name": kp.name, "probes": probes,
        "produce": {"key": "produce", "prompt": str(p.get("produce_hint") or f"用「{kp.name}」造一个句子")},
        "has_transfer": bool(p.get("transfer_seed")),
        "recognize": recog, "detect": detect, "produce_score": produce, "transfer_ok": transfer_ok,
        "mastered": _axes_mastered(recog, detect, produce, transfer_ok),
        "confirmed_mastered": confirmed_mastered(m),
        "status": _status_label(m),
    }


# ── 判分 + 掌握度(BKT)─────────────────────────────────────────────────
async def submit_probe(db: AsyncSession, *, student_id: uuid.UUID, kp_id: uuid.UUID,
                       key: str, answer: str) -> dict:
    """提交一道探针(recognize/detect):判分 → 对应维 BKT → 错题计数。"""
    await _cfg.get_config(db)   # 预热运营配置(阈值等)
    kp = (await db.execute(sa.select(KnowledgePoint).where(KnowledgePoint.id == kp_id))).scalar_one_or_none()
    if kp is None:
        raise AppError(code=404, message="知识点不存在")
    p = await ensure_probes(db, kp)
    ans = (answer or "").strip()

    try:
        kind, idx_s = key.split(":", 1)
        idx = int(idx_s)
    except (ValueError, AttributeError):
        raise AppError(code=400, message="探针 key 非法")

    if kind == "recognize":
        items = p.get("recognize") or []
        axis = "recognize"
    elif kind == "detect":
        items = p.get("detect") or []
        axis = "detect"
    else:
        raise AppError(code=400, message="未知探针类型")
    if idx >= len(items):
        raise AppError(code=400, message="探针不存在")

    item = items[idx]
    correct_answer = str(item["answer"]).strip()
    correct = ans == correct_answer
    misconception = None
    if not correct:
        if kind == "recognize":
            misconception = (item.get("misconception") or {}).get(ans)
        else:
            misconception = item.get("explain")

    m = await _get_or_create_mastery(db, student_id, kp_id)
    cur = getattr(m, f"mastery_{axis}")
    new = mastery_judge_service.bkt_update(None if cur is None else float(cur), correct)
    setattr(m, f"mastery_{axis}", new)
    if not correct:
        m.wrong_count = (m.wrong_count or 0) + 1
    m.last_seen_at = datetime.now(timezone.utc)
    m.prior_source = "learn"

    _maybe_schedule_retention(m)
    qid = uuid.uuid5(uuid.NAMESPACE_OID, f"grammar-probe:{kp_id}:{key}")
    await mastery_judge_service.log_answer(
        db, student_id=student_id, q_scope="platform", question_id=qid,
        node_id=None, is_correct=correct, feature="grammar_probe")
    await db.flush()

    recog = float(m.mastery_recognize) if m.mastery_recognize is not None else 0.0
    detect = float(m.mastery_detect) if m.mastery_detect is not None else 0.0
    produce = float(m.mastery_produce) if m.mastery_produce is not None else 0.0
    return {
        "correct": correct, "correct_answer": correct_answer, "misconception": misconception,
        "axis": axis, "recognize": recog, "detect": detect, "produce_score": produce,
        "transfer_ok": bool(m.transfer_ok),
        "mastered": _axes_mastered(recog, detect, produce, bool(m.transfer_ok)),
    }


# ── 产出维(造句,R10.2)──────────────────────────────────────────────────
async def grade_produce(kp_name: str, kp_desc: str, sentence: str) -> dict:
    """给学生用该语法点造的句子按维度打分(用对结构/句子正确/表意通顺 各 0-2)。
    返回 {dimensions, total, max, passed, feedback}。LLM 瞬时失败 → graded=False(不计分)。"""
    sentence = (sentence or "").strip()
    total_max = 2 * len(_PROD_DIMS)
    if not sentence:
        return {"dimensions": [{"key": k, "label": l, "score": 0, "max": 2, "note": ""} for k, l in _PROD_DIMS],
                "total": 0, "max": total_max, "passed": False, "feedback": "还没写句子"}
    if is_llm_dev_mode():
        base = 2 if len(sentence.split()) >= 4 else 1
        dims = [{"key": k, "label": l, "score": base, "max": 2, "note": ""} for k, l in _PROD_DIMS]
        tot = base * len(_PROD_DIMS)
        return {"dimensions": dims, "total": tot, "max": total_max,
                "passed": tot >= _PROD_PASS and base >= 1, "feedback": "(dev)规则近似评分"}
    system = (
        "你是初中英语写作评分老师。学生用指定语法知识点造了一句英文,按 3 维打分,每维 0/1/2(0 错/缺、1 部分、2 准确):\n"
        "- structure 用对结构:句子确实运用了该语法点,且结构正确;\n"
        "- accuracy 句子正确:无其他语法/拼写错误;\n"
        "- meaning 表意通顺:句子表意清楚、自然。\n"
        "若句子根本没用到该语法点,structure=0。每维给一句简短中文点评(note),再给一句总评(feedback,指出最该改进处)。\n"
        "严格输出 JSON:{\"structure\":{\"score\":0-2,\"note\":..},\"accuracy\":{..},\"meaning\":{..},\"feedback\":..}"
    )
    user = f"语法知识点:{kp_name}\n说明:{kp_desc}\n学生造句:{sentence}\n返回 JSON:"
    d = await complete_json(system_prompt=system, user_prompt=user, max_tokens=700,
                            model=fast_model(), feature="grammar_produce",
                            validate=lambda x: any(x.get(k) for k, _ in _PROD_DIMS))
    if not d:
        return {"dimensions": [{"key": k, "label": l, "score": 0, "max": 2, "note": ""} for k, l in _PROD_DIMS],
                "total": 0, "max": total_max, "passed": False, "graded": False,
                "feedback": "评分服务暂忙,请重试(本次不计分)"}
    dims = []
    for k, l in _PROD_DIMS:
        cell = d.get(k) or {}
        try:
            sc = max(0, min(2, int(cell.get("score", 0))))
        except (ValueError, TypeError):
            sc = 0
        dims.append({"key": k, "label": l, "score": sc, "max": 2, "note": str(cell.get("note") or "")})
    tot = sum(x["score"] for x in dims)
    struct_sc = next((x["score"] for x in dims if x["key"] == "structure"), 0)
    return {"dimensions": dims, "total": tot, "max": total_max,
            "passed": tot >= _PROD_PASS and struct_sc >= 1, "feedback": str(d.get("feedback") or "")}


async def submit_produce(db: AsyncSession, *, student_id: uuid.UUID, kp_id: uuid.UUID, sentence: str) -> dict:
    """提交造句:rubric 评分 → 产出掌握度 produce BKT(达标=正确)。LLM 失败则不计分。"""
    kp = (await db.execute(sa.select(KnowledgePoint).where(KnowledgePoint.id == kp_id))).scalar_one_or_none()
    if kp is None:
        raise AppError(code=404, message="知识点不存在")
    res = await grade_produce(kp.name, kp.description or "", sentence)
    m = await _get_or_create_mastery(db, student_id, kp_id)
    if res.get("graded", True):   # graded=False(评分服务失败)→ 不动掌握度、不计错
        m.mastery_produce = mastery_judge_service.bkt_update(
            None if m.mastery_produce is None else float(m.mastery_produce), res["passed"])
        if not res["passed"]:
            m.wrong_count = (m.wrong_count or 0) + 1
        m.last_seen_at = datetime.now(timezone.utc)
        m.prior_source = "learn"
        _maybe_schedule_retention(m)
        qid = uuid.uuid5(uuid.NAMESPACE_OID, f"grammar-produce:{kp_id}")
        await mastery_judge_service.log_answer(
            db, student_id=student_id, q_scope="platform", question_id=qid,
            node_id=None, is_correct=res["passed"], feature="grammar_produce")
    await db.flush()
    recog = float(m.mastery_recognize) if m.mastery_recognize is not None else 0.0
    detect = float(m.mastery_detect) if m.mastery_detect is not None else 0.0
    produce = float(m.mastery_produce) if m.mastery_produce is not None else 0.0
    res.update({"recognize": recog, "detect": detect, "produce_score": produce,
                "transfer_ok": bool(m.transfer_ok),
                "mastered": _axes_mastered(recog, detect, produce, bool(m.transfer_ok))})
    return res


# ── 迁移维(同点新语境,R10.3)────────────────────────────────────────────
async def _ensure_transfer_seed(db: AsyncSession, kp: KnowledgePoint) -> list:
    """取该点迁移题种子(新语境单选);缓存缺失则 LLM 现生成一题并写回缓存。"""
    p = kp.grammar_probes_json or {}
    seeds = p.get("transfer_seed") or []
    if seeds:
        return seeds
    if is_llm_dev_mode():
        seeds = [{"stem": f"(dev transfer) ___ about {kp.name}.", "options": ["A", "B", "C", "D"], "answer": "A"}]
    else:
        system = (
            "你是初中英语语法命题专家。给定一个语法知识点,生成 1 道「全新语境」的单选题,"
            "用于检验学生能否把规则迁移到没见过的句子(不要与常见例句雷同)。严格输出 JSON:"
            "{\"stem\":\"一句带 ___ 的英文(留一空)\",\"options\":[\"4个英文选项\"],\"answer\":\"正确选项(须在 options 内)\"}"
        )
        user = f"语法知识点:{kp.name}\n说明:{kp.description or ''}\n返回 JSON:"
        d = await complete_json(system_prompt=system, user_prompt=user, max_tokens=400,
                                model=fast_model(), feature="grammar_probe",
                                validate=lambda x: bool(x.get("stem") and x.get("options") and x.get("answer")))
        seeds = [d] if d and d.get("stem") and d.get("options") and d.get("answer") else []
    if seeds:
        p = dict(p)
        p["transfer_seed"] = seeds
        kp.grammar_probes_json = p
        await db.flush()
    return seeds


async def transfer_probe(db: AsyncSession, *, student_id: uuid.UUID, kp: KnowledgePoint) -> dict | None:
    """组装迁移题:同点新语境单选。无可用题→None。"""
    seeds = await _ensure_transfer_seed(db, kp)
    if not seeds:
        return None
    s = seeds[0]
    return {"probe": {"key": "transfer:0", "kind": "transfer",
                      "prompt": f"换个新句子:{s['stem']}", "options": list(s["options"])}}


async def submit_transfer(db: AsyncSession, *, student_id: uuid.UUID, kp_id: uuid.UUID,
                          key: str, answer: str) -> dict:
    """提交迁移题:判分 → 识别 BKT + 通过则置 transfer_ok=True。
    verdict=transferred(真懂、能迁移)/ memorized(疑似只记住练过的题)。"""
    kp = (await db.execute(sa.select(KnowledgePoint).where(KnowledgePoint.id == kp_id))).scalar_one_or_none()
    if kp is None:
        raise AppError(code=404, message="知识点不存在")
    seeds = await _ensure_transfer_seed(db, kp)
    try:
        idx = int(key.split(":", 1)[1])
    except (ValueError, IndexError, AttributeError):
        idx = 0
    if idx >= len(seeds):
        raise AppError(code=400, message="迁移题不存在")
    correct_answer = str(seeds[idx]["answer"]).strip()
    correct = (answer or "").strip() == correct_answer

    m = await _get_or_create_mastery(db, student_id, kp_id)
    m.mastery_recognize = mastery_judge_service.bkt_update(
        None if m.mastery_recognize is None else float(m.mastery_recognize), correct)
    if correct:
        m.transfer_ok = True
    else:
        m.wrong_count = (m.wrong_count or 0) + 1
    m.last_seen_at = datetime.now(timezone.utc)
    m.prior_source = "learn"
    _maybe_schedule_retention(m)
    qid = uuid.uuid5(uuid.NAMESPACE_OID, f"grammar-transfer:{kp_id}:{key}")
    await mastery_judge_service.log_answer(
        db, student_id=student_id, q_scope="platform", question_id=qid,
        node_id=None, is_correct=correct, feature="grammar_probe")
    await db.flush()
    recog = float(m.mastery_recognize) if m.mastery_recognize is not None else 0.0
    detect = float(m.mastery_detect) if m.mastery_detect is not None else 0.0
    produce = float(m.mastery_produce) if m.mastery_produce is not None else 0.0
    return {
        "correct": correct, "correct_answer": correct_answer,
        "verdict": "transferred" if correct else "memorized",
        "recognize": recog, "detect": detect, "produce_score": produce, "transfer_ok": bool(m.transfer_ok),
        "mastered": _axes_mastered(recog, detect, produce, bool(m.transfer_ok)),
    }


# ── 成组混合检测(反经验主义,R10.4)──────────────────────────────────────
async def group_mixed_quiz(db: AsyncSession, *, student_id: uuid.UUID, kp_ids: list) -> dict:
    """一组语法点的混合识别检测:每点取一题、打乱顺序、**不标注考的是哪条规则**。

    破"单点练习时无脑套规则"——题目混着来,学生必须逐句分析判断该用什么形式。
    每题保留各自 4 选项。<2 题时降级(返回 degraded,前端跳过直接走单点)。
    """
    items: list[dict] = []
    for kid in kp_ids:
        try:
            kid = kid if isinstance(kid, uuid.UUID) else uuid.UUID(str(kid))
        except (ValueError, TypeError):
            continue
        kp = (await db.execute(sa.select(KnowledgePoint).where(KnowledgePoint.id == kid))).scalar_one_or_none()
        if kp is None:
            continue
        p = await ensure_probes(db, kp)
        recog = p.get("recognize") or []
        if not recog:
            continue
        item = recog[0]
        opts = list(item["options"])
        random.shuffle(opts)
        items.append({"kp_id": str(kp.id), "key": "recognize:0",
                      "stem": item["stem"], "options": opts})   # 不回传 answer / 不标规则名
    random.shuffle(items)
    if len(items) < 2:
        return {"items": [], "count": len(items), "degraded": True}
    return {"items": items, "count": len(items), "degraded": False}


async def submit_group_mixed(db: AsyncSession, *, student_id: uuid.UUID, answers: dict) -> dict:
    """提交成组检测:逐点判分(chosen==该点识别题答案)→ 识别 BKT。answers={kp_id: 所选}。"""
    results = []
    for kid, chosen in (answers or {}).items():
        try:
            kp_id = uuid.UUID(str(kid))
        except (ValueError, TypeError):
            continue
        kp = (await db.execute(sa.select(KnowledgePoint).where(KnowledgePoint.id == kp_id))).scalar_one_or_none()
        if kp is None:
            continue
        recog = (kp.grammar_probes_json or {}).get("recognize") or []
        if not recog:
            continue
        correct_answer = str(recog[0]["answer"]).strip()
        correct = (chosen or "").strip() == correct_answer
        m = await _get_or_create_mastery(db, student_id, kp_id)
        m.mastery_recognize = mastery_judge_service.bkt_update(
            None if m.mastery_recognize is None else float(m.mastery_recognize), correct)
        if not correct:
            m.wrong_count = (m.wrong_count or 0) + 1
        m.last_seen_at = datetime.now(timezone.utc)
        m.prior_source = "learn"
        qid = uuid.uuid5(uuid.NAMESPACE_OID, f"grammar-grouped:{kp_id}")
        await mastery_judge_service.log_answer(
            db, student_id=student_id, q_scope="platform", question_id=qid,
            node_id=None, is_correct=correct, feature="grammar_group")
        results.append({
            "kp_id": str(kp_id), "kp_name": kp.name, "correct": correct,
            "correct_answer": correct_answer,
            "recognize": round(float(m.mastery_recognize or 0), 4),
            "mastered": _axes_mastered(
                float(m.mastery_recognize or 0), float(m.mastery_detect or 0),
                float(m.mastery_produce or 0), bool(m.transfer_ok)),
        })
    await db.flush()
    return {"results": results}


# ── 间隔复测(保持,R10.5)────────────────────────────────────────────────
def _maybe_schedule_retention(m: StudentGrammarMastery) -> None:
    """四维门槛首次达成 → 排首次复测(≥3 天后用新题考)。"""
    recog = float(m.mastery_recognize or 0)
    detect = float(m.mastery_detect or 0)
    produce = float(m.mastery_produce or 0)
    if _axes_mastered(recog, detect, produce, bool(m.transfer_ok)) and m.mastered_at is None:
        now = datetime.now(timezone.utc)
        ladder = _cfg.cached()["retain_ladder"] or _RETAIN_LADDER
        m.mastered_at = now
        m.retain_interval_days = ladder[0]
        m.next_retain_at = now + timedelta(days=ladder[0])


def confirmed_mastered(m: StudentGrammarMastery | None) -> bool:
    """最终「基本学会」= 四维门槛达成 且 ≥1 次隔期复测通过。"""
    if m is None:
        return False
    return _axes_mastered(
        float(m.mastery_recognize or 0), float(m.mastery_detect or 0),
        float(m.mastery_produce or 0), bool(m.transfer_ok)) and (m.retain_count or 0) >= 1


async def due_retentions(db: AsyncSession, *, student_id: uuid.UUID, limit: int = 50) -> list[dict]:
    """到期待复测的语法点(四维已达、next_retain_at 到期)。"""
    now = datetime.now(timezone.utc)
    rows = (await db.execute(
        sa.select(StudentGrammarMastery, KnowledgePoint.name)
        .join(KnowledgePoint, KnowledgePoint.id == StudentGrammarMastery.kp_id)
        .where(StudentGrammarMastery.student_id == student_id,
               StudentGrammarMastery.mastered_at.isnot(None),
               StudentGrammarMastery.next_retain_at <= now)
        .order_by(StudentGrammarMastery.next_retain_at).limit(limit))).all()
    return [{"kp_id": str(m.kp_id), "kp_name": name, "retain_count": m.retain_count,
             "due_at": m.next_retain_at.isoformat() if m.next_retain_at else None} for m, name in rows]


async def retention_probe(db: AsyncSession, *, student_id: uuid.UUID, kp: KnowledgePoint) -> dict | None:
    """取一道复测题:同点新语境单选(在迁移题池里按已复测次数轮换)。无题→None。"""
    seeds = await _ensure_transfer_seed(db, kp)
    if not seeds:
        return None
    m = await _get_mastery(db, student_id, kp.id)
    idx = (m.retain_count if m else 0) % len(seeds)
    s = seeds[idx]
    return {"probe": {"key": f"transfer:{idx}", "kind": "retention",
                      "prompt": f"隔期复测 · 换个新句子:{s['stem']}", "options": list(s["options"])},
            "interval_days": (m.retain_interval_days if m else _RETAIN_LADDER[0])}


async def submit_retention(db: AsyncSession, *, student_id: uuid.UUID, kp_id: uuid.UUID,
                           key: str, answer: str) -> dict:
    """提交复测:通过→间隔拉长(SM2 阶梯)+ retain_count++;失败→保持回落、重新进入学习。
    verdict=retained(仍记得)/ forgotten(遗忘,需重学)。"""
    kp = (await db.execute(sa.select(KnowledgePoint).where(KnowledgePoint.id == kp_id))).scalar_one_or_none()
    if kp is None:
        raise AppError(code=404, message="知识点不存在")
    seeds = await _ensure_transfer_seed(db, kp)
    try:
        idx = int(key.split(":", 1)[1])
    except (ValueError, IndexError, AttributeError):
        idx = 0
    if idx >= len(seeds):
        raise AppError(code=400, message="复测题不存在")
    correct_answer = str(seeds[idx]["answer"]).strip()
    correct = (answer or "").strip() == correct_answer

    m = await _get_or_create_mastery(db, student_id, kp_id)
    now = datetime.now(timezone.utc)
    m.mastery_recognize = mastery_judge_service.bkt_update(
        None if m.mastery_recognize is None else float(m.mastery_recognize), correct)
    if correct:
        ladder = _cfg.cached()["retain_ladder"] or _RETAIN_LADDER
        m.retain_count = (m.retain_count or 0) + 1
        m.last_retain_at = now
        step = ladder[min(m.retain_count, len(ladder) - 1)]
        m.retain_interval_days = step
        m.next_retain_at = now + timedelta(days=step)
    else:
        # 遗忘:保持回落,迁移作废、清排期 → 重新进入学习环
        m.transfer_ok = False
        m.mastered_at = None
        m.next_retain_at = None
        m.retain_interval_days = 0
        m.wrong_count = (m.wrong_count or 0) + 1
    m.last_seen_at = now
    qid = uuid.uuid5(uuid.NAMESPACE_OID, f"grammar-retain:{kp_id}:{key}")
    await mastery_judge_service.log_answer(
        db, student_id=student_id, q_scope="platform", question_id=qid,
        node_id=None, is_correct=correct, feature="grammar_retention")
    await db.flush()
    return {
        "correct": correct, "correct_answer": correct_answer,
        "verdict": "retained" if correct else "forgotten",
        "retain_count": m.retain_count,
        "next_retain_at": m.next_retain_at.isoformat() if m.next_retain_at else None,
        "confirmed_mastered": confirmed_mastered(m),
        "status": _status_label(m),
    }


def _status_label(m: StudentGrammarMastery | None) -> dict:
    """诚实的可解释掌握标签 + 证据(给学生看)。"""
    if m is None:
        return {"status": "new", "label": "未开始", "evidence": []}
    recog = float(m.mastery_recognize or 0)
    detect = float(m.mastery_detect or 0)
    produce = float(m.mastery_produce or 0)
    tok = bool(m.transfer_ok)
    axes = _axes_mastered(recog, detect, produce, tok)
    if not axes:
        c = _cfg.cached()
        done, todo = [], []
        (done if detect >= c["detect_mastered"] else todo).append("纠错")
        (done if produce >= c["produce_mastered"] else todo).append("产出")
        (done if tok else todo).append("迁移")
        ev = []
        if done:
            ev.append("已过:" + "、".join(done))
        if todo:
            ev.append("还差:" + "、".join(todo))
        return {"status": "learning", "label": "学习中", "evidence": ev}
    if (m.retain_count or 0) >= 1:
        return {"status": "mastered", "label": "已掌握",
                "evidence": ["四维(纠错/产出/迁移)均通过", f"隔期复测 {m.retain_count} 次仍对"]}
    now = datetime.now(timezone.utc)
    if m.next_retain_at and m.next_retain_at <= now:
        return {"status": "due_retain", "label": "待复测",
                "evidence": ["四维已通过", "到期复测一次即可确认掌握"]}
    return {"status": "retaining", "label": "待巩固",
            "evidence": ["四维已通过", f"约 {m.retain_interval_days} 天后复测确认"]}


async def kp_status(db: AsyncSession, *, student_id: uuid.UUID, kp_id: uuid.UUID) -> dict:
    """该语法点对该生的诚实掌握标签 + 各维度。"""
    m = await _get_mastery(db, student_id, kp_id)
    return {
        "kp_id": str(kp_id),
        "recognize": float(m.mastery_recognize or 0) if m else 0.0,
        "detect": float(m.mastery_detect or 0) if m else 0.0,
        "produce_score": float(m.mastery_produce or 0) if m else 0.0,
        "transfer_ok": bool(m.transfer_ok) if m else False,
        "confirmed_mastered": confirmed_mastered(m),
        **_status_label(m),
    }


# ── 内部 ────────────────────────────────────────────────────────────────
def _axes_mastered(recog: float, detect: float, produce: float = 0.0, transfer_ok: bool = False) -> bool:
    """阶段性掌握门槛:纠错 + 产出达阈 且 迁移通过(阈值走后台 grammar_config,常量仅兜底)。"""
    c = _cfg.cached()
    return detect >= c["detect_mastered"] and produce >= c["produce_mastered"] and transfer_ok


async def _get_mastery(db: AsyncSession, student_id: uuid.UUID, kp_id: uuid.UUID):
    return (await db.execute(
        sa.select(StudentGrammarMastery).where(
            StudentGrammarMastery.student_id == student_id,
            StudentGrammarMastery.kp_id == kp_id))).scalar_one_or_none()


async def _get_or_create_mastery(db: AsyncSession, student_id: uuid.UUID, kp_id: uuid.UUID) -> StudentGrammarMastery:
    m = await _get_mastery(db, student_id, kp_id)
    if m is None:
        m = StudentGrammarMastery(id=uuid.uuid4(), student_id=student_id, kp_id=kp_id)
        db.add(m)
        await db.flush()
    return m


# ── 离线预生成(后台异步 + 批量,R10.8;镜像 vocab)────────────────────────
_GEN_INFLIGHT: set = set()   # 去重:正在后台生成中的 kp_id


async def _bg_generate(kp_ids: list, *, budget_tokens: int = 80_000) -> None:
    """后台逐点生成语法探针:独立 session、缺失才生成、带 token 预算上限。"""
    from app.core.database import _async_session_factory
    try:
        with usage_log_service.budget(budget_tokens):
            for kid in kp_ids:
                if usage_log_service.over_budget():
                    _log.warning("[grammar-probe-bg] 预算用尽,停止预生成")
                    break
                try:
                    async with _async_session_factory() as db:
                        kp = (await db.execute(
                            sa.select(KnowledgePoint).where(KnowledgePoint.id == kid))).scalar_one_or_none()
                        if kp is None or ((kp.grammar_probes_json or {}).get("recognize")
                                          and (kp.grammar_probes_json or {}).get("detect")):
                            continue   # 不存在或已缓存 → 跳过
                        await ensure_probes(db, kp)
                        await db.commit()
                except Exception:  # noqa: BLE001
                    _log.exception("[grammar-probe-bg] 生成失败 kp_id=%s", kid)
                finally:
                    _GEN_INFLIGHT.discard(kid)
    finally:
        for kid in kp_ids:
            _GEN_INFLIGHT.discard(kid)


def enqueue_probe_gen(kp_ids, *, cap: int = 80) -> int:
    """登记若干语法点在后台异步预生成探针(立即返回,不阻塞请求)。

    KP 级公共缓存:同点全网只生成一次;去重在途;单次入队 cap 上限。
    无事件循环(同步脚本)时跳过,交给 cron 兜底。返回真正入队数。
    """
    import asyncio
    fresh: list = []
    for kid in (kp_ids or []):
        try:
            kid = kid if isinstance(kid, uuid.UUID) else uuid.UUID(str(kid))
        except (ValueError, TypeError):
            continue
        if kid in _GEN_INFLIGHT:
            continue
        _GEN_INFLIGHT.add(kid)
        fresh.append(kid)
        if len(fresh) >= cap:
            break
    if not fresh:
        return 0
    try:
        asyncio.get_running_loop()
        asyncio.create_task(_bg_generate(fresh))
    except RuntimeError:
        for kid in fresh:
            _GEN_INFLIGHT.discard(kid)
        return 0
    return len(fresh)


async def backfill_probes(db: AsyncSession, *, limit: int | None = None,
                          only_missing: bool = True, max_tokens_budget: int | None = 200_000) -> dict:
    """批量给语法点生成探针库。累计 token 超预算即停。返回 {scanned, filled, stopped, spent_tokens}。"""
    rows = (await db.execute(
        sa.select(KnowledgePoint).where(KnowledgePoint.category == "grammar"))).scalars().all()
    scanned = filled = 0
    stopped = False
    with usage_log_service.budget(max_tokens_budget):
        for kp in rows:
            if usage_log_service.over_budget():
                stopped = True
                break
            if only_missing and (kp.grammar_probes_json or {}).get("recognize") \
                    and (kp.grammar_probes_json or {}).get("detect"):
                continue
            scanned += 1
            before = usage_log_service.spent()
            p = await ensure_probes(db, kp)
            if (p or {}).get("recognize") and usage_log_service.spent() > before:
                filled += 1
            if limit and filled >= limit:
                break
        spent = usage_log_service.spent()
    await db.commit()
    return {"scanned": scanned, "filled": filled, "stopped": stopped, "spent_tokens": spent}
