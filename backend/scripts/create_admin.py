"""创建 / 重置运营管理员账号（M5 / D-098）。

用法（密码只从环境变量读，绝不写进 git、不打印明文）：

    ADMIN_USERNAME=ops ADMIN_PASSWORD='你的强密码' \
        /opt/anaconda3/bin/python scripts/create_admin.py

需在 backend 目录下、且已加载 .env（DATABASE_URL 指向目标库）：

    set -a && . ./.env && set +a && \
    ADMIN_USERNAME=ops ADMIN_PASSWORD='****' python scripts/create_admin.py
"""
import asyncio
import os
import sys

from app.core.database import _async_session_factory
from app.services import admin_auth_service


async def main() -> None:
    username = os.environ.get("ADMIN_USERNAME")
    password = os.environ.get("ADMIN_PASSWORD")
    if not username or not password:
        print("ERROR: 需设置环境变量 ADMIN_USERNAME 与 ADMIN_PASSWORD", file=sys.stderr)
        sys.exit(1)
    if len(password) < 8:
        print("ERROR: 密码至少 8 位", file=sys.stderr)
        sys.exit(1)
    async with _async_session_factory() as s:
        user = await admin_auth_service.create_admin(
            s, username=username, password=password,
        )
        await s.commit()
        print(f"✓ admin ready: username={username} id={user.id} role={user.role}")


if __name__ == "__main__":
    asyncio.run(main())
