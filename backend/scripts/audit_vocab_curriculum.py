"""词库 ↔ 教材关联体检脚本（内容铺设核对用）。

报告：
  1) 各(教材/年级/学期)的词数覆盖（铺了多少词）
  2) 未关联任何教材单元的词（孤立词，仅靠 P2 来源/全局回退才会被学到）
  3) 一词跨多个(教材/年级/学期)的词（多对多，去重后只学一次）

用法：cd backend && PYTHONPATH=. python scripts/audit_vocab_curriculum.py
      PYTHONPATH=. python scripts/audit_vocab_curriculum.py --sample 20
"""
from __future__ import annotations

import argparse
import asyncio
import logging

logging.disable(logging.CRITICAL)

from sqlalchemy import text  # noqa: E402

from app.core.database import _async_session_factory  # noqa: E402


async def main(sample: int) -> None:
    async with _async_session_factory() as db:
        tot = (await db.execute(text("SELECT count(*) FROM vocabulary_words"))).scalar_one()
        linked = (await db.execute(
            text("SELECT count(DISTINCT word_id) FROM curriculum_words")
        )).scalar_one()

        print("=" * 56)
        print(f"词库总词数: {tot}　|　已关联教材: {linked}　|　孤立: {tot - linked}")
        print("=" * 56)

        print("\n【1】各(教材/年级/学期)词数覆盖")
        rows = (await db.execute(text(
            """
            SELECT cu.textbook_version, cu.grade, cu.semester,
                   count(DISTINCT cw.word_id) AS n
            FROM curriculum_units cu
            JOIN curriculum_words cw ON cw.unit_id = cu.id
            GROUP BY 1, 2, 3 ORDER BY 1, 2, 3
            """
        ))).all()
        if rows:
            for t, g, s, n in rows:
                print(f"  {t} / {g} / {s}　→　{n} 词")
        else:
            print("  （暂无教材关联词）")

        print(f"\n【2】未关联任何教材单元的词（前 {sample} 个）")
        orphans = (await db.execute(text(
            """
            SELECT word FROM vocabulary_words
            WHERE id NOT IN (SELECT word_id FROM curriculum_words)
            ORDER BY word LIMIT :n
            """
        ), {"n": sample})).scalars().all()
        print("  " + (", ".join(orphans) if orphans else "（无）"))

        print(f"\n【3】一词跨多个(教材/年级/学期)的词（前 {sample} 个）")
        multi = (await db.execute(text(
            """
            SELECT vw.word,
                   count(DISTINCT cu.textbook_version||'|'||cu.grade||'|'||cu.semester) AS c
            FROM vocabulary_words vw
            JOIN curriculum_words cw ON cw.word_id = vw.id
            JOIN curriculum_units cu ON cu.id = cw.unit_id
            GROUP BY vw.id, vw.word HAVING count(DISTINCT cu.textbook_version||'|'||cu.grade||'|'||cu.semester) > 1
            ORDER BY c DESC, vw.word LIMIT :n
            """
        ), {"n": sample})).all()
        if multi:
            for w, c in multi:
                print(f"  {w}　→　{c} 个组合")
        else:
            print("  （无一词跨多学期）")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=15, help="各列表抽样条数")
    asyncio.run(main(ap.parse_args().sample))
