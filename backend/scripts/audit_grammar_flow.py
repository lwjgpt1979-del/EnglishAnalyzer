"""学生端语法流程自动走查 + 算法不变量审计(随机对错)。

跑一遍:分级测验(CAT)→ 单点四维 → 间隔复测 → 推进环,随机对错,
逐步断言算法要求,记录任何逻辑/系统错误。只读审计,不改产品代码。

用法:DATABASE_URL=... python -m scripts.audit_grammar_flow
"""
import asyncio
import random
import uuid
from datetime import datetime, timezone, timedelta

import sqlalchemy as sa

from app.core.database import _async_session_factory
from app.models.d4_knowledge import (
    KnowledgePoint, StudentGrammarMastery, GrammarPlacementSession,
)
from app.services import (
    grammar_placement_service as pl, grammar_probe_service as gp,
    grammar_path_service as path, grammar_config_service as gc,
)

SID = uuid.UUID("326abf5c-936e-40e8-b3e2-cfba157ea38b")
random.seed(42)
ISSUES: list[str] = []
def bug(msg): ISSUES.append(msg); print("  ❌ 问题:", msg)
def ok(msg): print("  ✓", msg)


async def reset(db):
    await db.execute(sa.delete(StudentGrammarMastery).where(StudentGrammarMastery.student_id == SID))
    await db.execute(sa.delete(GrammarPlacementSession).where(GrammarPlacementSession.student_id == SID))
    await db.commit()


def chk_bkt(v, where):
    if v is None:
        return
    if not (0.0 <= float(v) <= 1.0):
        bug(f"{where}: BKT 越界 {v}")


async def correct_answer(db, kp_id, key="recognize:0"):
    kp = (await db.execute(sa.select(KnowledgePoint).where(KnowledgePoint.id == uuid.UUID(kp_id)))).scalars().first()
    p = kp.grammar_probes_json or {}
    kind, idx = key.split(":"); idx = int(idx)
    if kind == "recognize":
        return str(p["recognize"][idx]["answer"])
    if kind == "detect":
        return str(p["detect"][idx]["answer"])
    if kind == "transfer":
        return str((p.get("transfer_seed") or [{}])[idx].get("answer"))
    return ""


async def phase_placement(db):
    print("\n=== ① 分级测验(CAT,随机对错)===")
    cfg = await gc.get_config(db)
    maxn = cfg["placement_max_items"]
    r = await pl.start(db, student_id=SID, use_paper_priors=False)
    await db.commit()
    asked = 0
    while not r.get("done"):
        it = r["item"]; kid = it["kp_id"]
        ca = await correct_answer(db, kid, it["item"]["key"])
        pick = ca if random.random() < 0.5 else "__wrong__"
        r = await pl.answer(db, student_id=SID, session_id=uuid.UUID(r["session_id"]), kp_id=kid, chosen=pick)
        await db.commit()
        asked += 1
        if asked > maxn + 2:
            bug(f"placement 未在 max({maxn}) 内收敛,已问 {asked}")
            break
    print(f"  共问 {asked} 题(上限 {maxn})")
    if asked > maxn:
        bug(f"placement 问题数 {asked} 超过上限 {maxn}")
    else:
        ok("placement 在上限内收敛")
    heat = r.get("heatmap") or []
    if not heat:
        bug("placement 结束无热力图")
    else:
        ok(f"热力图 {len(heat)} 点")
    sl = r.get("start_line")
    first_below = next((h for h in heat if h["prior"] < 0.5), None)
    if first_below and sl and sl["kp_id"] != first_below["kp_id"]:
        bug(f"起点线 {sl['name']} 不是第一个 prior<0.5 的点 {first_below['name']}")
    elif sl:
        ok(f"起点线 = {sl['name']}")
    # 暖启动先验是否写库
    rows = (await db.execute(sa.select(StudentGrammarMastery).where(
        StudentGrammarMastery.student_id == SID))).scalars().all()
    placed = [m for m in rows if m.prior_source == "placement"]
    if not placed:
        bug("placement 未写任何 prior_source=placement 先验")
    else:
        ok(f"暖启动写入 {len(placed)} 个先验")
    for m in rows:
        chk_bkt(m.mastery_recognize, "placement.recognize")


