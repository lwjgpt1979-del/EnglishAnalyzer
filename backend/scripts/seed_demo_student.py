"""演示学生「小明」全流程测试数据 seed（一次性，幂等）。

覆盖学生端所有功能的数据：
- 偏好：译林版/小学5年级/上（已有课程内容）
- 掌握台账 student_kp_mastery（弱/中/强混合）
- 练习记录 sim_practice_records（真实题 id，部分今日）
- 错题 wrong_questions + AI 分析 ai_analyses
- 模拟考 sim_exam_sessions（成绩趋势）
- 打卡 study_checkins（连续 5 天）
- 趋势快照 kp_mastery_snapshots

运行：PYTHONPATH=. python scripts/seed_demo_student.py
输出：学生 id（用于生成 JWT 注入 H5）
"""
import asyncio
import json
import uuid
from datetime import datetime, timezone, timedelta, date

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import _async_session_factory

OPENID = "demo_xiaoming"
NICK = "小明"
TB, GRADE, SEM = "译林版", "小学5年级", "上"
now = datetime.now(timezone.utc)
today = now.date()


async def _cleanup(s: AsyncSession, uid: uuid.UUID):
    for t in ["sim_practice_records", "sim_exam_sessions", "study_checkins",
              "kp_mastery_snapshots", "student_kp_mastery"]:
        await s.execute(text(f"DELETE FROM {t} WHERE student_id=:u"), {"u": uid})
    await s.execute(text(
        "DELETE FROM ai_analyses WHERE student_id=:u"), {"u": uid})
    await s.execute(text(
        "DELETE FROM wrong_question_knowledge_points WHERE wrong_question_id IN "
        "(SELECT id FROM wrong_questions WHERE student_id=:u)"), {"u": uid})
    await s.execute(text("DELETE FROM wrong_questions WHERE student_id=:u"), {"u": uid})


