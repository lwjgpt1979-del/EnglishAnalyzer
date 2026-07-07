"""打卡提醒 CLI：供服务器 crontab 每晚调用。
用法：DATABASE_URL=... python -m app.tasks.send_checkin_reminders
"""
import asyncio

from app.services import reminder_service, task_run_service


async def _work(s):
    res = await reminder_service.run_checkin_reminders(s)
    await s.commit()
    return res


async def _main() -> None:
    res = await task_run_service.run("checkin_reminders", _work)
    print(f"[checkin-reminders] notified={res['notified']}")


if __name__ == "__main__":
    asyncio.run(_main())
