"""
域1: 用户与租户 (8 张表)
  users · institutions · students · teachers · relatives ·
  student_relatives · teacher_students · invite_codes
"""

import uuid
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, INET, JSONB
from sqlalchemy.orm import mapped_column

from .base import Base

# ─── ENUM 定义 ────────────────────────────────────────────────────────────────

user_role_enum = sa.Enum(
    "student", "teacher", "relative",
    "institution_admin", "branch_admin", "platform_admin",
    name="user_role",
)
city_source_enum = sa.Enum(
    "ip_auto", "manual",
    name="city_source",
)
institution_status_enum = sa.Enum(
    "pending", "active", "suspended",
    name="institution_status",
)
semester_enum = sa.Enum("上", "下", name="semester")

cert_status_enum = sa.Enum(
    "uncertified", "pending", "certified", "rejected",
    name="cert_status",
)
bind_type_enum = sa.Enum(
    "institution_assigned", "self_bound",
    name="bind_type",
)
bind_source_enum = sa.Enum(
    "sms_invite", "miniprogram_link", "institution_assigned",
    name="bind_source",
)
# G17: 补充 inactive（unbound_at 有值时 status→inactive）
teacher_student_status_enum = sa.Enum(
    "pending", "active", "rejected", "inactive",
    name="teacher_student_status",
)
invite_code_type_enum = sa.Enum(
    "relative_bind", "institution_join", "teacher_bind",
    name="invite_code_type",
)

# ─── MODELS ──────────────────────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    openid = mapped_column(sa.String, nullable=False, unique=True)
    phone = mapped_column(sa.String, nullable=True)
    # —— 运营管理员账号密码登录（M5 / D-098；C 端用户这两列为 NULL）——
    username = mapped_column(sa.String, nullable=True, unique=True)
    password_hash = mapped_column(sa.String, nullable=True)
    # —— 模块权限(RBAC):NULL=全权超管;非空=子管理员仅可访问所列模块 ——
    # 模块键见 app/core/module_map.MODULES(content/vocab/…/finance/system)
    admin_modules = mapped_column(JSONB, nullable=True)
    nickname = mapped_column(sa.String, nullable=True)
    avatar_url = mapped_column(sa.String, nullable=True)
    role = mapped_column(user_role_enum, nullable=False)
    # —— 机构管理员 ↔ 机构绑定键（D-120；C 端用户为 NULL）——
    institution_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("institutions.id"), nullable=True
    )
    is_active = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("true")
    )
    city_code = mapped_column(sa.String, nullable=True)
    city_source = mapped_column(city_source_enum, nullable=True)
    # —— 渠道来源（§5.5）：注册时一次性写入，用于渠道获客分析 ——
    # school|stationery|training|search|referral|other（空=unknown）
    acquisition_channel = mapped_column(sa.String(20), nullable=True)
    ip_at_registration = mapped_column(INET, nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    # —— 合规：年龄核验 + 协议确认（D-073 / 需求文档 §4.1）——
    birth_year = mapped_column(sa.SmallInteger, nullable=True)
    guardian_phone = mapped_column(sa.String(20), nullable=True)
    guardian_verified_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    agreement_version = mapped_column(sa.String(16), nullable=True)
    agreement_agreed_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    profile_completed = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("false")
    )
    minor_purchase_consent_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)

    # —— 封禁（§5.3.1）：is_active=False 即封禁；banned_until 空=永久，有值=临时到期自动解封 ——
    ban_reason = mapped_column(sa.Text, nullable=True)
    banned_until = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    banned_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)

    # —— 合规：账号注销（D-073 / 需求文档 §4.2）——
    deactivation_requested_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    deactivation_scheduled_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    is_anonymized = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("false")
    )

    # —— SMS 验证码临时态（任意 purpose 复用）——
    phone_verify_code = mapped_column(sa.String(6), nullable=True)
    phone_verify_purpose = mapped_column(sa.String(32), nullable=True)
    phone_verify_target = mapped_column(sa.String(20), nullable=True)
    phone_verify_expires_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)

    # —— V2 教材偏好（D-079 / M1）——
    preferred_textbook_version = mapped_column(sa.String, nullable=True)
    preferred_grade = mapped_column(sa.String, nullable=True)
    preferred_semester = mapped_column(semester_enum, nullable=True)
    preferred_unit_no = mapped_column(sa.Integer, nullable=True)   # 学到第几单元(教材进度;算未学池的细粒度位置)
    exam_target = mapped_column(sa.String(8), nullable=True)   # 考试目标 junior(中考)|senior(高考);null=按年级派生(词力通按此出考纲词/短语)

    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class BanAppeal(Base):
    """封禁申诉（§5.3.1）：被封用户提交，后台审核；通过则解封并补偿会员时长。"""

    __tablename__ = "ban_appeals"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = mapped_column(UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False)
    reason = mapped_column(sa.Text, nullable=False)
    evidence_urls = mapped_column(JSONB, nullable=True)
    status = mapped_column(sa.String, nullable=False, server_default=sa.text("'pending'"))  # pending|approved|rejected
    note = mapped_column(sa.Text, nullable=True)
    reviewed_by = mapped_column(UUID(as_uuid=True), nullable=True)
    reviewed_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )


