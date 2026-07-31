"""回填 platform 题 option_vocab_ready + logic_display + 挂边。

用法:
    cd backend
    python -m app.tasks.backfill_option_vocab
    python -m app.tasks.backfill_option_vocab --limit 200
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import sys

import sqlalchemy as sa

from app.core.database import _async_session_factory
from app.models.d16_question_domain import PlatformQuestion
from app.services import option_vocab_service as ovs
from app.services.logic_display_service import compose_logic_display
from app.services.question_analysis_service import _passage_map


async def _refresh_ready(db, pq: PlatformQuestion) -> bool:
    from sqlalchemy.orm.attributes import flag_modified
    meta = pq.meta if isinstance(pq.meta, dict) else {}
    ana = meta.get("analysis")
    if not isinstance(ana, dict) or not ana.get("confirmed_at"):
        return False
    if ana.get("validation_skipped"):
        ana = copy.deepcopy(ana)
        ana["option_vocab_ready"] = False
        pq.meta = {**meta, "analysis": ana}
        flag_modified(pq, "meta")
        return False
    kind = ana.get("kind")
    attach_res = await ovs.attach_platform_option_vocab(
        db, question=pq, analysis_kind=kind, analysis=ana)
    pmap = await _passage_map(db, [pq])
    passage = pmap.get(pq.block_id) if pq.block_id else None
    vocab_preview = ovs.preview_option_vocab(pq, ana)
    ld = compose_logic_display(pq, ana, passage=passage, vocab_preview=vocab_preview)
    ready = (
        attach_res.get("correct", 0) > 0
        and bool(ld.get("ready"))
        and kind in ("grammar_mc", "cloze", "word_fill", "passage_fill")
    )
    ana = copy.deepcopy(ana)
    ana["logic_display"] = ld
    ana["option_vocab_ready"] = ready
    pq.meta = {**meta, "analysis": ana}
    flag_modified(pq, "meta")
    return ready


async def run(*, limit: int | None, only_analyzed: bool) -> dict:
    async with _async_session_factory() as db:
        q = sa.select(PlatformQuestion).where(PlatformQuestion.type == "real")
        if only_analyzed:
            q = q.where(PlatformQuestion.meta["analysis"].isnot(None))
        q = q.order_by(PlatformQuestion.created_at.desc())
        if limit:
            q = q.limit(limit)
        rows = list((await db.execute(q)).scalars().all())
        attached = 0
        ready_n = 0
        touched = 0
        for i, pq in enumerate(rows, 1):
            try:
                if await _refresh_ready(db, pq):
                    ready_n += 1
                    touched += 1
                meta = pq.meta if isinstance(pq.meta, dict) else {}
                ana = meta.get("analysis") if isinstance(meta, dict) else None
                if isinstance(ana, dict) and ana.get("option_vocab_ready"):
                    attached += 1
            except Exception as exc:  # noqa: BLE001
                print(f"  skip {pq.id}: {exc}", file=sys.stderr)
                await db.rollback()
                continue
            if i % 100 == 0:
                await db.commit()
                print(f"  … {i}/{len(rows)} ready={ready_n}", flush=True)
        await db.commit()
        return {"scanned": len(rows), "option_vocab_ready": ready_n}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--all", action="store_true",
                    help="不限已解析,凡真题有 options/answer 都挂")
    args = ap.parse_args()
    print("[option-vocab-backfill] start", flush=True)
    res = asyncio.run(run(limit=args.limit, only_analyzed=not args.all))
    print(f"[option-vocab-backfill] done {res}", flush=True)


if __name__ == "__main__":
    main()
