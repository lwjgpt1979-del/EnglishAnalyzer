"""按 rc 规则给存量阅读真题精确补标 rc-* 子技能(P1① 落存量)。

对每道阅读真题(type=real, question_type=阅读)按问法确定性归到 rc-* 叶子,
补挂对应 KP 节点(已挂同节点则跳过;无明显问法信号则跳过,交人工/LLM)。
默认 **dry-run** 只统计不落库;加 `--apply` 才写 platform_question_kp。

安全:分类器保守(无信号返回 None),只标高置信问法;不动已挂的边、不删任何东西。
用法:DATABASE_URL=... python -m scripts.backfill_rc_skills [--apply]
"""
import asyncio
import logging
import sys
from collections import Counter

import sqlalchemy as sa

from app.core.database import async_session_factory
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import PlatformQuestion, PlatformQuestionKp
from app.services import platform_question_service as pqs
from app.services.kp_suggest_service import classify_reading_skill

logging.disable(logging.INFO)


async def main(apply: bool):
    async with async_session_factory() as db:
        rc_nodes = {code: nid for nid, code in (await db.execute(
            sa.select(KnowledgeNode.id, KnowledgeNode.code)
            .where(KnowledgeNode.code.like("rc-%")))).all()}
        qs = (await db.execute(
            sa.select(PlatformQuestion).where(
                PlatformQuestion.type == "real",
                PlatformQuestion.question_type == "阅读"))).scalars().all()

        stat: Counter = Counter()
        tagged = have = no_match = 0
        for q in qs:
            code = classify_reading_skill(q.stem or "")
            nid = rc_nodes.get(code) if code else None
            if nid is None:
                no_match += 1
                continue
            exists = (await db.execute(
                sa.select(PlatformQuestionKp.question_id).where(
                    PlatformQuestionKp.question_id == q.id,
                    PlatformQuestionKp.node_id == nid))).first()
            if exists:
                have += 1
                continue
            stat[code] += 1
            tagged += 1
            if apply:
                await pqs.attach_node(db, q.id, nid)
        if apply:
            await db.commit()

        print(f"=== 阅读真题 {len(qs)} 道:可补标 {tagged}、已挂跳过 {have}、无明显问法(交LLM/人工){no_match} ===")
        for code, n in stat.most_common():
            print(f"  {code}: +{n}")
        print("(dry-run,未落库;加 --apply 落库)" if not apply else "(已落库 commit)")


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))
