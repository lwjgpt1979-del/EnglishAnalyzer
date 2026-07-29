"""考点 AI 审校 CLI(P5 自审 + P6 报错修正 + 二期 AI 预隐):crontab **低峰**调用。

推理档,三步(报错优先):
1) P6 报错修正:扫被学生报错达阈值的词,逐词审校报错项(删/改);
2) 二期 AI 预隐:中考高频(star=3)未预隐词的近义/易混,只预隐纯 LLM 无词库命中行;
3) P5 巡检自审:扫未审校词的用法/考法类文本维。

用法(建议北京时间凌晨低峰,如 02:00):
    DATABASE_URL=... python -m app.tasks.review_kp
    DATABASE_URL=... python -m app.tasks.review_kp --limit 200
    DATABASE_URL=... python -m app.tasks.review_kp --prehide-limit 50
"""
import argparse
import asyncio

from app.services import task_run_service
from app.services import word_kp_service


async def _main(limit: int, prehide_limit: int) -> None:
    async def _work(s):
        reported = await word_kp_service.fix_pending_reported_kp(s, limit=limit)
        prehide = await word_kp_service.prehide_pending_kp(s, limit=prehide_limit)
        review = await word_kp_service.review_pending_kp(s, limit=limit)
        return {"reported": reported, "prehide": prehide, "review": review}

    res = await task_run_service.run("kp_review", _work)
    print(f"[kp-review] {res}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100, help="P5/P6 本次最多词数(默认 100)")
    ap.add_argument("--prehide-limit", type=int, default=50, help="二期 AI 预隐本次最多词数(默认 50)")
    args = ap.parse_args()
    asyncio.run(_main(args.limit, args.prehide_limit))
