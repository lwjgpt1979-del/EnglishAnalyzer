"""图片上传预签名 URL API。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.exceptions import AppError
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.services.upload_service import ALLOWED_CONTENT_TYPES, PRESIGN_EXPIRES, generate_presign

router = APIRouter(prefix="/upload", tags=["upload"])

UserDep = Annotated[User, Depends(get_current_user)]

# ── Schemas ───────────────────────────────────────────────────────────────────


class PresignRequest(BaseModel):
    """预签名 URL 请求体。"""

    content_type: str = Field(
        ...,
        description="图片 MIME 类型，允许：image/jpeg · image/png · image/webp · image/gif",
    )


class PresignOut(BaseModel):
    """预签名 URL 响应。"""

    presign_url: str = Field(..., description="PUT 上传 URL，有效期10分钟")
    file_url: str = Field(..., description="上传成功后的最终访问 URL")
    key: str = Field(..., description="COS 对象 Key")
    expires_in: int = Field(..., description=f"预签名 URL 有效期（秒），固定 {PRESIGN_EXPIRES}")


# ── Endpoint ──────────────────────────────────────────────────────────────────


@router.post("/presign", response_model=BaseResponse[PresignOut])
async def get_upload_presign(body: PresignRequest, current_user: UserDep):
    """为当前用户生成图片上传预签名 PUT URL。

    1. 校验 content_type 在白名单内（jpeg / png / webp / gif）。
    2. 生成带用户 ID 隔离的 COS 对象 Key。
    3. 返回预签名 URL（dev 模式返回 mock URL）。

    客户端拿到 presign_url 后直接 HTTP PUT（body 为图片二进制），
    成功后用 file_url 调用 POST /wrong-questions/ 创建错题。
    """
    if body.content_type not in ALLOWED_CONTENT_TYPES:
        allowed = "、".join(ALLOWED_CONTENT_TYPES)
        raise AppError(code=400, message=f"不支持的图片类型：{body.content_type}，允许：{allowed}")

    result = generate_presign(
        user_id=current_user.id,
        content_type=body.content_type,
    )
    return make_ok(PresignOut(**result))
