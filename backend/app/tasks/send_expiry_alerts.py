"""机构会员到期预警 CLI：供服务器 crontab 每日调用。
用法：DATABASE_URL=... python -m app.tasks.send_expiry_alerts
"""
import asyncio

from app.services import institution_expiry_alert_service, task_run_service


async def _work(s):
    res = await institution_expiry_alert_service.run_expiry_alerts(s)
    await s.commit()
    return res


async def _main() -> None:
    res = await task_run_service.run("expiry_alerts", _work)
    print(f"[expiry-alerts] institutions={res['institutions_notified']} "
          f"admins={res['admins_notified']}")


if __name__ == "__main__":
    asyncio.run(_main())
