"""已核实的英语教材地图 seed(逐条查证 verified=True)。

策略(见 memory / 讨论):人教版是全国默认主导版,不逐市标;只把「非人教主导」的
例外省市查证后锁定,其余靠 textbook_map_service.seed_defaults 的省级默认兜底。
每新增一块例外(福建仁爱、河北冀教…),往下面 DIRECT / EXPAND_PROVINCE 追加即可。

用法:
  DATABASE_URL=postgresql+psycopg://... python backend/scripts/seed_textbook_verified.py

幂等:按 region_code upsert;只灌 region 表里存在的地区。可重复跑。
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

_JS_NOTE = ("译林版(牛津译林)——小学(三年级起点)/初中(7-9)/高中 三学段均为译林版。"
            "江苏系设区市选用制(省厅发目录、市级选),英语13市均选译林版;"
            "注意其它科有市际差异(如数学无锡/苏州人教版、余苏教版)。核实:2024秋-2025春江苏教学用书。")
_SH_NOTE = ("沪教版(牛津上海版/沪教牛津版)——小学/初中/高中三学段主导版本。"
            "上海系区级选用,英语公办校主用牛津上海版;小学少数校用新世纪版"
            "(杨浦/虹口/崇明部分学校,校级例外非整区)。核实:上海市教委2024秋-2025春教学用书目录。")
_SZ_NOTE = ("牛津深圳版(沪教牛津/深港版)——深圳全市非人教,有辨识度。"
            "广东省默认人教,深圳是清晰城市例外。核实:2024秋广东初中教学用书。")
_XM_NOTE = ("人教版——厦门初中用人教版(福建省其余设区市初中为仁爱版,厦门是例外)。"
            "小学思明等区用外研新标准,混。核实:2024秋福建初中教学用书。")
_GZ_NOTE = ("广州:小学(4-6年级)教科版(广州)、初中沪教牛津版——全市统筹统一,非人教。"
            "广东省默认人教,广州是清晰城市例外。核实:2024秋广州中小学教学用书目录。")
_LJ_NOTE = ("鲁教版(五四制)——整市五四学制(小学5年+初中4年),英语用鲁教版。"
            "山东省默认人教/外研,本市系五四制例外。核实:2024-2025山东五四制初中教学用书。")

# 直接按码落的行(省级/直辖市/地级市)。仅收「能干净确定」的例外;
# 福建/河北/山东/广东省内其余为混用,留省级默认(verified=False)兜底,不硬锁。
DIRECT: list[tuple[str, list[str], str]] = [
    ("31", ["沪教版(牛津上海)"], _SH_NOTE),          # 上海市(三学段沪教)
    ("4403", ["牛津深圳版"], _SZ_NOTE),               # 深圳市(广东例外)
    ("4401", ["教科版(广州)", "沪教版(牛津上海)"], _GZ_NOTE),  # 广州市(小学教科版/初中沪教牛津)
    ("3502", ["人教版"], _XM_NOTE),                  # 厦门市(福建例外)
    # 山东整市五四制 → 鲁教版(济宁任城/济南莱芜钢城仅区级,不整市锁)
    ("3706", ["鲁教版(五四制)"], _LJ_NOTE),          # 烟台市
    ("3703", ["鲁教版(五四制)"], _LJ_NOTE),          # 淄博市
    ("3705", ["鲁教版(五四制)"], _LJ_NOTE),          # 东营市
    ("3709", ["鲁教版(五四制)"], _LJ_NOTE),          # 泰安市
    ("3710", ["鲁教版(五四制)"], _LJ_NOTE),          # 威海市
]

# 按省名展开到该省全部 level-2 地级市(用于全省英语统一的省份)
EXPAND_PROVINCE: list[tuple[str, list[str], str]] = [
    ("江苏", ["译林版"], _JS_NOTE),
]


async def main() -> None:
    async with _async_session_factory() as db:
        n = 0
        for code, versions, note in DIRECT:
            reg = (await db.execute(sa.select(Region.code).where(Region.code == code))).scalar_one_or_none()
            if reg is None:
                print(f"  ✗ 跳过 {code}(region 表无此码)")
                continue
            await tb.upsert(db, region_code=code, versions=versions, note=note, verified=True)
            print(f"  ✓ {code} → {versions}")
            n += 1

        for prov_name, versions, note in EXPAND_PROVINCE:
            prov = (await db.execute(sa.select(Region.code, Region.name)
                    .where(Region.level == 1, Region.name.like(f"%{prov_name}%")))).first()
            if prov is None:
                print(f"  ✗ 跳过 {prov_name}(region 表无此省)")
                continue
            cities = (await db.execute(sa.select(Region.code, Region.name)
                      .where(Region.level == 2, Region.parent_code == prov[0])
                      .order_by(Region.code))).all()
            for c, cn in cities:
                await tb.upsert(db, region_code=c, versions=versions, note=note, verified=True)
                n += 1
            print(f"  ✓ {prov[1]} {len(cities)} 市 → {versions}")

        await db.commit()
        print(f"\n完成:已核实教材地图共 upsert {n} 行(verified=True)")


if __name__ == "__main__":
    asyncio.run(main())
