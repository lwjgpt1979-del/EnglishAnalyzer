"""图片上传预签名 URL API。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, Field

from app.core.exceptions import AppError
from app.core.security import get_current_user
from app.models.d1_users import User
from app.schemas.base import BaseResponse, make_ok
from app.services.upload_service import (
    ALLOWED_CONTENT_TYPES,
    PRESIGN_EXPIRES,
    generate_presign,
    upload_image_bytes,
)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB

# 文件名扩展名 → MIME，兜底推断（部分端 multipart 不带可靠 content_type）
_EXT_TO_CT = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
              "webp": "image/webp", "gif": "image/gif"}

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
    is_mock: bool = Field(False, description="dev 模式 mock：前端检测到 true 时跳过 PUT 上传步骤")


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


class ProxyUploadOut(BaseModel):
    """中转上传响应。"""

    file_url: str = Field(..., description="上传成功后的最终访问 URL")
    key: str = Field(..., description="COS 对象 Key")
    is_mock: bool = Field(False, description="dev 模式：返回占位图 URL")


@router.post("/proxy", response_model=BaseResponse[ProxyUploadOut])
async def proxy_upload(current_user: UserDep, file: Annotated[UploadFile, File()]):
    """服务端中转上传：接收图片字节 → 服务端传 COS → 返回 file_url。

    用于 H5 等无法浏览器直传 COS（CORS 限制）的端;小程序端仍走 /presign 直传。
    校验 MIME 白名单与大小上限（10MB）。
    """
    ct = (file.content_type or "").lower()
    if ct not in ALLOWED_CONTENT_TYPES:
        # content_type 不可靠时按扩展名兜底推断
        ext = (file.filename or "").rsplit(".", 1)[-1].lower()
        ct = _EXT_TO_CT.get(ext, "")
    if ct not in ALLOWED_CONTENT_TYPES:
        allowed = "、".join(ALLOWED_CONTENT_TYPES)
        raise AppError(code=400, message=f"不支持的图片类型，允许：{allowed}")

    data = await file.read()
    if not data:
        raise AppError(code=400, message="空文件")
    if len(data) > MAX_UPLOAD_BYTES:
        raise AppError(code=400, message="图片过大（上限 10MB）")

    result = upload_image_bytes(user_id=current_user.id, content_type=ct, data=data)
    return make_ok(ProxyUploadOut(**result))
