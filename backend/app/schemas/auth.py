from pydantic import BaseModel, Field


class WxLoginRequest(BaseModel):
    code: str


class AdminLoginRequest(BaseModel):
    """运营管理员账号密码登录（M5 / D-098）。"""
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserProfileOut(BaseModel):
    id: str
    role: str
    nickname: str | None
    avatar_url: str | None
    is_active: bool


class UpdateProfileRequest(BaseModel):
    """PATCH /auth/profile — 用户可修改的偏好字段（V2 M23）。"""
    preferred_textbook_version: str | None = None
    preferred_grade: str | None = None
    preferred_semester: str | None = None
    city_code: str | None = None  # V2 M27 预留
