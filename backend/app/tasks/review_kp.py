"""考点 AI 自审校 CLI(P5):供服务器 crontab **低峰**调用(DeepSeek 低峰时段更省钱)。

扫未审校(vocab_word_kp.reviewed_at 为空)的词,逐词用**推理档** LLM 审校其"用法/考法类文本维"考点
(可链维已 morph/wordnet/词库背书、搭配已语料印证,不重审):删明显错项 / 改表述不准 → 置 reviewed_at + 记
vocab_word_kp_review(before/after)。

用法(建议北京时间凌晨低峰,如 02:00):
    DATABASE_URL=... python -m app.tasks.review_kp
    DATABASE_URL=... python -m app.tasks.review_kp --limit 200
"""
import argparse
import asyncio

from app.services import task_run_service
from app.services import word_kp_service


async def _main(limit: int) -> None:
    async def _work(s):
        return await word_kp_service.review_pending_kp(s, limit=limit)

    res = await task_run_service.run("kp_review", _work)
    print(f"[kp-review] {res}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100, help="本次最多审校词数(默认 100)")
    args = ap.parse_args()
    asyncio.run(_main(args.limit))
