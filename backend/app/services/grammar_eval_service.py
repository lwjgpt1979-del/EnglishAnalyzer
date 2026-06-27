"""R10 验证闭环(第0步):用真实错题核对 R10 的「已掌握」判定准不准。

真值来源 = R3 错题闭环 `wrong_record`(node_id 指向规范受控树,做错/拍照/整卷统一收口
record_wrong 落库)——这是当前**唯一真正在流、且带 node 的真实作答**。限语法(词法/句法)子树。

只有错题、没有对题,所以不算「正确率」,而算一个更直接的报警信号:
  **R10 判会(mastered_at 已置)的点,之后又在真题里错了 → 实锤虚高。**
每条 created_at > mastered_at 的错题都是一发反例,不需要对题做分母。
不改产品逻辑,只读统计。配套真值流(刷题对题)后续在第2步补(见 [grammar_eval] note)。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d16_question_domain import WrongRecord
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d4_knowledge import StudentGrammarMastery
from app.services import grammar_node_service as gn
from app.services import grammar_probe_service as gp


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def calibration_report(db: AsyncSession, *, student_id: uuid.UUID | None = None) -> dict:
    sub = await gn.grammar_subtree_ids(db)
    if not sub:
        return {"source": "wrong_record", "note": "无语法子树",
                "mastered_points": 0, "false_mastery_hits": 0, "worst_nodes": []}

    # 1) R10 判定:取所有「判过会」(mastered_at 已置)的 (student,node)
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

    # 2) 真值:语法子树内的真实错题(wrong_record)
    wq = sa.select(WrongRecord.student_id, WrongRecord.node_id, WrongRecord.created_at).where(
        WrongRecord.node_id.in_(sub))
    if student_id:
        wq = wq.where(WrongRecord.student_id == student_id)
    wrongs = (await db.execute(wq)).all()

    # 3) 实锤:判会之后(created_at > mastered_at)又错
    hits = 0
    per_node: dict = {}   # nid -> {hits, last_wrong_at, confirmed, mastered_at}
    for sid, nid, created_at in wrongs:
        v = verdicts.get((sid, nid))
        if not v:
            continue
        ca = _aware(created_at)
        if ca and v["mastered_at"] and ca > v["mastered_at"]:
            hits += 1
            pn = per_node.setdefault(nid, {"hits": 0, "last_wrong_at": ca,
                                           "confirmed": v["confirmed"], "mastered_at": v["mastered_at"]})
            pn["hits"] += 1
            pn["confirmed"] = pn["confirmed"] or v["confirmed"]
            if ca > pn["last_wrong_at"]:
                pn["last_wrong_at"] = ca

    # 4) 虚高榜
    names = {}
    if per_node:
        for nid, nm in (await db.execute(sa.select(KnowledgeNode.id, KnowledgeNode.name).where(
                KnowledgeNode.id.in_(list(per_node.keys()))))).all():
            names[nid] = nm
    now = datetime.now(timezone.utc)
    worst = sorted(
        [{"node_id": str(nid), "name": names.get(nid, "?"), "hits": p["hits"],
          "confirmed": p["confirmed"],
          "days_since_mastered": round((now - p["mastered_at"]).total_seconds() / 86400.0, 1)
          if p["mastered_at"] else None,
          "last_wrong_at": p["last_wrong_at"].isoformat() if p["last_wrong_at"] else None}
         for nid, p in per_node.items()],
        key=lambda d: d["hits"], reverse=True)[:20]

    return {
        "source": "wrong_record",
        "note": "只有错题真值;hits=「R10判会后又错」=实锤虚高;对题正确率分母待第2步刷题真值流补全",
        "mastered_points": mastered_points,           # R10 判过会的语法点数(mastered_at 已置)
        "confirmed_points": confirmed_points,         # 其中已隔期复测坐实
        "false_mastery_hits": hits,                   # 判会后又错的错题总条数
        "affected_points": len(per_node),             # 至少翻车一次的点数
        "false_mastery_point_rate": round(len(per_node) / mastered_points, 4) if mastered_points else None,
        "worst_nodes": worst,                         # 虚高实锤榜(按翻车次数降序)
    }
