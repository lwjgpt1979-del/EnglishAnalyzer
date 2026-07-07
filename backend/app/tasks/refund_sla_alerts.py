"""退款/申诉 SLA 超时告警 CLI（§4.5.3）：供服务器 crontab 每日调用。
用法：DATABASE_URL=... python -m app.tasks.refund_sla_alerts
"""
import asyncio

from app.services import refund_service, task_run_service


async def _work(s):
    res = await refund_service.run_sla_alerts(s)
    await s.commit()
    return res


async def _main() -> None:
    res = await task_run_service.run("refund_sla_alerts", _work)
    print(f"[refund-sla] overdue={res['overdue']} admins_notified={res['admins_notified']}")


if __name__ == "__main__":
    asyncio.run(_main())