async def phase_four_axis(db, kp_id, name):
    print(f"\n=== ② 单点四维:{name} (随机对错)===")
    await db.execute(sa.delete(StudentGrammarMastery).where(
        StudentGrammarMastery.student_id == SID, StudentGrammarMastery.kp_id == uuid.UUID(kp_id)))
    await db.commit()
    out = await gp.comprehension_probes(db, student_id=SID,
                                        kp=(await db.execute(sa.select(KnowledgePoint).where(KnowledgePoint.id == uuid.UUID(kp_id)))).scalars().first())
    await db.commit()
    # 识别 + 纠错 探针随机作答
    for p in out["probes"]:
        ca = await correct_answer(db, kp_id, p["key"])
        pick = ca if random.random() < 0.5 else "__x__"
        res = await gp.submit_probe(db, student_id=SID, kp_id=uuid.UUID(kp_id), key=p["key"], answer=pick)
        await db.commit()
        chk_bkt(res["detect"], f"{name}.detect"); chk_bkt(res["recognize"], f"{name}.recognize")
        # 不变量:mastered 只在 detect+produce+transfer 齐时为真
        if res["mastered"] and not (res["detect"] >= 0.85 and res["produce_score"] >= 0.85 and res["transfer_ok"]):
            bug(f"{name}: 探针后 mastered=True 但四维未齐(d={res['detect']} p={res['produce_score']} t={res['transfer_ok']})")
    # 产出(随机句:一半像样、一半乱写)
    sent = "She goes to school every day and reads books." if random.random() < 0.5 else "asdf qwer zxcv."
    pr = await gp.submit_produce(db, student_id=SID, kp_id=uuid.UUID(kp_id), sentence=sent)
    await db.commit()
    chk_bkt(pr.get("produce_score"), f"{name}.produce")
    if pr.get("graded", True):
        ok(f"产出评分 total={pr['total']}/{pr['max']} passed={pr['passed']}")
    else:
        ok("产出评分服务失败 → graded=False 未计分(符合预期)")
    # 迁移随机作答
    tprobe = await gp.transfer_probe(db, student_id=SID,
                                     kp=(await db.execute(sa.select(KnowledgePoint).where(KnowledgePoint.id == uuid.UUID(kp_id)))).scalars().first())
    await db.commit()
    if tprobe and tprobe.get("probe"):
        tk = tprobe["probe"]["key"]
        ca = await correct_answer(db, kp_id, tk)
        pick = ca if random.random() < 0.5 else "__x__"
        tr = await gp.submit_transfer(db, student_id=SID, kp_id=uuid.UUID(kp_id), key=tk, answer=pick)
        await db.commit()
        ok(f"迁移 verdict={tr['verdict']} transfer_ok={tr['transfer_ok']}")
        if tr["mastered"] and not (tr["detect"] >= 0.85 and tr["produce_score"] >= 0.85 and tr["transfer_ok"]):
            bug(f"{name}: 迁移后 mastered=True 但四维未齐")
    # confirmed 不变量:四维齐但未复测 → confirmed 必须 False
    m = (await db.execute(sa.select(StudentGrammarMastery).where(
        StudentGrammarMastery.student_id == SID, StudentGrammarMastery.kp_id == uuid.UUID(kp_id)))).scalars().first()
    st = gp._status_label(m)
    print(f"  最终状态: {st['label']} | recognize={float(m.mastery_recognize or 0):.2f} detect={float(m.mastery_detect or 0):.2f} produce={float(m.mastery_produce or 0):.2f} transfer={m.transfer_ok}")
    if gp.confirmed_mastered(m) and (m.retain_count or 0) < 1:
        bug(f"{name}: confirmed_mastered=True 但 retain_count<1(应先隔期复测)")


