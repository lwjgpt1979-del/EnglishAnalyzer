"""ProMax 学生自助出卷（功能模块 5C，M51）。

ProMax 专属；每周最多 N 份（默认 3，自然周一 0:00 重置）。
组卷复用 adaptive_question_service.get_adaptive_set（按薄弱点）；
批改复用 question_service.submit_exam_attempts（错题统一落 wrong_questions）。
"""
from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d12_v2_exams import SelfExam
from app.schemas.questions import PracticeAttemptIn
from app.services import (
    adaptive_question_service,
    listening_service,
    membership_service,
    question_service,
)

WEEKLY_QUOTA = 3          # 每周自助出卷份数上限（5C，后台可配留后续）
OBJECTIVE_COUNT = 6       # 客观题数量
TIME_LIMIT_SEC = 1200     # 限时 20 分钟（含听力+客观+写作）

_LETTERS = ["A", "B", "C", "D", "E", "F"]

# 写作题库（MVP：少量固定题，后续可按学期/薄弱点 AI 生成）
_WRITING_PROMPTS = [
    "请以 \"My Weekend\" 为题写一篇 40 词左右的短文，介绍你周末的安排。",
    "请以 \"My Best Friend\" 为题写一篇 40 词左右的短文，描述你最好的朋友。",
    "请以 \"My School\" 为题写一篇 40 词左右的短文，介绍你的学校。",
]


def _week_start(now: datetime) -> datetime:
    monday = now.date() - timedelta(days=now.weekday())
    return datetime.combine(monday, time.min, tzinfo=timezone.utc)


async def is_promax(db: AsyncSession, *, student_id: uuid.UUID) -> bool:
    m = await membership_service.get_active_membership(db, user_id=student_id)
    return m is not None and str(m.tier) == "promax"


async def quota_status(db: AsyncSession, *, student_id: uuid.UUID) -> dict:
    used = (await db.execute(
        select(func.count()).select_from(SelfExam).where(
            SelfExam.student_id == student_id,
            SelfExam.created_at >= _week_start(datetime.now(timezone.utc)),
        )
    )).scalar_one()
    promax = await is_promax(db, student_id=student_id)
    return {
        "is_promax": promax,
        "used": int(used),
        "limit": WEEKLY_QUOTA,
        "remaining": max(0, WEEKLY_QUOTA - int(used)),
    }


async def create_self_exam(db: AsyncSession, *, student_id: uuid.UUID) -> SelfExam:
    if not await is_promax(db, student_id=student_id):
        raise AppError(code=403, message="自助出卷为 ProMax 会员专属功能")
    q = await quota_status(db, student_id=student_id)
    if q["remaining"] <= 0:
        raise AppError(code=429, message=f"本周自助出卷次数已用完（每周 {WEEKLY_QUOTA} 份）")

    aset = await adaptive_question_service.get_adaptive_set(
        db, student_id=student_id, total=OBJECTIVE_COUNT
    )
    if not aset.questions:
        raise AppError(code=400, message="暂无足够可组卷的题目，请先多做练习积累薄弱点")

    snapshot: list[dict] = []

    # ① 听力区：取一段听力素材，整段音频 + 其选择题
    try:
        briefs = listening_service.list_exercises()
        if briefs:
            idx = int(datetime.now(timezone.utc).timestamp()) % len(briefs)
            ex = listening_service.get_exercise(briefs[idx]["id"])
            for i, q in enumerate(ex["questions"]):
                snapshot.append({
                    "id": f"lst-{ex['id']}-{i}",
                    "section": "listening",
                    "question_type": "听力理解",
                    "stem": q["prompt"],
                    "options": q["options"],
                    "answer": _LETTERS[q["answer_index"]],
                    "explanation": q.get("explanation", ""),
                    "audio_text": ex["transcript"],
                })
    except Exception:  # noqa: BLE001
        pass

    # ② 客观区：按薄弱点组卷（沿用 simulated_questions，答案在库、批改时归错题库）
    for x in aset.questions:
        snapshot.append({
            "id": str(x.id),
            "section": "objective",
            "sim_question_id": str(x.id),
            "question_type": str(x.question_type),
            "stem": x.stem,
            "options": x.options,
            "difficulty": x.difficulty,
        })

    # ③ 写作区：1 题（不计入客观分，提交后可去作文精修）
    wprompt = _WRITING_PROMPTS[int(datetime.now(timezone.utc).timestamp()) % len(_WRITING_PROMPTS)]
    snapshot.append({
        "id": "writing-1",
        "section": "writing",
        "question_type": "写作",
        "stem": wprompt,
    })

    se = SelfExam(
        id=uuid.uuid4(),
        student_id=student_id,
        status="answering",
        question_ids=[it["id"] for it in snapshot],
        snapshot=snapshot,
        weak_kps=aset.weak_kp_names,
        time_limit_sec=TIME_LIMIT_SEC,
    )
    db.add(se)
    await db.flush()
    return se


