"""
Alembic 迁移运行环境。

关键点：
  1. 从 DATABASE_URL 环境变量读取连接（覆盖 alembic.ini 中的占位符）。
  2. import app.models 触发所有 37 张表注册到 Base.metadata。
  3. target_metadata = Base.metadata 让 autogenerate 感知模型变化。
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# ── 加载日志配置 ─────────────────────────────────────────────────────────────
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── 导入所有模型（必须在 target_metadata 之前）────────────────────────────────
import app.models  # noqa: F401, E402
from app.models.base import Base  # noqa: E402

target_metadata = Base.metadata

# ── 数据库连接 URL:优先 DATABASE_URL 环境变量;没有则回退读 .env(app settings)──
# 不回退时 alembic.ini 里是占位符 placeholder,本地直接跑会连到不存在的主机
# (被本机代理 fake-ip 解析成 198.18.x.x)而报连接失败——回退可让本地零配置直接跑。
database_url = os.environ.get("DATABASE_URL")
if not database_url:
    try:
        from app.core.config import settings
        database_url = str(getattr(settings, "database_url", "")
                           or getattr(settings, "DATABASE_URL", "")) or None
    except Exception:  # noqa: BLE001  读不到就维持占位符,交由环境变量提供
        database_url = None
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)


# ── offline 模式（生成 SQL 脚本，不实际连接）─────────────────────────────────
def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ── online 模式（直接连接数据库执行）─────────────────────────────────────────
def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
