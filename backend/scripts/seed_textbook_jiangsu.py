"""江苏 13 设区市英语教材地图 seed(译林版·已校对)。

背景:江苏英语小学(三年级起点)/初中(7-9)/高中三学段均为译林版(牛津译林)。
虽是设区市选用制(省厅发目录、市级选),但英语 13 市均选译林版(译林=江苏本省社);
注意其它科有市际差异(如数学无锡/苏州人教版),故本脚本只灌英语。
核实来源:2024 秋-2025 春江苏中小学教学用书。

用法:
  DATABASE_URL=postgresql+psycopg://... python backend/scripts/seed_textbook_jiangsu.py

幂等:按 region_code upsert;已存在则覆盖为译林版·已校对(verified=True),可重复跑。
只灌 region 表里存在的江苏 level-2 市;省级默认行不动(仍由 textbook_map_service.seed_defaults 管)。
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sqlalchemy as sa  # noqa: E402

from app.core.database import _async_session_factory  # noqa: E402
from app.models.d21_region import Region  # noqa: E402
from app.services import textbook_map_service as tb  # noqa: E402

NOTE = ("译林版(牛津译林)——小学(三年级起点)/初中(7-9)/高中 三学段均为译林版。"
        "江苏系设区市选用制(省厅发目录、市级选),英语13市均选译林版;"
        "注意其它科有市际差异(如数学无锡/苏州人教版、余苏教版)。核实:2024秋-2025春江苏教学用书。")


async def main() -> None:
    async with _async_session_factory() as db:
        js = (await db.execute(sa.select(Region.code, Region.name)
              .where(Region.level == 1, Region.name.like("%江苏%")))).first()
        if js is None:
            print("✗ region 表没有江苏省行,请先灌 region 数据")
            return
        js_code, js_name = js
        cities = (await db.execute(sa.select(Region.code, Region.name)
                  .where(Region.level == 2, Region.parent_code == js_code)
                  .order_by(Region.code))).all()
        if not cities:
            print(f"✗ {js_name}({js_code}) 下没有 level-2 地级市")
            return
        for code, name in cities:
            await tb.upsert(db, region_code=code, versions=["译林版"],
                            note=NOTE, verified=True)
            print(f"  ✓ {code} {name} → 译林版·已校对")
        await db.commit()
        print(f"\n完成:{js_name} {len(cities)} 个设区市英语=译林版(已校对)")


if __name__ == "__main__":
    asyncio.run(main())
