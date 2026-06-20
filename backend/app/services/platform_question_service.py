"""R2 平台题(真题/仿真)写入与生成。

统一进 platform_question(type=real|sim),小题挂 knowledge_nodes(走 kp_match_service)。
仿真**强制有源**(parent_real_id 派生 / is_fallback 备选,DB CHECK 兜底,见 m85)。

R2.1:真题导入 import_real_question + 挂 KP(继承/匹配)骨架 + 低层 add_sim(强校验)。
R2.2/R2.3:AI 改写派生仿真 / KP 直生备选 + 真题到来下架备选。
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d15_knowledge_graph import KnowledgeNode
from app.models.d16_question_domain import PlatformQuestion, PlatformQuestionKp, Passage
from app.services.kp_match_service import match_kp
from app.services.llm_provider import chat_completion, is_llm_dev_mode

_log = logging.getLogger(__name__)


@dataclass
class ImportResult:
    question_id: uuid.UUID
    matched_nodes: list[uuid.UUID] = field(default_factory=list)
    candidates: list[uuid.UUID] = field(default_factory=list)


async def create_passage(db: AsyncSession, *, text: str, kind: str = "reading_text") -> uuid.UUID:
    """新建一份题组语料(平台域),返回 passage.id;供阅读/完形/信息还原题组挂 block_id。"""
    p = Passage(id=uuid.uuid4(), scope="platform", kind=kind, text=text)
    db.add(p)
    await db.flush()
    return p.id


async def passages_for(
    db: AsyncSession, block_ids: list[uuid.UUID]
) -> dict[uuid.UUID, str | None]:
    """批量取题组短文正文 {passage_id: text}，供列表按 block_id 聚合显示。"""
    ids = list({b for b in block_ids if b})
    if not ids:
        return {}
    rows = (await db.execute(
        sa.select(Passage.id, Passage.text).where(Passage.id.in_(ids))
    )).all()
    return {pid: text for pid, text in rows}


async def attach_node(db: AsyncSession, question_id: uuid.UUID, node_id: uuid.UUID) -> bool:
    """platform_question_kp 挂边(幂等)。返回是否新建。"""
    stmt = (
        pg_insert(PlatformQuestionKp)
        .values(question_id=question_id, node_id=node_id)
        .on_conflict_do_nothing(index_elements=["question_id", "node_id"])
        .returning(PlatformQuestionKp.question_id)
    )
    return (await db.execute(stmt)).scalar_one_or_none() is not None


async def _node_ids_of(db: AsyncSession, question_id: uuid.UUID) -> list[uuid.UUID]:
    return list((await db.execute(
        sa.select(PlatformQuestionKp.node_id).where(PlatformQuestionKp.question_id == question_id)
    )).scalars().all())


async def import_real_question(
    db: AsyncSession, *,
    stem: str, answer: str | None = None, options: dict | list | None = None,
    question_type: str | None = None, explanation: str | None = None,
    difficulty: int | None = None, meta: dict | None = None,
    kp_names: list[str] | None = None, stage_hint: str | None = None,
    question_no: str | None = None, status: str = "published",
    block_id: uuid.UUID | None = None,
) -> ImportResult:
    """导入一道真题 → platform_question(type='real'),kp_names 走受控匹配挂 node/落候选。

    命中某 node 后调 deprecate_fallbacks_for_node:该 node 有真题了 → 其 KP 直生备选下架(决策④)。
    block_id:题组短文(passage)外键,阅读/完形/信息还原的同篇小问共享。
    """
    q = PlatformQuestion(
        id=uuid.uuid4(), type="real", question_no=question_no, block_id=block_id,
        question_type=question_type, stem=stem, options=options, answer=answer,
        explanation=explanation, difficulty=difficulty, meta=meta, status=status,
    )
    db.add(q)
    await db.flush()

    res = ImportResult(question_id=q.id)
    for name in (kp_names or []):
        if not name or not name.strip():
            continue
        m = await match_kp(db, raw_name=name, axis_hint="knowledge",
                           stage_hint=stage_hint, source_type="exam")
        if m.node_id is not None:
            await attach_node(db, q.id, m.node_id)
            res.matched_nodes.append(m.node_id)
            await deprecate_fallbacks_for_node(db, node_id=m.node_id)
        elif m.candidate_id is not None:
            res.candidates.append(m.candidate_id)
    return res


async def add_sim(
    db: AsyncSession, *,
    stem: str, parent_real_id: uuid.UUID | None = None, is_fallback: bool = False,
    answer: str | None = None, options: dict | list | None = None,
    question_type: str | None = None, explanation: str | None = None,
    difficulty: int | None = None, status: str = "draft",
) -> PlatformQuestion:
    """低层仿真写入,落地铁律:必须 parent_real_id 或 is_fallback,否则拒绝(应用层先于 DB CHECK)。"""
    if parent_real_id is None and not is_fallback:
        raise AppError(code=400, message="仿真题必须有源:派生真题(parent_real_id)或显式备选(is_fallback)")
    q = PlatformQuestion(
        id=uuid.uuid4(), type="sim", parent_real_id=parent_real_id, is_fallback=is_fallback,
        question_type=question_type, stem=stem, options=options, answer=answer,
        explanation=explanation, difficulty=difficulty, status=status,
    )
    db.add(q)
    await db.flush()
    return q


async def list_platform_questions(
    db: AsyncSession, *, type: str | None = None, status: str | None = None,
    node_id: uuid.UUID | None = None, skip: int = 0, limit: int = 20,
) -> tuple[list[PlatformQuestion], int]:
    """平台题分页查询(运营审核/查看)。可按 type/status/node 过滤。"""
    base = sa.select(PlatformQuestion)
    if node_id is not None:
        base = base.join(PlatformQuestionKp,
                         PlatformQuestionKp.question_id == PlatformQuestion.id
                         ).where(PlatformQuestionKp.node_id == node_id)
    if type is not None:
        base = base.where(PlatformQuestion.type == type)
    if status is not None:
        base = base.where(PlatformQuestion.status == status)
    total = (await db.execute(
        sa.select(sa.func.count()).select_from(base.subquery())
    )).scalar_one()
    rows = (await db.execute(
        base.order_by(PlatformQuestion.created_at).offset(skip).limit(limit)
    )).scalars().all()
    return list(rows), total


async def review_platform_question(
    db: AsyncSession, *, question_id: uuid.UUID, approve: bool
) -> PlatformQuestion:
    """审核平台题:approve→published,reject→retired。"""
    q = (await db.execute(
        sa.select(PlatformQuestion).where(PlatformQuestion.id == question_id)
    )).scalar_one_or_none()
    if q is None:
        raise AppError(code=404, message="平台题不存在")
    q.status = "published" if approve else "retired"
    await db.flush()
    return q


async def _rewrite_variants(real: PlatformQuestion, count: int) -> list[dict]:
    """真题 → count 道仿真变式。dev mock 确定性;生产走 LLM 改写(保持题型/难度/考点)。"""
    if is_llm_dev_mode():
        return [{
            "stem": f"{real.stem}(变式{i + 1})",
            "options": real.options, "answer": real.answer,
            "explanation": real.explanation,
        } for i in range(count)]
    system = (
        "你是英语命题专家。基于给定母题改写出同考点、同题型、同难度的新题,"
        "保持考查点不变、情境/数据不同。严格输出 JSON。"
    )
    user = (
        f"母题题干:{real.stem}\n题型:{real.question_type}\n选项:{json.dumps(real.options, ensure_ascii=False)}\n"
        f"答案:{real.answer}\n\n生成 {count} 道仿真题,返回 "
        '{"items":[{"stem":..,"options":..,"answer":..,"explanation":..}, ...]}'
    )
    try:
        resp = await chat_completion(system_prompt=system, user_prompt=user,
                                     max_tokens=2048, response_format={"type": "json_object"})
        items = json.loads(resp.choices[0].message.content or "{}").get("items", [])
        return items[:count]
    except Exception as exc:  # noqa: BLE001
        _log.warning("sim rewrite LLM failed (real=%s): %s", real.id, exc)
        return []


async def generate_sim_from_real(
    db: AsyncSession, *, real_id: uuid.UUID, count: int = 3, status: str = "draft"
) -> list[uuid.UUID]:
    """由真题派生 count 道仿真(parent_real_id=real_id),**继承母题 KP**(决策④-C 甲)。"""
    real = (await db.execute(
        sa.select(PlatformQuestion).where(PlatformQuestion.id == real_id)
    )).scalar_one_or_none()
    if real is None or real.type != "real":
        raise AppError(code=404, message="母题真题不存在")
    parent_nodes = await _node_ids_of(db, real_id)

    out: list[uuid.UUID] = []
    for v in await _rewrite_variants(real, count):
        if not v.get("stem"):
            continue
        sim = await add_sim(
            db, stem=v["stem"], parent_real_id=real_id, is_fallback=False,
            answer=v.get("answer"), options=v.get("options"),
            question_type=real.question_type, explanation=v.get("explanation"),
            difficulty=real.difficulty, status=status,
        )
        for nid in parent_nodes:   # 继承母题 KP
            await attach_node(db, sim.id, nid)
        out.append(sim.id)
    return out


async def has_real_for_node(db: AsyncSession, node_id: uuid.UUID) -> bool:
    """该 node 是否已有真题母题(决定能否启用真题派生 / 是否该下架备选)。"""
    row = (await db.execute(
        sa.select(PlatformQuestion.id)
        .join(PlatformQuestionKp, PlatformQuestionKp.question_id == PlatformQuestion.id)
        .where(PlatformQuestionKp.node_id == node_id, PlatformQuestion.type == "real")
        .limit(1)
    )).first()
    return row is not None


async def generate_fallback_sim(
    db: AsyncSession, *, node_id: uuid.UUID, count: int = 3, status: str = "draft"
) -> list[uuid.UUID]:
    """KP 直生备选(决策④):某 node 暂无真题母题 → 生成 is_fallback=true 备选,挂该 node。

    若该 node 已有真题 → 不生成备选(应走真题派生),返回空。
    """
    if await has_real_for_node(db, node_id):
        return []
    node_name = (await db.execute(
        sa.select(KnowledgeNode.name).where(KnowledgeNode.id == node_id)
    )).scalar_one_or_none()
    out: list[uuid.UUID] = []
    for i in range(count):
        sim = await add_sim(
            db, stem=f"[备选] {node_name or 'KP'} 练习题{i + 1}", is_fallback=True,
            question_type="单选", status=status,
        )
        await attach_node(db, sim.id, node_id)
        out.append(sim.id)
    return out


async def deprecate_fallbacks_for_node(db: AsyncSession, *, node_id: uuid.UUID) -> int:
    """某 node 有真题母题后,把该 node 上的 KP 直生备选(is_fallback,未下架)置 deprecated_at。

    返回下架数量。R2.1 提供;真正有 fallback 数据在 R2.3。
    """
    rows = (await db.execute(
        sa.select(PlatformQuestion.id)
        .join(PlatformQuestionKp, PlatformQuestionKp.question_id == PlatformQuestion.id)
        .where(PlatformQuestionKp.node_id == node_id,
               PlatformQuestion.type == "sim",
               PlatformQuestion.is_fallback.is_(True),
               PlatformQuestion.deprecated_at.is_(None))
    )).scalars().all()
    if not rows:
        return 0
    await db.execute(
        sa.update(PlatformQuestion)
        .where(PlatformQuestion.id.in_(rows))
        .values(deprecated_at=sa.func.now(), status="retired")
    )
    return len(rows)
