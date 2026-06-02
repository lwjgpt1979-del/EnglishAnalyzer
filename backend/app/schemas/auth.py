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
