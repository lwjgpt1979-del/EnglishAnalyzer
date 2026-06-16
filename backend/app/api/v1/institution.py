"""机构管理员后台 API（D-120）。

鉴权：require_role("institution_admin")；所有查询以 current_user.institution_id
为隔离键，机构只能看自己的数据。
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AppError
from app.core.security import create_access_token, create_refresh_token, require_role
from app.models.d1_users import User
from app.schemas.auth import AdminLoginRequest, TokenResponse
from app.schemas.base import BaseResponse, make_ok
from app.schemas.institution import (
    ActivationCodeOut,
    BatchRenewRequest,
    BatchRenewResult,
    BillItemOut,
    CaptchaOut,
    InstitutionApplyCodeRequest,
    InstitutionApplyRequest,
    InstitutionApplyResult,
    InstitutionOverviewOut,
    InstitutionProfileOut,
    InstitutionProfileUpdate,
    InstitutionTeacherOut,
    InviteCodeOut,
    PurchaseCreateRequest,
    PurchaseListItem,
    PurchaseOut,
    RenewableStudentOut,
    TeacherQuotaUpdate,
)
from app.services import (
    admin_auth_service,
    captcha_service,
    institution_apply_service,
    institution_billing_service,
    institution_purchase_service,
    institution_renew_service,
    institution_service,
)

router = APIRouter(prefix="/institution", tags=["institution"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
InstAdminDep = Annotated[User, Depends(require_role("institution_admin"))]


def _require_inst(admin: User):
    if admin.institution_id is None:
        raise AppError(code=400, message="该管理员未绑定机构")
    return admin.institution_id


# ─── 机构管理员登录（D-129：独立登录门，仅 institution_admin）──────────────
@router.post("/auth/login", response_model=BaseResponse[TokenResponse])
async def institution_login(body: AdminLoginRequest, db: DbDep):
    user = await admin_auth_service.authenticate(
        db, username=body.username, password=body.password,
        allowed_roles=("institution_admin",))
    if user is None:
        raise AppError(code=401, message="用户名或密码错误")
    return make_ok(TokenResponse(
        access_token=create_access_token(str(user.id), str(user.role)),
        refresh_token=create_refresh_token(str(user.id)),
    ))


# ─── 机构自助入驻申请（M47，公开免登录）────────────────────────────────────
@router.get("/apply/captcha", response_model=BaseResponse[CaptchaOut])
async def institution_apply_captcha(db: DbDep):
    """获取图形验证码（公开，挡在发短信前防盗刷）。"""
    captcha_id, svg = await captcha_service.generate(db)
    await db.commit()
    return make_ok(CaptchaOut(captcha_id=captcha_id, image_svg=svg))


@router.post("/apply/send-code", response_model=BaseResponse[dict])
async def institution_apply_send_code(body: InstitutionApplyCodeRequest, db: DbDep):
    """发送机构入驻申请手机验证码（公开）。需先过图形验证码。"""
    await institution_apply_service.send_apply_code(
        db, phone=body.phone, captcha_id=body.captcha_id, captcha_code=body.captcha_code)
    await db.commit()
    return make_ok({"sent": True})


@router.post("/apply", response_model=BaseResponse[InstitutionApplyResult])
async def institution_apply(body: InstitutionApplyRequest, db: DbDep):
    """提交机构入驻申请（公开）。验码通过后写入 pending 机构，进入超管审核队列。"""
    inst = await institution_apply_service.apply_institution(
        db,
        name=body.name, contact_phone=body.contact_phone,
        province_code=body.province_code, city_code=body.city_code,
        address=body.address, code=body.code,
    )
    await db.commit()
    return make_ok(InstitutionApplyResult(
        institution_id=inst.id, name=inst.name, status=str(inst.status)))


@router.get("/overview", response_model=BaseResponse[InstitutionOverviewOut])
async def get_overview(db: DbDep, admin: InstAdminDep):
    inst_id = _require_inst(admin)
    data = await institution_service.get_overview(db, institution_id=inst_id)
    return make_ok(InstitutionOverviewOut(**data))


@router.get("/learning-center", response_model=None)
async def learning_center(db: DbDep, admin: InstAdminDep):
    """机构学情数据中心（5B.4）：活跃率/打卡概览/薄弱知识点。"""
    inst_id = _require_inst(admin)
    return make_ok(await institution_service.learning_center(db, institution_id=inst_id))


@router.get("/profile", response_model=BaseResponse[InstitutionProfileOut])
async def get_profile(db: DbDep, admin: InstAdminDep):
    inst_id = _require_inst(admin)
    inst = await institution_service.get_profile(db, institution_id=inst_id)
    return make_ok(InstitutionProfileOut.model_validate(inst))


@router.patch("/profile", response_model=BaseResponse[InstitutionProfileOut])
async def update_profile(body: InstitutionProfileUpdate, db: DbDep, admin: InstAdminDep):
    inst_id = _require_inst(admin)
    inst = await institution_service.update_profile(
        db, institution_id=inst_id,
        name=body.name, contact_phone=body.contact_phone, address=body.address,
    )
    await db.commit()
    await db.refresh(inst)
    return make_ok(InstitutionProfileOut.model_validate(inst))


# ─── 老师管理（D-121）──────────────────────────────────────────────────────

@router.post("/teachers/invite-code", response_model=BaseResponse[InviteCodeOut])
async def gen_teacher_invite_code(db: DbDep, admin: InstAdminDep):
    inst_id = _require_inst(admin)
    invite = await institution_service.generate_join_code(
        db, institution_id=inst_id, issuer_id=admin.id)
    await db.commit()
    return make_ok(InviteCodeOut(code=invite.code, expires_at=invite.expires_at))


@router.get("/teachers", response_model=BaseResponse[list[InstitutionTeacherOut]])
async def list_institution_teachers(db: DbDep, admin: InstAdminDep):
    inst_id = _require_inst(admin)
    rows = await institution_service.list_teachers(db, institution_id=inst_id)
    return make_ok([
        InstitutionTeacherOut(
            id=t.id, nickname=u.nickname, phone=u.phone,
            subject=t.subject, cert_status=str(t.cert_status),
            monthly_paper_quota=t.monthly_paper_quota,
        ) for t, u in rows
    ])


@router.delete("/teachers/{teacher_id}", response_model=BaseResponse[dict])
async def remove_institution_teacher(teacher_id: uuid.UUID, db: DbDep, admin: InstAdminDep):
    inst_id = _require_inst(admin)
    await institution_service.remove_teacher(
        db, institution_id=inst_id, teacher_id=teacher_id)
    await db.commit()
    return make_ok({"removed": str(teacher_id)})


@router.patch("/teachers/{teacher_id}/quota", response_model=BaseResponse[InstitutionTeacherOut])
async def set_teacher_quota_api(
    teacher_id: uuid.UUID, body: TeacherQuotaUpdate, db: DbDep, admin: InstAdminDep,
):
    inst_id = _require_inst(admin)
    t = await institution_service.set_teacher_quota(
        db, institution_id=inst_id, teacher_id=teacher_id,
        monthly_paper_quota=body.monthly_paper_quota)
    await db.commit()
    u = await db.get(User, teacher_id)
    return make_ok(InstitutionTeacherOut(
        id=t.id, nickname=u.nickname if u else None, phone=u.phone if u else None,
        subject=t.subject, cert_status=str(t.cert_status),
        monthly_paper_quota=t.monthly_paper_quota,
    ))


# ─── 学生采购（D-122）──────────────────────────────────────────────────────

@router.post("/purchases", response_model=BaseResponse[PurchaseOut])
async def create_purchase(body: PurchaseCreateRequest, db: DbDep, admin: InstAdminDep):
    inst_id = _require_inst(admin)
    purchase, codes = await institution_purchase_service.create_purchase(
        db, institution_id=inst_id, created_by=admin.id,
        tier=body.tier, duration_months=body.duration_months, quantity=body.quantity)
    await db.commit()
    return make_ok(PurchaseOut(
        id=purchase.id, tier=str(purchase.tier), duration_months=purchase.duration_months,
        quantity=purchase.quantity, amount_fen=purchase.amount_fen, status=purchase.status,
        created_at=purchase.created_at,
        codes=[ActivationCodeOut(code=c.code, status=c.status, used_at=c.used_at) for c in codes],
    ))


@router.get("/purchases", response_model=BaseResponse[list[PurchaseListItem]])
async def list_purchases(db: DbDep, admin: InstAdminDep):
    inst_id = _require_inst(admin)
    rows = await institution_purchase_service.list_purchases(db, institution_id=inst_id)
    return make_ok([
        PurchaseListItem(
            id=p.id, tier=str(p.tier), duration_months=p.duration_months,
            quantity=p.quantity, amount_fen=p.amount_fen, status=p.status,
            created_at=p.created_at, used_count=used, total_count=total,
        ) for p, used, total in rows
    ])


@router.get("/purchases/{purchase_id}/codes", response_model=BaseResponse[list[ActivationCodeOut]])
async def get_purchase_codes(purchase_id: uuid.UUID, db: DbDep, admin: InstAdminDep):
    inst_id = _require_inst(admin)
    codes = await institution_purchase_service.get_purchase_codes(
        db, institution_id=inst_id, purchase_id=purchase_id)
    return make_ok([ActivationCodeOut(code=c.code, status=c.status, used_at=c.used_at) for c in codes])


# ─── 批量续费（D-124）──────────────────────────────────────────────────────

@router.get("/renewable-students", response_model=BaseResponse[list[RenewableStudentOut]])
async def list_renewable_students(db: DbDep, admin: InstAdminDep, expiring_days: int | None = None):
    inst_id = _require_inst(admin)
    rows = await institution_renew_service.list_renewable_students(
        db, institution_id=inst_id, expiring_days=expiring_days)
    return make_ok([
        RenewableStudentOut(student_id=sid, nickname=nick, tier=tier, expires_at=exp)
        for sid, nick, tier, exp in rows
    ])


@router.post("/batch-renew", response_model=BaseResponse[BatchRenewResult])
async def batch_renew(body: BatchRenewRequest, db: DbDep, admin: InstAdminDep):
    inst_id = _require_inst(admin)
    res = await institution_renew_service.batch_renew(
        db, institution_id=inst_id, student_ids=body.student_ids,
        semesters=body.semesters, duration_months=body.duration_months,
        operator_id=admin.id)
    await db.commit()
    return make_ok(BatchRenewResult(**res))


# ─── 账单（D-125）──────────────────────────────────────────────────────────

@router.get("/bills", response_model=BaseResponse[list[BillItemOut]])
async def list_bills(db: DbDep, admin: InstAdminDep):
    inst_id = _require_inst(admin)
    rows = await institution_billing_service.list_bills(db, institution_id=inst_id)
    return make_ok([BillItemOut(**r) for r in rows])
