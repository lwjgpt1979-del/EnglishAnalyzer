"""R10 验证闭环(第0+2步):用真实作答核对 R10 的「已掌握」判定准不准。

两路真值,都限语法(词法/句法)子树、都排除 R10 自身探针(探针 log_answer 传 node_id=None,
天然不进 node 聚合;feature notlike 'grammar_%' 再兜一道):

1) 对题真值(分母)= `answer_log`(node_id 已挂)。第2步起刷题对错经 kp_match→node 落 answer_log
   (q_scope=ai/feature=practice),平台/上传真题作答同样落库。→ 能算真实「正确率」。
   已掌握点的事后正确率应高 → 1-正确率 = false_mastery_rate(判定虚高,根因定位)。
2) 纸质错题(补充·只有错)= `wrong_record`(R3 错题闭环,做错/拍照/整卷收口,带 node_id)。
   覆盖不走刷题接口的纸面错题;只有错→只作「判会后又错」实锤,无分母,单列不混入正确率。

预测在前、真值在后:只统计「作答/错题时间 > mastered_at」的,才是对 R10 判定的前瞻校验。
不改产品逻辑,只读统计。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d16_question_domain import AnswerLog, WrongRecord
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d4_knowledge import StudentGrammarMastery
from app.services import grammar_node_service as gn
from app.services import grammar_probe_service as gp


def _acc(c: int, t: int):
    return round(c / t, 4) if t else None


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def calibration_report(db: AsyncSession, *, student_id: uuid.UUID | None = None) -> dict:
    sub = await gn.grammar_subtree_ids(db)
    empty = {"source": "answer_log(对题真值)+wrong_record(纸质错题)", "mastered_points": 0,
             "confirmed_points": 0, "post_mastery": {}, "paper_wrong_after_mastery": {}, "worst_nodes": []}
    if not sub:
        return {**empty, "note": "无语法子树"}

    # 1) R10 判定:所有「判会」(mastered_at 已置)的 (student,node)
    mq = sa.select(StudentGrammarMastery).where(
        StudentGrammarMastery.mastered_at.isnot(None),
        StudentGrammarMastery.kp_id.in_(sub))
    if student_id:
        mq = mq.where(StudentGrammarMastery.student_id == student_id)
    verdicts = {}   # (sid,nid) -> {mastered_at, confirmed}
    for m in (await db.execute(mq)).scalars().all():
        verdicts[(m.student_id, m.kp_id)] = {
            "mastered_at": _aware(m.mastered_at), "confirmed": gp.confirmed_mastered(m)}
    mastered_points = len(verdicts)
    confirmed_points = sum(1 for v in verdicts.values() if v["confirmed"])

    # per-node 聚合(判会后):对题分母 + 纸质错题
    per_node: dict = {}   # nid -> {ans_total, ans_correct, paper_hits, mastered_at, confirmed}

    def _node(nid):
        return per_node.setdefault(nid, {"ans_total": 0, "ans_correct": 0, "paper_hits": 0,
                                         "mastered_at": None, "confirmed": False})

    # 2) 对题真值:answer_log(node 已挂),分「判会后 / 其它」两桶
    aq = sa.select(AnswerLog.student_id, AnswerLog.node_id, AnswerLog.is_correct, AnswerLog.answered_at).where(
        AnswerLog.node_id.in_(sub),
        sa.or_(AnswerLog.feature.is_(None), AnswerLog.feature.notlike("grammar_%")))
    if student_id:
        aq = aq.where(AnswerLog.student_id == student_id)
    post = [0, 0]    # [correct, total] 判会后
    other = [0, 0]   # [correct, total] 未判会/判会前
    for sid, nid, correct, at in (await db.execute(aq)).all():
        v = verdicts.get((sid, nid))
        at = _aware(at)
        is_post = bool(v and v["mastered_at"] and at and at > v["mastered_at"])
        bucket = post if is_post else other
        bucket[1] += 1
        bucket[0] += 1 if correct else 0
        if is_post:
            p = _node(nid)
            p["ans_total"] += 1
            p["ans_correct"] += 1 if correct else 0
            p["mastered_at"] = v["mastered_at"]
            p["confirmed"] = p["confirmed"] or v["confirmed"]

    # 3) 纸质错题(补充·只有错):wrong_record 判会后又错
    wq = sa.select(WrongRecord.student_id, WrongRecord.node_id, WrongRecord.created_at).where(
        WrongRecord.node_id.in_(sub))
    if student_id:
        wq = wq.where(WrongRecord.student_id == student_id)
    paper_hits = 0
    paper_nodes = set()
    for sid, nid, created_at in (await db.execute(wq)).all():
        v = verdicts.get((sid, nid))
        ca = _aware(created_at)
        if v and v["mastered_at"] and ca and ca > v["mastered_at"]:
            paper_hits += 1
            paper_nodes.add(nid)
            p = _node(nid)
            p["paper_hits"] += 1
            p["mastered_at"] = p["mastered_at"] or v["mastered_at"]
            p["confirmed"] = p["confirmed"] or v["confirmed"]

    # 4) 虚高榜:判会点里事后表现最差的(对题正确率低 或 纸质又错)
    names = {}
    if per_node:
        for nid, nm in (await db.execute(sa.select(KnowledgeNode.id, KnowledgeNode.name).where(
                KnowledgeNode.id.in_(list(per_node.keys()))))).all():
            names[nid] = nm
    now = datetime.now(timezone.utc)

    def _worst_key(item):
        # 先按对题正确率升序(无对题数据排后),再按纸质错次降序
        acc = item["accuracy"]
        return (acc if acc is not None else 2.0, -item["paper_hits"])

    worst = sorted(
        [{"node_id": str(nid), "name": names.get(nid, "?"),
          "answers": p["ans_total"], "accuracy": _acc(p["ans_correct"], p["ans_total"]),
          "false_mastery_rate": round(1 - p["ans_correct"] / p["ans_total"], 4) if p["ans_total"] else None,
          "paper_hits": p["paper_hits"], "confirmed": p["confirmed"],
          "days_since_mastered": round((now - p["mastered_at"]).total_seconds() / 86400.0, 1)
          if p["mastered_at"] else None}
         # 只列有「虚高实证」的:对题有错(分母≥2)或纸质又错;全对的干净点不进榜
         for nid, p in per_node.items()
         if (p["ans_total"] >= 2 and p["ans_correct"] < p["ans_total"]) or p["paper_hits"] >= 1],
        key=_worst_key)[:20]

    pm_acc = _acc(*post)
    return {
        "source": "answer_log(对题真值)+wrong_record(纸质错题)",
        "note": "post_mastery=判会后真实作答正确率(分母=对题);false_mastery_rate 高=判定虚高;"
                "paper=纸质错题判会后又错(只有错,单列)",
        "mastered_points": mastered_points,        # R10 判过会的语法点数
        "confirmed_points": confirmed_points,      # 其中已隔期复测坐实
        "post_mastery": {"answers": post[1], "correct": post[0], "accuracy": pm_acc,
                         "false_mastery_rate": round(1 - pm_acc, 4) if pm_acc is not None else None},
        "pre_or_unmastered": {"answers": other[1], "accuracy": _acc(*other),
                              "hint": "此桶正确率高=可能漏判(低估)"},
        "paper_wrong_after_mastery": {"hits": paper_hits, "affected_points": len(paper_nodes)},
        "worst_nodes": worst,
    }
