"""R10 §13 语法推进环 / 学习路径引擎(地基稳后:从"补洞"切到"推进")。

设计见 docs/R10-...§13。三股流按配比交织,优先级引擎选下一步,跳测加速。
- ① 新点推进(i+1):沿难度序选下一个未掌握、已解锁的点(最近发展区)。
- ② 间隔维持:到期复测的已掌握点(防遗忘,复用 grammar_probe_service.due_retentions)。
- ③ 综合运用:把已掌握点导向长难句/写作/真题(Bloom 上行,跨模块,这里给指引)。
- 优先级:已解锁(前置已掌握)× 课程临近 × 考点权重 × 未掌握。
- 跳测(compaction):对即将学的点先迷你 placement,已会的跳过。
配比/每日量走 grammar_config(运营可配)。
"""
from __future__ import annotations

import logging
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d4_knowledge import StudentGrammarMastery
from app.models.d1_users import User


async def _student_scope(db: AsyncSession, student_id: uuid.UUID,
                         textbook: str | None, grade: str | None) -> tuple[str | None, str | None]:
    """未显式指定时,用学生教材偏好圈题库(译林初二语法点)。"""
    if textbook and grade:
        return textbook, grade
    u = (await db.execute(sa.select(User).where(User.id == student_id))).scalars().first()
    return (textbook or (u.preferred_textbook_version if u else None),
            grade or (u.preferred_grade if u else None))
from app.services import grammar_probe_service as gp
from app.services import grammar_placement_service as pl
from app.services import grammar_config_service as _cfg

_log = logging.getLogger(__name__)


async def _scored_pool(db: AsyncSession, *, student_id: uuid.UUID, textbook: str | None,
                       grade: str | None) -> list[dict]:
    """难度序题库 + 学生掌握,算每点"是否已确认掌握 + 优先级分"。"""
    pool = await pl.build_pool(db, textbook=textbook, grade=grade)
    if not pool:
        return []
    ids = [uuid.UUID(d["kp_id"]) for d in pool]
    rows = (await db.execute(sa.select(StudentGrammarMastery).where(
        StudentGrammarMastery.student_id == student_id,
        StudentGrammarMastery.kp_id.in_(ids)))).scalars().all()
    by_kp = {str(m.kp_id): m for m in rows}
    out = []
    n = len(pool)
    # 已确认掌握的点(用于"已解锁"判断:前置基本掌握才放出新点)
    prev_mastered = 0
    for i, d in enumerate(pool):
        m = by_kp.get(d["kp_id"])
        done = gp.confirmed_mastered(m)
        recog = float(m.mastery_recognize) if m and m.mastery_recognize is not None else 0.0
        # 课程临近:越靠前(地基/i+1)越优先 → (n-i)/n
        proximity = (n - i) / n
        # 已解锁:之前的点里已掌握比例越高越解锁(无显式 DAG,用累计近似)
        unlocked = 1.0 if i == 0 else min(1.0, prev_mastered / i + 0.3)
        # 未掌握程度(越不会越该学,但太低可能前置缺失,稍降)
        gap = 1.0 - recog
        score = round(unlocked * proximity * gap, 4)
        out.append({"kp_id": d["kp_id"], "name": d["name"], "index": i,
                    "confirmed_mastered": done, "recognize": round(recog, 4),
                    "unlocked": round(unlocked, 3), "score": score})
        if done:
            prev_mastered += 1
    return out


async def daily_batch(db: AsyncSession, *, student_id: uuid.UUID,
                      textbook: str | None = None, grade: str | None = None) -> dict:
    """组装推进环每日批次:间隔维持 + 新点推进 + 综合运用(按配比)。"""
    textbook, grade = await _student_scope(db, student_id, textbook, grade)
    c = await _cfg.get_config(db)
    size = int(c.get("daily_batch_size", 12))
    r_new = float(c.get("stream_new", 0.70))
    r_maintain = float(c.get("stream_maintain", 0.20))
    r_apply = float(c.get("stream_apply", 0.10))

    # ② 间隔维持:到期复测
    due = await gp.due_retentions(db, student_id=student_id, limit=size)
    n_maintain = min(len(due), max(0, round(size * r_maintain)))
    maintain = due[:n_maintain]

    # ① 新点推进:未掌握、按优先级
    scored = await _scored_pool(db, student_id=student_id, textbook=textbook, grade=grade)
    candidates = [s for s in scored if not s["confirmed_mastered"]]
    # 已确认掌握点数:统计学生全部 grammar 掌握(不限当前题库),供"综合运用"判断
    all_m = (await db.execute(sa.select(StudentGrammarMastery).where(
        StudentGrammarMastery.student_id == student_id))).scalars().all()
    mastered_cnt = sum(1 for m in all_m if gp.confirmed_mastered(m))
    candidates.sort(key=lambda s: (-s["score"], s["index"]))
    n_new = max(0, round(size * r_new))
    new_items = candidates[:n_new]

    # ③ 综合运用:已掌握点导向跨模块整合(Bloom 上行)——给指引,不深耦合
    n_apply = max(0, round(size * r_apply))
    apply = None
    if mastered_cnt >= 2 and n_apply > 0:
        apply = {"type": "integrated", "mastered_kp_count": mastered_cnt, "suggest_count": n_apply,
                 "hint": "把已掌握的语法点放进长难句 / 写作 / 真题里综合运用",
                 "targets": ["long_sentence", "essay", "exam_sim"]}

    return {
        "batch_size": size,
        "ratios": {"new": r_new, "maintain": r_maintain, "apply": r_apply},
        "maintain": maintain,                 # 到期复测(走 /grammar/kp/{id}/retention)
        "new": new_items,                     # 新学点(走 /grammar/kp/{id}/probes)
        "apply": apply,                       # 综合运用指引
        "stats": {"pool": len(scored), "mastered": mastered_cnt,
                  "due": len(due), "remaining_new": len(candidates)},
    }


async def skip_ahead(db: AsyncSession, *, student_id: uuid.UUID, kp_ids: list) -> dict:
    """跳测(curriculum compaction):对即将学的点先迷你 placement,已会的直接跳过(高先验)。

    复用分级测验引擎,题库=传入的前向点;通过的点拿到高 mastery_recognize 先验。
    """
    if not kp_ids or len(kp_ids) < 2:
        raise AppError(code=400, message="跳测至少需要 2 个知识点")
    return await pl.start(db, student_id=student_id, kp_ids=kp_ids, use_paper_priors=False)
