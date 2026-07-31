"""从小题所属试卷列回填 platform_question.region_code / region_name。

根因:批量上传共享 meta 残留旧 city_code,拆题时小题继承了错误市码(如无锡卷→3204 常州)。
卷表列已按文件名解析为正确地区,但 meta 与小题未同步。

用法:
    cd backend
    python -m app.tasks.backfill_question_region_from_paper
    python -m app.tasks.backfill_question_region_from_paper --dry-run
"""
from __future__ import annotations

import argparse
import asyncio

import sqlalchemy as sa

from app.core.database import _async_session_factory
from app.models.d16_question_domain import PlatformPaper, PlatformQuestion


async def run(*, dry_run: bool) -> dict:
    async with _async_session_factory() as db:
        mismatch = (await db.execute(
            sa.select(PlatformQuestion, PlatformPaper)
            .join(PlatformPaper, PlatformPaper.id == PlatformQuestion.paper_id)
            .where(
                PlatformPaper.region_code.isnot(None),
                PlatformPaper.region_code != "",
                sa.or_(
                    PlatformQuestion.region_code.is_distinct_from(PlatformPaper.region_code),
                    PlatformQuestion.region_name.is_distinct_from(PlatformPaper.region_name),
                ),
            )
        )).all()
        n_q = 0
        for q, p in mismatch:
            if not dry_run:
                q.region_code = p.region_code
                q.region_name = p.region_name
            n_q += 1

        papers = (await db.execute(
            sa.select(PlatformPaper).where(PlatformPaper.region_code.isnot(None))
        )).scalars().all()
        n_p = 0
        for p in papers:
            meta = dict(p.meta or {})
            rc, rn = p.region_code, p.region_name
            if meta.get("region_code") == rc and meta.get("city_code") == rc and meta.get("region_name") == rn:
                continue
            if not dry_run:
                meta["region_code"] = rc
                meta["city_code"] = rc
                meta["region_name"] = rn
                meta.pop("province_code", None)
                p.meta = meta
            n_p += 1

        if not dry_run:
            await db.commit()
        return {"questions_fixed": n_q, "papers_meta_synced": n_p, "dry_run": dry_run}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    print(asyncio.run(run(dry_run=args.dry_run)))


if __name__ == "__main__":
    main()
