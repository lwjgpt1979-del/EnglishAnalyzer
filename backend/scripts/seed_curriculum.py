"""V2 课程内容批量 seed 脚本（D-079 / M2）。

用法：
  # dev mock 跑 1 个单元（pilot）
  python backend/scripts/seed_curriculum.py --grade 小学5年级 --semester 上 --unit 1

  # dev mock 跑 1 个学期（10 个单元）
  python backend/scripts/seed_curriculum.py --grade 小学5年级 --semester 上 --units 1-10

  # 真实 API 跑 4 个学期全部
  DEEPSEEK_API_KEY=sk-real-key python backend/scripts/seed_curriculum.py --all

幂等：相同 (textbook, grade, semester, unit_no) 多次跑只会 upsert，不会重复。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# 让脚本能直接运行
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.database import _async_session_factory  # noqa: E402
from app.models.d4_knowledge import CurriculumUnit  # noqa: E402
from app.services import curriculum_ai_service, curriculum_service  # noqa: E402


FULL_SEMESTERS = [
    ("译林版", "小学5年级", "上"),
    ("译林版", "小学5年级", "下"),
    ("译林版", "初中7年级", "上"),
    ("译林版", "初中7年级", "下"),
]
UNITS_PER_SEMESTER = 8  # 默认每学期 8 单元


async def seed_one(textbook: str, grade: str, semester: str, unit_no: int) -> None:
    async with _async_session_factory() as db:
        # 断点续传：已存在的单元跳过
        existing = (await db.execute(
            select(CurriculumUnit).where(
                CurriculumUnit.textbook_version == textbook,
                CurriculumUnit.grade == grade,
                CurriculumUnit.semester == semester,
                CurriculumUnit.unit_no == unit_no,
            )
        )).scalar_one_or_none()
        if existing is not None:
            print(f"  [skip] {textbook} {grade} {semester} U{unit_no} 已存在")
            return

        print(f"  [gen]  {textbook} {grade} {semester} U{unit_no} …", end=" ", flush=True)
        ai = await curriculum_ai_service.generate_unit(
            textbook_version=textbook, grade=grade, semester=semester, unit_no=unit_no,
        )
        await curriculum_service.persist_unit(db, ai_unit=ai, content_status="published")
        await db.commit()
        print(f"✓ {len(ai.knowledge_points)} KP, {len(ai.words)} 词")


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--textbook", default="译林版")
    p.add_argument("--grade")
    p.add_argument("--semester")
    p.add_argument("--unit", type=int, help="单个单元号")
    p.add_argument("--units", help="范围，例如 1-10")
    p.add_argument("--all", action="store_true", help="跑全部 4 学期 × 8 单元")
    args = p.parse_args()

    if args.all:
        for textbook, grade, semester in FULL_SEMESTERS:
            print(f"\n=== {textbook} {grade} {semester} ===")
            for unit_no in range(1, UNITS_PER_SEMESTER + 1):
                await seed_one(textbook, grade, semester, unit_no)
        print("\n✓ 全部完成")
        return

    if not (args.grade and args.semester):
        p.error("--grade 和 --semester 必填（除非用 --all）")

    if args.unit:
        await seed_one(args.textbook, args.grade, args.semester, args.unit)
    elif args.units:
        lo, hi = (int(x) for x in args.units.split("-"))
        for unit_no in range(lo, hi + 1):
            await seed_one(args.textbook, args.grade, args.semester, unit_no)
    else:
        p.error("必须指定 --unit 或 --units 或 --all")


if __name__ == "__main__":
    asyncio.run(main())
