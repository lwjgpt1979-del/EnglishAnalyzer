"""域21: 行政区划地区表(唯一数据源)。

省/市/区县/乡镇靠 parent_code 任意层级;code 沿用 GB/T 2260 前缀方案
(省2位/市4位/区县6位/乡镇9位,子级 code 以父级 code 为前缀),与学生 user.city_code 同源。
前端不再硬编码地区,统一走 /api/v1/regions 懒加载。
"""
import sqlalchemy as sa
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
