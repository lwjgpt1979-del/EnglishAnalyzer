"""R0.2 种子迁移:knowledge_points → knowledge_node(+ alias / candidate)。

把现有旧知识点一次性映射进 KP-First 新域:
  - 标准点(code 非 auto_ 前缀)→ knowledge_node(active) + node_alias(名)
  - 游离点(code 以 auto_ 开头)→ kp_candidate(pending),交 R0.4 审核归并

**幂等**:按 code(节点)/(name_norm, suggested_axis)(候选)去重,可反复跑。
**不动旧表 knowledge_points**,只读它。

用法:
  python backend/scripts/migrate_kp_to_node.py --dry-run   # 只统计,不写
  python backend/scripts/migrate_kp_to_node.py             # 实迁移
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

# 让脚本能直接运行
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402

from app.core.database import _async_session_factory  # noqa: E402
from app.models.d4_knowledge import KnowledgePoint  # noqa: E402
from app.models.d15_knowledge_graph import (  # noqa: E402
    KnowledgeNode,
    NodeAlias,
    KpCandidate,
)
from app.services.kp_normalize import normalize_kp_name, stages_from_grades  # noqa: E402

# 旧 category → 新 (axis, node_kind);legacy 标准点统一落 knowledge 轴
CATEGORY_MAP: dict[str, tuple[str, str]] = {
    "grammar": ("knowledge", "句法"),
    "vocabulary": ("knowledge", "词汇"),
    "reading": ("knowledge", "阅读知识"),
    "writing": ("knowledge", "写作知识"),
    "listening": ("knowledge", "听力知识"),
}
DEFAULT_AXIS_KIND = ("knowledge", None)


def _is_auto(code: str) -> bool:
    return (code or "").startswith("auto_")


class Stats:
    def __init__(self) -> None:
        self.nodes = 0          # 新建节点(按归一名折叠后的唯一概念数)
        self.nodes_skip = 0     # 已存在跳过(复跑幂等)
        self.collapsed = 0      # 同名折叠掉的旧行数(多旧 code → 同一节点)
        self.aliases = 0        # 新建别名(每唯一名一条)
        self.cand = 0           # 新建候选
        self.cand_bumped = 0    # 候选 occur_count++ (复跑/同名)
        self.parents = 0        # 回填 parent_id

    def report(self, dry: bool) -> None:
        tag = "[dry-run] 预计" if dry else "[done]"
        print(f"\n{tag}:")
        print(f"  标准点 → 节点      新建 {self.nodes} / 跳过(已存在) {self.nodes_skip}")
        print(f"  同名折叠           折叠旧行 {self.collapsed}(多旧 code → 同一节点)")
        print(f"  节点别名           新建 {self.aliases}")
        print(f"  parent_id 回填     {self.parents}")
        print(f"  游离点 → 候选      新建 {self.cand} / 累加 occur_count {self.cand_bumped}")


async def migrate(dry: bool, only_codes: set[str] | None = None) -> Stats:
    """only_codes:仅处理这些旧 code(测试用,默认 None=全量)。"""
    st = Stats()
    async with _async_session_factory() as db:
        q = select(KnowledgePoint)
        if only_codes is not None:
            q = q.where(KnowledgePoint.code.in_(only_codes))
        rows = (await db.execute(q)).scalars().all()
        standard = [r for r in rows if not _is_auto(r.code)]
        autos = [r for r in rows if _is_auto(r.code)]

        # 预载已占用的别名归一键(复跑幂等:已迁过的名不再重建)
        existing_alias = set(
            (await db.execute(select(NodeAlias.alias_norm))).scalars().all()
        )

        # ── Pass 1:标准点 → 节点(**按 name_norm 折叠**,一个写法=一个节点)──
        # KP-First 本意:同名 KP(旧表按每单元/每次各播一行,不同 code)收敛成一个概念节点。
        norm_to_node: dict[str, uuid.UUID] = {}   # name_norm → 本次/已存在的节点 id
        old_code_to_node: dict[str, uuid.UUID] = {}  # 每个旧 code(含被折叠的)→ 节点 id(供接树)
        for kp in standard:
            norm = normalize_kp_name(kp.name)
            if not norm:
                continue
            stages = stages_from_grades(kp.applicable_grades)

            if norm in norm_to_node:
                # 同名折叠:并入已建节点,合并学段并集,不新建
                st.collapsed += 1
                node_id = norm_to_node[norm]
                old_code_to_node[kp.code] = node_id
                if not dry and stages:
                    node = await db.get(KnowledgeNode, node_id)
                    if node is not None:
                        merged = list(dict.fromkeys((node.applicable_stages or []) + stages))
                        node.applicable_stages = merged or None
                continue

            if norm in existing_alias:
                # 复跑:该名上轮已迁 → 找到其节点,记账跳过,补 code 映射
                st.nodes_skip += 1
                if not dry:
                    al = (await db.execute(
                        select(NodeAlias.node_id).where(NodeAlias.alias_norm == norm)
                    )).scalar_one()
                    norm_to_node[norm] = al
                    old_code_to_node[kp.code] = al
                continue

            # 新建节点 + 唯一别名
            axis, node_kind = CATEGORY_MAP.get(kp.category, DEFAULT_AXIS_KIND)
            new_id = uuid.uuid4()
            st.nodes += 1
            st.aliases += 1
            norm_to_node[norm] = new_id
            old_code_to_node[kp.code] = new_id
            existing_alias.add(norm)
            if not dry:
                db.add(KnowledgeNode(
                    id=new_id, axis=axis, node_kind=node_kind,
                    name=kp.name, code=kp.code,
                    applicable_stages=stages or None,
                    status="active", source="seed",
                    description=kp.description, sort_order=kp.sort_order or 0,
                ))
                await db.flush()
                db.add(NodeAlias(
                    id=uuid.uuid4(), node_id=new_id,
                    alias=kp.name, alias_norm=norm, source="seed",
                ))

        if not dry:
            await db.flush()

        # ── Pass 2:回填 parent_id(旧 parent 的 code → 折叠后节点 id;同节点自指则跳过)──
        old_id_to_code = {r.id: r.code for r in standard}
        for kp in standard:
            if kp.parent_id is None or kp.code not in old_code_to_node:
                continue
            parent_code = old_id_to_code.get(kp.parent_id)
            parent_new_id = old_code_to_node.get(parent_code) if parent_code else None
            child_new_id = old_code_to_node[kp.code]
            if not parent_new_id or parent_new_id == child_new_id:
                continue  # 折叠后父子同节点 → 无自环
            st.parents += 1
            if not dry:
                node = await db.get(KnowledgeNode, child_new_id)
                if node is not None and node.parent_id is None:
                    node.parent_id = parent_new_id

        # ── 游离点 → 候选(ON CONFLICT occur_count++)──
        for kp in autos:
            norm = normalize_kp_name(kp.name)
            if not norm:
                continue
            axis, _ = CATEGORY_MAP.get(kp.category, DEFAULT_AXIS_KIND)
            axis = axis or "knowledge"  # 决策②:绝不留 NULL,规避唯一键 NULL 去重失效
            stages = stages_from_grades(kp.applicable_grades)
            if dry:
                # 估算:同名是否已在候选(粗略,按 norm 唯一近似)
                st.cand += 1
                continue
            stmt = (
                pg_insert(KpCandidate)
                .values(
                    id=uuid.uuid4(), raw_name=kp.name, name_norm=norm,
                    suggested_axis=axis,
                    suggested_stage=(stages[0] if stages else None),
                    occur_count=1,
                    context_sample={"legacy_kp_id": str(kp.id), "legacy_code": kp.code},
                    source_type="legacy_auto",
                    status="pending",
                )
                .on_conflict_do_update(
                    constraint="uix_kp_candidate_norm_axis",
                    set_={"occur_count": KpCandidate.occur_count + 1},
                )
                .returning(KpCandidate.occur_count)
            )
            occ = (await db.execute(stmt)).scalar_one()
            if occ == 1:
                st.cand += 1
            else:
                st.cand_bumped += 1

        if dry:
            await db.rollback()
        else:
            await db.commit()
    return st


def main() -> None:
    ap = argparse.ArgumentParser(description="R0.2 KP 种子迁移 knowledge_points → knowledge_node")
    ap.add_argument("--dry-run", action="store_true", help="只统计不写库")
    args = ap.parse_args()
    st = asyncio.run(migrate(args.dry_run))
    st.report(args.dry_run)


if __name__ == "__main__":
    main()
