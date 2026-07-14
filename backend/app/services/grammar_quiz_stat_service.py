"""长难句语法提问式选择——正确率统计(以往至今累计,按学生×语法点)。

- record:每答一题累加 total、答对累加 correct(按 gp_key 幂等 upsert)。
- accuracy:批量取一组语法点的历史正确率,供学习页「考查完统计正确率」。
gp_key:匹配到语法节点则用 str(node_id),否则 'name:'+归一名——保证跨句稳定累计。
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d20_long_sentence import StudentGrammarQuizStat as Stat


async def record(db: AsyncSession, *, student_id: uuid.UUID, gp_key: str, label: str,
                 correct: bool, node_id: uuid.UUID | None = None) -> dict:
    """记一次作答:total+1,答对 correct+1。返回该语法点累计 {correct,total}。"""
    stmt = (
        pg_insert(Stat)
        .values(id=uuid.uuid4(), student_id=student_id, gp_key=gp_key[:64], node_id=node_id,
                label=label[:120], correct=(1 if correct else 0), total=1)
        .on_conflict_do_update(
            constraint="uq_grammar_quiz_stat_student_gp",
            set_={"correct": Stat.correct + (1 if correct else 0),
                  "total": Stat.total + 1, "label": label[:120],
                  "node_id": node_id, "updated_at": sa.func.now()})
    )
    await db.execute(stmt)
    await db.commit()
    row = (await db.execute(sa.select(Stat.correct, Stat.total).where(
        Stat.student_id == student_id, Stat.gp_key == gp_key[:64]))).first()
    return {"correct": int(row.correct), "total": int(row.total)} if row else {"correct": 0, "total": 0}


async def accuracy(db: AsyncSession, *, student_id: uuid.UUID,
                   gp_keys: list[str]) -> dict[str, dict]:
    """批量取历史累计 {gp_key: {correct, total}}(未作答过的键不在返回里)。"""
    if not gp_keys:
        return {}
    rows = (await db.execute(sa.select(Stat.gp_key, Stat.correct, Stat.total).where(
        Stat.student_id == student_id, Stat.gp_key.in_([k[:64] for k in gp_keys])))).all()
    return {k: {"correct": int(c), "total": int(t)} for k, c, t in rows}
