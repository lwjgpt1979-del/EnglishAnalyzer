"""真题解析 dry-run:扫所有平台卷,用当前切题逻辑算「重解后题数」,对比现有题数,只读不落库。

- docx / 文字版 PDF:走确定性 split_paper_text_structural(与线上 reparse 同源),快、零 LLM。
- 扫描件 PDF(pdfplumber 抽不到文字):标注 SCAN(需 OCR/视觉),dry-run 跳过。
- 本地无文件(仅 COS):标注 NO-FILE,跳过。
用法:DATABASE_URL=... python -m scripts.reparse_dryrun
"""
import asyncio
import logging

import sqlalchemy as sa

from app.core.database import async_session_factory
from app.models.d16_question_domain import PlatformPaper
from app.services import pdf_upload_service as pus
from app.services import paper_split_service as ps

logging.disable(logging.INFO)


def _would_be_count(file_id: str, source: str) -> tuple[int | None, str]:
    """返回 (重解后题数 或 None, 备注)。只跑确定性路径。"""
    try:
        if source == "docx":
            txt = pus.extract_docx_text(file_id)
        elif source == "pdf":
            txt = "\n".join(pus.extract_pages(file_id))
        else:
            return None, f"SKIP({source})"
    except FileNotFoundError:
        return None, "NO-FILE(仅COS)"
    except Exception as exc:  # noqa: BLE001
        return None, f"ERR:{type(exc).__name__}"
    if len((txt or "").strip()) < 200:
        return None, "SCAN(需OCR)"
    return len(ps.split_paper_text_structural(txt)), "ok"


async def main():
    async with async_session_factory() as db:
        papers = (await db.execute(sa.select(PlatformPaper).order_by(PlatformPaper.created_at.desc()))).scalars().all()
        # 现有题数
        counts = dict((await db.execute(sa.text(
            "SELECT paper_id, count(*) FROM platform_question GROUP BY paper_id"))).all())
        rows = []
        for p in papers:
            m = p.meta or {}
            fid, src = m.get("file_id"), m.get("source")
            cur = int(counts.get(p.id, 0))
            if not fid or src not in ("pdf", "docx", "doc"):
                new, note = None, "NO-FILE"
            else:
                new, note = _would_be_count(fid, src)
            rows.append((p.name, src, cur, new, note))

        # 报告:先列「会变化(变多/变少)」,再统计
        changed = [r for r in rows if r[3] is not None and r[3] != r[2]]
        changed.sort(key=lambda r: (r[3] - r[2]))   # 变少的排前(最危险),变多的排后
        print(f"=== 共 {len(rows)} 卷;可确定性重解 {sum(1 for r in rows if r[3] is not None)} 卷;"
              f"题数会变化 {len(changed)} 卷 ===\n")
        print(f"{'现':>4} {'重解后':>6} {'Δ':>6}  卷名 / 备注")
        for name, src, cur, new, note in changed:
            d = new - cur
            flag = "⬆️" if d > 0 else "⬇️"
            print(f"{cur:>4} {new:>6} {d:>+6} {flag} {name[:40]}")
        # 跳过/异常清单
        skipped = [r for r in rows if r[3] is None]
        if skipped:
            print(f"\n--- 跳过 {len(skipped)} 卷(需 OCR / 无本地文件 / 异常)---")
            from collections import Counter
            for note, c in Counter(r[4] for r in skipped).most_common():
                print(f"   {note}: {c} 卷")


if __name__ == "__main__":
    asyncio.run(main())
