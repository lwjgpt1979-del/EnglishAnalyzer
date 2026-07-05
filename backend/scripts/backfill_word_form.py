"""按词形规则给存量「词汇运用/动词填空」真题精确补标 cf-*/jf-* 考点(Phase A-4 落存量)。

对 section 归入 词汇/词语/适当形式/动词 的真题,按「语境信号+括号所给词」确定性归桶
(复数/比较级最高级/序数词/动名词/不定式/副词化/被动/时态),补挂对应 KP 节点。
无高置信信号则跳过(交 LLM/人工)。默认 **dry-run**;加 `--apply` 才落库。

用法:python -m scripts.backfill_word_form [--apply]
"""
import asyncio
import logging
import re
import sys
from collections import Counter

import sqlalchemy as sa

from app.core.database import async_session_factory
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import PlatformQuestion, PlatformQuestionKp
from app.services import platform_question_service as pqs
from app.services.kp_suggest_service import classify_word_form

logging.disable(logging.INFO)

_SECTION_RE = re.compile(r"词汇|词语|适当形式|词形|动词")


async def main(apply: bool):
    async with async_session_factory() as db:
        nodes = {code: nid for nid, code in (await db.execute(
            sa.select(KnowledgeNode.id, KnowledgeNode.code)
            .where(sa.or_(KnowledgeNode.code.like("cf-%"),
                          KnowledgeNode.code.like("jf-%"))))).all()}
        qs = (await db.execute(
            sa.select(PlatformQuestion).where(PlatformQuestion.type == "real"))).scalars().all()
        qs = [q for q in qs if _SECTION_RE.search(q.section or "")]

        stat: Counter = Counter()
        tagged = have = no_match = 0
        for q in qs:
            code = classify_word_form(q.stem or "")
            nid = nodes.get(code) if code else None
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

        print(f"=== 词汇运用/动词填空 {len(qs)} 道:可补标 {tagged}、已挂跳过 {have}、"
              f"无高置信信号(交LLM/人工){no_match} ===")
        for code, n in stat.most_common():
            print(f"  {code}: +{n}")
        print("(dry-run,未落库;加 --apply 落库)" if not apply else "(已落库 commit)")


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))