async def main():
    async with _async_session_factory() as s:
        # ── 学生 ────────────────────────────────────────────────────────────
        uid = (await s.execute(
            select(text("id")).select_from(text("users")).where(text("openid=:o"))
            , {"o": OPENID})).scalar()
        if uid is None:
            uid = uuid.uuid4()
            await s.execute(text(
                "INSERT INTO users (id, openid, role, nickname, profile_completed, "
                "preferred_textbook_version, preferred_grade, preferred_semester) "
                "VALUES (:id,:o,'student',:n,true,:tb,:g,:sm)"
            ), {"id": uid, "o": OPENID, "n": NICK, "tb": TB, "g": GRADE, "sm": SEM})
        else:
            await s.execute(text(
                "UPDATE users SET nickname=:n, profile_completed=true, "
                "preferred_textbook_version=:tb, preferred_grade=:g, preferred_semester=:sm "
                "WHERE id=:id"), {"id": uid, "n": NICK, "tb": TB, "g": GRADE, "sm": SEM})
        await s.flush()
        await _cleanup(s, uid)

        # ── 取 5年级上 KP + 每 KP 一道已发布题 ───────────────────────────────
        _raw = (await s.execute(text("""
            SELECT DISTINCT kp.id, kp.name, kp.category, kp.description
            FROM curriculum_units cu
            JOIN unit_knowledge_points ukp ON ukp.unit_id=cu.id
            JOIN knowledge_points kp ON kp.id=ukp.knowledge_point_id
            WHERE cu.textbook_version=:tb AND cu.grade=:g AND cu.semester=:sm
            ORDER BY kp.name
        """), {"tb": TB, "g": GRADE, "sm": SEM})).all()
        # 按 name 去重（台账主键含 kp_key=name，同名只取一条）
        kp_rows, _seen = [], set()
        for r in _raw:
            if r[1] in _seen:
                continue
            _seen.add(r[1])
            kp_rows.append(r)
            if len(kp_rows) >= 14:
                break
        # 每个 KP 找一道已发布题（用于 practice_records 的 FK）
        q_for_kp = {}
        for kp in kp_rows:
            qid = (await s.execute(text(
                "SELECT id FROM simulated_questions WHERE knowledge_point_id=:k "
                "AND status='published' LIMIT 1"), {"k": kp[0]})).scalar()
            q_for_kp[kp[0]] = qid

        # 14 个 KP 分配掌握度：(correct, wrong, days_ago_last)
        plan = [
            (2, 7, 0), (1, 6, 0), (3, 6, 1), (2, 5, 2),      # 弱 (今日练了前 2 个)
            (5, 5, 1), (6, 4, 3), (5, 4, 2), (6, 3, 4), (5, 3, 1),  # 中
            (9, 1, 2), (8, 1, 5), (9, 1, 3), (8, 2, 4), (10, 0, 6), # 强
        ]
        for (kp, (cor, wro, dago)) in zip(kp_rows, plan):
            kid, kname, kcat, kdesc = kp
            last = now - timedelta(days=dago)
            await s.execute(text(
                "INSERT INTO student_kp_mastery (student_id,kp_key,kp_id,correct_count,"
                "wrong_count,sources,kp_description,last_activity_at) "
                "VALUES (:s,:k,:kid,:c,:w,ARRAY['practice'],:d,:ts)"
            ), {"s": uid, "k": kname, "kid": kid, "c": cor, "w": wro, "d": kdesc, "ts": last})
            # 对应 practice 记录（真实题 id）
            qid = q_for_kp.get(kid)
            if qid:
                for i in range(cor + wro):
                    ok = i < cor
                    ts = last - timedelta(minutes=i * 3)
                    await s.execute(text(
                        "INSERT INTO sim_practice_records (id,student_id,simulated_question_id,"
                        "knowledge_point_id,is_correct,user_answer,created_at) "
                        "VALUES (:id,:s,:q,:k,:ok,'A',:ts)"
                    ), {"id": uuid.uuid4(), "s": uid, "q": qid, "k": kid, "ok": ok, "ts": ts})

        # ── 错题 + AI 分析（挂在前 4 个弱项 KP）────────────────────────────
        weak = kp_rows[:4]
        wq_specs = [
            ("单选", "She _____ to school every day. (go/goes)", False, 2),
            ("填空", "There ___ a book and two pens on the desk.", False, 3),
            ("单选", "Can you _____ English? (speak/speaks)", False, 2),
            ("判断", "复数名词 box 的复数是 boxs。(对/错)", True, 1),
        ]
        for (kp, (qtype, qtext, mastered, diff)) in zip(weak, wq_specs):
            kid, kname, kcat, kdesc = kp
            wqid = uuid.uuid4()
            await s.execute(text(
                "INSERT INTO wrong_questions (id,student_id,source_image_url,question_type,"
                "question_text,difficulty,is_mastered,created_at,mastered_at) "
                "VALUES (:id,:s,'demo-seed',:qt,:txt,:d,:m,:c,:ma)"
            ), {"id": wqid, "s": uid, "qt": qtype, "txt": qtext, "d": diff,
                "m": mastered, "c": now - timedelta(days=diff),
                "ma": (now if mastered else None)})
            await s.execute(text(
                "INSERT INTO wrong_question_knowledge_points (wrong_question_id,knowledge_point_id) "
                "VALUES (:w,:k)"), {"w": wqid, "k": kid})
            await s.execute(text(
                "INSERT INTO ai_analyses (id,wrong_question_id,student_id,llm_provider,"
                "error_types,knowledge_points,diagnosis,suggestions,tokens_used,created_at) "
                "VALUES (:id,:w,:s,'deepseek',CAST(:et AS jsonb),CAST(:kps AS jsonb),:diag,:sug,:tok,:c)"
            ), {"id": uuid.uuid4(), "w": wqid, "s": uid,
                "et": json.dumps(["语法错误", "时态错误"], ensure_ascii=False),
                "kps": json.dumps([kname], ensure_ascii=False),
                "diag": f"该题考查「{kname}」，学生对该知识点掌握不牢。",
                "sug": f"建议重点复习「{kname}」，多做同类基础题巩固。",
                "tok": 320, "c": now - timedelta(days=diff)})

        # ── 模拟考成绩（成绩趋势）────────────────────────────────────────
        for i, (tot, cor) in enumerate([(10, 5), (10, 6), (10, 7), (10, 8)]):
            await s.execute(text(
                "INSERT INTO sim_exam_sessions (id,student_id,total,correct_count,accuracy,created_at) "
                "VALUES (:id,:s,:t,:c,:a,:ts)"
            ), {"id": uuid.uuid4(), "s": uid, "t": tot, "c": cor,
                "a": round(cor / tot, 4), "ts": now - timedelta(days=(4 - i) * 2)})

        # ── 打卡（连续 5 天）────────────────────────────────────────────
        for d in range(5):
            await s.execute(text(
                "INSERT INTO study_checkins (id,student_id,checkin_date,new_words_count,"
                "review_done,streak_days) VALUES (:id,:s,:d,:nw,true,:st)"
            ), {"id": uuid.uuid4(), "s": uid, "d": today - timedelta(days=d),
                "nw": 5, "st": 5 - d})

        # ── 趋势快照（前 3 个弱项 KP，近 5 天上升趋势）──────────────────
        for kp in kp_rows[:3]:
            kid, kname, kcat, kdesc = kp
            for d in range(5):
                acc = round(0.3 + d * 0.12, 4)
                await s.execute(text(
                    "INSERT INTO kp_mastery_snapshots (id,student_id,kp_key,snapshot_date,"
                    "accuracy,correct_count,wrong_count) VALUES (:id,:s,:k,:dt,:a,:c,:w) "
                    "ON CONFLICT ON CONSTRAINT uq_kp_snapshot_student_kp_date DO UPDATE "
                    "SET accuracy=EXCLUDED.accuracy"
                ), {"id": uuid.uuid4(), "s": uid, "k": kname,
                    "dt": today - timedelta(days=(4 - d)), "a": acc,
                    "c": int(acc * 10), "w": 10 - int(acc * 10)})

        await s.commit()
        print("DEMO_STUDENT_ID=" + str(uid))
        print("openid=" + OPENID + " nick=" + NICK)
        print("KPs seeded:", len(kp_rows), "| wrong_q: 4 | exams: 4 | checkins: 5")


if __name__ == "__main__":
    asyncio.run(main())
