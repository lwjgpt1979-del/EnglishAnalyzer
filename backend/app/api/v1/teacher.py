"""教师端 API。"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.exceptions import AppError
from app.core.security import get_current_user, require_role
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.teacher import (
    BecomeTeacherRequest,
    BindTeacherRequest,
    CertSubmitRequest,
    InviteCodeOut,
    QRCodeOut,
    SendInviteSmsRequest,
    SendInviteSmsOut,
    TeacherCommentCreate,
    TeacherCommentOut,
    TeacherProfileOut,
    TeacherStudentOut,
)
from app.services.qrcode_service import get_miniprogram_qrcode_base64
from app.services.sms_service import send_invite_sms
from app.schemas.diagnosis import DiagnosisReport
from app.schemas.wrong_questions import WrongQuestionOut
from app.services import teacher_service
from app.schemas.classes import (
    ClassCreateRequest, ClassOut,
    ClassStudentAddRequest, ClassStudentOut,
    ClassReport,
)
from app.services import class_service

router = APIRouter(prefix="/teacher", tags=["teacher"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.post("/profile", response_model=BaseResponse[TeacherProfileOut])
async def become_teacher(
    body: BecomeTeacherRequest,
    db: DbDep,
    current_user: UserDep,
):
    """任意用户升级为教师角色（幂等）。"""
    await get_rls_db(db, str(current_user.id))
    teacher = await teacher_service.become_teacher(db, user=current_user, data=body)
    await db.commit()
    return make_ok(
        TeacherProfileOut(
            user_id=teacher.id,
            subject=teacher.subject,
            cert_status=str(teacher.cert_status),
            cert_doc_url=teacher.cert_doc_url,
            max_students=teacher.max_students,
        )
    )


@router.post("/invite-code", response_model=BaseResponse[InviteCodeOut])
async def create_invite_code(db: DbDep, current_user: UserDep):
    """教师生成邀请码（有效期24小时）。"""
    if str(current_user.role) != "teacher":
        raise AppError(code=403, message="仅教师可生成邀请码")
    await get_rls_db(db, str(current_user.id))
    # cert 认证 gate（D-075）
    from sqlalchemy import select as _sel
    from app.models.d1_users import Teacher as _T
    _r = await db.execute(_sel(_T).where(_T.id == current_user.id))
    teacher_service.ensure_certified(_r.scalar_one_or_none())
    invite = await teacher_service.generate_invite_code(
        db, teacher_id=current_user.id
    )
    await db.commit()
    return make_ok(InviteCodeOut(code=invite.code, expires_at=invite.expires_at))


@router.post("/bind", response_model=BaseResponse[TeacherStudentOut])
async def bind_teacher(
    body: BindTeacherRequest,
    db: DbDep,
    current_user: UserDep,
):
    """学生通过邀请码绑定老师。"""
    await get_rls_db(db, str(current_user.id))
    relation = await teacher_service.bind_with_teacher(
        db, student=current_user, code=body.code.upper()
    )
    await db.commit()
    return make_ok(
        TeacherStudentOut(
            student_id=relation.student_id,
            bound_at=relation.bound_at,
        )
    )


@router.get("/students", response_model=BaseResponse[list[TeacherStudentOut]])
async def list_my_students(db: DbDep, current_user: UserDep):
    """教师查看所有绑定学生。"""
    if str(current_user.role) != "teacher":
        raise AppError(code=403, message="仅教师可查看学生列表")
    await get_rls_db(db, str(current_user.id))
    # cert 认证 gate（D-075）
    from sqlalchemy import select as _sel
    from app.models.d1_users import Teacher as _T
    _r = await db.execute(_sel(_T).where(_T.id == current_user.id))
    teacher_service.ensure_certified(_r.scalar_one_or_none())
    students = await teacher_service.get_my_students(
        db, teacher_id=current_user.id
    )
    return make_ok(
        [TeacherStudentOut(student_id=s.student_id, bound_at=s.bound_at) for s in students]
    )


@router.get(
    "/students/{student_id}/wrong-questions",
    response_model=BaseResponse[list[WrongQuestionOut]],
)
async def get_student_wrong_questions(
    student_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
):
    """教师查看指定绑定学生的错题列表。"""
    if str(current_user.role) != "teacher":
        raise AppError(code=403, message="仅教师可查看学生错题")
    await get_rls_db(db, str(current_user.id))
    # cert 认证 gate（D-075）
    from sqlalchemy import select as _sel
    from app.models.d1_users import Teacher as _T
    _r = await db.execute(_sel(_T).where(_T.id == current_user.id))
    teacher_service.ensure_certified(_r.scalar_one_or_none())
    wqs = await teacher_service.get_student_wrong_questions(
        db, teacher_id=current_user.id, student_id=student_id
    )
    return make_ok([WrongQuestionOut.model_validate(wq) for wq in wqs])


@router.post(
    "/wrong-questions/{wq_id}/comments",
    response_model=BaseResponse[TeacherCommentOut],
)
async def add_comment(
    wq_id: uuid.UUID,
    body: TeacherCommentCreate,
    db: DbDep,
    current_user: UserDep,
):
    """教师为错题添加批注。"""
    if str(current_user.role) != "teacher":
        raise AppError(code=403, message="仅教师可添加批注")
    await get_rls_db(db, str(current_user.id))
    # cert 认证 gate（D-075）
    from sqlalchemy import select as _sel
    from app.models.d1_users import Teacher as _T
    _r = await db.execute(_sel(_T).where(_T.id == current_user.id))
    teacher_service.ensure_certified(_r.scalar_one_or_none())
    comment = await teacher_service.add_comment(
        db, teacher_id=current_user.id, wq_id=wq_id, data=body
    )
    await db.commit()
    return make_ok(TeacherCommentOut.model_validate(comment))


@router.get(
    "/wrong-questions/{wq_id}/comments",
    response_model=BaseResponse[list[TeacherCommentOut]],
)
async def get_comments(
    wq_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
):
    """查看错题上的所有老师批注。

    学生（WQ 所有者）和绑定该学生的老师均可访问。
    未授权则返回空列表（不报错，前端容错更友好）。
    """
    await get_rls_db(db, str(current_user.id))
    comments = await teacher_service.get_comments_for_wq_authorized(
        db, wq_id=wq_id, caller_id=current_user.id
    )
    return make_ok([TeacherCommentOut.model_validate(c) for c in comments])


@router.get(
    "/students/{student_id}/diagnosis-report",
    response_model=BaseResponse[DiagnosisReport],
)
async def student_diagnosis_api(student_id: uuid.UUID, db: DbDep, current_user: UserDep):
    if str(current_user.role) != "teacher":
        raise AppError(code=403, message="仅教师可访问")
    await get_rls_db(db, str(current_user.id))
    # cert gate
    from sqlalchemy import select as _sel
    from app.models.d1_users import Teacher as _T
    _r = await db.execute(_sel(_T).where(_T.id == current_user.id))
    teacher_service.ensure_certified(_r.scalar_one_or_none())

    report = await teacher_service.get_student_diagnosis_report(
        db, teacher_id=current_user.id, student_id=student_id,
    )
    return make_ok(report)


@router.post("/cert/submit", response_model=BaseResponse[TeacherProfileOut])
async def submit_cert_api(body: CertSubmitRequest, db: DbDep, current_user: UserDep):
    """教师提交认证材料。dev 模式自动通过，生产模式进入 pending。"""
    if str(current_user.role) != "teacher":
        raise AppError(code=403, message="请先成为教师")
    await get_rls_db(db, str(current_user.id))
    from sqlalchemy import select as _sel
    from app.models.d1_users import Teacher as _T
    r = await db.execute(_sel(_T).where(_T.id == current_user.id))
    teacher = r.scalar_one_or_none()
    if teacher is None:
        raise AppError(code=400, message="教师扩展记录缺失，请先调用 /teacher/profile")
    teacher = await teacher_service.submit_cert(db, teacher=teacher, cert_doc_url=body.cert_doc_url)
    await db.commit()
    return make_ok(TeacherProfileOut(
        user_id=teacher.id, subject=teacher.subject,
        cert_status=str(teacher.cert_status),
        cert_doc_url=teacher.cert_doc_url,
        max_students=teacher.max_students,
    ))


# ─── 班级管理端点（D-075 Task 2）────────────────────────────────────────────────


async def _require_certified_teacher(db: AsyncSession, current_user: User) -> None:
    """老师认证检查 helper（统一 cert gate 调用）。"""
    if str(current_user.role) != "teacher":
        raise AppError(code=403, message="仅教师可访问")
    from sqlalchemy import select as _sel
    from app.models.d1_users import Teacher as _T
    r = await db.execute(_sel(_T).where(_T.id == current_user.id))
    teacher_service.ensure_certified(r.scalar_one_or_none())


@router.post("/classes", response_model=BaseResponse[ClassOut])
async def create_class_api(body: ClassCreateRequest, db: DbDep, current_user: UserDep):
    await _require_certified_teacher(db, current_user)
    await get_rls_db(db, str(current_user.id))
    cls = await class_service.create_class(db, teacher_id=current_user.id, name=body.name)
    await db.commit()
    return make_ok(ClassOut(id=cls.id, name=cls.name, student_count=0, created_at=cls.created_at))


@router.get("/classes", response_model=BaseResponse[list[ClassOut]])
async def list_classes_api(db: DbDep, current_user: UserDep):
    await _require_certified_teacher(db, current_user)
    await get_rls_db(db, str(current_user.id))
    pairs = await class_service.list_classes(db, teacher_id=current_user.id)
    return make_ok([
        ClassOut(id=c.id, name=c.name, student_count=cnt, created_at=c.created_at)
        for c, cnt in pairs
    ])


@router.delete("/classes/{class_id}", response_model=BaseResponse[dict])
async def delete_class_api(class_id: uuid.UUID, db: DbDep, current_user: UserDep):
    await _require_certified_teacher(db, current_user)
    await get_rls_db(db, str(current_user.id))
    await class_service.delete_class(db, teacher_id=current_user.id, class_id=class_id)
    await db.commit()
    return make_ok({"deleted": True})


@router.post("/classes/{class_id}/students", response_model=BaseResponse[dict])
async def add_class_students_api(
    class_id: uuid.UUID, body: ClassStudentAddRequest, db: DbDep, current_user: UserDep,
):
    await _require_certified_teacher(db, current_user)
    await get_rls_db(db, str(current_user.id))
    added = await class_service.add_students(
        db, teacher_id=current_user.id, class_id=class_id, student_ids=body.student_ids,
    )
    await db.commit()
    return make_ok({"added": added})


@router.delete("/classes/{class_id}/students/{student_id}", response_model=BaseResponse[dict])
async def remove_class_student_api(
    class_id: uuid.UUID, student_id: uuid.UUID, db: DbDep, current_user: UserDep,
):
    await _require_certified_teacher(db, current_user)
    await get_rls_db(db, str(current_user.id))
    await class_service.remove_student(
        db, teacher_id=current_user.id, class_id=class_id, student_id=student_id,
    )
    await db.commit()
    return make_ok({"removed": True})


@router.get("/classes/{class_id}/students", response_model=BaseResponse[list[ClassStudentOut]])
async def list_class_students_api(class_id: uuid.UUID, db: DbDep, current_user: UserDep):
    await _require_certified_teacher(db, current_user)
    await get_rls_db(db, str(current_user.id))
    items = await class_service.list_class_students(
        db, teacher_id=current_user.id, class_id=class_id,
    )
    return make_ok([ClassStudentOut(student_id=cs.student_id, joined_at=cs.joined_at) for cs in items])


@router.get("/classes/{class_id}/report", response_model=BaseResponse[ClassReport])
async def class_report_api(class_id: uuid.UUID, db: DbDep, current_user: UserDep):
    await _require_certified_teacher(db, current_user)
    await get_rls_db(db, str(current_user.id))
    data = await class_service.build_class_report(
        db, teacher_id=current_user.id, class_id=class_id,
    )
    return make_ok(ClassReport(**data))


@router.post("/invite-code/qrcode", response_model=BaseResponse[QRCodeOut])
async def teacher_invite_qrcode(db: DbDep, current_user: UserDep):
    await _require_certified_teacher(db, current_user)
    await get_rls_db(db, str(current_user.id))
    invite = await teacher_service.generate_invite_code(db, teacher_id=current_user.id)
    await db.commit()
    qb64 = await get_miniprogram_qrcode_base64(
        scene=f"t:{invite.code}",
        page="pages/teacher/students",
    )
    return make_ok(QRCodeOut(
        code=invite.code, expires_at=invite.expires_at, qrcode_base64=qb64,
    ))


@router.post("/invite-code/sms", response_model=BaseResponse[SendInviteSmsOut])
async def teacher_invite_sms(body: SendInviteSmsRequest, db: DbDep, current_user: UserDep):
    await _require_certified_teacher(db, current_user)
    await get_rls_db(db, str(current_user.id))
    invite = await teacher_service.generate_invite_code(db, teacher_id=current_user.id)
    await db.commit()
    await send_invite_sms(
        phone=body.phone, code=invite.code,
        inviter_name=current_user.nickname or "您的老师",
        role="teacher",
    )
    return make_ok(SendInviteSmsOut(sent=True, code=invite.code))


# ─── 出卷下发闭环（D-113 / Module 5B）──────────────────────────────────────────
from datetime import datetime as _dt  # noqa: E402
from app.services import assignment_service  # noqa: E402
from app.schemas.assignment import (  # noqa: E402
    AssignmentCreate, AssignmentListItem, AssignmentOut, AssignmentStatsOut,
    GradeIn, SubmissionItem, SuggestOut, TeacherAssignmentDetail,
)


def _assignment_out(a) -> AssignmentOut:
    return AssignmentOut(
        id=a.id, class_id=a.class_id, title=a.title, questions=a.questions or [],
        due_at=a.due_at.isoformat() if a.due_at else None, status=str(a.status),
        published_at=a.published_at.isoformat() if a.published_at else None,
        created_at=a.created_at.isoformat(),
    )


@router.post("/assignments", response_model=BaseResponse[AssignmentOut])
async def create_assignment_api(body: AssignmentCreate, db: DbDep, current_user: UserDep):
    await _require_certified_teacher(db, current_user)
    await get_rls_db(db, str(current_user.id))
    due = _dt.fromisoformat(body.due_at) if body.due_at else None
    a = await assignment_service.create_assignment(
        db, teacher_id=current_user.id, class_id=body.class_id, title=body.title,
        questions=[q.model_dump() for q in body.questions], due_at=due)
    await db.commit()
    return make_ok(_assignment_out(a))


@router.post("/assignments/{assignment_id}/publish", response_model=BaseResponse[AssignmentOut])
async def publish_assignment_api(assignment_id: uuid.UUID, db: DbDep, current_user: UserDep):
    await _require_certified_teacher(db, current_user)
    await get_rls_db(db, str(current_user.id))
    a = await assignment_service.publish_assignment(db, teacher_id=current_user.id, assignment_id=assignment_id)
    await db.commit()
    return make_ok(_assignment_out(a))


@router.post("/assignments/{assignment_id}/close", response_model=BaseResponse[AssignmentOut])
async def close_assignment_api(assignment_id: uuid.UUID, db: DbDep, current_user: UserDep):
    await _require_certified_teacher(db, current_user)
    await get_rls_db(db, str(current_user.id))
    a = await assignment_service.close_assignment(db, teacher_id=current_user.id, assignment_id=assignment_id)
    await db.commit()
    return make_ok(_assignment_out(a))


@router.get("/assignments", response_model=BaseResponse[list[AssignmentListItem]])
async def list_assignments_api(db: DbDep, current_user: UserDep, class_id: uuid.UUID | None = None):
    await _require_certified_teacher(db, current_user)
    await get_rls_db(db, str(current_user.id))
    rows = await assignment_service.list_teacher_assignments(
        db, teacher_id=current_user.id, class_id=class_id)
    return make_ok([
        AssignmentListItem(
            id=a.id, class_id=a.class_id, title=a.title, status=str(a.status),
            due_at=a.due_at.isoformat() if a.due_at else None, submission_count=cnt)
        for a, cnt in rows
    ])


@router.get("/assignments/suggest", response_model=BaseResponse[SuggestOut])
async def suggest_questions_api(student_id: uuid.UUID, db: DbDep, current_user: UserDep, count: int = 5):
    """AI 智能选题：按目标学生薄弱知识点生成题目建议（dev-mock 免费）。"""
    await _require_certified_teacher(db, current_user)
    await get_rls_db(db, str(current_user.id))
    res = await assignment_service.suggest_questions(db, student_id=student_id, count=count)
    return make_ok(SuggestOut(**res))


@router.get("/assignments/{assignment_id}", response_model=BaseResponse[TeacherAssignmentDetail])
async def get_assignment_api(assignment_id: uuid.UUID, db: DbDep, current_user: UserDep):
    await _require_certified_teacher(db, current_user)
    await get_rls_db(db, str(current_user.id))
    a, subs = await assignment_service.get_assignment_for_teacher(
        db, teacher_id=current_user.id, assignment_id=assignment_id)
    return make_ok(TeacherAssignmentDetail(
        assignment=_assignment_out(a),
        submissions=[
            SubmissionItem(
                id=su.id, student_id=su.student_id, answers=su.answers,
                score=float(su.score) if su.score is not None else None,
                submitted_at=su.submitted_at.isoformat())
            for su in subs
        ],
    ))


@router.post("/submissions/{submission_id}/grade", response_model=BaseResponse[dict])
async def grade_submission_api(submission_id: uuid.UUID, body: GradeIn, db: DbDep, current_user: UserDep):
    await _require_certified_teacher(db, current_user)
    await get_rls_db(db, str(current_user.id))
    sub = await assignment_service.grade_submission(
        db, teacher_id=current_user.id, submission_id=submission_id, score=body.score)
    await db.commit()
    return make_ok({"id": str(sub.id), "score": float(sub.score)})


@router.get("/assignments/{assignment_id}/stats", response_model=BaseResponse[AssignmentStatsOut])
async def assignment_stats_api(assignment_id: uuid.UUID, db: DbDep, current_user: UserDep):
    await _require_certified_teacher(db, current_user)
    await get_rls_db(db, str(current_user.id))
    st = await assignment_service.get_assignment_stats(
        db, teacher_id=current_user.id, assignment_id=assignment_id)
    return make_ok(AssignmentStatsOut(**st))


# ─── 加入机构（D-121）──────────────────────────────────────────────────────
from app.schemas.institution import InstitutionTeacherOut, JoinInstitutionRequest

TeacherDep = Annotated[User, Depends(require_role("teacher"))]


@router.post("/join-institution", response_model=BaseResponse[InstitutionTeacherOut])
async def join_institution_api(
    body: JoinInstitutionRequest, db: DbDep, current_user: TeacherDep,
):
    t = await teacher_service.join_institution(
        db, teacher_user_id=current_user.id, code=body.code)
    await db.commit()
    await db.refresh(t)
    return make_ok(InstitutionTeacherOut(
        id=t.id, nickname=current_user.nickname, phone=current_user.phone,
        subject=t.subject, cert_status=str(t.cert_status),
    ))
