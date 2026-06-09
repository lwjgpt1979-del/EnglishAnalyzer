"""老师出卷下发闭环 service（D-113 / Module 5B + 5B-S）。零迁移、无 LLM。"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d1_users import Teacher, User
from app.models.d3_wrong_questions import WrongQuestion
from app.models.d7_teacher import Assignment, AssignmentSubmission, ClassStudent
from app.services import class_service, notification_service
from app.services.question_service import _grade


def _normalize_answers(answers) -> dict[int, str]:
    """支持 [{index,answer}] / dict / 裸 list → {index: answer_str}。"""
    out: dict[int, str] = {}
    if isinstance(answers, list):
        for i, it in enumerate(answers):
            if isinstance(it, dict) and "index" in it:
                out[int(it["index"])] = str(it.get("answer", ""))
            else:
                out[i] = str(it)
    elif isinstance(answers, dict):
        for k, v in answers.items():
            try:
                out[int(k)] = str(v)
            except (ValueError, TypeError):
                pass
    return out


def _auto_judge(questions: list, answers) -> tuple[float | None, list[dict]]:
    """返回 (score|None, wrong_items)。仅对有 answer 的客观题判分。"""
    amap = _normalize_answers(answers)
    objective = [(i, q) for i, q in enumerate(questions) if (q or {}).get("answer")]
    if not objective:
        return None, []
    correct = 0
    wrong: list[dict] = []
    for i, q in objective:
        ua = amap.get(i, "")
        if _grade(str(q.get("type") or "其他"), str(q["answer"]), ua):
            correct += 1
        else:
            wrong.append({
                "stem": q.get("stem", ""), "student_answer": ua,
                "correct_answer": str(q["answer"]),
            })
    return round(correct / len(objective) * 100, 2), wrong


async def _sync_assignment_wrongs(db: AsyncSession, *, student_id, assignment_id, wrong_items) -> None:
    marker = f"assignment://{assignment_id}"
    await db.execute(delete(WrongQuestion).where(
        WrongQuestion.student_id == student_id,
        WrongQuestion.source_image_url == marker))
    for w in wrong_items:
        db.add(WrongQuestion(
            id=uuid.uuid4(), student_id=student_id, source_image_url=marker,
            question_text=w["stem"], student_answer=w["student_answer"],
            correct_answer=w["correct_answer"], question_type=None))


# ─── 老师端 ──────────────────────────────────────────────────────────

async def _get_owned_assignment(
    db: AsyncSession, *, teacher_id: uuid.UUID, assignment_id: uuid.UUID,
) -> Assignment:
    a = (await db.execute(
        select(Assignment).where(
            Assignment.id == assignment_id, Assignment.teacher_id == teacher_id)
    )).scalar_one_or_none()
    if a is None:
        raise AppError(code=404, message="作业不存在或无权访问")
    return a


async def create_assignment(
    db: AsyncSession, *, teacher_id: uuid.UUID, class_id: uuid.UUID,
    title: str, questions: list, due_at: datetime | None = None,
) -> Assignment:
    await class_service._get_owned_class(db, teacher_id=teacher_id, class_id=class_id)
    # —— 机构出卷月额度闸门（D-128；老师未配额度=不限）——
    teacher = await db.get(Teacher, teacher_id)
    if teacher is not None and teacher.monthly_paper_quota is not None:
        month_start = datetime.now(timezone.utc).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0)
        used = (await db.execute(
            select(func.count()).select_from(Assignment).where(
                Assignment.teacher_id == teacher_id,
                Assignment.created_at >= month_start,
            )
        )).scalar_one()
        if used >= teacher.monthly_paper_quota:
            raise AppError(code=403, message="本月出卷额度已用尽，请联系机构管理员")
    a = Assignment(
        id=uuid.uuid4(), teacher_id=teacher_id, class_id=class_id,
        title=title, questions=questions, due_at=due_at, status="draft",
    )
    db.add(a)
    await db.flush()
    return a


async def publish_assignment(
    db: AsyncSession, *, teacher_id: uuid.UUID, assignment_id: uuid.UUID,
) -> Assignment:
    a = await _get_owned_assignment(db, teacher_id=teacher_id, assignment_id=assignment_id)
    if str(a.status) == "closed":
        raise AppError(code=400, message="作业已关闭，无法发布")
    a.status = "published"
    if a.published_at is None:
        a.published_at = datetime.now(timezone.utc)
    await db.flush()
    # ── 查教师昵称（用于微信推送显示）────────────────────────────────────────
    teacher_user = await db.get(User, teacher_id)
    teacher_name = (teacher_user.nickname if teacher_user else None) or "老师"
    due_at_str = a.due_at.strftime("%m月%d日 %H:%M") if a.due_at else "无截止时间"

    # ── 下发站内通知 + 微信订阅消息给班级每个学生 ────────────────────────────
    student_rows = (await db.execute(
        select(ClassStudent.student_id).where(ClassStudent.class_id == a.class_id)
    )).scalars().all()

    # 批量查学生 openid（用于微信推送）
    student_users = list(
        (await db.execute(
            select(User.id, User.openid).where(User.id.in_(student_rows))
        )).all()
    )
    openid_map = {row.id: row.openid for row in student_users if row.openid}

    from app.services.wechat_subscribe_service import send_assignment_notification

    for sid in student_rows:
        await notification_service.emit(
            db, user_id=sid, type_="assignment",
            title="老师布置了新作业",
            content=f"《{a.title}》，请尽快完成。",
            meta={"assignment_id": str(a.id)},
        )
        openid = openid_map.get(sid)
        if openid:
            asyncio.create_task(
                send_assignment_notification(
                    openid=openid,
                    assignment_title=a.title,
                    teacher_name=teacher_name,
                    due_at_str=due_at_str,
                )
            )
    return a


async def close_assignment(
    db: AsyncSession, *, teacher_id: uuid.UUID, assignment_id: uuid.UUID,
) -> Assignment:
    a = await _get_owned_assignment(db, teacher_id=teacher_id, assignment_id=assignment_id)
    a.status = "closed"
    await db.flush()
    return a


async def list_teacher_assignments(
    db: AsyncSession, *, teacher_id: uuid.UUID, class_id: uuid.UUID | None = None,
) -> list[tuple[Assignment, int]]:
    q = select(Assignment).where(Assignment.teacher_id == teacher_id)
    if class_id is not None:
        q = q.where(Assignment.class_id == class_id)
    rows = list((await db.execute(q.order_by(Assignment.created_at.desc()))).scalars().all())
    out: list[tuple[Assignment, int]] = []
    for a in rows:
        from sqlalchemy import func
        cnt = (await db.execute(
            select(func.count()).select_from(AssignmentSubmission)
            .where(AssignmentSubmission.assignment_id == a.id)
        )).scalar_one()
        out.append((a, int(cnt)))
    return out


async def get_assignment_for_teacher(
    db: AsyncSession, *, teacher_id: uuid.UUID, assignment_id: uuid.UUID,
) -> tuple[Assignment, list[AssignmentSubmission]]:
    a = await _get_owned_assignment(db, teacher_id=teacher_id, assignment_id=assignment_id)
    subs = list((await db.execute(
        select(AssignmentSubmission).where(AssignmentSubmission.assignment_id == a.id)
        .order_by(AssignmentSubmission.submitted_at)
    )).scalars().all())
    return a, subs


async def suggest_questions(db: AsyncSession, *, student_id: uuid.UUID, count: int = 5) -> dict:
    """AI 智能选题：读目标学生最薄弱知识点 → 生成 count 题（dev-mock 免费）。"""
    from app.services import diagnosis_service, question_ai_service
    report = await diagnosis_service.get_diagnosis_report(db, student_id=student_id)
    if not report.top_weak_knowledge_points:
        raise AppError(code=400, message="该生暂无薄弱知识点，请先完成错题 AI 分析")
    kp = report.top_weak_knowledge_points[0].knowledge_point
    gen = await question_ai_service.generate_questions(
        kp_name=kp, kp_category="语法", kp_description=None, count=count)
    questions = [
        {"stem": q.stem, "type": q.question_type, "options": q.options, "answer": q.answer}
        for q in gen
    ]
    return {"knowledge_point": kp, "questions": questions}


async def suggest_questions_by_kp(kp_key: str, count: int = 5) -> dict:
    """按指定 KP 名称直接生成出题建议（M47，不需要 student_id）。"""
    from app.services import question_ai_service
    if not kp_key or not kp_key.strip():
        raise AppError(code=400, message="kp_key 不能为空")
    gen = await question_ai_service.generate_questions(
        kp_name=kp_key.strip(), kp_category="语法", kp_description=None, count=count)
    questions = [
        {"stem": q.stem, "type": q.question_type, "options": q.options, "answer": q.answer}
        for q in gen
    ]
    return {"knowledge_point": kp_key.strip(), "questions": questions}


async def get_assignment_stats(
    db: AsyncSession, *, teacher_id: uuid.UUID, assignment_id: uuid.UUID,
) -> dict:
    from sqlalchemy import func
    a = await _get_owned_assignment(db, teacher_id=teacher_id, assignment_id=assignment_id)
    total_students = (await db.execute(
        select(func.count()).select_from(ClassStudent).where(ClassStudent.class_id == a.class_id)
    )).scalar_one()
    subs = list((await db.execute(
        select(AssignmentSubmission).where(AssignmentSubmission.assignment_id == a.id)
    )).scalars().all())
    submitted = len(subs)
    completion_rate = round(submitted / total_students, 2) if total_students else 0.0
    scores = [float(s.score) for s in subs if s.score is not None]
    avg_score = round(sum(scores) / len(scores), 2) if scores else None
    max_score = max(scores) if scores else None
    min_score = min(scores) if scores else None
    # 逐题正确率（客观题）
    questions = a.questions or []
    per_question = []
    for i, q in enumerate(questions):
        if not (q or {}).get("answer"):
            continue
        correct = 0
        for su in subs:
            ua = _normalize_answers(su.answers).get(i, "")
            if _grade(str(q.get("type") or "其他"), str(q["answer"]), ua):
                correct += 1
        per_question.append({
            "index": i, "stem": q.get("stem", ""), "correct": correct,
            "total": submitted, "rate": round(correct / submitted, 2) if submitted else 0.0,
        })
    return {
        "total_students": int(total_students), "submitted_count": submitted,
        "completion_rate": completion_rate, "graded_count": len(scores),
        "avg_score": avg_score, "max_score": max_score, "min_score": min_score,
        "per_question": per_question,
    }


async def grade_submission(
    db: AsyncSession, *, teacher_id: uuid.UUID, submission_id: uuid.UUID, score: float,
) -> AssignmentSubmission:
    sub = (await db.execute(
        select(AssignmentSubmission).where(AssignmentSubmission.id == submission_id)
    )).scalar_one_or_none()
    if sub is None:
        raise AppError(code=404, message="提交不存在")
    # 校验该提交所属作业归本老师
    await _get_owned_assignment(db, teacher_id=teacher_id, assignment_id=sub.assignment_id)
    sub.score = score
    await db.flush()
    return sub


# ─── 学生端 ──────────────────────────────────────────────────────────

async def _assert_in_class(db: AsyncSession, *, student_id: uuid.UUID, class_id: uuid.UUID) -> None:
    r = (await db.execute(
        select(ClassStudent).where(
            ClassStudent.class_id == class_id, ClassStudent.student_id == student_id)
    )).scalar_one_or_none()
    if r is None:
        raise AppError(code=403, message="你不在该班级，无法访问此作业")


async def _my_submission(
    db: AsyncSession, *, student_id: uuid.UUID, assignment_id: uuid.UUID,
) -> AssignmentSubmission | None:
    return (await db.execute(
        select(AssignmentSubmission).where(
            AssignmentSubmission.assignment_id == assignment_id,
            AssignmentSubmission.student_id == student_id)
    )).scalar_one_or_none()


async def list_received(
    db: AsyncSession, *, student_id: uuid.UUID,
) -> list[tuple[Assignment, AssignmentSubmission | None]]:
    class_ids = (await db.execute(
        select(ClassStudent.class_id).where(ClassStudent.student_id == student_id)
    )).scalars().all()
    if not class_ids:
        return []
    rows = list((await db.execute(
        select(Assignment).where(
            Assignment.class_id.in_(class_ids), Assignment.status == "published")
        .order_by(Assignment.published_at.desc())
    )).scalars().all())
    out: list[tuple[Assignment, AssignmentSubmission | None]] = []
    for a in rows:
        sub = await _my_submission(db, student_id=student_id, assignment_id=a.id)
        out.append((a, sub))
    return out


async def get_for_student(
    db: AsyncSession, *, student_id: uuid.UUID, assignment_id: uuid.UUID,
) -> tuple[Assignment, AssignmentSubmission | None]:
    a = (await db.execute(
        select(Assignment).where(Assignment.id == assignment_id)
    )).scalar_one_or_none()
    if a is None or str(a.status) == "draft":
        raise AppError(code=404, message="作业不存在")
    await _assert_in_class(db, student_id=student_id, class_id=a.class_id)
    sub = await _my_submission(db, student_id=student_id, assignment_id=a.id)
    return a, sub


async def submit_assignment(
    db: AsyncSession, *, student_id: uuid.UUID, assignment_id: uuid.UUID, answers,
) -> AssignmentSubmission:
    a = (await db.execute(
        select(Assignment).where(Assignment.id == assignment_id)
    )).scalar_one_or_none()
    if a is None or str(a.status) != "published":
        raise AppError(code=400, message="作业不可提交")
    await _assert_in_class(db, student_id=student_id, class_id=a.class_id)
    if a.due_at is not None and datetime.now(timezone.utc) > a.due_at:
        raise AppError(code=400, message="作业已截止")
    sub = await _my_submission(db, student_id=student_id, assignment_id=a.id)
    now = datetime.now(timezone.utc)
    if sub is not None:
        sub.answers = answers
        sub.submitted_at = now
    else:
        sub = AssignmentSubmission(
            id=uuid.uuid4(), assignment_id=a.id, student_id=student_id,
            answers=answers, submitted_at=now,
        )
        db.add(sub)
    await db.flush()
    # 客观题自动判分 + 答错入错题库（D-114）
    score, wrong = _auto_judge(a.questions or [], answers)
    if score is not None:
        sub.score = score
    await _sync_assignment_wrongs(db, student_id=student_id, assignment_id=a.id, wrong_items=wrong)
    await db.flush()

    # M41: 写入知识点台账（source="assignment"）
    await _upsert_assignment_mastery(
        db, student_id=student_id, questions=a.questions or [], answers=answers, wrong_items=wrong
    )

    return sub


async def _upsert_assignment_mastery(
    db: AsyncSession,
    *,
    student_id: uuid.UUID,
    questions: list,
    answers,
    wrong_items: list[dict],
) -> None:
    """把作业每道客观题的对/错写入知识点台账。

    KP 通过 kp_classifier_service 推断（dev 模式直接返回 mock KP）。
    """
    try:
        from app.services import kp_mastery_service
        from app.services.kp_classifier_service import classify_kps
        from app.services.paper_split_service import ParsedPaperQuestion

        amap = _normalize_answers(answers)
        # 只处理有答案的客观题
        objective = [(i, q) for i, q in enumerate(questions) if (q or {}).get("answer")]
        if not objective:
            return

        # 构造 ParsedPaperQuestion 列表，供 classify_kps 推断知识点
        pq_list: list[ParsedPaperQuestion] = []
        for i, q in objective:
            ua = amap.get(i, "")
            pq_list.append(
                ParsedPaperQuestion(
                    question_no=str(i),
                    question_type=str(q.get("type") or "其他"),
                    stem=str(q.get("stem") or ""),
                    student_answer=ua,
                    correct_answer=str(q.get("answer") or ""),
                    explanation=None,
                )
            )

        # KP 分类（dev mock 直接返回固定 KP）
        kp_map = await classify_kps(pq_list)  # {question_no: kp_key}

        # 构建答错题的 stem set，方便判断对/错
        wrong_stems = {w["stem"] for w in wrong_items}

        for pq in pq_list:
            kp_key = kp_map.get(pq.question_no)
            if not kp_key:
                continue
            is_correct = pq.stem not in wrong_stems
            await kp_mastery_service.upsert_mastery(
                db,
                student_id=student_id,
                kp_key=kp_key,
                kp_id=None,
                is_correct=is_correct,
                source="assignment",
            )
    except Exception:
        # 台账写入失败不影响主链路
        import logging
        logging.getLogger(__name__).exception("M41: 作业台账写入失败")
