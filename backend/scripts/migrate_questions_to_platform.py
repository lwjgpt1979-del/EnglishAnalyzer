"""R2.4 历史题迁移:exam_questions / simulated_questions → platform_question。

- exam_questions → platform_question(type='real'),meta.legacy_exam_question_id 记溯源(幂等键);
  exam_question_knowledge_points(旧 KP 名)→ 经 node_alias 归一映射 → platform_question_kp(命中);
  未命中只计数(迁移=映射,不在此造候选)。
- simulated_questions → platform_question(type='sim'):
  · 有 source_exam_question_id 且其真题已迁 → parent_real_id 映射、is_fallback=false;
  · 无母题历史仿真 → is_fallback=true(标记不丢,符合铁律 CHECK)。
  其 knowledge_point_id(旧 1:1)同样映射挂 node。
**幂等**:按 meta 溯源键跳过已迁;**不动旧表**。

用法:
  python backend/scripts/migrate_questions_to_platform.py --dry-run
  python backend/scripts/migrate_questions_to_platform.py
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.database import _async_session_factory  # noqa: E402
from app.models.d4_knowledge import KnowledgePoint  # noqa: E402
from app.models.d12_v2_exams import (  # noqa: E402
    ExamQuestion, ExamQuestionKnowledgePoint, SimulatedQuestion,
)
from app.models.d15_knowledge_graph import NodeAlias  # noqa: E402
from app.models.d16_question_domain import PlatformQuestion, PlatformQuestionKp  # noqa: E402
from app.services.kp_normalize import normalize_kp_name  # noqa: E402


class Stats:
    def __init__(self) -> None:
        self.real = self.real_skip = 0
        self.sim_parent = self.sim_fallback = self.sim_skip = 0
        self.kp_edges = self.kp_miss = 0

    def report(self, dry: bool) -> None:
        tag = "[dry-run] 预计" if dry else "[done]"
        print(f"\n{tag}:")
        print(f"  真题→real        新建 {self.real} / 跳过(已迁) {self.real_skip}")
        print(f"  仿真→sim         派生(parent) {self.sim_parent} / 备选(fallback) {self.sim_fallback} / 跳过 {self.sim_skip}")
        print(f"  KP 边            挂 {self.kp_edges} / 未命中(旧名无对应节点) {self.kp_miss}")


async def _node_for_kp_name(db, alias_cache: dict, name: str | None) -> uuid.UUID | None:
    if not name:
        return None
    norm = normalize_kp_name(name)
    if norm in alias_cache:
        return alias_cache[norm]
    nid = (await db.execute(
        select(NodeAlias.node_id).where(NodeAlias.alias_norm == norm)
    )).scalar_one_or_none()
    alias_cache[norm] = nid
    return nid


async def migrate(dry: bool, only_exam_ids=None, only_sim_ids=None) -> Stats:
    st = Stats()
    alias_cache: dict = {}
    async with _async_session_factory() as db:
        # 预载已迁溯源键(幂等)
        migrated = (await db.execute(
            select(PlatformQuestion.meta).where(PlatformQuestion.meta.isnot(None))
        )).scalars().all()
        done_exam = {m.get("legacy_exam_question_id") for m in migrated if m}
        done_sim = {m.get("legacy_sim_id") for m in migrated if m}
        exam_to_real: dict[str, uuid.UUID] = {}

        # ── Pass A:exam_questions → real ──
        eq = select(ExamQuestion)
        if only_exam_ids is not None:
            eq = eq.where(ExamQuestion.id.in_(only_exam_ids))
        for q in (await db.execute(eq)).scalars().all():
            if str(q.id) in done_exam:
                st.real_skip += 1
                # 仍需 exam→real 映射供仿真 parent 解析
                rid = (await db.execute(
                    select(PlatformQuestion.id).where(
                        PlatformQuestion.meta["legacy_exam_question_id"].astext == str(q.id))
                )).scalar_one_or_none()
                if rid:
                    exam_to_real[str(q.id)] = rid
                continue
            new_id = uuid.uuid4()
            st.real += 1
            exam_to_real[str(q.id)] = new_id
            if not dry:
                db.add(PlatformQuestion(
                    id=new_id, type="real", question_no=q.question_no,
                    question_type=q.question_type, stem=q.stem, options=q.options,
                    answer=q.answer, explanation=q.explanation, difficulty=q.difficulty,
                    meta={"legacy_exam_question_id": str(q.id)}, status="published",
                ))
                await db.flush()
                # KP 边:exam_question_knowledge_points → 旧 KP 名 → node
                kp_names = (await db.execute(
                    select(KnowledgePoint.name)
                    .join(ExamQuestionKnowledgePoint,
                          ExamQuestionKnowledgePoint.knowledge_point_id == KnowledgePoint.id)
                    .where(ExamQuestionKnowledgePoint.exam_question_id == q.id)
                )).scalars().all()
                for nm in kp_names:
                    nid = await _node_for_kp_name(db, alias_cache, nm)
                    if nid:
                        db.add(PlatformQuestionKp(question_id=new_id, node_id=nid))
                        st.kp_edges += 1
                    else:
                        st.kp_miss += 1

        if not dry:
            await db.flush()

        # ── Pass B:simulated_questions → sim ──
        sq = select(SimulatedQuestion)
        if only_sim_ids is not None:
            sq = sq.where(SimulatedQuestion.id.in_(only_sim_ids))
        for s in (await db.execute(sq)).scalars().all():
            if str(s.id) in done_sim:
                st.sim_skip += 1
                continue
            parent = exam_to_real.get(str(s.source_exam_question_id)) if s.source_exam_question_id else None
            is_fallback = parent is None
            if parent is not None:
                st.sim_parent += 1
            else:
                st.sim_fallback += 1
            if dry:
                continue
            new_id = uuid.uuid4()
            db.add(PlatformQuestion(
                id=new_id, type="sim", parent_real_id=parent, is_fallback=is_fallback,
                question_type=s.question_type, stem=s.stem, options=s.options,
                answer=s.answer, explanation=s.explanation, difficulty=s.difficulty,
                meta={"legacy_sim_id": str(s.id)}, status=str(s.status or "draft"),
            ))
            await db.flush()
            # 旧 1:1 KP → node
            kp_name = (await db.execute(
                select(KnowledgePoint.name).where(KnowledgePoint.id == s.knowledge_point_id)
            )).scalar_one_or_none()
            nid = await _node_for_kp_name(db, alias_cache, kp_name)
            if nid:
                db.add(PlatformQuestionKp(question_id=new_id, node_id=nid))
                st.kp_edges += 1
            elif kp_name:
                st.kp_miss += 1

        if dry:
            await db.rollback()
        else:
            await db.commit()
    return st


def main() -> None:
    ap = argparse.ArgumentParser(description="R2.4 历史题迁移 → platform_question")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    st = asyncio.run(migrate(args.dry_run))
    st.report(args.dry_run)


if __name__ == "__main__":
    main()
