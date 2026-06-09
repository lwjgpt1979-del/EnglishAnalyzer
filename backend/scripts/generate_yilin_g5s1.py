"""译林版 小学5年级 上学期 — 用真实 DeepSeek AI 生成 6 单元内容。

用法（从 backend 目录执行）：
    DATABASE_URL=postgresql+psycopg://... \\
    ASYNC_DATABASE_URL=postgresql+psycopg://... \\
    python -m scripts.generate_yilin_g5s1

会先清除该学期旧数据再重建，约 60-120 秒完成。
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import _async_session_factory
from app.services import curriculum_service
from app.services.llm_provider import is_llm_dev_mode

TEXTBOOK = "译林版"
GRADE = "小学5年级"
SEMESTER = "上"
UNIT_COUNT = 6


async def main() -> None:
    if is_llm_dev_mode():
        print("⚠️  当前为 dev-mock 模式（DEEPSEEK_API_KEY 以 sk-placeholder 开头），"
              "将生成 mock 内容而非真实 AI 内容。")
        print("   若要生成真实内容，请在 .env 中配置真实的 DEEPSEEK_API_KEY。")
    else:
        print(f"🚀 使用真实 DeepSeek AI 生成：{TEXTBOOK} {GRADE} {SEMESTER}学期 × {UNIT_COUNT} 单元")

    print()
    start = time.time()

    async with _async_session_factory() as db:
        print(f"🧹 清除旧数据 ({TEXTBOOK} {GRADE} {SEMESTER}学期)…")
        deleted = await curriculum_service.reset_semester(
            db, textbook_version=TEXTBOOK, grade=GRADE, semester=SEMESTER,
        )
        print(f"   已删除 {deleted} 个旧单元")
        await db.flush()
        print()

        for unit_no in range(1, UNIT_COUNT + 1):
            t0 = time.time()
            print(f"📚 Unit {unit_no}/{UNIT_COUNT} 生成中…", end="", flush=True)
            from app.services import curriculum_ai_service
            ai_unit = await curriculum_ai_service.generate_unit(
                textbook_version=TEXTBOOK,
                grade=GRADE,
                semester=SEMESTER,
                unit_no=unit_no,
            )
            cu = await curriculum_service.persist_unit(db, ai_unit=ai_unit, content_status="published")
            await db.flush()
            elapsed = time.time() - t0
            print(f" ✓  「{ai_unit.unit_title}」 ({len(ai_unit.knowledge_points)} KP, "
                  f"{len(ai_unit.words)} 词, {elapsed:.1f}s)")

        await db.commit()

    total = time.time() - start
    print()
    print(f"✅ 全部完成！共 {UNIT_COUNT} 单元，耗时 {total:.1f}s")
    print(f"   教材：{TEXTBOOK} {GRADE} {SEMESTER}学期")
    print("   前端访问：学生端 → 我的 → 课程单元")


if __name__ == "__main__":
    asyncio.run(main())
