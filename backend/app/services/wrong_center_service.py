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
) -> dict:
    """状态 chip 计数(不受分页/状态筛选影响,仅受 kind 影响)。"""
    conds = [WrongRecord.student_id == student_id]
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
    status: str | None = None, skip: int = 0, limit: int = 20,
) -> tuple[list[dict], int]:
    """「我的错题」统一列表:只读 wrong_record(题面已冗余,自洽)。

    kind ∈ {None(全部), grammar, vocab};status ∈ {None(全部), pending, reviewing, mastered}。
    排序:未掌握在前、已掌握沉底(灰显折叠),各按 created_at 倒序。
    返回卡片字典(含 lifecycle/进度)。
    """
    base = sa.select(WrongRecord).where(WrongRecord.student_id == student_id)
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


def _source_route(source_label: str | None, source_id: uuid.UUID | None) -> str | None:
    """错题来源实体的小程序路由(供「点来源→回到来源→再返回」)。无可跳目标返回 None。"""
    if source_id is None:
        return None
    if source_label == "整卷":
        return f"/pages/user-papers/detail?id={source_id}"
    if source_label == "作业":
        return f"/pages/assignments/detail?id={source_id}"
    return None


async def record_practice_result(
    db: AsyncSession, *, student_id: uuid.UUID, wrong_record_id: uuid.UUID,
    total: int, correct: int,
) -> dict:
    """练同类一轮做完 → 记 practice_count/correct(待巩固→巩固中);
    语法错题按正确率推进 SM-2(可达标判掌握);词汇仅记数(掌握判定留 P3 词力通)。"""
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
    if total > 0 and wr.kp_kind == "grammar" and wr.status == "open":
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


async def _sync_vocab_wrong_mastery(db: AsyncSession, *, student_id: uuid.UUID, word_id: uuid.UUID) -> bool:
    """该词双维(接收+产出)达标 → 把该生指向此词的 open 词汇错题全部判掌握(source=vocab)。返回是否判掌握。"""
    import datetime as _dt
    from app.services.vocab_probe_service import dual_mastered, _get_or_create_learning
    lr = await _get_or_create_learning(db, student_id, word_id)
    if not dual_mastered(lr):
        return False
    await db.execute(
        sa.update(WrongRecord)
        .where(WrongRecord.student_id == student_id, WrongRecord.vocab_word_id == word_id,
               WrongRecord.status == "open")
        .values(status="mastered", mastered_at=_dt.datetime.now(_dt.timezone.utc),
                mastery_source="vocab"))
    await db.flush()
    return True


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


async def vocab_learn_payload(db: AsyncSession, *, student_id: uuid.UUID, wrong_record_id: uuid.UUID) -> dict:
    """词汇错题「学这个词」:单词卡(无媒体即时生成)+ 接收探针 + 拼写提示 + 当前双维进度。"""
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
    probes = await vocab_probe_service.comprehension_probes(db, student_id=student_id, word=word)
    defs = word.definitions if isinstance(word.definitions, list) else []
    zh = (defs[0].get("zh") if defs and isinstance(defs[0], dict) else None) or ""
    recep = float(lr.mastery_recep or 0)
    prod = float(lr.mastery_prod or 0)
    return {
        "wrong_record_id": str(wr.id),
        "word": {
            "id": str(word.id), "word": word.word, "phonetic": word.phonetic,
            "definitions": defs, "examples": word.examples or [],
            "audio_url": word.word_audio_url, "image_urls": getattr(word, "image_urls", None),
        },
        "recep_probes": [p for p in probes.get("probes", []) if p.get("kind") == "sense"] or probes.get("probes", []),
        "spell_prompt": f"根据释义拼出单词：{zh}" if zh else "根据发音/释义拼出这个单词",
        "recep": round(recep, 4), "prod": round(prod, 4),
        "recep_mastered": recep >= vocab_probe_service.RECEP_MASTERED,
        "prod_mastered": prod >= vocab_probe_service.PROD_MASTERED,
        "mastered": wr.status == "mastered",
    }


async def submit_vocab_recep(db: AsyncSession, *, student_id: uuid.UUID, wrong_record_id: uuid.UUID,
                             key: str, answer: str) -> dict:
    """接收探针作答 → 词力通 recep BKT;词汇错题进巩固中;双维达标则判掌握。"""
    from app.services import vocab_probe_service
    wr, word = await _vocab_wr_and_word(db, student_id, wrong_record_id)
    res = await vocab_probe_service.submit_probe(db, student_id=student_id, word_id=word.id, key=key, answer=answer)
    wr.practice_count = (wr.practice_count or 0) + 1
    wr.practice_correct = (wr.practice_correct or 0) + (1 if res.get("correct") else 0)
    mastered = await _sync_vocab_wrong_mastery(db, student_id=student_id, word_id=word.id)
    await db.flush()
    return {**res, "lifecycle": _lifecycle_of(wr), "wrong_mastered": wr.status == "mastered",
            "just_mastered": mastered}


async def submit_vocab_spell(db: AsyncSession, *, student_id: uuid.UUID, wrong_record_id: uuid.UUID,
                             answer: str) -> dict:
    """拼写作答(产出维度)→ 词力通 prod BKT;词汇错题进巩固中;双维达标则判掌握。"""
    from app.services import vocab_probe_service
    wr, word = await _vocab_wr_and_word(db, student_id, wrong_record_id)
    res = await vocab_probe_service.submit_spell(db, student_id=student_id, word_id=word.id, answer=answer)
    wr.practice_count = (wr.practice_count or 0) + 1
    wr.practice_correct = (wr.practice_correct or 0) + (1 if res.get("correct") else 0)
    mastered = await _sync_vocab_wrong_mastery(db, student_id=student_id, word_id=word.id)
    await db.flush()
    return {**res, "lifecycle": _lifecycle_of(wr), "wrong_mastered": wr.status == "mastered",
            "just_mastered": mastered}


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
