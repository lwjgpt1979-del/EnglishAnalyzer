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

# 专题 code → [考点标题…](如实照《中考考频分区速学·词法》PDF,考点数 4–8 不等)
KAODIAN: dict[str, list[str]] = {
    # 名词
    "cf-1-1": ["名词的定义及分类", "可数名词复数的规则变化", "可数名词变复数的不规则变化",
               "复合名词的构成及复数变化"],
    "cf-1-2": ["不可数名词的定义", "常见的不可数名词", "不可数名词量的表达",
               "既可数又不可数的名词", "名词的修饰语"],
    "cf-1-3": ["名词所有格的定义", "-'s 所有格的构成", "-'s 所有格的用法",
               "of 所有格的用法", "双重所有格的用法", "共同拥有与各自拥有"],
    # 冠词
    "cf-2-1": ["冠词的用法及分类", "不定冠词 a/an 的基本用法", "不定冠词 a/an 的用法区别",
               "含不定冠词的常用短语", "不定冠词的位置"],
    "cf-2-2": ["定冠词的功能及发音", "定冠词的使用原则", "定冠词的常见用法",
               "含定冠词的常用短语", "定冠词的位置", "定冠词的易错用法"],
    "cf-2-3": ["零冠词的使用原则", "零冠词的高频用法", "零冠词的固定搭配", "有无冠词的短语辨析"],
    # 代词
    "cf-3-1": ["代词的定义及分类", "人称代词的定义", "人称代词的形式及分类",
               "人称代词的句法功能", "人称代词的易错用法"],
    "cf-3-2": ["物主代词的定义", "物主代词的形式及分类", "反身代词的定义", "反身代词的形式及分类",
               "物主代词的句法功能", "反身代词的句法功能", "物主代词的常用短语", "反身代词的常用短语"],
    "cf-3-3": ["不定代词的定义及句法功能", "some 与 any 的用法", "复合不定代词的分类",
               "复合不定代词的常用表达", "复合不定代词的用法"],
    "cf-3-4": ["each 与 every 的用法及区别", "“三三两两”的用法及区别", "other 系列的用法及区别",
               "“多多少少”的用法及区别"],
    "cf-3-5": ["指示代词的分类及用法", "疑问代词的定义", "疑问代词的用法", "what 的常用句型",
               "it 的相关用法及句型"],
    # 动词
    "cf-4-1": ["动词的概念及分类", "实义动词的分类及用法", "助动词的分类及用法", "常见动词短语搭配"],
    "cf-4-2": ["系动词的定义及分类", "感官系动词", "持续系动词和表象系动词", "变化系动词"],
    "cf-4-3": ["情态动词的特征", "情态动词表能力", "情态动词表请求", "情态动词表意见或意愿"],
    "cf-4-4": ["情态动词表推测", "情态动词表命令或禁止", "其他常用情态动词", "情态共存的动词"],
    # 形容词和副词
    "cf-5-1": ["形容词的定义及构成", "形容词的句法功能", "常考的形容词修饰名词的搭配",
               "-ing 和 -ed 结尾的形容词", "形容词的排列顺序", "形容词的特殊用法"],
    "cf-5-2": ["副词的定义及构成", "副词的句法功能", "常见副词的分类", "副词的位置",
               "易混淆的形容词和副词"],
    "cf-5-3": ["形容词和副词的级", "形容词和副词的原级句型", "比较级与最高级的规则变化",
               "比较级与最高级的不规则变化", "形容词和副词的比较级句型", "形容词和副词的最高级句型"],
    # 数词
    "cf-6-1": ["基数词定义及构成", "序数词的定义及构成", "基数词的用法", "序数词的用法", "数词表达易错点"],
    "cf-6-2": ["数词的句法功能", "分数 / 小数 / 百分数的表达", "概数的表达", "倍数的表达"],
    # 介词
    "cf-7-1": ["介词的定义及分类", "时间介词的用法", "地点介词的用法", "方位介词的用法",
               "易错地点、方位介词辨析"],
    "cf-7-2": ["介词短语的句法功能", "常见的介词短语", "方式介词的用法", "其他介词的用法",
               "易混淆的介词辨析"],
    # 连词
    "cf-8-1": ["连词的定义及分类", "并列连词的用法", "引导原因、结果状语从句",
               "引导目的、让步、方式状语从句", "引导时间、条件状语从句", "引导名词性从句"],
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
