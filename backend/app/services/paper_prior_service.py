"""R10.7 纸质作业/试卷 → 语法分级先验(错题找洞)。

设计见 docs/R10-...§5。核心:**错题可信(找洞)、对题不可信(只当候选)**。
- 数据源:R3 错题闭环 wrong_record(node_id 指向规范受控树 knowledge_nodes;
  上传真题/错题经 classify_kps→match_kp 命中 node 后 record_wrong 落库),限语法(词法/句法)子树。
- 加权:新近度衰减(半衰期默认 90 天)+ 已复盘掌握(status=mastered)的错题打折。
- 只设起始先验(prior_source=paper,低置信),**不当掌握证据**;真会由日常四维 + 间隔环坐实。
- 优先级:learn(实练)> paper(错题)> placement(测验推断)> default。
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d16_question_domain import WrongRecord
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d4_knowledge import StudentGrammarMastery
from app.services import grammar_config_service as _cfg
from app.services import grammar_node_service as gn

_log = logging.getLogger(__name__)

HALF_LIFE_DAYS = 90        # 兜底:新近度半衰期(实际见 grammar_config.paper_half_life_days)
_MASTERED_DISCOUNT = 0.3   # 兜底:已掌握错题信号折扣(实际见 grammar_config.paper_mastered_discount)
_WEAK_PRIOR_FLOOR = 0.10   # 强新鲜错题 → 先验下探到 0.10(洞)
_WEAK_PRIOR_CEIL = 0.40    # 旧/已掌握错题 → 至多到 0.40(临界)


def _recency(now: datetime, created_at: datetime, half_life: float) -> float:
    """新近度权重 ∈ (0,1]:越近越接近 1,按半衰期指数衰减。"""
    if created_at is None:
        return 0.5
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (now - created_at).total_seconds() / 86400.0)
    return 0.5 ** (age_days / max(1.0, half_life))


async def compute_paper_priors(db: AsyncSession, *, student_id: uuid.UUID,
                               half_life_days: int = HALF_LIFE_DAYS) -> dict:
    """从 R3 错题闭环(wrong_record,限语法子树)算每个语法点的"洞"先验。
    返回 {priors:{node_id:{name,prior,errors,signal}}, weak_kps:[...]}。"""
    cfg = await _cfg.get_config(db)
    half_life_days = int(cfg.get("paper_half_life_days", half_life_days))
    discount = float(cfg.get("paper_mastered_discount", _MASTERED_DISCOUNT))
    sub = await gn.grammar_subtree_ids(db)
    if not sub:
        return {"priors": {}, "weak_kps": []}
    rows = (await db.execute(
        sa.select(WrongRecord.created_at, WrongRecord.status, KnowledgeNode.id, KnowledgeNode.name)
        .join(KnowledgeNode, KnowledgeNode.id == WrongRecord.node_id)
        .where(WrongRecord.student_id == student_id, WrongRecord.node_id.in_(sub)))).all()
    now = datetime.now(timezone.utc)
    agg: dict = {}   # node_id -> {name, signal, errors}
    for created_at, status, nid, name in rows:
        w = _recency(now, created_at, half_life_days)
        if status == "mastered":         # 已复盘掌握的错题:信号打折
            w *= discount
        a = agg.setdefault(str(nid), {"name": name, "signal": 0.0, "errors": 0})
        a["signal"] = max(a["signal"], w)
        a["errors"] += 1
    priors = {}
    for nid, a in agg.items():
        prior = round(_WEAK_PRIOR_FLOOR + (1 - a["signal"]) * (_WEAK_PRIOR_CEIL - _WEAK_PRIOR_FLOOR), 4)
        priors[nid] = {"name": a["name"], "prior": prior, "errors": a["errors"],
                       "signal": round(a["signal"], 4)}
    weak = sorted(priors.items(), key=lambda kv: kv[1]["prior"])
    return {"priors": priors, "weak_kps": [{"kp_id": k, **v} for k, v in weak]}


async def apply_paper_priors(db: AsyncSession, *, student_id: uuid.UUID,
                             half_life_days: int = HALF_LIFE_DAYS) -> dict:
    """把纸质错题先验写入 student_grammar_mastery(prior_source=paper,不覆盖 learn)。
    返回 {applied, skipped, weak_kps}。"""
    out = await compute_paper_priors(db, student_id=student_id, half_life_days=half_life_days)
    now = datetime.now(timezone.utc)
    applied = skipped = 0
    for kid, info in out["priors"].items():
        m = (await db.execute(sa.select(StudentGrammarMastery).where(
            StudentGrammarMastery.student_id == student_id,
            StudentGrammarMastery.kp_id == uuid.UUID(kid)))).scalar_one_or_none()
        if m is None:
            m = StudentGrammarMastery(id=uuid.uuid4(), student_id=student_id, kp_id=uuid.UUID(kid))
            db.add(m)
        # 不覆盖学生已实练出的掌握(learn);可覆盖 default / placement 推断
        if m.prior_source in (None, "default", "placement"):
            m.mastery_recognize = info["prior"]
            m.prior_source = "paper"
            m.last_seen_at = now
            applied += 1
        else:
            skipped += 1
    await db.flush()
    return {"applied": applied, "skipped": skipped, "weak_kps": out["weak_kps"]}
