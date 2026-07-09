"""个人知识点掌握台账服务（M39）。

所有写入通过 upsert_mastery 完成，调用方负责 commit。
查询通过 get_mastery_tree，按正确率升序返回（弱项在前）。

来源标识符约定：
  'practice'      — 自适应练习（AI 生成题）
  'paper_upload'  — 学生上传整卷
  'assignment'    — 教师布置作业
  'wrong_question'— 错题 AI 分析
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d4_knowledge import StudentKpMastery, KpMasterySnapshot

# 合法来源标识符
KpSource = Literal["practice", "paper_upload", "assignment", "wrong_question"]

# ── 复习建议规则（M6c，单一来源；diagnosis_service / relative 端点共用）──────────
_WEAK_THRESHOLD = 0.4    # 正确率 < 0.4 视为薄弱
_MEDIUM_THRESHOLD = 0.7  # 0.4 ≤ 正确率 < 0.7 视为待巩固
_STALE_DAYS = 14         # 超过 N 天未练习 → 提醒复习

# ── 加权掌握度(m139;替代裸正确率)──────────────────────────────────────────────
# 裸正确率(correct/total)对小样本(3对3=100%)/少量错误误导。改为加权:基数下限 10
# 压小样本、错罚重、订正回收部分分。四计数器见 student_kp(fa_correct/fa_wrong/
# corrected_count/redo_wrong_count),写入见 mastery_judge_service.log_answer(首答)与
# wrong_review_service(订正对/错)。分档沿用上面的 0.4/0.7 阈值。
MASTERY_BASE = 10           # 分母下限(证据基数);事件数 < 10 时按 10 计
W_CORRECT = 1.0
W_WRONG = -1.5
W_REDO_OK = 0.3
W_REDO_BAD = -0.3


def weighted_mastery(
    fa_correct: int, fa_wrong: int, corrected: int, redo_wrong: int
) -> tuple[float, int]:
    """加权掌握度。返回 (掌握度 0–1, 事件数 C)。

    S = 1·首答对 − 1.5·首答错 + 0.3·订正对 − 0.3·订正错
    C = 首答对 + 首答错 + 订正对 + 订正错 ; D = max(10, C) ; m = clamp(S/D, 0, 1)
    C < 10 视为证据不足(调用方可据此提示「需更多练习」)。
    """
    fa_correct = fa_correct or 0
    fa_wrong = fa_wrong or 0
    corrected = corrected or 0
    redo_wrong = redo_wrong or 0
    s = (W_CORRECT * fa_correct + W_WRONG * fa_wrong
         + W_REDO_OK * corrected + W_REDO_BAD * redo_wrong)
    c = fa_correct + fa_wrong + corrected + redo_wrong
    d = max(MASTERY_BASE, c)
    m = s / d
    return max(0.0, min(1.0, round(m, 4))), c


def review_suggestion(
    *, accuracy: float, total: int, days_since: int | None
) -> tuple[str, str]:
    """根据正确率与活跃度生成 (level, suggestion)。纯规则，不调 AI。

    level ∈ {weak, medium, good}；suggestion 为中文建议文案。
    """
    if accuracy < _WEAK_THRESHOLD:
        level = "weak"
        msg = "薄弱项，建议优先做专项练习，从基础题逐步加难。"
    elif accuracy < _MEDIUM_THRESHOLD:
        level = "medium"
        msg = "已有基础但不稳，再多练几组巩固熟练度。"
    else:
        level = "good"
        msg = "掌握较好，保持节奏并定期回顾防遗忘。"
    if total < 3:
        msg = "练习量偏少，建议先多做几题以获得可靠评估。"
    if days_since is not None and days_since >= _STALE_DAYS:
        msg += f"（已 {days_since} 天未练习，注意及时复习）"
    return level, msg


async def get_kp_mastery_nodes(db: AsyncSession, *, student_id: uuid.UUID) -> list[dict]:
    """B:个人知识点掌握(node 维度,直读新表 student_kp)→ /kp-mastery 形状。弱项在前。"""
    from app.models.d15_knowledge_graph import KnowledgeNode
    from app.models.d16_question_domain import StudentKp
    rows = (await db.execute(
        select(StudentKp.node_id, KnowledgeNode.name, KnowledgeNode.description,
               StudentKp.practice_count, StudentKp.wrong_count, StudentKp.source_tags,
               StudentKp.last_practice_at,
               StudentKp.fa_correct, StudentKp.fa_wrong,
               StudentKp.corrected_count, StudentKp.redo_wrong_count)
        .join(KnowledgeNode, KnowledgeNode.id == StudentKp.node_id)
        .where(StudentKp.student_id == student_id)
    )).all()
    out = []
    for nid, name, desc, pc, wc, tags, last, fac, faw, kc, kf in rows:
        correct = max((pc or 0) - (wc or 0), 0)
        total = correct + (wc or 0)
        mastery, events = weighted_mastery(fac, faw, kc, kf)
        out.append({
            "kp_key": name, "kp_id": nid, "kp_description": desc,
            "correct_count": correct, "wrong_count": wc or 0,
            "accuracy": round(correct / total, 4) if total else 0.0,  # 兼容:原始正确率
            "mastery": mastery,          # 加权掌握度 0–1(展示口径)
            "mastery_events": events,    # 事件数 C;< 10 证据不足
            "sources": list(tags or []),
            "last_activity_at": last.isoformat() if last else None,
        })
    # 弱项在前:按加权掌握度升序(证据越少越靠不确定,用事件数补足次序)
    out.sort(key=lambda x: (x["mastery"], -x["mastery_events"]))
    return out


async def get_kp_mastery_trend(
    db: AsyncSession, *, student_id: uuid.UUID, node_id: uuid.UUID, days: int = 30
) -> list[dict]:
    """某 node 近 N 天的**加权掌握度**日趋势(从 answer_log 逐事件重放,无需历史快照)。

    重放规则与写侧(log_answer / wrong_review._grade_and_log)一致:
      · 非订正(feature!='review')且该题首次出现 → 首答对/错(fa)。
      · 订正(feature='review'):答对且该题首次订正对 → Kc;答错 → Kf(每次)。
    每个事件后按 weighted_mastery 计当前掌握度,同一天以最后一个事件为准(日末值)。
    返回按日期升序、仅活动日的点:[{date, mastery, mastery_events}]。
    """
    from datetime import date as _date, timedelta
    from app.models.d16_question_domain import AnswerLog

    rows = (await db.execute(
        select(AnswerLog.question_id, AnswerLog.is_correct,
               AnswerLog.feature, AnswerLog.answered_at)
        .where(AnswerLog.student_id == student_id, AnswerLog.node_id == node_id)
        .order_by(AnswerLog.answered_at.asc())
    )).all()

    fa_c = fa_w = kc = kf = 0
    seen: set = set()          # 出现过的题(判首次)
    review_ok: set = set()     # 已计过订正对的题(Kc 每题一次)
    by_day: dict[str, dict] = {}
    for qid, is_correct, feature, answered_at in rows:
        first_seen = qid not in seen
        if feature != "review":
            if first_seen:
                if is_correct:
                    fa_c += 1
                else:
                    fa_w += 1
        else:
            if is_correct:
                if qid not in review_ok:
                    kc += 1
                    review_ok.add(qid)
            else:
                kf += 1
        seen.add(qid)
        m, c = weighted_mastery(fa_c, fa_w, kc, kf)
        day = answered_at.date().isoformat()
        by_day[day] = {"date": day, "mastery": m, "mastery_events": c}   # 日末值

    since = (_date.today() - timedelta(days=days - 1)).isoformat()
    return sorted((p for d, p in by_day.items() if d >= since),
                  key=lambda p: p["date"])


async def upsert_mastery(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    kp_key: str,
    kp_id: uuid.UUID | None,
    is_correct: bool,
    source: KpSource,
    kp_description: str | None = None,
) -> None:
    """UPSERT 一次答题结果到个人知识点台账。

    - 原子性累加 correct_count / wrong_count（PostgreSQL ON CONFLICT DO UPDATE）
    - source 合并到 sources 数组（PostgreSQL array_append + DISTINCT，去重）
    - kp_description 仅首次写入（已有值则保留）
    - 不 commit，由调用方负责
    """
    delta_correct = 1 if is_correct else 0
    delta_wrong = 0 if is_correct else 1
    now = datetime.now(timezone.utc)

    stmt = pg_insert(StudentKpMastery).values(
        student_id=student_id,
        kp_key=kp_key,
        kp_id=kp_id,
        correct_count=delta_correct,
        wrong_count=delta_wrong,
        sources=[source],
        kp_description=kp_description,
        last_activity_at=now,
    ).on_conflict_do_update(
        index_elements=["student_id", "kp_key"],
        set_={
            "correct_count": StudentKpMastery.correct_count + delta_correct,
            "wrong_count": StudentKpMastery.wrong_count + delta_wrong,
            # 合并来源：用 PostgreSQL array 去重（避免 Python 层竞态）
            "sources": text(
                "ARRAY(SELECT DISTINCT unnest(student_kp_mastery.sources || ARRAY[:src]))"
            ).bindparams(src=source),
            # kp_description 仅首次写入有值时填入，已有值保留
            "kp_description": text(
                "COALESCE(student_kp_mastery.kp_description, :desc)"
            ).bindparams(desc=kp_description),
            "last_activity_at": now,
            # kp_id 首次写入后固定，不覆盖
            "kp_id": StudentKpMastery.kp_id,
        },
    )
    await db.execute(stmt)

    # ── 日快照（M46）─────────────────────────────────────────────────────────
    # 读取更新后的台账行，写入/更新当天快照（每 UTC 日期最多一行）
    today = now.date()
    row = (await db.execute(
        select(StudentKpMastery).where(
            StudentKpMastery.student_id == student_id,
            StudentKpMastery.kp_key == kp_key,
        )
    )).scalar_one_or_none()

    if row is not None:
        total = row.correct_count + row.wrong_count
        snap_accuracy = row.correct_count / total if total > 0 else 0.0
        snap_stmt = pg_insert(KpMasterySnapshot).values(
            student_id=student_id,
            kp_key=kp_key,
            snapshot_date=today,
            accuracy=snap_accuracy,
            correct_count=row.correct_count,
            wrong_count=row.wrong_count,
            recorded_at=now,
        ).on_conflict_do_update(
            constraint="uq_kp_snapshot_student_kp_date",
            set_={
                "accuracy": snap_accuracy,
                "correct_count": row.correct_count,
                "wrong_count": row.wrong_count,
                "recorded_at": now,
            },
        )
        await db.execute(snap_stmt)

    # ── B:同步补写新域 student_kp(node 维度,供 /kp-mastery 直读新表)──────────────
    # kp_key(名)精确解析到句法/知识 node(node_alias);命中才补写,不创建候选、失败不阻断主台账。
    try:
        from app.models.d15_knowledge_graph import NodeAlias
        from app.models.d16_question_domain import StudentKp
        from app.services.kp_normalize import normalize_kp_name
        node_id = (await db.execute(
            select(NodeAlias.node_id).where(NodeAlias.alias_norm == normalize_kp_name(kp_key))
        )).scalar_one_or_none()
        if node_id is not None:
            await db.execute(
                pg_insert(StudentKp).values(
                    student_id=student_id, node_id=node_id,
                    practice_count=1, wrong_count=delta_wrong,
                    last_practice_at=now, source_tags=[source], in_scope=True,
                ).on_conflict_do_update(
                    index_elements=["student_id", "node_id"],
                    set_={
                        "practice_count": StudentKp.practice_count + 1,
                        "wrong_count": StudentKp.wrong_count + delta_wrong,
                        "last_practice_at": now,
                        "source_tags": text(
                            "ARRAY(SELECT DISTINCT unnest(student_kp.source_tags || ARRAY[:src]))"
                        ).bindparams(src=source),
                        "in_scope": True,
                    },
                ))
    except Exception:  # noqa: BLE001
        pass


async def get_kp_trend(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    kp_key: str,
    days: int = 30,
) -> list[dict]:
    """返回指定 KP 的历史趋势快照（最近 days 天，按日期 ASC）。

    返回格式：[{date: "YYYY-MM-DD", accuracy: float, correct_count: int, wrong_count: int}, ...]
    """
    from datetime import timedelta
    since = datetime.now(timezone.utc).date() - timedelta(days=days - 1)

    rows = (await db.execute(
        select(KpMasterySnapshot)
        .where(
            KpMasterySnapshot.student_id == student_id,
            KpMasterySnapshot.kp_key == kp_key,
            KpMasterySnapshot.snapshot_date >= since,
        )
        .order_by(KpMasterySnapshot.snapshot_date.asc())
    )).scalars().all()

    return [
        {
            "date": str(r.snapshot_date),
            "accuracy": round(r.accuracy, 4),
            "correct_count": r.correct_count,
            "wrong_count": r.wrong_count,
        }
        for r in rows
    ]


async def get_mastery_tree_for_teacher(
    db: AsyncSession,
    *,
    teacher_id: uuid.UUID,
    student_id: uuid.UUID,
) -> list["MasteryRow"]:
    """教师查学生 KP 台账，先鉴权（学生须绑定该教师）。

    未绑定 → 抛 AppError(403)。
    """
    from sqlalchemy import select as _sel
    from app.models.d1_users import TeacherStudent
    from app.core.exceptions import AppError

    rel = (await db.execute(
        _sel(TeacherStudent).where(
            TeacherStudent.teacher_id == teacher_id,
            TeacherStudent.student_id == student_id,
            TeacherStudent.status == "active",
        )
    )).scalar_one_or_none()

    if rel is None:
        raise AppError(code=403, message="该学生未绑定到您，无法查看其知识点台账")

    return await get_mastery_tree(db, student_id=student_id)


async def get_class_kp_stats(
    db: AsyncSession,
    *,
    teacher_id: uuid.UUID,
    class_id: uuid.UUID,
) -> dict:
    """聚合班级 KP 统计数据。

    返回结构：
      class_id, class_name, student_count
      top_weak_kps       — 全班平均正确率最低的 KP（≤10 条），按 avg_accuracy ASC
        · kp_key, avg_accuracy, student_count（有记录人数）,
          weak_count（<60%人数）, mastered_count（≥80%人数）
      students_attention — 全班平均正确率最低的学生（≤5 条），按 avg_accuracy ASC
        · student_id, nickname, avg_accuracy, weak_kp_count, total_kp_count
    """
    from collections import defaultdict
    from app.models.d1_users import User as _U
    from app.models.d7_teacher import ClassStudent
    from app.core.exceptions import AppError
    from app.services.class_service import _get_owned_class

    cls = await _get_owned_class(db, teacher_id=teacher_id, class_id=class_id)

    # 获取班级所有学生 ID
    student_ids = list(
        (await db.execute(
            select(ClassStudent.student_id).where(ClassStudent.class_id == class_id)
        )).scalars().all()
    )

    if not student_ids:
        return {
            "class_id": str(class_id),
            "class_name": cls.name,
            "student_count": 0,
            "top_weak_kps": [],
            "students_attention": [],
        }

    # 批量查台账（一次 SQL，按 student_id IN）——R8.1:读 student_kp(node),按 name 当 kp_key
    from app.models.d16_question_domain import StudentKp
    from app.models.d15_knowledge_graph import KnowledgeNode
    _ClsRow = _namedtuple("_ClsRow", "student_id kp_key correct_count wrong_count")
    mastery_rows = [
        _ClsRow(sid, name, max((pc or 0) - (wc or 0), 0), wc or 0)
        for sid, name, pc, wc in (await db.execute(
            select(StudentKp.student_id, KnowledgeNode.name,
                   StudentKp.practice_count, StudentKp.wrong_count)
            .join(KnowledgeNode, KnowledgeNode.id == StudentKp.node_id)
            .where(StudentKp.student_id.in_(student_ids), StudentKp.practice_count > 0)
        )).all()
    ]

    # 拿学生昵称
    nick_map: dict[str, str | None] = {
        str(row.id): row.nickname
        for row in (await db.execute(
            select(_U.id, _U.nickname).where(_U.id.in_(student_ids))
        )).all()
    }

    # ── 按 kp_key 聚合 ──────────────────────────────────────────────────
    kp_data: dict[str, list[float]] = defaultdict(list)  # kp_key → [accuracy, ...]
    for row in mastery_rows:
        total = row.correct_count + row.wrong_count
        if total == 0:
            continue
        acc = row.correct_count / total
        kp_data[row.kp_key].append(acc)

    top_weak_kps = []
    for kp_key, accs in kp_data.items():
        avg_acc = sum(accs) / len(accs)
        top_weak_kps.append({
            "kp_key": kp_key,
            "avg_accuracy": round(avg_acc, 4),
            "student_count": len(accs),
            "weak_count": sum(1 for a in accs if a < 0.6),
            "mastered_count": sum(1 for a in accs if a >= 0.8),
        })
    top_weak_kps.sort(key=lambda x: x["avg_accuracy"])
    top_weak_kps = top_weak_kps[:10]

    # ── 按 student_id 聚合 ──────────────────────────────────────────────
    stu_data: dict[str, list[float]] = defaultdict(list)
    for row in mastery_rows:
        total = row.correct_count + row.wrong_count
        if total == 0:
            continue
        acc = row.correct_count / total
        stu_data[str(row.student_id)].append(acc)

    students_attention = []
    for stu_id_str, accs in stu_data.items():
        avg_acc = sum(accs) / len(accs)
        weak_kp_count = sum(1 for a in accs if a < 0.6)
        students_attention.append({
            "student_id": stu_id_str,
            "nickname": nick_map.get(stu_id_str),
            "avg_accuracy": round(avg_acc, 4),
            "weak_kp_count": weak_kp_count,
            "total_kp_count": len(accs),
        })
    students_attention.sort(key=lambda x: x["avg_accuracy"])
    students_attention = students_attention[:5]

    return {
        "class_id": str(class_id),
        "class_name": cls.name,
        "student_count": len(student_ids),
        "top_weak_kps": top_weak_kps,
        "students_attention": students_attention,
    }


from collections import namedtuple as _namedtuple

# R8.1:掌握台账统一到 node。get_mastery_tree 直读 student_kp(node),不再读旧
# student_kp_mastery(kp_key)。返回与旧台账**字段等价**的轻量行,消费者(diagnosis/
# learning_plan/teacher/relative)按属性取用无需改。correct = practice_count − wrong_count。
MasteryRow = _namedtuple(
    "MasteryRow", "kp_key kp_id kp_description correct_count wrong_count last_activity_at sources")


async def get_mastery_tree(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
) -> list["MasteryRow"]:
    """返回当前学生的知识点树(node 维度),按正确率升序(弱项在前)。

    正确率 = correct_count / (correct_count + wrong_count)，total=0 时视为 0。
    R8.1:读 student_kp join knowledge_nodes(替代旧 student_kp_mastery)。
    """
    from app.models.d15_knowledge_graph import KnowledgeNode
    from app.models.d16_question_domain import StudentKp
    rows = (await db.execute(
        select(StudentKp.node_id, KnowledgeNode.name, KnowledgeNode.description,
               StudentKp.practice_count, StudentKp.wrong_count, StudentKp.last_practice_at,
               StudentKp.source_tags)
        .join(KnowledgeNode, KnowledgeNode.id == StudentKp.node_id)
        .where(StudentKp.student_id == student_id)
        .order_by(
            text(
                "CASE WHEN student_kp.practice_count = 0 THEN 0.0 "
                "ELSE (student_kp.practice_count - student_kp.wrong_count)::float "
                "/ student_kp.practice_count END ASC"
            ),
            StudentKp.last_practice_at.desc().nulls_last(),
        )
    )).all()
    return [
        MasteryRow(kp_key=name, kp_id=nid, kp_description=desc,
                   correct_count=max((pc or 0) - (wc or 0), 0), wrong_count=wc or 0,
                   last_activity_at=last, sources=list(tags or []))
        for nid, name, desc, pc, wc, last, tags in rows
    ]
