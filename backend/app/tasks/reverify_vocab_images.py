"""存量坏图清理 CLI:VLM 复核已发布单词配图,只对不达标(词不达意 / 含文字)的重刷。

供服务器 crontab 低峰调用,分批扫描全库已发布配图:
- 复核结果按图 md5 缓存(vocab_image_verify_cache)→ 重复跑跳过已复核好图,天然收敛、不二次付费;
- 坏图走新管线(生成前可画性自评 → 负向约束多图 → VLM 复核选优)重生成,拿不到好图则降级词义卡。

用法:
    DATABASE_URL=... python -m app.tasks.reverify_vocab_images
    DATABASE_URL=... python -m app.tasks.reverify_vocab_images --limit 200 --max-scan 2000
"""
import argparse
import asyncio

from app.services import task_run_service
from app.services import vocab_media_service as vms


async def _main(batch: int, max_scan: int) -> None:
    async def _work(s):
        total = {"scanned": 0, "bad": 0, "regen_ok": 0, "regen_degraded": 0}
        offset = 0
        while offset < max_scan:
            r = await vms.reverify_and_regen_batch(s, limit=batch, offset=offset)
            for k in total:
                total[k] += int(r.get(k, 0))
            offset = int(r.get("next_offset", offset + batch))
            if int(r.get("scanned", 0)) < batch:   # 扫到底
                break
        return total

    res = await task_run_service.run("vocab_image_reverify", _work)
    print(f"[vocab-image-reverify] {res}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200, help="每批扫描词数(默认 200)")
    ap.add_argument("--max-scan", type=int, default=5000,
                    help="本次最多扫描词数,防单次跑太久(默认 5000)")
    args = ap.parse_args()
    asyncio.run(_main(args.limit, args.max_scan))
