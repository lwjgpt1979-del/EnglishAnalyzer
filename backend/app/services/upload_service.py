"""图片上传预签名 URL 服务。

流程：后端生成 COS 预签名 PUT URL → 客户端直接 PUT 到 COS → 用 file_url 创建 WrongQuestion。
Dev 模式（cos_secret_key 以 'placeholder' 开头）跳过 COS，返回 mock URL。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.core.config import settings

# ── 常量 ─────────────────────────────────────────────────────────────────────

ALLOWED_CONTENT_TYPES: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}

PRESIGN_EXPIRES: int = 600  # 10 分钟（秒）


# ── 内部辅助 ──────────────────────────────────────────────────────────────────


def _is_cos_dev_mode() -> bool:
    """True 当 cos_secret_key 为占位符——无法调用真实 COS。"""
    return settings.cos_secret_key.startswith("placeholder")


def _make_cos_client():  # type: ignore[return]
    """创建 COS S3 客户端（仅 prod 模式调用）。"""
    from qcloud_cos import CosConfig, CosS3Client  # type: ignore[import]

    config = CosConfig(
        Region=settings.cos_region,
        SecretId=settings.cos_secret_id,
        SecretKey=settings.cos_secret_key,
    )
    return CosS3Client(config)


def _build_key(user_id: uuid.UUID, ext: str) -> str:
    """生成唯一对象 Key：uploads/{user_id}/{YYYYMMDD}/{8位uuid}.{ext}"""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    short_id = uuid.uuid4().hex[:8]
    return f"uploads/{user_id}/{today}/{short_id}.{ext}"


# ── 公开接口 ──────────────────────────────────────────────────────────────────


def generate_presign(
    *,
    user_id: uuid.UUID,
    content_type: str,
) -> dict[str, str | int]:
    """生成 COS 预签名 PUT URL。

    参数：
        user_id: 当前登录用户 ID（用于 key 路径隔离）
        content_type: 已通过白名单校验的 MIME 类型（如 'image/jpeg'）

    返回：
        {presign_url, file_url, key, expires_in}
    """
    ext = ALLOWED_CONTENT_TYPES[content_type]
    key = _build_key(user_id, ext)

    if _is_cos_dev_mode():
        # dev 模式：用 picsum.photos 公开占位图作为最终 URL（小程序详情页能真显示出图）
        # presign_url 仍是 mock；前端检测 is_mock=True 时跳过 PUT 直接走 createWQ
        seed = key.replace("/", "-").rsplit(".", 1)[0]  # 每张图随机
        return {
            "presign_url": f"https://mock-cos.dev/{key}?X-Mock-Sig=dev",
            "file_url": f"https://picsum.photos/seed/{seed}/600/800.jpg",
            "key": key,
            "expires_in": PRESIGN_EXPIRES,
            "is_mock": True,
        }

    client = _make_cos_client()
    presign_url: str = client.get_presigned_url(
        Method="PUT",
        Bucket=settings.cos_bucket,
        Key=key,
        Expired=PRESIGN_EXPIRES,
    )
    file_url = f"{settings.cos_base_url}/{key}"
    return {
        "presign_url": presign_url,
        "file_url": file_url,
        "key": key,
        "expires_in": PRESIGN_EXPIRES,
        "is_mock": False,
    }
