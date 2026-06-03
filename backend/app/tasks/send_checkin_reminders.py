"""打卡提醒 CLI：供服务器 crontab 每晚调用。
用法：DATABASE_URL=... python -m app.tasks.send_checkin_reminders
"""
import asyncio

from app.core.database import _async_session_factory
from app.services import reminder_service


async def _main() -> None:
    async with _async_session_factory() as s:
        res = await reminder_service.run_checkin_reminders(s)
        await s.commit()
        print(f"[checkin-reminders] notified={res['notified']}")


if __name__ == "__main__":
    asyncio.run(_main())
