"""机构会员到期预警 CLI：供服务器 crontab 每日调用。
用法：DATABASE_URL=... python -m app.tasks.send_expiry_alerts
"""
import asyncio

from app.core.database import _async_session_factory
from app.services import institution_expiry_alert_service


async def _main() -> None:
    async with _async_session_factory() as s:
        res = await institution_expiry_alert_service.run_expiry_alerts(s)
        await s.commit()
        print(f"[expiry-alerts] institutions={res['institutions_notified']} "
              f"admins={res['admins_notified']}")


if __name__ == "__main__":
    asyncio.run(_main())
