import time
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.d1_users import User

# 微信小程序全局 access_token 进程内缓存（约 2h 有效，提前 5min 失效）
_access_token_cache: dict = {"token": None, "expires_at": 0.0}


def _is_wechat_dev() -> bool:
    return settings.wechat_appid.startswith("wx_dev")


async def get_wechat_access_token() -> str:
    """获取微信小程序全局 access_token，进程内缓存。

    文档: https://developers.weixin.qq.com/miniprogram/dev/OpenApiDoc/mp-access-token/getAccessToken.html
    """
    if _is_wechat_dev():
        return "dev_access_token"

    now = time.time()
    if _access_token_cache["token"] and _access_token_cache["expires_at"] > now:
        return _access_token_cache["token"]

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            settings.wechat_access_token_url,
            params={
                "grant_type": "client_credential",
                "appid": settings.wechat_appid,
                "secret": settings.wechat_appsecret,
            },
        )
    data = resp.json()
    token = data.get("access_token")
    if not token:
        raise AppError(
            code=503,
            message=f"获取微信 access_token 失败（{data.get('errmsg', 'unknown')}）",
        )
    _access_token_cache["token"] = token
    _access_token_cache["expires_at"] = now + int(data.get("expires_in", 7200)) - 300
    return token


async def get_wx_phone_number(phone_code: str) -> str:
    """用小程序 getPhoneNumber 回调的 code 换取用户手机号（纯号码，不含区号）。

    文档: https://developers.weixin.qq.com/miniprogram/dev/OpenApiDoc/user-info/phone-number/getPhoneNumber.html
    需企业认证主体小程序；每次调用消耗手机号快速验证组件额度。
    """
    if not phone_code:
        raise AppError(code=400, message="缺少手机号授权 code")
    if _is_wechat_dev():
        return "13800138000"  # dev mock

    token = await get_wechat_access_token()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            settings.wechat_get_phone_url,
            params={"access_token": token},
            json={"code": phone_code},
        )
    data = resp.json()
    if data.get("errcode") not in (0, None):
        raise AppError(
            code=400,
            message=f"获取手机号失败（{data.get('errmsg', 'unknown')}），请重试",
        )
    phone = (data.get("phone_info") or {}).get("purePhoneNumber")
    if not phone:
        raise AppError(code=400, message="微信未返回手机号，请重试")
    return phone


async def wechat_code2session(code: str) -> dict:
    """调用微信 jscode2session 接口，返回 {openid, session_key}。

    文档: https://developers.weixin.qq.com/miniprogram/dev/OpenApiDoc/user-login/code2Session.html
    session_key 不落库，不透传业务层（Tech Spec §1.2）。

    Dev 模式（WECHAT_APPID 以 'wx_dev' 开头）：跳过真实 API，返回固定 mock openid。
    """
    if settings.wechat_appid.startswith("wx_dev"):
        # 本地测试 mock：code 作为 openid 的 suffix，每个 code 对应固定用户
        return {"openid": f"dev_openid_{code}", "session_key": "dev_session_key"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            settings.wechat_code2session_url,
            params={
                "appid": settings.wechat_appid,
                "secret": settings.wechat_appsecret,
                "js_code": code,
                "grant_type": "authorization_code",
            },
        )
    data = resp.json()

    if data.get("errcode") and data["errcode"] != 0:
        raise AppError(
            code=401,
            message=f"微信登录失败（{data.get('errmsg', 'unknown')}），请重试",
        )

    openid = data.get("openid")
    if not openid:
        raise AppError(code=401, message="微信未返回 openid，请重试")

    return {"openid": openid, "session_key": data.get("session_key", "")}


async def upsert_user(db: AsyncSession, *, openid: str) -> User:
    """按 openid 查找用户；不存在则创建（默认 role=student）。

    使用 db.flush() 而非 db.commit()，让调用方控制事务边界。
    """
    result = await db.execute(select(User).where(User.openid == openid))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            id=uuid.uuid4(),
            openid=openid,
            role="student",
            is_active=True,
        )
        db.add(user)
        await db.flush()  # get id without committing

    return user


# ─── 合规扩展：年龄核验 + 协议确认（D-073 / 需求文档 §4.1）────────────────────
from datetime import datetime, timezone

from app.schemas.compliance import CompleteProfileResponse
from app.services.sms_service import (
    generate_code,
    expires_at_from_now,
    send_sms_code,
)

GUARDIAN_AGE_THRESHOLD = 14


def compute_age(birth_year: int) -> int:
    return datetime.now(timezone.utc).year - birth_year


async def complete_profile(
    db: AsyncSession,
    *,
    user: User,
    birth_year: int,
    guardian_phone: str | None,
    user_phone: str | None,
    agreement_version: str,
    preferred_textbook_version: str | None = None,
    preferred_grade: str | None = None,
    preferred_semester: str | None = None,
) -> CompleteProfileResponse:
    """首次登录完善资料。<14岁需监护人手机号 + 发码（profile_completed=False 直到 guardian_verify）。
    V2 教材偏好字段可选写入（D-079 / M1）。
    """
    age = compute_age(birth_year)
    needs_guardian = age < GUARDIAN_AGE_THRESHOLD

    if needs_guardian and not guardian_phone:
        raise AppError(code=400, message=f"未满 {GUARDIAN_AGE_THRESHOLD} 岁需提供监护人手机号")

    user.birth_year = birth_year
    user.agreement_version = agreement_version
    user.agreement_agreed_at = datetime.now(timezone.utc)
    if user_phone:
        user.phone = user_phone
    # V2 教材偏好
    if preferred_textbook_version:
        user.preferred_textbook_version = preferred_textbook_version
    if preferred_grade:
        user.preferred_grade = preferred_grade
    if preferred_semester:
        user.preferred_semester = preferred_semester  # type: ignore[assignment]

    if needs_guardian:
        user.guardian_phone = guardian_phone
        code = generate_code()
        user.phone_verify_code = code
        user.phone_verify_purpose = "guardian_verify"
        user.phone_verify_target = guardian_phone
        user.phone_verify_expires_at = expires_at_from_now()
        await send_sms_code(phone=guardian_phone, code=code, purpose="guardian_verify")
        user.profile_completed = False
    else:
        user.profile_completed = True

    await db.flush()
    return CompleteProfileResponse(
        profile_completed=user.profile_completed,
        needs_guardian_verify=needs_guardian,
        age=age,
    )


async def guardian_verify(
    db: AsyncSession,
    *,
    user: User,
    code: str,
) -> None:
    """监护人填写验证码确认。"""
    if user.phone_verify_purpose != "guardian_verify":
        raise AppError(code=400, message="无待确认的监护人验证")
    if (
        user.phone_verify_code != code
        or user.phone_verify_expires_at is None
        or user.phone_verify_expires_at < datetime.now(timezone.utc)
    ):
        raise AppError(code=400, message="验证码错误或已过期")

    user.guardian_verified_at = datetime.now(timezone.utc)
    user.profile_completed = True
    user.phone_verify_code = None
    user.phone_verify_purpose = None
    user.phone_verify_target = None
    user.phone_verify_expires_at = None
    await db.flush()


def is_minor_14_to_17(user: User) -> bool:
    """14-17 岁返回 True（购买会员需勾选监护人同意）。"""
    if user.birth_year is None:
        return False
    age = compute_age(user.birth_year)
    return 14 <= age <= 17
