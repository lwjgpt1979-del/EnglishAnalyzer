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
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d4_knowledge import KnowledgePoint, StudentGrammarMastery
from app.services import mastery_judge_service
from app.services.llm_provider import complete_json, fast_model, is_llm_dev_mode

_log = logging.getLogger(__name__)

RECOGNIZE_MASTERED = 0.85   # 识别维掌握阈
DETECT_MASTERED = 0.85      # 纠错维掌握阈


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
    return {
        "kp_id": str(kp.id), "kp_name": kp.name, "probes": probes,
        "recognize": recog, "detect": detect,
        "mastered": _axes_mastered(recog, detect),
    }


# ── 判分 + 掌握度(BKT)─────────────────────────────────────────────────
async def submit_probe(db: AsyncSession, *, student_id: uuid.UUID, kp_id: uuid.UUID,
                       key: str, answer: str) -> dict:
    """提交一道探针(recognize/detect):判分 → 对应维 BKT → 错题计数。"""
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

    qid = uuid.uuid5(uuid.NAMESPACE_OID, f"grammar-probe:{kp_id}:{key}")
    await mastery_judge_service.log_answer(
        db, student_id=student_id, q_scope="platform", question_id=qid,
        node_id=None, is_correct=correct, feature="grammar_probe")
    await db.flush()

    recog = float(m.mastery_recognize) if m.mastery_recognize is not None else 0.0
    detect = float(m.mastery_detect) if m.mastery_detect is not None else 0.0
    return {
        "correct": correct, "correct_answer": correct_answer, "misconception": misconception,
        "axis": axis, "recognize": recog, "detect": detect,
        "mastered": _axes_mastered(recog, detect),
    }


# ── 内部 ────────────────────────────────────────────────────────────────
def _axes_mastered(recog: float, detect: float) -> bool:
    """R10.1 阶段性掌握 = 识别 + 纠错均达阈(产出/迁移/间隔留后续步骤补全门槛)。"""
    return recog >= RECOGNIZE_MASTERED and detect >= DETECT_MASTERED


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
