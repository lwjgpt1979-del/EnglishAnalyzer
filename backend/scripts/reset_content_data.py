"""上线前清库:清空 教材/题库/词力通/KP 图谱 + 学生进度(掌握/错题/练习),保留 users/订单/机构/教师账号。

安全设计:
  - 从"内容+进度"种子表出发,**运行时按外键自动求级联闭包**(谁引用种子→一并清),
    保证清得干净又不漏外键依赖;
  - **护栏**:断言闭包不含保留表(users/orders/institutions/teachers/classes…),命中即中止;
  - 默认 `--dry-run` 只打印将清表与行数;`--execute` 且二次确认 DB 主机后才真 TRUNCATE。

用法:
  python backend/scripts/reset_content_data.py --dry-run          # 只报告
  python backend/scripts/reset_content_data.py --execute          # 真清(会再确认)
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import _async_session_factory  # noqa: E402

# ── 想清空的"内容 + 进度"种子表(其余按外键自动带出)──────────────────────────────
SEED = {
    # 教材/课程内容
    "curriculum_units", "knowledge_points", "unit_knowledge_points",
    "curriculum_words", "knowledge_point_contents",
    # KP-First 知识图谱
    "knowledge_nodes", "knowledge_node_aliases", "knowledge_node_relations",
    "kp_candidates", "unit_node", "node_resource", "pending_kp_content",
    # 题库
    "ai_questions", "simulated_questions", "platform_question", "platform_question_kp",
    "uploaded_question", "uploaded_question_kp", "passage",
    "exam_papers", "exam_questions", "exam_question_knowledge_points",
    # 词力通内容
    "vocabulary_words", "vocab_node", "vocab_list", "vocab_list_item",
    "vocab_question", "vocab_wrong", "vocab_pron_logs", "vocab_media",
    # 长难句
    "long_sentence", "long_sentence_node",
    # 学生进度 / 掌握 / 错题 / 词学习
    "student_kp_mastery", "student_kp", "kp_mastery_snapshots", "answer_log",
    "wrong_record", "wrong_questions", "wrong_question_knowledge_points",
    "vocabulary_learning", "student_vocab_candidates", "student_vocab_settings",
    # 进度/会话头表 + 教师测试内容(只挂 users/classes,不挂内容外键 → 显式列出)
    "user_uploaded_papers", "sim_exam_sessions", "study_checkins", "speaking_sessions",
    "listening_records", "listening_shadow_weak", "listening_wrong_questions",
    "assignments", "assignment_submissions", "class_papers",
}

# ── 护栏:闭包一旦触及这些"保留体系",立即中止 ───────────────────────────────────
KEEP_GUARD = {
    "users", "orders", "refunds", "invoices", "payment_accounts", "branch_companies",
    "institutions", "institution_purchases", "activation_codes", "teachers",
    "teacher_students", "classes", "class_students", "entitlements", "memberships",
}


async def _existing_tables(s) -> set[str]:
    return set((await s.execute(text(
        "SELECT tablename FROM pg_tables WHERE schemaname='public'"))).scalars().all())


async def _fk_pairs(s) -> list[tuple[str, str]]:
    return [(c, p) for c, p in (await s.execute(text("""
        SELECT tc.table_name AS child, ccu.table_name AS parent
        FROM information_schema.table_constraints tc
        JOIN information_schema.constraint_column_usage ccu
          ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema
        WHERE tc.constraint_type='FOREIGN KEY' AND tc.table_schema='public'
    """))).all()]


def _closure(seed: set[str], fks: list[tuple[str, str]]) -> set[str]:
    refmap: dict[str, set[str]] = {}
    for child, parent in fks:
        refmap.setdefault(parent, set()).add(child)
    closure, frontier = set(seed), set(seed)
    while frontier:
        nxt: set[str] = set()
        for p in frontier:
            for c in refmap.get(p, ()):
                if c not in closure:
                    closure.add(c)
                    nxt.add(c)
        frontier = nxt
    return closure


async def main() -> None:
    ap = argparse.ArgumentParser(description="上线前清库(内容+进度,留用户)")
    ap.add_argument("--execute", action="store_true", help="真清(默认仅 dry-run)")
    args = ap.parse_args()

    db_url = settings.database_url or ""
    host = db_url.split("@")[-1].split("/")[0] if "@" in db_url else "?"

    async with _async_session_factory() as s:
        existing = await _existing_tables(s)
        fks = await _fk_pairs(s)
        closure = sorted(t for t in _closure(SEED, fks) if t in existing)

        hit = sorted(set(closure) & KEEP_GUARD)
        if hit:
            print(f"⛔ 中止:级联闭包触及保留表 {hit};请检查 FK / 调整种子。")
            return

        counts = {}
        for t in closure:
            counts[t] = (await s.execute(text(f'SELECT count(*) FROM "{t}"'))).scalar()

    print(f"目标库主机: {host}")
    print(f"将清空 {len(closure)} 张表(内容+进度,保留 users/订单/机构/教师):\n")
    for t in closure:
        print(f"  {counts[t]:>8}  {t}")
    total = sum(counts.values())
    print(f"\n合计 {total} 行。保留体系(users/orders/机构/班级/教师等)不动。")

    if not args.execute:
        print("\n[dry-run] 未写库。确认无误后加 --execute 执行。")
        return

    print(f"\n⚠️  即将 TRUNCATE 上述 {len(closure)} 张表(主机 {host})。输入 YES 继续:")
    if input().strip() != "YES":
        print("已取消。")
        return

    async with _async_session_factory() as s:
        tbls = ", ".join(f'"{t}"' for t in closure)
        await s.execute(text(f"TRUNCATE {tbls} RESTART IDENTITY CASCADE"))
        await s.commit()
    print(f"✅ 已清空 {len(closure)} 张表。可重新上传真实教材/词库。")


if __name__ == "__main__":
    asyncio.run(main())
