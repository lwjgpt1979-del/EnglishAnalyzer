"""一次性数据归一:vocabulary_words.definitions 统一为 {meaning, pos}。

背景:历史上词条 definitions 有两种格式——
  {meaning, pos}（词力通/多数来源）与 {zh, part_of_speech}（课程导入 curriculum_vocab_service 旧写法）。
全项目消费方(配图 brief、口语、题目分析、学生端多数词卡)只读 {meaning, pos},
导致 {zh,part_of_speech} 的词词义/词性读空 → 配图画歪、词卡空白。

本脚本把每条 definition 里的 zh→meaning、part_of_speech→pos(不覆盖已有),并删除旧键。
幂等:再次运行对已归一的数据无操作。写入方已同步改为写 {meaning, pos}(curriculum_vocab_service)。

跑法(在 backend/ 下):  python scripts/normalize_vocab_definitions.py
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.d5_learning import VocabularyWord


def normalize_defs(defs):
    """{zh,part_of_speech} → {meaning,pos};保留其它键。返回 (new_list, changed)。"""
    if not isinstance(defs, list):
        return defs, False
    changed = False
    out = []
    for it in defs:
        if isinstance(it, dict):
            d = dict(it)
            if "zh" in d:
                if not d.get("meaning"):
                    d["meaning"] = d.get("zh") or ""
                d.pop("zh", None)
                changed = True
            if "part_of_speech" in d:
                if not d.get("pos"):
                    d["pos"] = d.get("part_of_speech") or ""
                d.pop("part_of_speech", None)
                changed = True
            out.append(d)
        else:
            out.append(it)
    return out, changed


async def main() -> None:
    async with async_session_factory() as db:
        rows = (await db.execute(
            select(VocabularyWord).where(VocabularyWord.definitions.isnot(None)))).scalars().all()
        n = 0
        for w in rows:
            new, changed = normalize_defs(w.definitions)
            if changed:
                w.definitions = new    # 整体重赋值触发 JSONB 更新
                n += 1
        await db.commit()
        print(f"扫描 {len(rows)} 条,归一 {n} 条")


if __name__ == "__main__":
    asyncio.run(main())
