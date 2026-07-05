"""域21: 行政区划地区表(唯一数据源)。

省/市/区县/乡镇靠 parent_code 任意层级;code 沿用 GB/T 2260 前缀方案
(省2位/市4位/区县6位/乡镇9位,子级 code 以父级 code 为前缀),与学生 user.city_code 同源。
前端不再硬编码地区,统一走 /api/v1/regions 懒加载。
"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import mapped_column

from .base import Base


class Region(Base):
    __tablename__ = "region"

    code = mapped_column(sa.String(12), primary_key=True)          # 行政区划代码
    name = mapped_column(sa.String(64), nullable=False)
    parent_code = mapped_column(sa.String(12), nullable=True)      # 上级;省为 NULL
    level = mapped_column(sa.SmallInteger, nullable=False)         # 1省 2市 3区县 4乡镇

    __table_args__ = (
        sa.Index("ix_region_parent", "parent_code"),
        sa.Index("ix_region_level", "level"),
    )


class RegionTextbook(Base):
    """地区↔英语教材版本 对应(以初中英语为主)。

    数据源=公开信息整理,**各地由地市教育局自定**,故均为「省级默认+可校对」:
    seed 省级默认(verified=False 待校对),地市有例外时按 4/6 位码另加一行覆盖。
    查询 textbook_for(code) 时:精确码 → 逐级上溯(区县→市→省)取最近一条命中。
    versions 存版本名列表(如 ["人教版"] 或 ["人教版","外研版"]);note 记地市差异。
    """

    __tablename__ = "region_textbook"

    region_code = mapped_column(sa.String(12), primary_key=True)   # 省/市/区县码(与 region.code 同源)
    region_name = mapped_column(sa.String(64), nullable=False)
    level = mapped_column(sa.SmallInteger, nullable=False)         # 1省 2市 3区县
    versions = mapped_column(JSONB, nullable=False)                # 版本名列表
    note = mapped_column(sa.String(255), nullable=True)            # 地市差异/备注
    verified = mapped_column(sa.Boolean, nullable=False, default=False)  # 是否已人工校对
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False,
        server_default=sa.func.now(), onupdate=sa.func.now())

    __table_args__ = (sa.Index("ix_region_textbook_level", "level"),)
