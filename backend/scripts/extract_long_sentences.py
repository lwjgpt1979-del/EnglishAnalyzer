"""长难句抽取(独立后台任务,决策 D):三源 → 长句 → AI 拆解 → 挂句法 node → 落 long_sentence。

用法:
  python backend/scripts/extract_long_sentences.py --dry-run
  python backend/scripts/extract_long_sentences.py --limit 200
  python backend/scripts/extract_long_sentences.py --source textbook   # ②教材语料
  python backend/scripts/extract_long_sentences.py --source uploaded   # ③学生上传
  python backend/scripts/extract_long_sentences.py --source all        # 三源
缺省(--source config)读后台 long_sentence.sources 配置。
幂等:平台真题/上传题按 source_question_id、教材语料按 source_passage_id 跳过已抽,可重跑回填。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import _async_session_factory  # noqa: E402
from app.services import long_sentence_service as lss  # noqa: E402


_ALL_SOURCES = ["platform_real", "textbook", "uploaded"]


async def run(*, source: str, limit: int | None, dry_run: bool, min_words: int) -> None:
    if source == "config":
        sources = None  # run_extract 读配置
    elif source == "all":
        sources = _ALL_SOURCES
    else:
        sources = [source]
    async with _async_session_factory() as db:
        st = await lss.run_extract(db, sources=sources, limit=limit, min_words=min_words, dry_run=dry_run)
    st.report(dry_run)
    if st.syntax_points:
        print("涉及句法点:", "、".join(sorted(st.syntax_points)))


def main() -> None:
    ap = argparse.ArgumentParser(description="长难句抽取(三源:平台真题/教材语料/学生上传)")
    ap.add_argument("--source", choices=["config", "all", *_ALL_SOURCES], default="config",
                    help="抽取来源;config(默认)读后台 long_sentence.sources 配置")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--min-words", type=int, default=lss.DEFAULT_MIN_WORDS)
    args = ap.parse_args()
    asyncio.run(run(source=args.source, limit=args.limit, dry_run=args.dry_run, min_words=args.min_words))


if __name__ == "__main__":
    main()
