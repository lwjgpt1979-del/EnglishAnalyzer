"""按《中考考频分区速学·词法/句法》PDF 目录如实重建词法、句法知识树(E 期数据)。

如实取自 PDF 目录(词类/句法板块 → 专题),不加工。仅替换 词法/句法 两棵子树
(清掉 E1 seed 的 code k-1*/k-2*),保留 篇章/能力/考点 等其它轴/节点。
默认 dry-run;--execute 写库。
运行:DATABASE_URL=... python3 scripts/build_grammar_tree_from_pdf.py --execute
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

# ── 如实取自 PDF 目录(专题=叶子知识点;板块=中间分类)──
TREES: dict[str, dict[str, list[str]]] = {
    "词法": {
        "名词": ["可数名词", "不可数名词", "名词所有格"],
        "冠词": ["不定冠词", "定冠词", "零冠词"],
        "代词": ["人称代词", "物主代词和反身代词", "不定代词（1）", "不定代词（2）",
                 "指示代词、疑问代词和 it"],
        "动词": ["实义动词与助动词", "系动词", "情态动词（1）", "情态动词（2）"],
        "形容词和副词": ["形容词", "副词", "形容词和副词的级"],
        "数词": ["基数词和序数词", "数词的用法"],
        "介词": ["时间、地点、方位介词", "方式介词和其他介词"],
        "连词": ["并列连词和从属连词"],
        "附录": ["构词法 & 感叹词"],
    },
    "句法": {
        "句子种类": ["陈述句", "疑问句", "祈使句", "感叹句"],
        "句子结构": ["简单句的基本句型", "there be 句型（存现句）"],
        "时态": ["一般现在时", "一般过去时", "一般将来时", "现在进行时",
                 "过去进行时", "现在完成时", "过去完成时"],
        "被动语态": ["被动语态的基本用法", "被动语态的特殊用法"],
        "非谓语": ["动词的非谓语形式（1）", "动词的非谓语形式（2）"],
        "并列复合句": ["并列复合句的用法"],
        "主从复合句": ["宾语从句的用法", "地点、时间、原因状语从句",
                       "目的、结果、让步状语从句", "比较、条件、方式状语从句",
                       "定语从句的用法"],
        "主谓一致": ["必单原则 & 必复原则", "可单可复原则和并列主语"],
        "特殊句式": ["倒装句", "虚拟语气", "强调句与省略句"],
        "附录": ["常见不规则动词表"],
    },
}
ROOT_CODE = {"词法": "cf", "句法": "jf"}


def _rows():
    """展开为 (code, name, parent_code, sort) 列表,深度 root→板块→专题。"""
    out = []
    for root, cats in TREES.items():
        rc = ROOT_CODE[root]
        out.append({"code": rc, "name": root, "parent_code": None, "sort": 0})
        for ci, (cat, leaves) in enumerate(cats.items(), start=1):
            cc = f"{rc}-{ci}"
            out.append({"code": cc, "name": cat, "parent_code": rc, "sort": ci})
            for li, leaf in enumerate(leaves, start=1):
                out.append({"code": f"{cc}-{li}", "name": leaf, "parent_code": cc, "sort": li})
    return out


_OLD = "(code IN ('k-1','k-2') OR code LIKE 'k-1-%' OR code LIKE 'k-2-%')"
# 所有引用 knowledge_nodes 的表(FK),清旧 词法/句法 节点前先清干净(含测试残留)
_DEP = [("node_resource", "node_id"), ("vocab_node", "node_id"),
        ("platform_question_kp", "node_id"), ("uploaded_question_kp", "node_id"),
        ("student_kp", "node_id"), ("wrong_record", "node_id"),
        ("unit_node", "node_id"), ("long_sentence_node", "node_id"),
        ("knowledge_node_relations", "from_node_id"), ("knowledge_node_relations", "to_node_id"),
        ("knowledge_node_aliases", "node_id")]


async def main(execute: bool):
    rows = _rows()
    n_root = sum(1 for r in rows if r["parent_code"] is None)
    n_cat = sum(1 for r in rows if r["parent_code"] and "-" not in r["code"][3:])
    print(f"[build] 将建 {len(rows)} 节点(根 {n_root} / 总 {len(rows)});替换 E1 seed 的 词法/句法(k-1*/k-2*)")
    if not execute:
        for r in rows[:12]:
            print(f"  {r['code']:>8}  {'  ' * (r['code'].count('-'))}{r['name']}")
        print("  ... (--execute 写库)")
        return

    async with async_session_factory() as db:
        old_ids = (await db.execute(text(f"SELECT id FROM knowledge_nodes WHERE {_OLD}"))).scalars().all()
        for t, col in _DEP:
            await db.execute(text(f"DELETE FROM {t} WHERE {col} = ANY(:ids)"), {"ids": old_ids})
        # 先断自引用(parent_id 指向被删节点),再删,避免自 FK 违例
        await db.execute(text(f"UPDATE knowledge_nodes SET parent_id=NULL WHERE {_OLD}"))
        await db.execute(text(f"DELETE FROM knowledge_nodes WHERE {_OLD}"))
        print(f"  清掉旧 词法/句法 seed 节点: {len(old_ids)}")

        for r in rows:
            await db.execute(text(
                "INSERT INTO knowledge_nodes (id, axis, name, code, status, source, sort_order, "
                "created_at, updated_at) VALUES (:id,'knowledge',:name,:code,'active','seed',:so, now(), now()) "
                "ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name, sort_order=EXCLUDED.sort_order"),
                {"id": uuid.uuid4(), "name": r["name"], "code": r["code"], "so": r["sort"]})
        code2id = dict((c, i) for c, i in (await db.execute(
            text("SELECT code, id FROM knowledge_nodes WHERE code = ANY(:cs)"),
            {"cs": [r["code"] for r in rows]})).all())
        for r in rows:
            nid = code2id[r["code"]]
            await db.execute(text(
                "INSERT INTO knowledge_node_aliases (id, node_id, alias, alias_norm, source) "
                "VALUES (:id,:nid,:al,:norm,'seed') ON CONFLICT DO NOTHING"),
                {"id": uuid.uuid4(), "nid": nid, "al": r["name"], "norm": normalize_kp_name(r["name"])})
            if r["parent_code"]:
                await db.execute(text("UPDATE knowledge_nodes SET parent_id=:p WHERE code=:c"),
                                 {"p": code2id[r["parent_code"]], "c": r["code"]})
        await db.commit()
        print(f"[build] 已重建 词法/句法 共 {len(rows)} 节点 + 别名,parent 回填完成。")


if __name__ == "__main__":
    asyncio.run(main("--execute" in sys.argv))
