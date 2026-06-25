"""给「译林版·八年级」播一小份干净的语法知识点 + 教材单元映射,并设测试生教材偏好。

让语法精进页能按真实译林初二语法点圈题库(替代 build_pool 退回的测试脏数据)。
幂等:按 KP 名称去重复用,已存在的单元/映射跳过。

用法:DATABASE_URL=... python -m scripts.seed_yilin_grammar [student_id]
"""
import asyncio
import sys
import uuid

import sqlalchemy as sa

from app.core.database import _async_session_factory
from app.models.d4_knowledge import KnowledgePoint, CurriculumUnit, UnitKnowledgePoint
from app.models.d1_users import User

TEXTBOOK = "译林版"
GRADE = "八年级"
SEMESTER = "上"

# 初二常见语法点(名称 + 简介,简介喂给 LLM 出探针)
KPS = [
    ("一般现在时", "描述习惯/事实;第三人称单数动词加 -s/-es;否定/疑问用 do/does。"),
    ("一般过去时", "描述过去发生的动作;规则动词加 -ed,不规则动词需记忆;否定/疑问用 did。"),
    ("现在进行时", "描述此刻正在进行的动作;be(am/is/are)+ 动词-ing。"),
    ("过去进行时", "描述过去某时正在进行的动作;was/were + 动词-ing;常与 when/while 连用。"),
    ("现在完成时", "have/has + 过去分词;表示对现在的影响或持续到现在;常与 already/yet/ever/since/for。"),
    ("一般将来时", "表示将来的动作或计划;will + 动词原形 或 be going to + 动词原形。"),
    ("主谓一致", "谓语动词的人称和数与主语保持一致(三单、不可数、就近原则等)。"),
    ("比较级与最高级", "形容词/副词的比较级(-er/more)与最高级(-est/most)及其句型。"),
]


async def main(student_id: str | None) -> None:
    async with _async_session_factory() as db:
        # 1) upsert KP(按名称去重)
        kp_ids = []
        for i, (name, desc) in enumerate(KPS):
            kp = (await db.execute(sa.select(KnowledgePoint).where(
                KnowledgePoint.category == "grammar", KnowledgePoint.name == name))).scalars().first()
            if kp is None:
                kp = KnowledgePoint(
                    id=uuid.uuid4(), code=f"gr-yl8-{i:02d}-{uuid.uuid4().hex[:6]}",
                    name=name, category="grammar", description=desc,
                    applicable_grades=[GRADE], applicable_textbooks=[TEXTBOOK], sort_order=i)
                db.add(kp)
                await db.flush()
            else:
                if not kp.description:
                    kp.description = desc
                kp.sort_order = i   # 用本表顺序当难度阶梯
            kp_ids.append(kp.id)

        # 2) 译林版·八年级·上 单元(语法专项)
        unit = (await db.execute(sa.select(CurriculumUnit).where(
            CurriculumUnit.textbook_version == TEXTBOOK, CurriculumUnit.grade == GRADE,
            CurriculumUnit.semester == SEMESTER, CurriculumUnit.unit_no == 1))).scalars().first()
        if unit is None:
            unit = CurriculumUnit(id=uuid.uuid4(), textbook_version=TEXTBOOK, grade=GRADE,
                                  semester=SEMESTER, unit_no=1, unit_title="语法专项(初二)")
            db.add(unit)
            await db.flush()

        # 3) 单元 ↔ 语法点 映射
        existing = set((await db.execute(sa.select(UnitKnowledgePoint.knowledge_point_id)
                                         .where(UnitKnowledgePoint.unit_id == unit.id))).scalars().all())
        added = 0
        for kid in kp_ids:
            if kid not in existing:
                db.add(UnitKnowledgePoint(unit_id=unit.id, knowledge_point_id=kid))
                added += 1

        # 4) 设测试生教材偏好(便于页面按译林初二圈题库)
        if student_id:
            u = (await db.execute(sa.select(User).where(User.id == uuid.UUID(student_id)))).scalars().first()
            if u is not None:
                u.preferred_textbook_version = TEXTBOOK
                u.preferred_grade = GRADE
                u.preferred_semester = SEMESTER

        await db.commit()
        print(f"[seed-yilin-grammar] KP={len(kp_ids)} unit={unit.id} 新增映射={added} "
              f"student_pref={'set' if student_id else 'skip'}")


if __name__ == "__main__":
    sid = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(main(sid))
