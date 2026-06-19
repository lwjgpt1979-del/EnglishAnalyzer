"""导入区县/乡镇(或任意层级)到 region 表。幂等 upsert by code。

支持 CSV / JSON。code 沿用 GB/T 2260 前缀方案,parent_code 缺省按 code 前缀自动推断
(6位区县→前4位市;9位乡镇→前6位区县),也可在数据里显式给 parent_code/level。

用法:
  python backend/scripts/import_regions.py --csv districts.csv      # 表头: code,name[,parent_code][,level]
  python backend/scripts/import_regions.py --json regions.json      # [{code,name,parent_code?,level?}]
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402

from app.core.database import _async_session_factory  # noqa: E402
from app.models.d21_region import Region  # noqa: E402


def _infer_parent(code: str) -> str | None:
    if len(code) <= 2:
        return None
    if len(code) <= 4:
        return code[:2]
    if len(code) <= 6:
        return code[:4]
    if len(code) <= 9:
        return code[:6]
    return code[:9]


def _infer_level(code: str) -> int:
    return {2: 1, 4: 2, 6: 3}.get(len(code), 4)


def _normalize(rec: dict) -> dict:
    code = str(rec["code"]).strip()
    return {
        "code": code, "name": str(rec["name"]).strip(),
        "parent_code": (rec.get("parent_code") or "").strip() or _infer_parent(code),
        "level": int(rec["level"]) if rec.get("level") else _infer_level(code),
    }


async def _load(records: list[dict]) -> None:
    rows = [_normalize(r) for r in records if r.get("code") and r.get("name")]
    async with _async_session_factory() as db:
        for r in rows:
            await db.execute(
                pg_insert(Region).values(**r).on_conflict_do_update(
                    index_elements=["code"],
                    set_={"name": r["name"], "parent_code": r["parent_code"], "level": r["level"]}))
        await db.commit()
    print(f"[import] region 导入/更新 {len(rows)} 行。")


def main() -> None:
    ap = argparse.ArgumentParser(description="导入区县/乡镇到 region 表")
    ap.add_argument("--csv")
    ap.add_argument("--json")
    args = ap.parse_args()
    if args.csv:
        with open(args.csv, encoding="utf-8-sig", newline="") as f:
            records = list(csv.DictReader(f))
    elif args.json:
        records = json.loads(Path(args.json).read_text(encoding="utf-8"))
    else:
        ap.error("需 --csv 或 --json")
    asyncio.run(_load(records))


if __name__ == "__main__":
    main()
