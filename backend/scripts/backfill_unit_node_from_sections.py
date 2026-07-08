"""回填 unit_node:把「单元 section → 图谱节点」的挂靠聚合为单元级 unit_node 边。

背景:单元↔知识图谱有两条挂靠链路——
  1) 生成时 match_kp 命中受控树 → 写 unit_node(学生端读它);
  2) 结构化解析/人工挂靠 → 只写 curriculum_unit_section.node_id(admin「单元考点」读它)。
链路 2 历史上没回写 unit_node,导致学生端单元列表「N 个知识点」显示 0、单元详情看不到考点,
而 admin 却有(两边数不同源)。本脚本一次性把 section.node_id 去重聚合进 unit_node。
之后由 curriculum_service._sync_unit_node 在挂靠时实时回写,不再需要跑本脚本。

用法:python -m scripts.backfill_unit_node_from_sections
幂等(ON CONFLICT DO NOTHING)。
"""
import asyncio

from sqlalchemy import text

from app.core.database import _async_session_factory


async def main() -> None:
    async with _async_session_factory() as s:
        r = await s.execute(text("""
            INSERT INTO unit_node (unit_id, node_id, source)
            SELECT DISTINCT unit_id, node_id, 'structured'
            FROM curriculum_unit_section
            WHERE node_id IS NOT NULL
            ON CONFLICT (unit_id, node_id) DO NOTHING
        """))
        await s.commit()
        print(f"backfilled unit_node edges: {r.rowcount}")


if __name__ == "__main__":
    asyncio.run(main())
