"""V2 仿真题批量 seed 脚本（D-079 / M3a）。

用法：
  # 跑指定 KP id 的题目（5 题）
  python backend/scripts/seed_questions.py --kp <uuid>

  # 跑某 (textbook, grade, semester, unit_no) 单元下所有 KP
  python backend/scripts/seed_questions.py --textbook 译林版 --grade 小学5年级 --semester 上 --unit-no 1

  # 跑全部 free-unit（每学期 unit_no=1）的 KP
  python backend/scripts/seed_questions.py --all-free

幂等：按 (kp_id, stem) 去重，重跑只增量。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid as _uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.database import _async_session_factory  # noqa: E402
from app.models.d4_knowledge import (  # noqa: E402
    CurriculumUnit, KnowledgePoint, UnitKnowledgePoint,
)
from app.services import question_ai_service, question_service  # noqa: E402

# 4 个维度，各自生成专属题目（听力/听写文本近似，语法/写作原样）
DIMENSIONS = ["listening", "dictation", "grammar", "writing"]


async def seed_one_kp(kp_id: _uuid.UUID, count: int = 5) -> int:
    """为 1 个 KP 的 4 个维度各生成 count 道题；返回累计行数（含已存在的）。"""
    async with _async_session_factory() as db:
        kp = (await db.execute(
            select(KnowledgePoint).where(KnowledgePoint.id == kp_id)
        )).scalar_one_or_none()
        if kp is None:
            print(f"  [skip] KP {kp_id} 不存在")
            return 0

        total = 0
        for dimension in DIMENSIONS:
            print(
                f"  [gen]  {kp.name} ({str(kp.category)}) [{dimension}] ...",
                end=" ", flush=True,
            )
            qs = await question_ai_service.generate_questions(
                kp_name=kp.name,
                kp_category=str(kp.category),
                kp_description=kp.description,
                dimension=dimension,
                count=count,
            )
            rows = await question_service.persist_questions(
                db, kp_id=kp.id, questions=qs, dimension=dimension,
                status="published",  # seed 是可信 dev 内容，直接发布（M5 审核闸门只拦线上 AI 题）
            )
            total += len(rows)
            print(f"✓ {len(rows)} 道（含已存在）")
        await db.commit()
        return total


async def list_kps_for_unit(
    textbook: str, grade: str, semester: str, unit_no: int,
) -> list:
    async with _async_session_factory() as db:
        rows = (await db.execute(
            select(KnowledgePoint).join(
                UnitKnowledgePoint,
                UnitKnowledgePoint.knowledge_point_id == KnowledgePoint.id,
            ).join(
                CurriculumUnit, CurriculumUnit.id == UnitKnowledgePoint.unit_id,
            ).where(
                CurriculumUnit.textbook_version == textbook,
                CurriculumUnit.grade == grade,
                CurriculumUnit.semester == semester,
                CurriculumUnit.unit_no == unit_no,
            )
        )).scalars().all()
        return list(rows)


FREE_UNITS = [
    ("译林版", "小学5年级", "上", 1),
    ("译林版", "小学5年级", "下", 1),
    ("译林版", "初中7年级", "上", 1),
    ("译林版", "初中7年级", "下", 1),
]


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--kp", help="KP UUID")
    p.add_argument("--textbook", default="译林版")
    p.add_argument("--grade")
    p.add_argument("--semester")
    p.add_argument("--unit-no", type=int)
    p.add_argument("--count", type=int, default=5, help="每 KP 题数")
    p.add_argument("--all-free", action="store_true", help="跑全部 free-unit KP")
    args = p.parse_args()

    if args.kp:
        await seed_one_kp(_uuid.UUID(args.kp), args.count)
        return

    targets: list[tuple] = []
    if args.all_free:
        targets = FREE_UNITS
    elif args.grade and args.semester and args.unit_no:
        targets = [(args.textbook, args.grade, args.semester, args.unit_no)]
    else:
        p.error("必须提供 --kp / --all-free / 或 (--grade --semester --unit-no)")

    for textbook, grade, semester, unit_no in targets:
        print(f"\n=== {textbook} {grade} {semester} U{unit_no} ===")
        kps = await list_kps_for_unit(textbook, grade, semester, unit_no)
        if not kps:
            print(f"  (无 KP，跳过；先跑 M2 seed_curriculum 灌单元内容)")
            continue
        for kp in kps:
            await seed_one_kp(kp.id, args.count)
    print("\n✓ 完成")


if __name__ == "__main__":
    asyncio.run(main())
