import os
from collections.abc import AsyncGenerator

import sqlalchemy as sa
from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

# ── Sync engine（Alembic 迁移专用）────────────────────────────────────────────


def get_engine_url() -> str | None:
    """从环境变量读取同步数据库 URL（不存在则返回 None）。"""
    return os.getenv("DATABASE_URL")


def create_sync_engine(url: str | None = None) -> Engine:
    """创建同步 SQLAlchemy engine（供 Alembic 迁移使用）。"""
    db_url = url or get_engine_url()
    if not db_url:
        raise RuntimeError(
            "DATABASE_URL 环境变量未设置。"
            "请复制 .env.example 为 .env 并填写真实数据库连接。"
        )
    return create_engine(db_url, echo=False)


def create_session_factory(engine: Engine) -> "sessionmaker[Session]":
    """返回 SessionLocal 工厂。"""
    return sessionmaker(engine, autocommit=False, autoflush=False)


# ── Async engine（FastAPI 请求处理专用）────────────────────────────────────────


def _build_async_engine():
    url = os.getenv("ASYNC_DATABASE_URL")
    if not url:
        raise RuntimeError(
            "ASYNC_DATABASE_URL 环境变量未设置。"
            "请复制 .env.example 为 .env 并填写真实数据库连接。"
        )
    return create_async_engine(url, echo=os.getenv("DEBUG", "false").lower() == "true")


_async_engine = _build_async_engine()
_async_session_factory = async_sessionmaker(_async_engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：yield 一个 AsyncSession，请求结束自动关闭。"""
    async with _async_session_factory() as session:
        yield session


async def get_rls_db(
    session: AsyncSession,
    user_id: str,
) -> None:
    """在当前事务中注入 RLS 会话变量 app.current_user_id。

    使用方式（在 endpoint 依赖链中）：
        db = Depends(get_db)
        current_user = Depends(get_current_user)
        await get_rls_db(db, str(current_user.id))
        # 之后的 db 操作自动受 RLS 过滤

    SET LOCAL 作用域为当前事务，连接归还连接池时自动清除。
    """
    # PostgreSQL SET LOCAL does not support parameterised values ($1 / :uid);
    # the value must be embedded as a literal.  user_id is always a UUID
    # string (hex + hyphens), so it is safe to interpolate directly.
    await session.execute(sa.text(f"SET LOCAL app.current_user_id = '{user_id}'"))


async def close_async_engine() -> None:
    """应用关闭时释放连接池（在 lifespan shutdown 中调用）。"""
    await _async_engine.dispose()
