"""为受控知识树的"专题"挂上"考点"叶子(第 4 层),如实取自《中考考频分区速学》PDF。

KAODIAN 按 专题 code(见 build_grammar_tree_from_pdf:词法 cf-板块-专题)逐专题登记考点标题,
随阅读 PDF 增量补全。幂等(按 alias_norm 跳过已存在)。
运行:DATABASE_URL=... python3 scripts/add_kaodian.py --execute
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.core.database import async_session_factory  # noqa: E402
from app.services.kp_normalize import normalize_kp_name  # noqa: E402

# 专题 code → [考点标题…](如实照 PDF,考点数 4–6 不等)
KAODIAN: dict[str, list[str]] = {
    # 词法 · 名词
    "cf-1-1": ["名词的定义及分类", "可数名词复数的规则变化", "可数名词变复数的不规则变化",
               "复合名词的构成及复数变化"],                                  # 可数名词
    "cf-1-2": ["不可数名词的定义", "常见的不可数名词", "不可数名词量的表达",
               "既可数又不可数的名词", "名词的修饰语"],                       # 不可数名词
    "cf-1-3": ["名词所有格的定义", "-'s 所有格的构成", "-'s 所有格的用法",
               "of 所有格的用法", "双重所有格的用法", "共同拥有与各自拥有"],  # 名词所有格
}


async def main(execute: bool):
    total = sum(len(v) for v in KAODIAN.values())
    print(f"[kaodian] 专题 {len(KAODIAN)} 个,考点 {total} 个")
    if not execute:
        for code, ks in KAODIAN.items():
            print(f"  {code}: {ks}")
        print("  (--execute 写库)")
        return
    async with async_session_factory() as db:
        added = 0
        for pcode, kds in KAODIAN.items():
            pid = (await db.execute(
                text("SELECT id, axis FROM knowledge_nodes WHERE code=:c"), {"c": pcode})).first()
            if pid is None:
                print(f"  ! 专题 {pcode} 不存在,跳过"); continue
            parent_id, axis = pid
            for i, title in enumerate(kds, start=1):
                norm = normalize_kp_name(title)
                if (await db.execute(text(
                    "SELECT 1 FROM knowledge_node_aliases WHERE alias_norm=:n"), {"n": norm})).first():
                    continue
                nid = uuid.uuid4()
                await db.execute(text(
                    "INSERT INTO knowledge_nodes (id, axis, name, code, parent_id, status, source, "
                    "sort_order, created_at, updated_at) VALUES (:id,:ax,:nm,:code,:p,'active','seed',:so,now(),now()) "
                    "ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name"),
                    {"id": nid, "ax": axis, "nm": title, "code": f"{pcode}-{i}", "p": parent_id, "so": i})
                await db.execute(text(
                    "INSERT INTO knowledge_node_aliases (id, node_id, alias, alias_norm, source) "
                    "VALUES (:id,:nid,:al,:norm,'seed') ON CONFLICT DO NOTHING"),
                    {"id": uuid.uuid4(), "nid": nid, "al": title, "norm": norm})
                added += 1
        await db.commit()
        print(f"[kaodian] 已挂考点 {added} 个。")


if __name__ == "__main__":
    asyncio.run(main("--execute" in sys.argv))
