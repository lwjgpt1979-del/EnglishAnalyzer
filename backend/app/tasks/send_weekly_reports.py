"""学情周报 CLI：供服务器 crontab 每周一 08:00 调用（V2 M30）。

用法：
    DATABASE_URL=... python -m app.tasks.send_weekly_reports

Cron 条目（每周一 08:00）：
    0 8 * * 1 cd /opt/enggramer/backend && DATABASE_URL=... /path/python -m app.tasks.send_weekly_reports
"""
import asyncio

from app.core.database import _async_session_factory
from app.services import weekly_report_service


async def _main() -> None:
    async with _async_session_factory() as s:
        res = await weekly_report_service.run_weekly_reports(s)
        await s.commit()
        print(
            f"[weekly-reports] students_processed={res['students_processed']} "
            f"relatives_notified={res['relatives_notified']}"
        )


if __name__ == "__main__":
    asyncio.run(_main())
