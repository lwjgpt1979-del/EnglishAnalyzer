from pydantic import BaseModel


class WxLoginRequest(BaseModel):
    code: str


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