async def phase_retention(db, kp_id, name):
    print(f"\n=== ③ 间隔复测:{name} ===")
    # 强制四维达成 → 应排复测
    m = await gp._get_or_create_mastery(db, SID, uuid.UUID(kp_id))
    m.mastery_detect = 0.9; m.mastery_produce = 0.9; m.transfer_ok = True
    gp._maybe_schedule_retention(m); await db.commit()
    if m.mastered_at is None or m.next_retain_at is None:
        bug(f"{name}: 四维达成但未排复测(mastered_at/next_retain 为空)")
    else:
        ok("四维达成 → 已排首次复测")
    if gp.confirmed_mastered(m):
        bug(f"{name}: 未复测就 confirmed_mastered=True")
    else:
        ok("未复测 → 尚未 confirmed(符合)")
    # 回溯到期 → 应进 due
    m.next_retain_at = datetime.now(timezone.utc) - timedelta(days=1); await db.commit()
    due = await gp.due_retentions(db, student_id=SID)
    if not any(d["kp_id"] == kp_id for d in due):
        bug(f"{name}: 到期但未进 due_retentions")
    else:
        ok("到期 → 进入待复测列表")
    # 复测答错 → 应遗忘回落
    seeds = (await db.execute(sa.select(KnowledgePoint).where(KnowledgePoint.id == uuid.UUID(kp_id)))).scalars().first().grammar_probes_json.get("transfer_seed") or []
    if seeds:
        rr = await gp.submit_retention(db, student_id=SID, kp_id=uuid.UUID(kp_id), key="transfer:0", answer="__wrong__")
        await db.commit()
        m2 = await gp._get_mastery(db, SID, uuid.UUID(kp_id))
        if rr["verdict"] == "forgotten" and (m2.transfer_ok or m2.mastered_at is not None):
            bug(f"{name}: 复测失败但未回落(transfer_ok={m2.transfer_ok} mastered_at={m2.mastered_at})")
        else:
            ok(f"复测失败 → 遗忘回落(verdict={rr['verdict']})")


async def phase_path(db):
    print("\n=== ④ 推进环 daily_batch ===")
    b = await path.daily_batch(db, student_id=SID)
    await db.commit()
    rs = b["ratios"]
    if abs(rs["new"] + rs["maintain"] + rs["apply"] - 1.0) > 0.001:
        bug(f"三股流配比之和 ≠ 1: {rs}")
    else:
        ok(f"配比 {rs}")
    if len(b["new"]) > b["batch_size"]:
        bug("新点数超过 batch_size")
    # 优先级:new 应按 score 降序
    scores = [n["score"] for n in b["new"]]
    if scores != sorted(scores, reverse=True):
        bug(f"新点未按优先级降序: {scores}")
    else:
        ok(f"新点按优先级降序({len(b['new'])} 个)")
    # 不变量:同一点不得同时出现在「新点」与「维持」
    new_ids = {n["kp_id"] for n in b["new"]}
    dup = [x["kp_name"] for x in b["maintain"] if x["kp_id"] in new_ids]
    if dup:
        bug(f"以下点同时出现在新点与维持: {dup}")
    else:
        ok("新点与维持无重叠")
    print(f"  stats={b['stats']}")


async def main():
    async with _async_session_factory() as db:
        await reset(db)
        try:
            await phase_placement(db)
        except Exception as e:
            bug(f"placement 抛异常: {type(e).__name__}: {e}")
        # 取译林八年级题库前两个点深测四维
        pool = await pl.build_pool(db, textbook="译林版", grade="八年级", kp_ids=None)
        for d in pool[:2]:
            try:
                await phase_four_axis(db, d["kp_id"], d["name"])
                await phase_retention(db, d["kp_id"], d["name"])
            except Exception as e:
                bug(f"{d['name']} 四维/复测抛异常: {type(e).__name__}: {e}")
        try:
            await phase_path(db)
        except Exception as e:
            bug(f"daily_batch 抛异常: {type(e).__name__}: {e}")
        await reset(db)
        print("\n" + "=" * 40)
        if ISSUES:
            print(f"发现 {len(ISSUES)} 个问题:")
            for i in ISSUES:
                print("  -", i)
        else:
            print("✅ 全部不变量通过,未发现逻辑/系统错误")


if __name__ == "__main__":
    asyncio.run(main())
