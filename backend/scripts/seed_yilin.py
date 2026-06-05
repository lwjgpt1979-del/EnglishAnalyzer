"""译林版种子数据脚本（dev mock 模式）。

用法：
    cd backend
    ASYNC_DATABASE_URL="..." DATABASE_URL="..." python -m scripts.seed_yilin
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# 确保 backend 目录在 sys.path，兼容 python -m scripts.seed_yilin 和 pytest
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import _async_session_factory
from app.services import curriculum_ai_service, curriculum_service

TEXTBOOKS = [
    {"textbook_version": "译林版", "grade": "小学5年级"},
    {"textbook_version": "译林版", "grade": "初中7年级"},
]
SEMESTERS = ["上", "下"]
UNITS_PER_SEMESTER = 6


async def seed_grade(
    db,
    *,
    textbook_version: str,
    grade: str,
    units_per_semester: int = UNITS_PER_SEMESTER,
) -> None:
    """为指定教材/年级写入上下学期各 units_per_semester 个单元。

    不在内部 commit——由调用方决定事务边界，方便测试用 rollback 隔离。
    """
    for semester in SEMESTERS:
        for unit_no in range(1, units_per_semester + 1):
            ai_unit = await curriculum_ai_service.generate_unit(
                textbook_version=textbook_version,
                grade=grade,
                semester=semester,
                unit_no=unit_no,
            )
            await curriculum_service.persist_unit(
                db, ai_unit=ai_unit, content_status="published"
            )
            await db.flush()
            print(
                f"[seed] {textbook_version} {grade} {semester}学期 Unit {unit_no} ✓"
            )


async def main() -> None:
    async with _async_session_factory() as db:
        for tb in TEXTBOOKS:
            await seed_grade(
                db,
                textbook_version=tb["textbook_version"],
                grade=tb["grade"],
            )
        await db.commit()
        print("[seed] 全部写入完成。")


if __name__ == "__main__":
    asyncio.run(main())
