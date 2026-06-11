"""图形验证码 service（M48，防短信盗刷）。

服务端生成 4 位字符 SVG 图形验证码，挑战存库一次性核销。无第三方依赖。
"""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d9_system import CaptchaChallenge

# 去掉易混字符（0/O、1/I/l 等）
_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_LENGTH = 4
TTL_MINUTES = 5
_COLORS = ["#3d8bf5", "#2b6fd6", "#ff7a59", "#18a058", "#7b4dff", "#d9603f"]


def _random_code() -> str:
    return "".join(random.choices(_CHARS, k=_LENGTH))


def _build_svg(code: str) -> str:
    w, h = 120, 44
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}">',
        f'<rect width="{w}" height="{h}" fill="#f2f5fa" rx="6"/>',
    ]
    # 干扰线
    for _ in range(4):
        x1, y1, x2, y2 = (random.randint(0, w), random.randint(0, h),
                          random.randint(0, w), random.randint(0, h))
        c = random.choice(_COLORS)
        parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{c}" stroke-width="1" opacity="0.4"/>'
        )
    # 干扰点
    for _ in range(18):
        parts.append(
            f'<circle cx="{random.randint(0, w)}" cy="{random.randint(0, h)}" '
            f'r="1" fill="{random.choice(_COLORS)}" opacity="0.5"/>'
        )
    # 字符
    for i, ch in enumerate(code):
        x = 16 + i * 26
        y = 30 + random.randint(-3, 3)
        angle = random.randint(-18, 18)
        c = random.choice(_COLORS)
        parts.append(
            f'<text x="{x}" y="{y}" font-size="26" font-weight="700" '
            f'font-family="Arial, sans-serif" fill="{c}" '
            f'transform="rotate({angle} {x} {y})">{ch}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


async def generate(db: AsyncSession) -> tuple[str, str]:
    """生成一个图形验证码，返回 (captcha_id, svg)。"""
    code = _random_code()
    challenge = CaptchaChallenge(
        id=uuid.uuid4(), answer=code.upper(),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=TTL_MINUTES),
    )
    db.add(challenge)
    await db.flush()
    return str(challenge.id), _build_svg(code)


async def verify(db: AsyncSession, *, captcha_id: str, answer: str) -> None:
    """校验并核销图形验证码；失败抛 AppError。"""
    try:
        cid = uuid.UUID(str(captcha_id))
    except (ValueError, TypeError):
        raise AppError(code=400, message="图形验证码无效，请刷新重试")
    row = (await db.execute(
        select(CaptchaChallenge).where(CaptchaChallenge.id == cid)
    )).scalar_one_or_none()
    if row is None or row.consumed:
        raise AppError(code=400, message="图形验证码已失效，请刷新重试")
    if row.expires_at < datetime.now(timezone.utc):
        raise AppError(code=400, message="图形验证码已过期，请刷新重试")
    if row.answer != (answer or "").strip().upper():
        # 答错也核销，避免被暴力穷举
        row.consumed = True  # type: ignore[assignment]
        await db.flush()
        raise AppError(code=400, message="图形验证码错误，请刷新重试")
    row.consumed = True  # type: ignore[assignment]
    await db.flush()
