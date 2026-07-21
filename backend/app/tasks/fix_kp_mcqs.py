"""考点题 AI 审校修正 CLI:供服务器 crontab **低峰**调用(DeepSeek 低峰时段更省钱)。

扫报错数 ≥ 阈值(system_configs.kp_mcq_report_threshold,默认 3)的考点题,逐题用**推理档** LLM
审校修正答案/解析/干扰项 → 更新题 + 记修改记录(vocab_kp_mcq_revision)+ report_count 归 0。

用法(建议北京时间凌晨低峰,如 01:30):
    DATABASE_URL=... python -m app.tasks.fix_kp_mcqs
    DATABASE_URL=... python -m app.tasks.fix_kp_mcqs --limit 200
"""
import argparse
import asyncio

from app.services import task_run_service
from app.services import word_kp_service


async def _main(limit: int) -> None:
    async def _work(s):
        return await word_kp_service.fix_pending_kp_mcqs(s, limit=limit)

    res = await task_run_service.run("kp_mcq_autofix", _work)
    print(f"[kp-mcq-autofix] {res}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100, help="本次最多修正题数(默认 100)")
    args = ap.parse_args()
    asyncio.run(_main(args.limit))
