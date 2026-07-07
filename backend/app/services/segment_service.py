"""用户分群:rule(条件组,AND)→ 编译成 SQL → 命中用户集。

rule = {"conditions": [{"field": <key>, "value": <v>}, ...]}  条件 AND 连接。
字段语义固定(见 FIELDS),不暴露通用 op,规避注入与歧义。会员维度走 purchased_semesters
子查询(与续费同源);活跃度维度(inactive_days)缺 last-active 表,MVP 暂不做。
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d1_users import User
from app.models.d14_v2_semesters import PurchasedSemester

# 分群可用字段(admin UI 据此渲染 + 后端校验白名单)
FIELDS: dict = {
    "expiring_within_days": {"label": "会员将在N天内到期(仍有效)", "type": "int", "hint": "续费召回主力"},
    "churned_within_days": {"label": "已流失:会员在近N天内过期且无有效会员", "type": "int", "hint": "流失召回"},
    "has_paid": {"label": "是否付费用户", "type": "bool"},
    "tier": {"label": "付费档位", "type": "enum", "options": ["basic", "pro", "promax"]},
    "registered_within_days": {"label": "新注册:注册在N天内", "type": "int"},
    "registered_days_ago_gte": {"label": "老用户:注册满N天", "type": "int"},
    "acquisition_channel": {"label": "获客渠道", "type": "enum",
                            "options": ["school", "stationery", "training", "search", "referral", "other"]},
    "city_prefix": {"label": "城市/省(region码前缀,如32=江苏)", "type": "str"},
    "grade": {"label": "偏好年级(如 初中7年级)", "type": "str"},
    "inactive_days": {"label": "近N天无任何学习行为(不活跃)", "type": "int", "hint": "流失预警/沉睡召回"},
    "textbook_version": {"label": "偏好教材版本(如 译林版/人教版)", "type": "str"},
    "institution_member": {"label": "是否机构学员", "type": "bool"},
    "birth_year_gte": {"label": "出生年 ≥(卡低龄下限)", "type": "int"},
    "birth_year_lte": {"label": "出生年 ≤(卡高龄上限)", "type": "int"},
}

_NOW = sa.func.now()

# 「活跃」信号源:学生行为表(student_id + created_at)。近N天任一有记录=活跃。
_ACTIVITY_SOURCES = [
    ("study_checkins", "student_id"),
    ("essays", "student_id"),
    ("listening_records", "student_id"),
    ("speaking_sessions", "student_id"),
]


def _inactive_clause(n: int):
    """近 n 天无任何学习行为:NOT(任一行为表在窗口内存在该用户的记录)。"""
    exists_list = []
    for tname, ucol in _ACTIVITY_SOURCES:
        t = sa.table(tname, sa.column(ucol), sa.column("created_at"))
        exists_list.append(sa.exists().where(sa.and_(
            t.c[ucol] == User.id, t.c.created_at >= _NOW - timedelta(days=n))))
    return sa.not_(sa.or_(*exists_list))


def _active_ps_exists():
    """存在仍有效(未过期)的已购学期。"""
    return sa.exists().where(sa.and_(
        PurchasedSemester.user_id == User.id, PurchasedSemester.expires_at > _NOW))


def _condition_clause(field: str, value):
    """把单条件 → SQLAlchemy 过滤子句。未知字段/坏值 → AppError。"""
    if field not in FIELDS:
        raise AppError(code=400, message=f"未知分群字段 {field}")

    def _int(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            raise AppError(code=400, message=f"字段 {field} 需整数,得到 {value!r}")

    if field == "expiring_within_days":
        n = _int(value)
        return sa.exists().where(sa.and_(
            PurchasedSemester.user_id == User.id,
            PurchasedSemester.expires_at >= _NOW,
            PurchasedSemester.expires_at <= _NOW + timedelta(days=n)))
    if field == "churned_within_days":
        n = _int(value)
        expired_recent = sa.exists().where(sa.and_(
            PurchasedSemester.user_id == User.id,
            PurchasedSemester.expires_at < _NOW,
            PurchasedSemester.expires_at >= _NOW - timedelta(days=n)))
        return sa.and_(expired_recent, sa.not_(_active_ps_exists()))
    if field == "has_paid":
        any_ps = sa.exists().where(PurchasedSemester.user_id == User.id)
        return any_ps if bool(value) else sa.not_(any_ps)
    if field == "tier":
        if value not in FIELDS["tier"]["options"]:
            raise AppError(code=400, message=f"档位非法 {value!r}")
        return sa.exists().where(sa.and_(
            PurchasedSemester.user_id == User.id,
            sa.cast(PurchasedSemester.tier, sa.String) == value))
    if field == "registered_within_days":
        return User.created_at >= _NOW - timedelta(days=_int(value))
    if field == "registered_days_ago_gte":
        return User.created_at <= _NOW - timedelta(days=_int(value))
    if field == "acquisition_channel":
        return User.acquisition_channel == str(value)
    if field == "inactive_days":
        return _inactive_clause(_int(value))
    if field == "textbook_version":
        return User.preferred_textbook_version == str(value)
    if field == "institution_member":
        return User.institution_id.isnot(None) if bool(value) else User.institution_id.is_(None)
    if field == "birth_year_gte":
        return User.birth_year >= _int(value)
    if field == "birth_year_lte":
        return User.birth_year <= _int(value)
    if field == "city_prefix":
        return User.city_code.like(f"{str(value)}%")
    if field == "grade":
        return User.preferred_grade == str(value)
    raise AppError(code=400, message=f"字段 {field} 未实现")


def _base_filters():
    """恒定圈定:真实学生、未封禁、未注销/匿名化(避免触达到无效账号)。"""
    return [
        sa.cast(User.role, sa.String) == "student",
        User.is_active.is_(True),
        User.is_anonymized.is_(False),
    ]


def build_where(rule: dict) -> list:
    conds = list(_base_filters())
    for c in (rule or {}).get("conditions", []):
        if not isinstance(c, dict) or "field" not in c:
            raise AppError(code=400, message="条件格式错误,需 {field, value}")
        conds.append(_condition_clause(c["field"], c.get("value")))
    return conds


async def resolve(db: AsyncSession, rule: dict, *, sample: int = 20) -> dict:
    """rule → {count, sample:[{id,phone,nickname,city_code}]}。sample 仅预览用。"""
    where = build_where(rule)
    count = (await db.execute(
        sa.select(sa.func.count()).select_from(User).where(*where))).scalar_one()
    rows = (await db.execute(
        sa.select(User.id, User.phone, User.nickname, User.city_code)
        .where(*where).limit(sample))).all()
    return {"count": int(count),
            "sample": [{"id": str(r.id), "phone": r.phone, "nickname": r.nickname,
                        "city_code": r.city_code} for r in rows]}


async def resolve_users(db: AsyncSession, rule: dict, *, limit: int = 5000):
    """执行触达用:返回命中用户行(id/phone/nickname/city_code),带上限防跑飞。"""
    where = build_where(rule)
    return (await db.execute(
        sa.select(User.id, User.phone, User.nickname, User.city_code)
        .where(*where).limit(limit))).all()


# ── 分群 CRUD ────────────────────────────────────────────────────────────────

async def list_segments(db: AsyncSession, *, skip: int = 0, limit: int = 50) -> dict:
    from app.models.d24_reach import UserSegment
    total = (await db.execute(sa.select(sa.func.count()).select_from(UserSegment))).scalar_one()
    rows = (await db.execute(sa.select(UserSegment)
            .order_by(UserSegment.updated_at.desc()).offset(skip).limit(limit))).scalars().all()
    return {"total": int(total), "items": rows}


async def upsert_segment(db: AsyncSession, *, segment_id: uuid.UUID | None, name: str,
                         description: str | None, rule: dict, admin_id: uuid.UUID) -> "UserSegment":
    from app.models.d24_reach import UserSegment
    build_where(rule)  # 校验规则合法(坏规则直接 400,不落库)
    res = await resolve(db, rule, sample=0)
    if segment_id:
        seg = await db.get(UserSegment, segment_id)
        if seg is None:
            raise AppError(code=404, message="分群不存在")
        seg.name, seg.description, seg.rule, seg.last_count = name, description, rule, res["count"]
    else:
        seg = UserSegment(id=uuid.uuid4(), name=name, description=description, rule=rule,
                          last_count=res["count"], created_by=admin_id)
        db.add(seg)
    await db.flush()
    return seg


async def delete_segment(db: AsyncSession, *, segment_id: uuid.UUID) -> None:
    from app.models.d24_reach import UserSegment
    seg = await db.get(UserSegment, segment_id)
    if seg is not None:
        await db.delete(seg)
