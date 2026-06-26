"""把测试学生的译林八年级 16 个语法点都走到「已掌握」(四维 + 隔期复测)。

每点:纠错×2 → 产出×2(用该语法的正确例句)→ 迁移答对 → 回溯到期复测答对 → confirmed。
真 LLM 评分,逐点 try/except,失败不中断。仅用于演示/验收。

用法:DATABASE_URL=... python -m scripts.drive_master_all
"""
import asyncio
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from app.core.database import _async_session_factory
from app.models.d4_knowledge import KnowledgePoint
from app.services import grammar_probe_service as gp, grammar_placement_service as pl

SID = uuid.UUID("326abf5c-936e-40e8-b3e2-cfba157ea38b")

# 每个语法点的"正确造句"(确保产出 rubric 能过)
SENT = {
    "一般现在时": "She gets up early and goes to school every day.",
    "一般过去时": "I visited my grandmother last weekend.",
    "现在进行时": "She is reading an interesting book right now.",
    "过去进行时": "They were playing football when it started to rain.",
    "现在完成时": "I have already finished my homework.",
    "一般将来时": "We will travel to Beijing next month.",
    "主谓一致": "Each of the students has a new textbook.",
    "比较级与最高级": "This book is more interesting than that one.",
    "被动语态": "The window was broken by the naughty boy.",
    "情态动词": "You must finish your homework before dinner.",
    "宾语从句": "I think that he is right about the answer.",
    "定语从句": "The man who lives next door is a kind doctor.",
    "感叹句": "What a beautiful flower it is!",
    "反意疑问句": "You are a student, aren't you?",
    "不定式": "She wants to learn English well.",
    "动词-ing 形式": "He enjoys playing basketball after school.",
    # 一般现在时 子细点
    "一般现在时·动词三单": "She gets up early and goes to school every day.",
    "一般现在时·否定与疑问": "He doesn't watch TV on weekdays.",
    "一般现在时·be 动词": "They are students and she is my best friend.",
    "一般现在时·时间状语": "I read English books every evening.",
    "一般现在时·频度副词位置": "She always gets up early in the morning.",
}


async def master_one(db, kp) -> dict:
    KID = kp.id
    p = await gp.ensure_probes(db, kp)
    await db.commit()
    # ① 纠错 ×2
    det_items = p.get("detect") or []
    if det_items:
        for _ in range(2):
            await gp.submit_probe(db, student_id=SID, kp_id=KID, key="detect:0",
                                  answer=str(det_items[0]["answer"]))
            await db.commit()
    # ② 产出 ×2(用例句;若没过再补一次)
    sent = SENT.get(kp.name, "")
    for _ in range(2):
        await gp.submit_produce(db, student_id=SID, kp_id=KID, sentence=sent)
        await db.commit()
    # ③ 迁移答对
    seeds = await gp._ensure_transfer_seed(db, kp)
    await db.commit()
    if seeds:
        await gp.submit_transfer(db, student_id=SID, kp_id=KID, key="transfer:0",
                                 answer=str(seeds[0]["answer"]))
        await db.commit()
    # ④ 回溯到期 + 复测答对
    m = await gp._get_mastery(db, SID, KID)
    if m and m.mastered_at is not None and seeds:
        m.next_retain_at = datetime.now(timezone.utc) - timedelta(days=1)
        await db.commit()
        await gp.submit_retention(db, student_id=SID, kp_id=KID, key="transfer:0",
                                  answer=str(seeds[0]["answer"]))
        await db.commit()
    return await gp.kp_status(db, student_id=SID, kp_id=KID)


async def main():
    async with _async_session_factory() as db:
        pool = await pl.build_pool(db, textbook="译林版", grade="八年级", kp_ids=None)
        done = fail = 0
        for d in pool:
            kp = (await db.execute(select(KnowledgePoint).where(KnowledgePoint.id == uuid.UUID(d["kp_id"])))).scalars().first()
            try:
                st = await master_one(db, kp)
                ok = st["confirmed_mastered"]
                done += ok
                fail += (not ok)
                print(f"  {'✓' if ok else '✗'} {kp.name:12s} {st['label']} | 纠错{st['detect']:.2f} 产出{st['produce_score']:.2f} 迁移{st['transfer_ok']}", flush=True)
            except Exception as e:  # noqa: BLE001
                fail += 1
                print(f"  ✗ {kp.name:12s} 异常 {type(e).__name__}: {e}", flush=True)
        print(f"=== 已掌握 {done}/{len(pool)} (失败 {fail}) ===", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
