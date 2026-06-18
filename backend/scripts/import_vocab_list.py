"""R5 通用词库导入:把权威考纲词表导入 vocab_list + vocab_list_item。

用法:
  # 从 JSON 文件导入(格式见下)
  python backend/scripts/import_vocab_list.py --name "高考3500" --exam-level senior --file words.json

JSON 格式:[{"word": "abandon", "rank": 1, "star": 5}, ...] 或纯词数组 ["abandon", ...]。
幂等:同名词库复用;条目按 (list_id, word_id) upsert。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.database import _async_session_factory  # noqa: E402
from app.models.d18_vocab_kg import VocabList  # noqa: E402
from app.services import vocab_list_service as vls  # noqa: E402


async def run(*, name: str, exam_level: str | None, source_type: str, items: list[dict]) -> None:
    async with _async_session_factory() as db:
        existing = (await db.execute(select(VocabList).where(VocabList.name == name))).scalar_one_or_none()
        if existing is None:
            vl = await vls.create_list(db, name=name, exam_level=exam_level,
                                       source_type=source_type, status="published")
        else:
            vl = existing
        n = await vls.add_items(db, list_id=vl.id, items=items)
        await db.commit()
        print(f"[done] 词库 '{name}' 导入条目 {n}")


def _normalize(raw: list) -> list[dict]:
    out = []
    for i, x in enumerate(raw):
        if isinstance(x, str):
            out.append({"word": x, "rank": i + 1})
        elif isinstance(x, dict) and x.get("word"):
            out.append(x)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="导入通用词库")
    ap.add_argument("--name", required=True)
    ap.add_argument("--exam-level", default=None)
    ap.add_argument("--source-type", default="official_syllabus")
    ap.add_argument("--file", required=True, help="JSON 文件(词数组或 {word,rank,star} 数组)")
    args = ap.parse_args()
    raw = json.loads(Path(args.file).read_text(encoding="utf-8"))
    items = _normalize(raw)
    asyncio.run(run(name=args.name, exam_level=args.exam_level,
                    source_type=args.source_type, items=items))


if __name__ == "__main__":
    main()
