"""把 app/data/regions_seed.json(省/市,源自前端 cities.ts)灌入 region 表。幂等(upsert by code)。

用法: python backend/scripts/seed_regions.py
区县/乡镇用 import_regions.py 后补。
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402

from app.core.database import _async_session_factory  # noqa: E402
from app.models.d21_region import Region  # noqa: E402

_DATA = Path(__file__).resolve().parents[1] / "app" / "data" / "regions_seed.json"


async def main() -> None:
    rows = json.loads(_DATA.read_text(encoding="utf-8"))
    async with _async_session_factory() as db:
        for r in rows:
            await db.execute(
                pg_insert(Region)
                .values(code=r["code"], name=r["name"],
                        parent_code=r.get("parent_code"), level=r["level"])
                .on_conflict_do_update(index_elements=["code"],
                                       set_={"name": r["name"], "parent_code": r.get("parent_code"),
                                             "level": r["level"]})
            )
        await db.commit()
    print(f"[seed] region 灌入 {len(rows)} 行(省+市)。")


if __name__ == "__main__":
    asyncio.run(main())
