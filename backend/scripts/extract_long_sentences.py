"""长难句抽取(独立后台任务,决策 D):扫平台真题 → 长句 → AI 拆解 → 挂句法 node → 落 long_sentence。

用法:
  python backend/scripts/extract_long_sentences.py --dry-run
  python backend/scripts/extract_long_sentences.py --limit 200
幂等:按 source_question_id 跳过已抽真题,可重跑回填。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import _async_session_factory  # noqa: E402
from app.services import long_sentence_service as lss  # noqa: E402


async def run(*, limit: int | None, dry_run: bool, min_words: int) -> None:
    async with _async_session_factory() as db:
        st = await lss.extract_from_platform(
            db, limit=limit, min_words=min_words, dry_run=dry_run)
    st.report(dry_run)
    if st.syntax_points:
        print("涉及句法点:", "、".join(sorted(st.syntax_points)))


def main() -> None:
    ap = argparse.ArgumentParser(description="长难句抽取(平台真题)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--min-words", type=int, default=lss.DEFAULT_MIN_WORDS)
    args = ap.parse_args()
    asyncio.run(run(limit=args.limit, dry_run=args.dry_run, min_words=args.min_words))


if __name__ == "__main__":
    main()
