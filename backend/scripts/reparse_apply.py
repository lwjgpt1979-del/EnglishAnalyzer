"""真题解析批量修复:只对「重解后题数 > 现有题数」的卷执行真正 reparse(落库),逐卷提交。

安全约束:
- 只碰会**变多**的卷(dry-run 已证全部为增加、无一变少)。已正常的卷不动——避免清掉其已匹配
  的知识点/派生仿真。
- 逐卷独立 commit + try/except 隔离:单卷失败不影响其它卷。
- 扫描件/旧 .doc/无本地文件:跳过并计数(需 OCR/转换,另行处理)。
用法:DATABASE_URL=... python -m scripts.reparse_apply
"""
import asyncio
import logging

import sqlalchemy as sa

from app.core.database import async_session_factory
from app.models.d16_question_domain import PlatformPaper
from app.services import pdf_upload_service as pus
from app.services import paper_split_service as ps
from app.services import platform_question_service as pqs

logging.disable(logging.INFO)


def _would_be(file_id: str, source: str) -> int | None:
    """确定性路径算重解后题数;扫描件/无文件/异常返回 None。"""
    try:
        if source == "docx":
            txt = pus.extract_docx_text(file_id)
        elif source == "pdf":
            txt = "\n".join(pus.extract_pages(file_id))
        else:
            return None
    except Exception:  # noqa: BLE001
        return None
    if len((txt or "").strip()) < 200:
        return None
    return len(ps.split_paper_text_structural(txt))


async def main():
    async with async_session_factory() as db:
        papers = (await db.execute(sa.select(PlatformPaper))).scalars().all()
        counts = dict((await db.execute(sa.text(
            "SELECT paper_id, count(*) FROM platform_question GROUP BY paper_id"))).all())

        # 先筛「会变多」的目标卷
        targets = []
        for p in papers:
            m = p.meta or {}
            fid, src = m.get("file_id"), m.get("source")
            if not fid or src not in ("pdf", "docx"):
                continue
            cur = int(counts.get(p.id, 0))
            wb = _would_be(fid, src)
            if wb is not None and wb > cur:
                targets.append((p.id, p.name, cur, wb))
        targets.sort(key=lambda t: t[3] - t[2], reverse=True)
        print(f"=== 目标:{len(targets)} 卷会变多,开始逐卷重解 ===\n")

        ok = fail = 0
        total_before = total_after = 0
        for pid, name, cur, wb in targets:
            try:
                r = await pqs.parse_paper_questions(db, paper_id=pid)
                await db.commit()
                imported = r.get("imported", 0)
                ok += 1
                total_before += cur
                total_after += imported
                print(f"  ✓ {cur:>3}→{imported:<3} {name[:44]}")
            except Exception as exc:  # noqa: BLE001
                await db.rollback()
                fail += 1
                print(f"  ✗ FAIL {name[:44]} :: {type(exc).__name__}: {str(exc)[:60]}")

        print(f"\n=== 完成:成功 {ok} 卷,失败 {fail} 卷;题数 {total_before} → {total_after} "
              f"(+{total_after - total_before})===")


if __name__ == "__main__":
    asyncio.run(main())
