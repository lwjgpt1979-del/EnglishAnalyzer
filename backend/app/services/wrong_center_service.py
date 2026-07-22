"""R3 统一错题中心(KP-First):各渠道做错 → 收口写 wrong_record(指题 + 定位 node)。

wrong_record 是错题**事件**(不是题):指向 platform/uploaded 题 + node_id 定位 KP。
单一收口入口 record_wrong,各渠道(练习做错/整卷错题/单题/复习再错)统一调用。
承接 SM-2 复习(字段见 m86)。旧 wrong_questions 并存供 OCR/诊断富字段。
"""
from __future__ import annotations

import datetime as _dt
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d16_question_domain import WrongRecord


def _source_cond(source_label: str | list[str] | None):
    """来源过滤:支持单值 / 逗号分隔 / 列表(一个 tab 可合并多来源,如「作业错题」= 整卷 + 作业)。"""
    if not source_label:
        return None
    labels = source_label if isinstance(source_label, list) else [s for s in str(source_label).split(",") if s]
    if not labels:
        return None
    return WrongRecord.source_label == labels[0] if len(labels) == 1 else WrongRecord.source_label.in_(labels)


async def record_wrong(
    db: AsyncSession, *, student_id: uuid.UUID, q_scope: str, question_id: uuid.UUID,
    node_id: uuid.UUID | None = None, is_original: bool = True,
    today: _dt.date | None = None,
    stem: str | None = None, student_answer: str | None = None,
    correct_answer: str | None = None, explanation: str | None = None,
    question_type: str | None = None, kp_kind: str | None = None,
    kp_name: str | None = None, source_label: str | None = None,
    source_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """收口:某题做错 → upsert wrong_record。

    新建:status=open,next_review_at=今日(立即入复习队列)。
    复发(已存在,含已 mastered):重置 status=open、清 mastered_at、SM-2 归零、今日重排。
    q_scope ∈ {platform, uploaded}。返回 wrong_record id。
    冗余题面(stem/答案/解析/kp_kind/source_label 等)随写,「我的错题」只读本表即可自洽。
    """
    today = today or _dt.date.today()
    stmt = (
        pg_insert(WrongRecord)
        .values(
            id=uuid.uuid4(), student_id=student_id, q_scope=q_scope,
            question_id=question_id, node_id=node_id, is_original=is_original,
            status="open", next_review_at=today,
            stem=stem, student_answer=student_answer, correct_answer=correct_answer,
            explanation=explanation, question_type=question_type, kp_kind=kp_kind,
            kp_name=kp_name, source_label=source_label, source_id=source_id,
        )
        .on_conflict_do_update(
            constraint="uix_wrong_record_identity",
            set_={
                "status": "open", "mastered_at": None, "mastery_source": None,
                "review_count": 0, "review_interval_days": 1,
                "next_review_at": today,
                # node_id 及题面命中更新(保留已有非空)
                "node_id": sa.func.coalesce(sa.text("EXCLUDED.node_id"), WrongRecord.node_id),
                "stem": sa.func.coalesce(sa.text("EXCLUDED.stem"), WrongRecord.stem),
                "student_answer": sa.func.coalesce(sa.text("EXCLUDED.student_answer"), WrongRecord.student_answer),
                "correct_answer": sa.func.coalesce(sa.text("EXCLUDED.correct_answer"), WrongRecord.correct_answer),
                "explanation": sa.func.coalesce(sa.text("EXCLUDED.explanation"), WrongRecord.explanation),
                "question_type": sa.func.coalesce(sa.text("EXCLUDED.question_type"), WrongRecord.question_type),
                "kp_kind": sa.func.coalesce(sa.text("EXCLUDED.kp_kind"), WrongRecord.kp_kind),
                "kp_name": sa.func.coalesce(sa.text("EXCLUDED.kp_name"), WrongRecord.kp_name),
                "source_label": sa.func.coalesce(sa.text("EXCLUDED.source_label"), WrongRecord.source_label),
                "source_id": sa.func.coalesce(sa.text("EXCLUDED.source_id"), WrongRecord.source_id),
            },
        )
        .returning(WrongRecord.id)
    )
    wid = (await db.execute(stmt)).scalar_one()
    # R4:错题命中 → 个人图谱来源追加 'wrong_hit'(并入 in_scope)
    if node_id is not None:
        from app.services import student_graph_service
        await student_graph_service.add_source(
            db, student_id=student_id, node_id=node_id, tag="wrong_hit", in_scope=True)
    return wid


# ============ 练习衍生错题(打标隔离,is_original=false,q_scope='kp')============
# ①错题网·考点扩展测试 + ③词力通·考点扩展测试的逐维错误。按 (word, dim) 去重,连对 N 次即掌握清除。
# ②练同类仿真题不走这里(维持 record_practice_result 推父错题 SM-2)。

_KP_PRACTICE_NS = uuid.UUID("a7f1e2c3-4b5d-4e6f-8a90-112233445566")  # (word,dim) → 确定性 question_id 的命名空间
_KP_PRACTICE_SOURCE = "练习巩固"
_KP_PRACTICE_MASTER_N = 2   # 连对达标 → status=mastered,移出「练习巩固」(决策3)


def kp_practice_qid(word_id: uuid.UUID, dim: str) -> uuid.UUID:
    """(word, dim) 的确定性 question_id(决策1b):命中现有唯一键 (student,q_scope,question_id) 天然去重。"""
    return uuid.uuid5(_KP_PRACTICE_NS, f"{word_id}:{dim}")


async def record_kp_practice(
    db: AsyncSession, *, student_id: uuid.UUID, word_id: uuid.UUID, word: str,
    dim: str, dim_label: str, correct: bool, missed_desc: str | None = None,
) -> dict:
    """考点扩展测试逐维结果落库(练习衍生):
    错 → upsert 一条 (word,dim) 练习衍生错题、practice_streak 归 0、practice_count(错次)+1、status=open;
    对 → 命中 open 记录则 practice_streak+1,≥N 置 mastered(移出练习巩固);无记录则忽略(不为"对"建记录)。
    """
    qid = kp_practice_qid(word_id, dim)
    existing = (await db.execute(sa.select(WrongRecord).where(
        WrongRecord.student_id == student_id, WrongRecord.q_scope == "kp",
        WrongRecord.question_id == qid))).scalar_one_or_none()

    if correct:
        if existing is None or existing.status != "open":
            return {"changed": False}
        existing.practice_streak = (existing.practice_streak or 0) + 1
        mastered = existing.practice_streak >= _KP_PRACTICE_MASTER_N
        if mastered:
            existing.status = "mastered"
            existing.mastered_at = _dt.datetime.now(_dt.timezone.utc)
            existing.mastery_source = "auto"
        await db.flush()
        return {"changed": True, "streak": existing.practice_streak, "mastered": mastered}

    # 答错:upsert 练习衍生错题(不进 SM-2 队列 → next_review_at 保持 NULL)
    kp_name = f"{word}·{dim_label}"
    stmt = (
        pg_insert(WrongRecord)
        .values(
            id=uuid.uuid4(), student_id=student_id, q_scope="kp", question_id=qid,
            is_original=False, status="open", next_review_at=None,
            vocab_word_id=word_id, dim=dim, kp_kind="vocab", kp_name=kp_name,
            source_label=_KP_PRACTICE_SOURCE, stem=missed_desc,
            practice_count=1, practice_streak=0,
        )
        .on_conflict_do_update(
            constraint="uix_wrong_record_identity",
            set_={
                "status": "open", "mastered_at": None, "mastery_source": None,
                "practice_streak": 0,
                "practice_count": WrongRecord.practice_count + 1,
                "dim": dim, "vocab_word_id": word_id, "kp_kind": "vocab",
                "kp_name": kp_name, "source_label": _KP_PRACTICE_SOURCE,
                "stem": sa.func.coalesce(sa.text("EXCLUDED.stem"), WrongRecord.stem),
            },
        )
        .returning(WrongRecord.id)
    )
    wid = (await db.execute(stmt)).scalar_one()
    await db.flush()
    return {"changed": True, "wrong_record_id": str(wid), "streak": 0, "mastered": False}


# ============ 长难句练习衍生错题(句·维,is_original=false,q_scope='ls')============
# 认成分/认语法/重点词/理解 探针答错 → 按 (句, 维) 落库。成分/理解=整句维,语法/重点词=单项维(展示层区分)。
# 连对 N 次清除,规则同词·维。source_label='长难句薄弱' 独占「长难句薄弱」tab。

_LS_PRACTICE_NS = uuid.UUID("b8e2f3d4-5c6e-4f70-9b01-223344556677")   # (sentence_md5,dim) → question_id
_LS_SENT_NS = uuid.UUID("c9f3a4e5-6d7f-4081-ac12-334455667788")       # sentence_md5 → 句分组键 source_id
_LS_SOURCE = "长难句薄弱"
_LS_DIM_LABEL = {"component": "成分", "comprehension": "理解", "grammar": "语法", "keyword": "重点词"}


def _sent_md5(sentence: str) -> str:
    import hashlib
    return hashlib.md5((sentence or "").strip().encode("utf-8")).hexdigest()


def ls_practice_qid(sentence_md5: str, dim: str) -> uuid.UUID:
    return uuid.uuid5(_LS_PRACTICE_NS, f"{sentence_md5}:{dim}")


def ls_sentence_key(sentence_md5: str) -> uuid.UUID:
    return uuid.uuid5(_LS_SENT_NS, sentence_md5)


async def record_ls_practice(
    db: AsyncSession, *, student_id: uuid.UUID, sentence: str, dim: str,
    correct: bool, missed_desc: str | None = None, ref_id: uuid.UUID | None = None,
) -> dict:
    """长难句探针逐维结果落库(练习衍生):dim ∈ {component,comprehension,grammar,keyword}。
    错 → upsert 一条 (句,维);对 → 命中 open 记录 streak+1,≥N 掌握清除。句分组键存 source_id。
    ref_id(理解维=LongSentence.id)存 vocab_word_id,供「重做整句理解」深链回理解检测页。"""
    md5 = _sent_md5(sentence)
    qid = ls_practice_qid(md5, dim)
    existing = (await db.execute(sa.select(WrongRecord).where(
        WrongRecord.student_id == student_id, WrongRecord.q_scope == "ls",
        WrongRecord.question_id == qid))).scalar_one_or_none()

    if correct:
        if existing is None or existing.status != "open":
            return {"changed": False}
        existing.practice_streak = (existing.practice_streak or 0) + 1
        mastered = existing.practice_streak >= _KP_PRACTICE_MASTER_N
        if mastered:
            existing.status = "mastered"
            existing.mastered_at = _dt.datetime.now(_dt.timezone.utc)
            existing.mastery_source = "auto"
        await db.flush()
        return {"changed": True, "streak": existing.practice_streak, "mastered": mastered}

    kp_name = f"{_LS_DIM_LABEL.get(dim, dim)}"
    stmt = (
        pg_insert(WrongRecord)
        .values(
            id=uuid.uuid4(), student_id=student_id, q_scope="ls", question_id=qid,
            is_original=False, status="open", next_review_at=None,
            source_id=ls_sentence_key(md5), dim=dim, kp_name=kp_name,
            source_label=_LS_SOURCE, stem=(sentence or "").strip()[:600],
            vocab_word_id=ref_id, practice_count=1, practice_streak=0,
        )
        .on_conflict_do_update(
            constraint="uix_wrong_record_identity",
            set_={
                "status": "open", "mastered_at": None, "mastery_source": None,
                "practice_streak": 0,
                "practice_count": WrongRecord.practice_count + 1,
                "dim": dim, "kp_name": kp_name, "source_label": _LS_SOURCE,
                "source_id": ls_sentence_key(md5),
                "vocab_word_id": sa.func.coalesce(sa.text("EXCLUDED.vocab_word_id"), WrongRecord.vocab_word_id),
                "stem": sa.func.coalesce(WrongRecord.stem, sa.text("EXCLUDED.stem")),
            },
        )
        .returning(WrongRecord.id)
    )
    wid = (await db.execute(stmt)).scalar_one()
    await db.flush()
    return {"changed": True, "wrong_record_id": str(wid), "streak": 0, "mastered": False}


# 维展示分区:整句维(整体判断,重做整句) vs 单项维(可单练)
_LS_WHOLE_DIMS = ("component", "comprehension")


async def list_ls_consolidation(db: AsyncSession, *, student_id: uuid.UUID) -> list[dict]:
    """「长难句薄弱」tab:练习衍生句卡,按句(source_id)聚合 → [{sentence, dims:[{dim,dim_label,whole,miss,streak}]}]。"""
    rows = list((await db.execute(
        sa.select(WrongRecord).where(
            WrongRecord.student_id == student_id, WrongRecord.q_scope == "ls",
            WrongRecord.status == "open")
        .order_by(WrongRecord.created_at.desc()))).scalars().all())
    by_sent: dict = {}
    for r in rows:
        g = by_sent.setdefault(str(r.source_id), {"source_id": str(r.source_id), "sentence": r.stem or "", "dims": []})
        dim = r.dim or ""
        g["dims"].append({
            "id": str(r.id), "dim": dim, "dim_label": _LS_DIM_LABEL.get(dim, dim),
            "whole": dim in _LS_WHOLE_DIMS, "miss_count": r.practice_count or 0,
            "streak": r.practice_streak or 0, "master_n": _KP_PRACTICE_MASTER_N,
            "ref_id": str(r.vocab_word_id) if r.vocab_word_id else None})
    _order = {"component": 0, "comprehension": 1, "grammar": 2, "keyword": 3}
    out = []
    for g in by_sent.values():
        g["dims"].sort(key=lambda d: _order.get(d["dim"], 9))
        g["miss_total"] = sum(d["miss_count"] for d in g["dims"])
        out.append(g)
    return out


async def list_open_wrongs(
    db: AsyncSession, *, student_id: uuid.UUID, node_id: uuid.UUID | None = None,
    limit: int = 100,
) -> list[WrongRecord]:
    """未掌握错题(KP-First 视图);可按 node 过滤。"""
    stmt = sa.select(WrongRecord).where(
        WrongRecord.student_id == student_id, WrongRecord.status == "open"
    )
    if node_id is not None:
        stmt = stmt.where(WrongRecord.node_id == node_id)
    return list((await db.execute(
        stmt.order_by(WrongRecord.created_at.desc()).limit(limit)
    )).scalars().all())


# ── 错题三态生命周期(方案B)────────────────────────────────────────────────
# 待巩固(pending):open 且从未复习/练习;巩固中(reviewing):open 且已复习或已练同类;
# 已掌握(mastered):status=mastered。
def _lifecycle_of(r: "WrongRecord") -> str:
    if r.status == "mastered":
        return "mastered"
    if (r.review_count or 0) > 0 or (r.practice_count or 0) > 0:
        return "reviewing"
    return "pending"


def _status_filter(status: str | None):
    """把 chip 状态映射成 where 条件列表。None/all → 不过滤。"""
    if status == "pending":
        return [WrongRecord.status == "open", WrongRecord.review_count == 0,
                WrongRecord.practice_count == 0]
    if status == "reviewing":
        return [WrongRecord.status == "open",
                sa.or_(WrongRecord.review_count > 0, WrongRecord.practice_count > 0)]
    if status == "mastered":
        return [WrongRecord.status == "mastered"]
    return []


async def lifecycle_counts(
    db: AsyncSession, *, student_id: uuid.UUID, kind: str | None = None,
    source_label: str | None = None, is_original: bool | None = True,
) -> dict:
    """状态 chip 计数(不受分页/状态筛选影响;受 kind/来源/is_original 影响)。"""
    conds = [WrongRecord.student_id == student_id, WrongRecord.status != "skipped"]
    if is_original is not None:
        conds.append(WrongRecord.is_original.is_(is_original))
    _sc = _source_cond(source_label)
    if _sc is not None:
        conds.append(_sc)
    if kind in ("grammar", "vocab"):
        conds.append(WrongRecord.kp_kind == kind)
    rows = (await db.execute(
        sa.select(WrongRecord.status, WrongRecord.review_count, WrongRecord.practice_count)
        .where(*conds))).all()
    out = {"all": len(rows), "pending": 0, "reviewing": 0, "mastered": 0}
    for st, rc, pc in rows:
        if st == "mastered":
            out["mastered"] += 1
        elif (rc or 0) > 0 or (pc or 0) > 0:
            out["reviewing"] += 1
        else:
            out["pending"] += 1
    return out


async def list_center(
    db: AsyncSession, *, student_id: uuid.UUID, kind: str | None = None,
    status: str | None = None, source_label: str | None = None,
    kp_name: str | None = None, source_id: uuid.UUID | None = None,
    is_original: bool | None = True, skip: int = 0, limit: int = 20,
) -> tuple[list[dict], int]:
    """「我的错题」统一列表:只读 wrong_record(题面已冗余,自洽)。

    kind ∈ {None(全部), grammar, vocab}(副筛选);source_label = 来源 tab(作业|整卷|长难句|平台…);
    kp_name/source_id = 折叠卡展开某组时按考点名/批次过滤;
    is_original 默认 True(只列真实错题,练习衍生走 list_practice_consolidation);
    status ∈ {None(全部), pending, reviewing, mastered}。
    排序:未掌握在前、已掌握沉底(灰显折叠),各按 created_at 倒序。
    """
    base = sa.select(WrongRecord).where(
        WrongRecord.student_id == student_id, WrongRecord.status != "skipped")
    if is_original is not None:
        base = base.where(WrongRecord.is_original.is_(is_original))
    _sc = _source_cond(source_label)
    if _sc is not None:
        base = base.where(_sc)
    if kp_name:
        base = base.where(sa.func.coalesce(WrongRecord.kp_name, "未分类") == kp_name)
    if source_id is not None:
        base = base.where(WrongRecord.source_id == source_id)
    if kind in ("grammar", "vocab"):
        base = base.where(WrongRecord.kp_kind == kind)
    for c in _status_filter(status):
        base = base.where(c)
    total = (await db.execute(
        sa.select(sa.func.count()).select_from(base.subquery()))).scalar_one()
    # 已掌握沉底:先按 (status=mastered) 升序,再 created_at 倒序
    mastered_flag = sa.case((WrongRecord.status == "mastered", 1), else_=0)
    rows = list((await db.execute(
        base.order_by(mastered_flag.asc(), WrongRecord.created_at.desc())
        .offset(skip).limit(limit)
    )).scalars().all())
    items = [{
        "id": str(r.id), "question_id": str(r.question_id), "q_scope": r.q_scope,
        "node_id": str(r.node_id) if r.node_id else None,
        "stem": r.stem, "student_answer": r.student_answer,
        "correct_answer": r.correct_answer, "explanation": r.explanation,
        "question_type": r.question_type, "kp_kind": r.kp_kind, "kp_name": r.kp_name,
        "source_label": r.source_label or "错题",
        "source_id": str(r.source_id) if r.source_id else None,
        "source_route": _source_route(r.source_label, r.source_id),
        "is_mastered": r.status == "mastered",
        "lifecycle": _lifecycle_of(r),
        "review_count": r.review_count or 0,
        "practice_count": r.practice_count or 0,
        "practice_correct": r.practice_correct or 0,
        "next_review_at": r.next_review_at.isoformat() if r.next_review_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]
    return items, total


async def group_by_kp(
    db: AsyncSession, *, student_id: uuid.UUID, source_label: str | None = None,
    kind: str | None = None,
) -> list[dict]:
    """真实错题按考点(kp_name)聚合(A 视图):[{kp, node_id, count, mastered, rate}],错多的在前。"""
    grp = sa.func.coalesce(WrongRecord.kp_name, "未分类")
    mastered = sa.func.sum(sa.case((WrongRecord.status == "mastered", 1), else_=0))
    conds = [WrongRecord.student_id == student_id, WrongRecord.status != "skipped",
             WrongRecord.is_original.is_(True)]
    _sc = _source_cond(source_label)
    if _sc is not None:
        conds.append(_sc)
    if kind in ("grammar", "vocab"):
        conds.append(WrongRecord.kp_kind == kind)
    rows = (await db.execute(
        sa.select(grp.label("kp"), sa.func.count().label("cnt"), mastered.label("m"))
        .where(*conds).group_by(grp).order_by(sa.func.count().desc()))).all()
    return [{"kp": kp, "count": int(cnt), "mastered": int(m or 0),
             "rate": round((m or 0) / cnt, 2) if cnt else 0}
            for kp, cnt, m in rows]


async def group_by_batch(
    db: AsyncSession, *, student_id: uuid.UUID, source_label: str | None = None,
    kind: str | None = None,
) -> list[dict]:
    """真实错题按来源批次(source_id)聚合(B 视图):[{source_id, count, mastered, rate, last_at}],新批次在前。"""
    mastered = sa.func.sum(sa.case((WrongRecord.status == "mastered", 1), else_=0))
    conds = [WrongRecord.student_id == student_id, WrongRecord.status != "skipped",
             WrongRecord.is_original.is_(True), WrongRecord.source_id.isnot(None)]
    _sc = _source_cond(source_label)
    if _sc is not None:
        conds.append(_sc)
    if kind in ("grammar", "vocab"):
        conds.append(WrongRecord.kp_kind == kind)
    last_at = sa.func.max(WrongRecord.created_at)
    rows = (await db.execute(
        sa.select(WrongRecord.source_id, sa.func.count().label("cnt"), mastered.label("m"),
                  last_at.label("last_at"))
        .where(*conds).group_by(WrongRecord.source_id).order_by(last_at.desc()))).all()
    return [{"source_id": str(sid), "source_label": source_label, "count": int(cnt),
             "mastered": int(m or 0), "rate": round((m or 0) / cnt, 2) if cnt else 0,
             "last_at": la.isoformat() if la else None}
            for sid, cnt, m, la in rows]


async def list_practice_consolidation(
    db: AsyncSession, *, student_id: uuid.UUID,
) -> list[dict]:
    """「练习巩固」tab:练习衍生薄弱项(is_original=false, open),按 (词·维) 聚合(每 (word,dim) 一行)。
    含 词/维/错次(practice_count)/连对(practice_streak)。"""
    from app.models.d5_learning import VocabularyWord
    from app.services import word_kp_service
    rows = list((await db.execute(
        sa.select(WrongRecord).where(
            WrongRecord.student_id == student_id, WrongRecord.q_scope == "kp",
            WrongRecord.status == "open")
        .order_by(WrongRecord.practice_count.desc(), WrongRecord.created_at.desc()))).scalars().all())
    wmap: dict = {}
    wids = [r.vocab_word_id for r in rows if r.vocab_word_id]
    if wids:
        wmap = {wid: w for wid, w in (await db.execute(
            sa.select(VocabularyWord.id, VocabularyWord.word).where(VocabularyWord.id.in_(wids)))).all()}
    out = []
    for r in rows:
        dim = r.dim or ""
        word = wmap.get(r.vocab_word_id) or (r.kp_name or "").split("·")[0]
        out.append({
            "id": str(r.id), "word_id": str(r.vocab_word_id) if r.vocab_word_id else None,
            "word": word,
            "dim": dim, "dim_label": word_kp_service._dim_label(dim) if dim else "",
            "kp_name": r.kp_name, "stem": r.stem,
            "miss_count": r.practice_count or 0, "streak": r.practice_streak or 0,
            "master_n": _KP_PRACTICE_MASTER_N,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })
    return out


def _source_route(source_label: str | None, source_id: uuid.UUID | None) -> str | None:
    """错题来源实体的小程序路由(供「点来源→回到来源→再返回」)。无可跳目标返回 None。"""
    if source_id is None:
        return None
    # 学生上传的卷子(user_paper)= 「作业错题」,回卷详情;"整卷" 为历史别名(已洗为"作业",保留兜底)
    if source_label in ("作业", "整卷"):
        return f"/pages/user-papers/detail?id={source_id}"
    return None


async def record_practice_result(
    db: AsyncSession, *, student_id: uuid.UUID, wrong_record_id: uuid.UUID,
    total: int, correct: int, advance_review: bool = False,
) -> dict:
    """练同类一轮做完 → 记 practice_count/correct(待巩固→巩固中);
    语法错题按正确率推进 SM-2(可达标判掌握);词汇仅记数(掌握判定留 P3 词力通)。

    advance_review=True(复习页对「无选项原卷题」以练同类代替客观重做时传)→ 不限 grammar,
    一律按本轮正确率推进 SM-2,让该错题离开今日复习队列。"""
    from app.core.exceptions import AppError
    from app.services import wrong_review_service
    wr = await db.get(WrongRecord, wrong_record_id)
    if wr is None or wr.student_id != student_id:
        raise AppError(code=404, message="错题不存在或无权访问")
    total = max(0, int(total))
    correct = max(0, min(int(correct), total))
    wr.practice_count = (wr.practice_count or 0) + total
    wr.practice_correct = (wr.practice_correct or 0) + correct
    mastered = False
    if total > 0 and wr.status == "open" and (advance_review or wr.kp_kind == "grammar"):
        mastered = await wrong_review_service.advance_by_practice(
            db, wr=wr, accuracy=correct / total)
    await db.flush()
    return {
        "lifecycle": _lifecycle_of(wr),
        "is_mastered": wr.status == "mastered",
        "just_mastered": mastered,
        "practice_count": wr.practice_count,
        "practice_correct": wr.practice_correct,
        "review_count": wr.review_count or 0,
        "next_review_at": wr.next_review_at.isoformat() if wr.next_review_at else None,
    }


# ── 词汇错题 → 词力通双维闭环(P3)────────────────────────────────────────────
async def _resolve_vocab_word(db: AsyncSession, wr: "WrongRecord"):
    """定位这道词汇错题考查的目标词:优先 correct_answer 命中词库,否则题干里首个命中词。
    命中后缓存到 wr.vocab_word_id;进词力通统一错词本(is_wrong)。返回 VocabularyWord|None。"""
    from app.models.d5_learning import VocabularyWord
    from app.services.vocab_pin_service import _words_from_text
    if wr.vocab_word_id:
        return await db.get(VocabularyWord, wr.vocab_word_id)
    cands: list[str] = []
    if (wr.correct_answer or "").strip():
        cands.append(wr.correct_answer.strip())
    cands += _words_from_text(f"{wr.correct_answer or ''} {wr.stem or ''}")
    for c in cands:
        w = (await db.execute(sa.select(VocabularyWord).where(
            sa.func.lower(VocabularyWord.word) == c.lower()))).scalar_one_or_none()
        if w is not None:
            wr.vocab_word_id = w.id
            await db.flush()
            return w
    return None


async def _mark_vocab_word_mastered(db: AsyncSession, *, student_id: uuid.UUID, word_id: uuid.UUID) -> bool:
    """仿真练习 5 题全对 → 把该生指向此词的 open 词汇错题全部判掌握(source=vocab)、移出词力通错词本。返回是否有错题被判掌握。"""
    import datetime as _dt
    from app.services.vocab_probe_service import _get_or_create_learning
    lr = await _get_or_create_learning(db, student_id, word_id)
    lr.is_wrong = False   # 移出词力通统一错词本
    res = await db.execute(
        sa.update(WrongRecord)
        .where(WrongRecord.student_id == student_id, WrongRecord.vocab_word_id == word_id,
               WrongRecord.status == "open")
        .values(status="mastered", mastered_at=_dt.datetime.now(_dt.timezone.utc),
                mastery_source="vocab"))
    await db.flush()
    return (res.rowcount or 0) > 0


# ── 仿真练习 5 题:从该词全局缓存 probes_json + 词条字段拼装(纯选择题)──────────────
def _zh_of(word) -> str:
    defs = word.definitions if isinstance(word.definitions, list) else []
    for d in defs:
        if isinstance(d, dict):
            v = d.get("meaning") or d.get("zh") or d.get("en")   # 词条释义键为 meaning
            if v:
                return str(v)
    return ""


def _sentences_with(word, probes: dict) -> list[str]:
    """取含该词、长度适中的句子(例句 + 缓存兜底例句),去重保序。"""
    import re
    W = word.word
    pat = re.compile(rf"\b{re.escape(W)}\b", re.I)
    out: list[str] = []
    for ex in (word.examples or []):
        s = ex.get("en") if isinstance(ex, dict) else None
        if s and pat.search(s) and 3 <= len(s.split()) <= 40:
            out.append(s.strip())
    for c in (probes.get("cloze_fallback") or []):
        s = c.get("sentence") if isinstance(c, dict) else None
        if s and pat.search(s):
            out.append(s.strip())
    seen, res = set(), []
    for s in out:
        if s not in seen:
            seen.add(s); res.append(s)
    return res


def _mc(stem: str, correct: str, wrongs: list[str], explanation: str = "") -> dict:
    """组一道选择题:正确项 + 至多 3 个不重复干扰项,打乱。"""
    import random
    correct = (correct or "").strip()
    opts = [correct]
    for w in wrongs:
        w = (w or "").strip()
        if w and w.lower() != correct.lower() and w not in opts:
            opts.append(w)
        if len(opts) >= 4:
            break
    random.shuffle(opts)
    return {"id": str(uuid.uuid4()), "stem": stem, "options": opts, "answer": correct,
            "explanation": explanation or ""}


def _build_vocab_sim_questions(word, probes: dict, siblings: list) -> list[dict]:
    """拼 5 道纯选择题(义→词 / 语境挖空 / 词→义 / 搭配 / 多义 / 短语 / 例句译),不足 5 用变体补;全局缓存复用不额外付费。"""
    import re
    W = word.word
    zh = _zh_of(word)
    ex0 = next((e for e in (word.examples or []) if isinstance(e, dict) and e.get("en")), {}) or {}
    example, example_zh = ex0.get("en") or "", ex0.get("zh") or ""
    distractors = [str(x) for x in (probes.get("distractors") or [])
                   if str(x).strip() and str(x).strip().lower() != W.lower()]
    sib_words = [s.word for s in siblings if s.word and s.word.lower() != W.lower()]
    sib_zh = [z for z in (_zh_of(s) for s in siblings) if z and z != zh]
    word_wrongs = distractors + sib_words                 # 选「词」类题的干扰项

    qs: list[dict] = []
    if zh:                                                # 1) 义→词
        qs.append(_mc(f"「{zh}」对应哪个单词?", W, word_wrongs, example or zh))
    for s in _sentences_with(word, probes):               # 2) 语境挖空选词(每句一题)
        blanked = re.sub(rf"\b{re.escape(W)}\b", "____", s, count=1, flags=re.I)
        qs.append(_mc(f"选出填入空格的词:\n{blanked}", W, word_wrongs, zh))
    if zh and sib_zh:                                     # 3) 词→义
        qs.append(_mc(f"「{W}」的意思是?", zh, sib_zh, example))
    for c in (probes.get("collocation") or []):           # 4) 搭配
        if c.get("q") and c.get("options") and c.get("answer"):
            qs.append({"id": str(uuid.uuid4()), "stem": str(c["q"]),
                       "options": [str(o) for o in c["options"]], "answer": str(c["answer"]),
                       "explanation": ""})
    for s in (probes.get("sense") or []):                 # 5) 多义辨析
        if s.get("sentence") and s.get("answer") and s.get("options"):
            qs.append({"id": str(uuid.uuid4()), "stem": f"句中 {W} 的意思是?\n{s['sentence']}",
                       "options": [str(o) for o in s["options"]], "answer": str(s["answer"]),
                       "explanation": ""})
    for ph in (word.phrases or []):                       # 6) 短语→义(词条无中文义时也可出题)
        if isinstance(ph, dict) and ph.get("en") and ph.get("zh") and sib_zh:
            qs.append(_mc(f"短语「{ph['en']}」的意思是?", str(ph["zh"]), sib_zh, ""))
            break
    if example_zh:                                        # 7) 例句译→词(整句中文,选目标英文词)
        qs.append(_mc(f"「{example_zh}」这句话里的目标词是?", W, word_wrongs, example))

    # 去重(按题干)+ 过滤选项不足 2 的
    seen, uniq = set(), []
    for q in qs:
        if q["stem"] in seen or not q["options"] or len(q["options"]) < 2:
            continue
        seen.add(q["stem"]); uniq.append(q)
    # 不足 5(极少数稀疏词)→ 用现有素材(义/例句译)出变体补足;都没有则返回已有(≥1)
    guard = 0
    while len(uniq) < 5 and word_wrongs and guard < 6:
        guard += 1
        if zh:
            stem = f"选出「{zh}」的英文单词(第{guard}题):"
        elif example_zh:
            stem = f"「{example_zh}」对应的英文词是(第{guard}题)?"
        else:
            break
        if stem not in seen:
            seen.add(stem); uniq.append(_mc(stem, W, word_wrongs, example))
    return uniq[:5]


async def _sibling_words(db: AsyncSession, word, n: int = 8) -> list:
    """随机取若干其它词,给「选词/选义」题当干扰项。"""
    from app.models.d5_learning import VocabularyWord
    return (await db.execute(
        sa.select(VocabularyWord).where(VocabularyWord.id != word.id)
        .order_by(sa.func.random()).limit(n))).scalars().all()


async def _vocab_wr_and_word(db, student_id, wrong_record_id):
    from app.core.exceptions import AppError
    wr = await db.get(WrongRecord, wrong_record_id)
    if wr is None or wr.student_id != student_id:
        raise AppError(code=404, message="错题不存在或无权访问")
    if wr.kp_kind != "vocab":
        raise AppError(code=400, message="非词汇错题")
    word = await _resolve_vocab_word(db, wr)
    if word is None:
        raise AppError(code=400, message="未能定位到这道题考查的单词")
    return wr, word


async def vocab_sim_payload(db: AsyncSession, *, student_id: uuid.UUID, wrong_record_id: uuid.UUID) -> dict:
    """词汇错题「学这个词」:富词卡(配图/短语/发音,无媒体即时生成)+ 仿真练习 5 题(纯选择,全局缓存复用)。"""
    from app.services import vocab_media_service, vocab_probe_service
    wr, word = await _vocab_wr_and_word(db, student_id, wrong_record_id)
    # 查看即生成媒体(幂等)+ 进词力通统一错词本
    try:
        await vocab_media_service.ensure_word_media(db, word_id=word.id)
        word = await db.get(type(word), word.id)   # 取回可能被填充的媒体
    except Exception:  # noqa: BLE001
        pass
    lr = await vocab_probe_service._get_or_create_learning(db, student_id, word.id)
    lr.is_wrong = True
    await db.flush()
    probes = await vocab_probe_service.ensure_probes(db, word)   # 词级全局缓存,命中不付费
    siblings = await _sibling_words(db, word, 8)
    questions = _build_vocab_sim_questions(word, probes, siblings)
    example = next((e for e in (word.examples or []) if isinstance(e, dict) and e.get("en")), None)
    phrase = next((p for p in (word.phrases or []) if isinstance(p, dict) and p.get("en")), None)
    return {
        "wrong_record_id": str(wr.id),
        "card": {
            "id": str(word.id), "word": word.word, "phonetic": word.phonetic,
            "def_zh": _zh_of(word),
            "example": (example or {}).get("en"), "example_zh": (example or {}).get("zh"),
            "phrase": {"en": phrase["en"], "zh": phrase.get("zh")} if phrase else None,
            "audio_url": word.word_audio_url,
            "image_urls": getattr(word, "image_urls", None),
        },
        "questions": questions,
        "mastered": wr.status == "mastered",
    }


async def submit_vocab_sim(db: AsyncSession, *, student_id: uuid.UUID, wrong_record_id: uuid.UUID,
                           total: int, correct: int) -> dict:
    """仿真练习一轮结算:记 practice_count;**5 题全对 → 判掌握、进已掌握**(source=vocab)。"""
    wr, word = await _vocab_wr_and_word(db, student_id, wrong_record_id)
    wr.practice_count = (wr.practice_count or 0) + 1
    all_correct = total > 0 and correct >= total
    wr.practice_correct = (wr.practice_correct or 0) + (1 if all_correct else 0)
    mastered = False
    if total >= 5 and all_correct:               # 恒 5 题,全对才判掌握
        mastered = await _mark_vocab_word_mastered(db, student_id=student_id, word_id=word.id)
    await db.flush()
    return {"mastered": mastered, "wrong_mastered": wr.status == "mastered",
            "lifecycle": _lifecycle_of(wr)}


async def record_practice_for_question(
    db: AsyncSession, *, student_id: uuid.UUID, question_id: uuid.UUID,
    total: int, correct: int,
) -> dict:
    """作业详情里练同类结算:按 user_paper_question 找到对应错题(wrong_record)回写成绩。
    该题不是错题(无 wrong_record)→ 只返回 recorded=False(不影响练习体验)。"""
    wr = (await db.execute(
        sa.select(WrongRecord).where(
            WrongRecord.student_id == student_id, WrongRecord.q_scope == "uploaded",
            WrongRecord.question_id == question_id))).scalars().first()
    if wr is None:
        return {"recorded": False}
    r = await record_practice_result(
        db, student_id=student_id, wrong_record_id=wr.id, total=total, correct=correct)
    return {"recorded": True, **r}


async def practice_for_wrong(
    db: AsyncSession, *, student_id: uuid.UUID, wrong_record_id: uuid.UUID,
    count: int = 5, difficulty: int = 3,
) -> dict:
    """错题「练同类」(统一):按 wrong_record 派发。

    uploaded → 复用 user_paper_service.practice_for_question(三级兜底,含即时归类);
    platform/其它 → 用 wrong_record 冗余的 kp_name 直接出题。
    """
    from app.core.exceptions import AppError
    from app.services import practice_service, user_paper_service

    wr = await db.get(WrongRecord, wrong_record_id)
    if wr is None or wr.student_id != student_id:
        raise AppError(code=404, message="错题不存在或无权访问")
    if wr.q_scope == "uploaded":
        return await user_paper_service.practice_for_question(
            db, question_id=wr.question_id, student_id=student_id,
            count=count, difficulty=difficulty)
    kp_name = wr.kp_name
    if not kp_name and wr.node_id:
        from app.models.d15_knowledge_graph import KnowledgeNode
        kp_name = await db.scalar(
            sa.select(KnowledgeNode.name).where(KnowledgeNode.id == wr.node_id))
    if not kp_name:
        raise AppError(code=400, message="该题暂无关联知识点，无法生成同类练习")
    questions = await practice_service.generate_practice_questions(
        db, student_id=student_id, knowledge_point=kp_name, count=count, difficulty=difficulty)
    return {"knowledge_point": kp_name, "questions": questions}


async def list_by_node(
    db: AsyncSession, *, student_id: uuid.UUID, node_id: uuid.UUID,
    skip: int = 0, limit: int = 50,
) -> tuple[list[WrongRecord], int]:
    """某 node 下该生的**全部**错题(open + mastered),分页。知识点页「相关错题」用。"""
    base = sa.select(WrongRecord).where(
        WrongRecord.student_id == student_id, WrongRecord.node_id == node_id)
    total = (await db.execute(
        sa.select(sa.func.count()).select_from(base.subquery()))).scalar_one()
    rows = list((await db.execute(
        base.order_by(WrongRecord.created_at.desc()).offset(skip).limit(limit)
    )).scalars().all())
    return rows, total
