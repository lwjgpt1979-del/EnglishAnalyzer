"""灌入受控知识树骨架(E1)。

默认 dry-run 只打印将清空/灌入的量;--execute 真正执行。
--reset:先清空知识图谱节点 + 内容层(node_resource/版本、unit_node 边、别名、
vocab_node、platform_question_kp、student_kp、候选/暂存),再灌骨架。系统未上线专用。

骨架来自 app/data/knowledge_tree_seed.json(嵌套:axis→顶层→子类→叶子)。
code 由路径确定性生成(如 k-1-9-1-1),可重复灌入幂等覆盖。
运行:
  DATABASE_URL=... python3 scripts/seed_knowledge_tree.py            # dry-run
  DATABASE_URL=... python3 scripts/seed_knowledge_tree.py --reset --execute
"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.core.database import async_session_factory  # noqa: E402
from app.services.kp_normalize import normalize_kp_name  # noqa: E402

SEED = Path(__file__).resolve().parent.parent / "app" / "data" / "knowledge_tree_seed.json"
AXIS_SHORT = {"knowledge": "k", "ability": "a", "exam": "e"}

# 清空顺序(FK 安全):先内容/边/引用,后节点
_CLEAR = [
    "node_resource_version", "node_resource", "vocab_node",
    "platform_question_kp", "student_kp", "unit_node",
    "knowledge_node_aliases", "pending_kp_content", "kp_candidates",
    "knowledge_nodes",
]


def _flatten(axis: str, nodes: list, parent_code, prefix, out):
    """深度优先生成 (code, axis, name, node_kind, parent_code, sort_order, depth)。"""
    for i, n in enumerate(nodes, start=1):
        code = f"{prefix}-{i}"
        out.append({
            "code": code, "axis": axis, "name": n["name"],
            "node_kind": n.get("node_kind"), "parent_code": parent_code,
            "sort_order": i, "stages": n.get("applicable_stages"),
        })
        if n.get("children"):
            _flatten(axis, n["children"], code, code, out)


async def main(reset: bool, execute: bool):
    tree = json.loads(SEED.read_text(encoding="utf-8"))
    rows: list[dict] = []
    for axis, tops in tree.items():
        _flatten(axis, tops, None, AXIS_SHORT.get(axis, axis), rows)
    print(f"[seed-tree] 骨架节点 {len(rows)} 个(知识/能力/考点三轴)")

    if not execute:
        print("[seed-tree] DRY-RUN(未写库)。加 --execute 执行;加 --reset 先清空。")
        for r in rows[:8]:
            print(f"  {r['code']:>12}  {'  '*(r['code'].count('-')-1)}{r['name']}")
        print("  ...")
        return

    async with async_session_factory() as db:
        if reset:
            for t in _CLEAR:
                try:
                    n = (await db.execute(text(f"DELETE FROM {t}"))).rowcount
                    print(f"  清空 {t}: {n}")
                except Exception as e:  # 表可能不存在
                    print(f"  跳过 {t}: {e}")
            await db.commit()

        # 1) upsert 全部节点(parent_id 暂空)
        for r in rows:
            await db.execute(text(
                "INSERT INTO knowledge_nodes (id, axis, node_kind, name, code, applicable_stages, "
                "status, source, sort_order, created_at, updated_at) "
                "VALUES (:id,:axis,:kind,:name,:code, CAST(:stages AS JSONB), 'active','seed',:so, now(), now()) "
                "ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name, node_kind=EXCLUDED.node_kind, "
                "axis=EXCLUDED.axis, sort_order=EXCLUDED.sort_order"),
                {"id": uuid.uuid4(), "axis": r["axis"], "kind": r["node_kind"], "name": r["name"],
                 "code": r["code"], "stages": json.dumps(r["stages"]) if r["stages"] else None,
                 "so": r["sort_order"]})
        # 2) 读回真实 id(幂等可靠)
        codes = [r["code"] for r in rows]
        code2id = dict((c, i) for c, i in (await db.execute(
            text("SELECT code, id FROM knowledge_nodes WHERE code = ANY(:cs)"), {"cs": codes})).all())
        # 3) 别名 + parent 回填
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
        print(f"[seed-tree] 已灌入 {len(rows)} 节点 + 别名,parent 回填完成。")


if __name__ == "__main__":
    asyncio.run(main("--reset" in sys.argv, "--execute" in sys.argv))
