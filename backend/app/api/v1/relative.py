"""亲人端 API（D-076 / P0 亲人端）。"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_rls_db
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.schemas.relative import (
    BindRelativeRequest,
    BoundStudentOut,
    CheckinCalendarOut,
    CheckinDayItem,
    QRCodeOut,
    RelativeInviteCodeOut,
    SendInviteSmsRequest,
    SendInviteSmsOut,
    StudentRelativeOut,
)
from app.services import relative_service
from app.services.qrcode_service import get_miniprogram_qrcode_base64
from app.services.sms_service import send_invite_sms

router = APIRouter(prefix="/relative", tags=["relative"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.post("/invite-code", response_model=BaseResponse[RelativeInviteCodeOut])
async def generate_relative_invite_code(db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    invite = await relative_service.generate_invite_code(db, student_id=current_user.id)
    await db.commit()
    return make_ok(RelativeInviteCodeOut(code=invite.code, expires_at=invite.expires_at))


@router.post("/bind", response_model=BaseResponse[StudentRelativeOut])
async def bind_as_relative(body: BindRelativeRequest, db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    sr = await relative_service.bind_relative(
        db, relative_user=current_user, code=body.code.upper(), relationship=body.relationship,
    )
    await db.commit()
    return make_ok(StudentRelativeOut(
        id=sr.id, student_id=sr.student_id, relative_id=sr.relative_id,
        relationship=sr.relationship, is_active=sr.is_active, bound_at=sr.bound_at,
    ))


@router.get("/students", response_model=BaseResponse[list[BoundStudentOut]])
async def list_my_students(db: DbDep, current_user: UserDep):
    from sqlalchemy import select
    await get_rls_db(db, str(current_user.id))
    from app.models.d1_users import StudentRelative
    rows = (await db.execute(
        select(StudentRelative, User)
        .join(User, User.id == StudentRelative.student_id)
        .where(
            StudentRelative.relative_id == current_user.id,
            StudentRelative.is_active.is_(True),
        )
        .order_by(StudentRelative.bound_at.desc())
    )).all()
    return make_ok([
        BoundStudentOut(
            student_id=sr.student_id,
            relationship=sr.relationship,
            bound_at=sr.bound_at,
            nickname=u.nickname,
        )
        for sr, u in rows
    ])


@router.get("/my-relatives", response_model=BaseResponse[list[BoundStudentOut]])
async def list_my_relatives(db: DbDep, current_user: UserDep):
    from sqlalchemy import select
    await get_rls_db(db, str(current_user.id))
    from app.models.d1_users import StudentRelative
    rows = (await db.execute(
        select(StudentRelative, User)
        .join(User, User.id == StudentRelative.relative_id)
        .where(
            StudentRelative.student_id == current_user.id,
            StudentRelative.is_active.is_(True),
        )
        .order_by(StudentRelative.bound_at.desc())
    )).all()
    return make_ok([
        BoundStudentOut(
            student_id=sr.relative_id,
            relationship=sr.relationship,
            bound_at=sr.bound_at,
            nickname=u.nickname,
        )
        for sr, u in rows
    ])


@router.delete("/relatives/{relative_id}", response_model=BaseResponse[dict])
async def unbind_my_relative(relative_id: uuid.UUID, db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    await relative_service.unbind_relative(
        db, student_id=current_user.id, relative_id=relative_id,
    )
    await db.commit()
    return make_ok({"unbound": True})


from app.schemas.diagnosis import DiagnosisReport
from app.schemas.wrong_questions import WrongQuestionOut


@router.get(
    "/students/{student_id}/diagnosis-report",
    response_model=BaseResponse[DiagnosisReport],
)
async def relative_view_student_diagnosis(
    student_id: uuid.UUID, db: DbDep, current_user: UserDep,
):
    await get_rls_db(db, str(current_user.id))
    await relative_service.assert_bound(
        db, relative_id=current_user.id, student_id=student_id,
    )
    from app.services.diagnosis_service import get_diagnosis_report
    report = await get_diagnosis_report(db, student_id=student_id)
    return make_ok(report)


@router.get("/students/{student_id}/speaking-stats", response_model=BaseResponse[dict])
async def relative_view_student_speaking(
    student_id: uuid.UUID, db: DbDep, current_user: UserDep,
):
    """家人查看孩子的口语练习情况。"""
    await get_rls_db(db, str(current_user.id))
    await relative_service.assert_bound(
        db, relative_id=current_user.id, student_id=student_id,
    )
    from app.services import speaking_dialogue_service
    return make_ok(await speaking_dialogue_service.speaking_stats(db, student_id))


@router.get("/students/{student_id}/vocab-overview", response_model=BaseResponse[dict])
async def relative_view_student_vocab(
    student_id: uuid.UUID, db: DbDep, current_user: UserDep,
):
    """家人查看孩子的词力通学情（词数分布/错词/连续天数/发音概况）。"""
    await get_rls_db(db, str(current_user.id))
    await relative_service.assert_bound(
        db, relative_id=current_user.id, student_id=student_id,
    )
    from app.services import vocabulary_service
    return make_ok(await vocabulary_service.vocab_overview(db, student_id=student_id))


@router.get(
    "/students/{student_id}/wrong-questions",
    response_model=BaseResponse[list[WrongQuestionOut]],
)
async def relative_view_student_wqs(
    student_id: uuid.UUID, db: DbDep, current_user: UserDep,
):
    await get_rls_db(db, str(current_user.id))
    await relative_service.assert_bound(
        db, relative_id=current_user.id, student_id=student_id,
    )
    from sqlalchemy import select as _sel
    from app.models.d3_wrong_questions import WrongQuestion
    r = await db.execute(
        _sel(WrongQuestion).where(WrongQuestion.student_id == student_id)
        .order_by(WrongQuestion.created_at.desc())
    )
    items = list(r.scalars().all())
    return make_ok([WrongQuestionOut.model_validate(wq) for wq in items])


@router.get(
    "/students/{student_id}/checkin-calendar",
    response_model=BaseResponse[CheckinCalendarOut],
)
async def relative_view_student_checkin_calendar(
    student_id: uuid.UUID,
    db: DbDep,
    current_user: UserDep,
    year: int | None = None,
    month: int | None = None,
):
    from datetime import datetime, timezone
    from app.services import checkin_service
    await get_rls_db(db, str(current_user.id))
    await relative_service.assert_bound(
        db, relative_id=current_user.id, student_id=student_id,
    )
    now = datetime.now(timezone.utc)
    cal = await checkin_service.get_month_calendar(
        db, student_id=student_id,
        year=year or now.year, month=month or now.month,
    )
    return make_ok(CheckinCalendarOut(
        year=cal["year"], month=cal["month"],
        days=[CheckinDayItem(**d) for d in cal["days"]],
        checked_count=cal["checked_count"],
        current_streak=cal["current_streak"],
        longest_streak=cal["longest_streak"],
    ))


@router.get(
    "/students/{student_id}/kp-mastery",
    response_model=None,
    summary="家长查看孩子知识点台账（M45）",
)
async def relative_view_student_kp_mastery(
    student_id: uuid.UUID, db: DbDep, current_user: UserDep,
):
    await get_rls_db(db, str(current_user.id))
    await relative_service.assert_bound(
        db, relative_id=current_user.id, student_id=student_id,
    )
    from datetime import datetime, timezone
    from app.services.kp_mastery_service import get_mastery_tree, review_suggestion

    rows = await get_mastery_tree(db, student_id=student_id)
    now = datetime.now(timezone.utc)
    items = []
    for r in rows:
        total = r.correct_count + r.wrong_count
        accuracy = r.correct_count / total if total > 0 else 0.0
        days_since: int | None = None
        if r.last_activity_at is not None:
            days_since = (now - r.last_activity_at.astimezone(timezone.utc)).days
        level, suggestion = review_suggestion(
            accuracy=accuracy, total=total, days_since=days_since
        )
        items.append({
            "kp_key": r.kp_key,
            "kp_id": str(r.kp_id) if r.kp_id else None,
            "kp_description": r.kp_description,
            "correct_count": r.correct_count,
            "wrong_count": r.wrong_count,
            "total": total,
            "accuracy": round(accuracy, 4),
            "level": level,
            "suggestion": suggestion,
            "sources": list(r.sources or []),
            "last_activity_at": r.last_activity_at.isoformat() if r.last_activity_at else None,
            "days_since_last": days_since,
        })
    return make_ok(items)


@router.post("/invite-code/qrcode", response_model=BaseResponse[QRCodeOut])
async def relative_invite_qrcode(db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    invite = await relative_service.generate_invite_code(db, student_id=current_user.id)
    await db.commit()
    qb64 = await get_miniprogram_qrcode_base64(
        scene=f"r:{invite.code}",
        page="pages/relative/center",
    )
    return make_ok(QRCodeOut(
        code=invite.code, expires_at=invite.expires_at, qrcode_base64=qb64,
    ))


@router.post("/invite-code/sms", response_model=BaseResponse[SendInviteSmsOut])
async def relative_invite_sms(body: SendInviteSmsRequest, db: DbDep, current_user: UserDep):
    await get_rls_db(db, str(current_user.id))
    invite = await relative_service.generate_invite_code(db, student_id=current_user.id)
    await db.commit()
    await send_invite_sms(
        phone=body.phone, code=invite.code,
        inviter_name=current_user.nickname or "您的家人",
        role="relative",
    )
    return make_ok(SendInviteSmsOut(sent=True, code=invite.code))
