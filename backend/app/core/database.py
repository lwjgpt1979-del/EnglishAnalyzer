import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def get_engine_url() -> str | None:
    """从环境变量读取数据库 URL（不存在则返回 None）。"""
    return os.getenv("DATABASE_URL")


def create_sync_engine(url: str | None = None):
    """创建同步 SQLAlchemy engine（供 Alembic 迁移使用）。"""
    db_url = url or get_engine_url()
    if not db_url:
        raise RuntimeError(
            "DATABASE_URL 环境变量未设置。"
            "请复制 .env.example 为 .env 并填写真实数据库连接。"
        )
    return create_engine(db_url, echo=False)


def create_session_factory(engine):
    """返回 SessionLocal 工厂。"""
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)
