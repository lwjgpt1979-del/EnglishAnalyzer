"""重切「旧数据丢题」的卷 + 题号连续性核验(只修变好的,异常回滚报人工)。

背景:部分卷在旧切题逻辑期间入库,整段丢题(如徐州卷阅读理解 26-40 丢失)。当前
切题逻辑已修好,重切即可找回。但**不能盲目批量**:个别卷重切反而会碎(题数骤降),
故每卷重切后做**题号连续性核验**,只在"明显更好"时落库,否则回滚、列入人工清单。

核验(全过才 commit,否则 rollback):
- 重切题数 >= 原题数(不允许变少);
- 题号 1..max 覆盖率不下降(越连续越好,少孤儿高题号如短文百分比 75 被当题号)。
安全:**每卷独立 session/事务**;`--apply` 才落库,默认 dry-run 只核验打印。
用法:python -m scripts.reparse_verified [--apply]
"""
import asyncio
import logging
import re
import sys

import sqlalchemy as sa

from app.core.database import async_session_factory
from app.models.d16_question_domain import PlatformPaper
from app.services import platform_question_service as pqs

logging.disable(logging.INFO)

_SQL = "SELECT question_no FROM platform_question WHERE paper_id=:p AND type='real'"


def _coverage(rows) -> tuple[int, int, float]:
    """(题数, 最大题号, 1..max 覆盖率)。覆盖率高=题号连续、少孤儿高号。"""
    nums = set()
    for (no,) in rows:
        m = re.match(r"\s*(\d{1,3})", no or "")
        if m:
            nums.add(int(m.group(1)))
    if not nums:
        return 0, 0, 0.0
    mx = max(nums)
    return len(nums), mx, round(len(nums) / mx, 3) if mx else 0.0


async def main(apply: bool):
    async with async_session_factory() as db0:
        papers = (await db0.execute(sa.select(PlatformPaper.id, PlatformPaper.name,
                                              PlatformPaper.meta))).all()
    # 收敛:只碰 docx(文本干净、确定性切题能修)且现有题号覆盖率<0.85(疑似丢题)的卷。
    # pdf/OCR 卷源文字就乱,reparse 救不了,单列另处理,不在此脚本。
    targets = [(pid, nm, meta or {}) for pid, nm, meta in papers
               if (meta or {}).get("file_id") and (meta or {}).get("source") == "docx"]
    print(f"=== docx 卷 {len(targets)} 个,筛覆盖率<0.85 的逐卷 parse 核验 ===\n", flush=True)
    fixable = ok = worse = same = fail = 0
    for pid, nm, meta in targets:
        async with async_session_factory() as db:      # 每卷独立事务
            try:
                b_cnt, _bmx, b_cov = _coverage((await db.execute(sa.text(_SQL), {"p": pid})).all())
                if b_cov >= 0.85:                       # 覆盖率高=题号连续=无嫌疑,跳过不试切
                    same += 1; continue
                await pqs.parse_paper_questions(db, paper_id=pid)
                a_cnt, _amx, a_cov = _coverage((await db.execute(sa.text(_SQL), {"p": pid})).all())
                # 只修「题数增加 且 题号更连续」的(=真找回丢题;切碎的覆盖率会降,不修)
                good = a_cnt > b_cnt and a_cov >= b_cov - 0.02
                if a_cnt < b_cnt or a_cov < b_cov - 0.05:
                    worse += 1
                    print(f"  ⚠ 变差(不修) {nm[:34]:<36} 题 {b_cnt}→{a_cnt} 覆盖 {b_cov}→{a_cov}")
                elif good:
                    fixable += 1
                    print(f"  ✓ 可修       {nm[:34]:<36} 题 {b_cnt}→{a_cnt} 覆盖 {b_cov}→{a_cov}")
                else:
                    same += 1
                if good and apply:
                    await db.commit(); ok += 1
                else:
                    await db.rollback()
            except Exception as exc:  # noqa: BLE001
                await db.rollback()
                print(f"  ✗ 异常 {nm[:34]} :: {type(exc).__name__}: {str(exc)[:46]}"); fail += 1
    verb = "已落库修" if apply else "dry-run 可修"
    print(f"\n=== {verb} {ok if apply else fixable} 卷、变差跳过 {worse}、无变化 {same}、异常 {fail}(共 {len(targets)})===")


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))