async def get_self_exam(
    db: AsyncSession, *, exam_id: uuid.UUID, student_id: uuid.UUID
) -> SelfExam:
    se = (await db.execute(
        select(SelfExam).where(SelfExam.id == exam_id, SelfExam.student_id == student_id)
    )).scalar_one_or_none()
    if se is None:
        raise AppError(code=404, message="试卷不存在")
    return se


async def submit_self_exam(
    db: AsyncSession, *, exam_id: uuid.UUID, student_id: uuid.UUID, answers: list,
) -> tuple[SelfExam, dict]:
    """多分区批改：听力本地判分、客观沿用 submit_exam_attempts(错题归库)、写作不计分。"""
    se = await get_self_exam(db, exam_id=exam_id, student_id=student_id)
    if str(se.status) == "done":
        raise AppError(code=400, message="该试卷已提交")

    ans_map = {a.question_id: (a.user_answer or "").strip() for a in answers}
    snapshot = se.snapshot or []
    obj_items = [it for it in snapshot if it.get("section") == "objective"]
    lst_items = [it for it in snapshot if it.get("section") == "listening"]
    wri_items = [it for it in snapshot if it.get("section") == "writing"]

    result_items: list[dict] = []

    # 听力：本地判分
    lst_correct = 0
    for it in lst_items:
        ua = ans_map.get(it["id"], "")
        ok = ua == it.get("answer")
        if ok:
            lst_correct += 1
        result_items.append({
            "id": it["id"], "section": "listening", "stem": it["stem"],
            "correct": ok, "correct_answer": it.get("answer", ""),
            "user_answer": ua or "未作答", "explanation": it.get("explanation", ""),
        })

    # 客观：沿用 submit_exam_attempts（按 simulated_question id 判分 + 错题归 wrong_questions）
    obj_total = obj_correct = 0
    if obj_items:
        obj_answers = [
            PracticeAttemptIn(
                question_id=uuid.UUID(it["sim_question_id"]),
                user_answer=ans_map.get(it["id"]) or "未作答",
            )
            for it in obj_items
        ]
        obj_res = await question_service.submit_exam_attempts(
            db, user_id=student_id, answers=obj_answers
        )
        obj_total, obj_correct = obj_res.total, obj_res.correct_count
        stem_by_sid = {it["sim_question_id"]: it["stem"] for it in obj_items}
        for r in obj_res.items:
            result_items.append({
                "id": str(r.question_id), "section": "objective",
                "stem": stem_by_sid.get(str(r.question_id), ""),
                "correct": r.correct, "correct_answer": r.correct_answer,
                "user_answer": r.user_answer or "未作答", "explanation": r.explanation,
            })

    # 写作：记录，不计分
    writing_text = ans_map.get("writing-1", "")
    writing_prompt = wri_items[0]["stem"] if wri_items else ""
    if wri_items:
        result_items.append({
            "id": "writing-1", "section": "writing", "stem": writing_prompt,
            "correct": None, "correct_answer": "", "user_answer": writing_text or "未作答",
            "explanation": "写作题不计入客观分，可前往「作文精修」获取 AI 批改。",
        })

    total = len(lst_items) + obj_total
    correct = lst_correct + obj_correct

    se.status = "done"  # type: ignore[assignment]
    se.total = total  # type: ignore[assignment]
    se.correct_count = correct  # type: ignore[assignment]
    se.accuracy = (correct / total) if total else 0.0  # type: ignore[assignment]
    se.submitted_at = datetime.now(timezone.utc)  # type: ignore[assignment]
    await db.flush()

    result = {
        "total": total, "correct_count": correct, "items": result_items,
        "writing_submitted": bool(writing_text),
        "writing_prompt": writing_prompt, "writing_text": writing_text,
    }
    return se, result


async def list_history(
    db: AsyncSession, *, student_id: uuid.UUID, limit: int = 50
) -> list[SelfExam]:
    return list((await db.execute(
        select(SelfExam)
        .where(SelfExam.student_id == student_id)
        .order_by(SelfExam.created_at.desc())
        .limit(limit)
    )).scalars().all())