class Institution(Base):
    __tablename__ = "institutions"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = mapped_column(sa.String, nullable=False)
    contact_phone = mapped_column(sa.String, nullable=False)
    commission_rate = mapped_column(sa.Numeric(5, 4), nullable=True)
    province_code = mapped_column(sa.String, nullable=False)
    city_code = mapped_column(sa.String, nullable=False)
    address = mapped_column(sa.String, nullable=False)
    status = mapped_column(
        institution_status_enum,
        nullable=False,
        server_default=sa.text("'pending'"),
    )
    # 来源：'admin'=超管手动录入 / 'self_apply'=对外自助入驻申请（M49）
    source = mapped_column(
        sa.String(20), nullable=False, server_default=sa.text("'admin'")
    )
    # —— 机构套餐（§9.1 / §5.6；配置驱动，非枚举）——
    # package_tier 对应 system_configs.institution_packages.tiers[].key；
    # NULL = 非套餐机构（走老逻辑，不受机构池限制）。custom = 仅用下列 override。
    package_tier = mapped_column(sa.String(20), nullable=True)
    teacher_seats_override = mapped_column(sa.Integer, nullable=True)   # 老师席位数覆盖
    paper_pool_override = mapped_column(sa.Integer, nullable=True)      # 月出卷池覆盖
    grading_pool_override = mapped_column(sa.Integer, nullable=True)    # 月批改池覆盖
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class Student(Base):
    """学生扩展信息表（PK 同时是 users.id 的 FK）。"""

    __tablename__ = "students"

    id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True
    )
    institution_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("institutions.id"), nullable=True
    )
    grade = mapped_column(sa.String, nullable=True)
    textbook_ver = mapped_column(sa.String, nullable=True)
    semester = mapped_column(semester_enum, nullable=True)
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class Teacher(Base):
    """教师扩展信息表。"""

    __tablename__ = "teachers"

    id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True
    )
    institution_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("institutions.id"), nullable=True
    )
    cert_status = mapped_column(
        cert_status_enum,
        nullable=False,
        server_default=sa.text("'uncertified'"),
    )
    cert_doc_url = mapped_column(sa.String, nullable=True)
    subject = mapped_column(sa.String, nullable=True)
    # —— 认证审核队列增强（§5.8）——
    cert_submitted_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)  # 提交认证时间
    cert_claimed_by = mapped_column(UUID(as_uuid=True), nullable=True)             # 认领审核员（防多人同审）
    cert_claimed_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    cert_reject_reason = mapped_column(sa.Text, nullable=True)                     # 驳回原因
    cert_reviewed_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    max_students = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("50")
    )
    # —— 月度额度个体覆盖（§5.6；NULL=随全局配置 teacher_limits）——
    monthly_paper_quota = mapped_column(sa.Integer, nullable=True)     # 月度出卷上限覆盖
    monthly_grading_quota = mapped_column(sa.Integer, nullable=True)   # 月度批改/点评上限覆盖
    enterprise_userid = mapped_column(sa.String, nullable=True)
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class Relative(Base):
    """家长扩展信息表（仅做角色标记，无额外字段）。"""

    __tablename__ = "relatives"

    id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True
    )


class StudentRelative(Base):
    """学生-家长绑定关系（最多 4 个家长，service 层校验）。"""

    __tablename__ = "student_relatives"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    relative_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    relationship = mapped_column(sa.String, nullable=False)
    is_active = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("true")
    )
    bound_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False)
    unbound_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)


class TeacherStudent(Base):
    """师生绑定关系。status=inactive 表示已解绑（unbound_at 有值）。"""

    __tablename__ = "teacher_students"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    student_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    bind_type = mapped_column(bind_type_enum, nullable=False)
    bind_source = mapped_column(bind_source_enum, nullable=False)
    status = mapped_column(teacher_student_status_enum, nullable=False)
    institution_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("institutions.id"), nullable=True
    )
    requested_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False)
    bound_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    unbound_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        # 每对师生同一时刻只能有一条 active 记录；允许重新绑定
        sa.Index(
            "uix_teacher_students_active",
            "teacher_id",
            "student_id",
            unique=True,
            postgresql_where=sa.text("status = 'active'"),
        ),
    )


class InviteCode(Base):
    __tablename__ = "invite_codes"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = mapped_column(sa.String(6), nullable=False, unique=True)
    type = mapped_column(invite_code_type_enum, nullable=False)
    issuer_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    target_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
    )
    expires_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False)
    used_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
    )
