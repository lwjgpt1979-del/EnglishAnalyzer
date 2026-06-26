"""给粗语法点播标准「子细点」(受控细分树第一步:一般现在时)。

解决"粗点盖住细则"——掌握判定落到子叶点,粗点做 rollup(子点全过才算粗点掌握)。
幂等:按名称去重;子点 parent_id=粗点,并挂到粗点所在单元。

用法:DATABASE_URL=... python -m scripts.seed_grammar_subkp
"""
import asyncio
import uuid

import sqlalchemy as sa
from app.core.database import _async_session_factory
from app.models.d4_knowledge import KnowledgePoint, UnitKnowledgePoint

# 粗点名 → 标准子点 [(名, 简介)]
SUBKP = {
    "一般现在时": [
        ("一般现在时·动词三单", "第三人称单数动词加 -s/-es 的变化规则(go→goes, study→studies)。"),
        ("一般现在时·否定与疑问", "用 do/does 构成否定(don't/doesn't)和一般疑问句。"),
        ("一般现在时·be 动词", "am/is/are 随主语变化(I am, he is, they are)。"),
        ("一般现在时·时间状语", "every day/usually/on Sundays 等标志一般现在时。"),
        ("一般现在时·频度副词位置", "always/usually/often 等放在实义动词前、be 动词后。"),
    ],
}


async def main() -> None:
    async with _async_session_factory() as db:
        for coarse_name, subs in SUBKP.items():
            parent = (await db.execute(sa.select(KnowledgePoint).where(
                KnowledgePoint.category == "grammar", KnowledgePoint.name == coarse_name))).scalars().first()
            if parent is None:
                print(f"[skip] 粗点不存在:{coarse_name}")
                continue
            # 粗点所在单元(挂子点用)
            unit_ids = (await db.execute(sa.select(UnitKnowledgePoint.unit_id).where(
                UnitKnowledgePoint.knowledge_point_id == parent.id))).scalars().all()
            added = 0
            for i, (nm, desc) in enumerate(subs):
                kp = (await db.execute(sa.select(KnowledgePoint).where(
                    KnowledgePoint.category == "grammar", KnowledgePoint.name == nm))).scalars().first()
                if kp is None:
                    kp = KnowledgePoint(
                        id=uuid.uuid4(), code=f"gr-subkp-{uuid.uuid4().hex[:8]}", name=nm,
                        category="grammar", description=desc, applicable_grades=parent.applicable_grades,
                        applicable_textbooks=parent.applicable_textbooks, parent_id=parent.id, sort_order=i)
                    db.add(kp)
                    await db.flush()
                    added += 1
                else:
                    kp.parent_id = parent.id
                for uid in unit_ids:
                    ex = (await db.execute(sa.select(UnitKnowledgePoint).where(
                        UnitKnowledgePoint.unit_id == uid,
                        UnitKnowledgePoint.knowledge_point_id == kp.id))).first()
                    if not ex:
                        db.add(UnitKnowledgePoint(unit_id=uid, knowledge_point_id=kp.id))
            print(f"[{coarse_name}] 子点 {len(subs)} 个(新增 {added}),挂到 {len(unit_ids)} 个单元")
        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
