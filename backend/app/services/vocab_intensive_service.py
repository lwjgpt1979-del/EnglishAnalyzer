"""单词精讲(作业精讲/课程精讲 的「单词」模块)取数。

- 作业:学生「加入待学习」的词(student_vocab_candidates,带 source_paper_id)→ 按【卷=批次】归组;
- 课程:学生当前教材(preferred_textbook_version)的单元词(curriculum_words)→ 按【年级→册→单元】归组;
- 词的详解统一取词库 VocabularyWord(word/phonetic/definitions);词库缺词走 vocab_review 审核(见 vocab_review_service)。
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d1_users import User
from app.models.d4_knowledge import CurriculumUnit, CurriculumWord
from app.models.d5_learning import VocabularyWord, StudentVocabCandidate
from app.models.d13_v2_user_papers import UserUploadedPaper


def _word_out(w: VocabularyWord) -> dict:
    return {"word_id": str(w.id), "word": w.word, "phonetic": w.phonetic,
            "definitions": w.definitions}


# ── 作业精讲 · 单词:按卷(批次)──────────────────────────────────────────────
async def homework_batches(db: AsyncSession, *, student_id: uuid.UUID) -> list[dict]:
    """学生加入待学习的词,按来源卷(批次)归组;每批次带卷名/日期/词数。年月日倒序。"""
    rows = (await db.execute(
        select(StudentVocabCandidate.source_paper_id, func.count(StudentVocabCandidate.id),
               UserUploadedPaper.title, UserUploadedPaper.created_at)
        .join(UserUploadedPaper, UserUploadedPaper.id == StudentVocabCandidate.source_paper_id)
        .where(StudentVocabCandidate.student_id == student_id,
               StudentVocabCandidate.source_paper_id.isnot(None))
        .group_by(StudentVocabCandidate.source_paper_id, UserUploadedPaper.title,
                  UserUploadedPaper.created_at)
        .order_by(UserUploadedPaper.created_at.desc()))).all()
    return [{"paper_id": str(pid), "title": title or "未命名试卷",
             "date": created_at.strftime("%Y-%m-%d") if created_at else "",
             "word_count": int(cnt)} for pid, cnt, title, created_at in rows]


async def homework_words(db: AsyncSession, *, student_id: uuid.UUID,
                         paper_id: uuid.UUID) -> list[dict]:
    """某批次(卷)里加入待学习的词 + 词库详解。"""
    rows = (await db.execute(
        select(VocabularyWord)
        .join(StudentVocabCandidate, StudentVocabCandidate.word_id == VocabularyWord.id)
        .where(StudentVocabCandidate.student_id == student_id,
               StudentVocabCandidate.source_paper_id == paper_id)
        .order_by(StudentVocabCandidate.created_at.desc()))).scalars().all()
    return [_word_out(w) for w in rows]


# ── 课程精讲 · 单词:按教材单元 ────────────────────────────────────────────────
async def course_units(db: AsyncSession, *, student_id: uuid.UUID) -> dict:
    """学生当前教材(preferred_textbook_version)的单元 + 每单元词数,供【年级→册→单元】下钻。
    未设教材版本 → {version:None, units:[]}。"""
    student = await db.get(User, student_id)
    tv = student.preferred_textbook_version if student else None
    if not tv:
        return {"version": None, "units": []}
    rows = (await db.execute(
        select(CurriculumUnit.id, CurriculumUnit.grade, CurriculumUnit.semester,
               CurriculumUnit.unit_no, CurriculumUnit.unit_title, func.count(CurriculumWord.word_id))
        .join(CurriculumWord, CurriculumWord.unit_id == CurriculumUnit.id)
        .where(CurriculumUnit.textbook_version == tv)
        .group_by(CurriculumUnit.id, CurriculumUnit.grade, CurriculumUnit.semester,
                  CurriculumUnit.unit_no, CurriculumUnit.unit_title)
        .order_by(CurriculumUnit.grade, CurriculumUnit.semester, CurriculumUnit.unit_no))).all()
    units = [{"unit_id": str(uid), "grade": grade, "semester": sem, "unit_no": uno,
              "unit_title": title or f"Unit {uno}", "word_count": int(cnt)}
             for uid, grade, sem, uno, title, cnt in rows]
    return {"version": tv, "units": units}


async def course_words(db: AsyncSession, *, unit_id: uuid.UUID) -> list[dict]:
    """某教材单元的词 + 词库详解。"""
    rows = (await db.execute(
        select(VocabularyWord)
        .join(CurriculumWord, CurriculumWord.word_id == VocabularyWord.id)
        .where(CurriculumWord.unit_id == unit_id)
        .order_by(VocabularyWord.word))).scalars().all()
    return [_word_out(w) for w in rows]


# ── 缺词审核:词库没有的词 → 队列 → admin 审核入库 ────────────────────────────
async def report_missing_words(db: AsyncSession, *, words: list[str], source: str = "paper") -> int:
    """作业/课程里出现、但词库没有的词 → 落审核队列(按归一化词形去重累加)。返回新增/累加条数。"""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.models.d28_vocab_review import VocabReview
    norms = {(w or "").strip().lower(): (w or "").strip() for w in words if (w or "").strip()}
    if not norms:
        return 0
    # 已在词库的不报
    existing = set(x.lower() for x in (await db.execute(
        select(VocabularyWord.word).where(func.lower(VocabularyWord.word).in_(list(norms))))).scalars().all())
    n = 0
    for norm, orig in norms.items():
        if norm in existing:
            continue
        await db.execute(
            pg_insert(VocabReview)
            .values(id=uuid.uuid4(), word_norm=norm, word=orig, source=source)
            .on_conflict_do_update(index_elements=["word_norm"],
                                   set_={"occur_count": VocabReview.occur_count + 1}))
        n += 1
    await db.commit()
    return n


async def list_reviews(db: AsyncSession, *, status: str = "pending",
                       skip: int = 0, limit: int = 50) -> dict:
    """admin:缺词审核列表(分页)。"""
    from app.models.d28_vocab_review import VocabReview
    total = (await db.execute(
        select(func.count(VocabReview.id)).where(VocabReview.status == status))).scalar() or 0
    rows = (await db.execute(
        select(VocabReview).where(VocabReview.status == status)
        .order_by(VocabReview.occur_count.desc(), VocabReview.created_at.desc())
        .offset(skip).limit(limit))).scalars().all()
    return {"total": int(total), "items": [
        {"id": str(r.id), "word": r.word, "source": r.source,
         "occur_count": r.occur_count, "status": r.status,
         "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]}


# ── 词条要素生成(入库即生成词力通全要素:文本 LLM + 接收探针 + 媒体)──────────────
async def _enrich_word_text(word: str) -> dict:
    """LLM 生成词条文本要素:音标/难度/释义/例句/短语。dev-mock 离线可跑。"""
    from app.services.llm_provider import complete_json, fast_model, is_llm_dev_mode
    if is_llm_dev_mode():
        return {"phonetic": "", "difficulty": 3,
                "definitions": [{"pos": "n.", "meaning": f"(dev){word} 的中文释义"}],
                "examples": [{"en": f"This is a {word}.", "zh": f"这是一个 {word}。"}],
                "phrases": []}
    system = (
        "你是英语词典编纂助手。给定一个英文单词或词组,输出面向初中生的学习词条要素,严格输出 JSON:\n"
        '{"phonetic":"国际音标(不含斜杠,无则空串)",'
        '"difficulty":1-5的整数(1易5难),'
        '"definitions":[{"pos":"词性缩写 n./v./adj. 等","meaning":"简洁中文释义"}](覆盖常见义项,最多3条),'
        '"examples":[{"en":"英文例句(用到该词,初中难度)","zh":"中文翻译"}](2条),'
        '"phrases":[{"en":"含该词的常用短语/搭配","zh":"中文"}](0-2条,无则空数组)}\n'
        "只返回纯 JSON,不臆造不存在的词义。")
    d = await complete_json(
        system_prompt=system, user_prompt=f"单词/词组:{word}\n返回 JSON:",
        max_tokens=800, model=fast_model(), feature="vocab_enrich",
        validate=lambda x: bool(x.get("definitions")))
    if not d:
        return {"phonetic": "", "difficulty": 3, "definitions": [], "examples": [], "phrases": []}
    defs = [{"pos": str(x.get("pos") or ""), "meaning": str(x.get("meaning") or "")}
            for x in (d.get("definitions") or []) if isinstance(x, dict) and x.get("meaning")]
    exs = [{"en": str(x.get("en") or ""), "zh": str(x.get("zh") or "")}
           for x in (d.get("examples") or []) if isinstance(x, dict) and x.get("en")]
    phr = [{"en": str(x.get("en") or ""), "zh": str(x.get("zh") or "")}
           for x in (d.get("phrases") or []) if isinstance(x, dict) and x.get("en")]
    try:
        diff = max(1, min(5, int(d.get("difficulty") or 3)))
    except (ValueError, TypeError):
        diff = 3
    return {"phonetic": str(d.get("phonetic") or ""), "difficulty": diff,
            "definitions": defs, "examples": exs, "phrases": phr}


_gen_state: dict = {"running": False, "total": 0, "done": 0, "ok": 0, "failed": 0}


def gen_status() -> dict:
    """入库要素生成进度(进程内)。"""
    return dict(_gen_state)


async def _run_gen(word_ids: list) -> None:
    """后台:逐词生成词力通全要素(文本要素 → 接收探针 → 媒体)。每词独立 session,失败不阻断。
    第三方付费调用天然落地(写 VocabularyWord),同词不重复付费(缺失才生成)。"""
    import logging
    from app.core.database import _async_session_factory
    from app.services import vocab_probe_service, vocab_media_service
    _gen_state.update(running=True, total=len(word_ids), done=0, ok=0, failed=0)
    try:
        for wid in word_ids:
            try:
                async with _async_session_factory() as db:
                    w = (await db.execute(
                        select(VocabularyWord).where(VocabularyWord.id == wid))).scalar_one_or_none()
                    if w is None:
                        _gen_state["failed"] += 1
                        continue
                    # 1) 文本要素:仅当缺失时生成(不覆盖 admin 已填 / 已有)
                    if not w.definitions:
                        t = await _enrich_word_text(w.word)
                        w.phonetic = w.phonetic or (t["phonetic"] or None)
                        w.definitions = t["definitions"] or []
                        w.examples = w.examples or (t["examples"] or None)
                        w.phrases = w.phrases or (t["phrases"] or None)
                        if not w.difficulty:
                            w.difficulty = t["difficulty"]
                        await db.commit()
                    # 2) 接收探针(需释义作输入)
                    await vocab_probe_service.ensure_probes(db, w)
                    await db.commit()
                    # 3) 媒体(en 描述 + 单词发音 + 配图,落 draft 走媒体审核)
                    await vocab_media_service.generate_for_word(db, word_id=w.id)
                    await db.commit()
                    _gen_state["ok"] += 1
            except Exception:  # noqa: BLE001 单词失败不阻断整批
                logging.getLogger(__name__).exception("vocab element gen failed wid=%s", wid)
                _gen_state["failed"] += 1
            finally:
                _gen_state["done"] += 1
    finally:
        _gen_state["running"] = False


async def _get_or_create_word(db: AsyncSession, r) -> uuid.UUID:
    """按归一化词形取或建 bare 词条(difficulty NOT NULL → 暂置 3,要素由后台生成)。"""
    wid = (await db.execute(
        select(VocabularyWord.id).where(func.lower(VocabularyWord.word) == r.word_norm).limit(1))).scalar()
    if wid is None:
        w = VocabularyWord(id=uuid.uuid4(), word=r.word, definitions=[], difficulty=3, source="import")
        db.add(w)
        await db.flush()
        wid = w.id
    return wid


async def approve_batch(db: AsyncSession, *, review_ids: list) -> dict:
    """批量审核通过:同步标 approved + 建 bare 词条(快),要素(文本/探针/媒体)由后台 _run_gen 生成。"""
    import asyncio
    from app.models.d28_vocab_review import VocabReview
    word_ids: list = []
    approved = 0
    for rid in review_ids:
        r = await db.get(VocabReview, rid)
        if r is None or r.status != "pending":
            continue
        word_ids.append(await _get_or_create_word(db, r))
        r.status = "approved"
        approved += 1
    await db.commit()
    if word_ids and not _gen_state["running"]:
        asyncio.create_task(_run_gen(list(word_ids)))
    return {"approved": approved, "generating": len(word_ids)}


async def approve_review(db: AsyncSession, *, review_id: uuid.UUID,
                         phonetic: str | None = None, definitions=None) -> bool:
    """admin:审核通过 → 入库 + 后台生成词力通全要素(文本/探针/媒体)。
    definitions 非空则作 admin 手填(后台只补 examples/probes/媒体,不覆盖释义)。"""
    import asyncio
    from app.models.d28_vocab_review import VocabReview
    r = await db.get(VocabReview, review_id)
    if r is None or r.status != "pending":
        return False
    wid = await _get_or_create_word(db, r)
    if definitions:   # admin 手填释义/音标 → 写入(后台文本 enrich 会因 definitions 非空而跳过)
        w = await db.get(VocabularyWord, wid)
        if w is not None:
            w.definitions = definitions
            if phonetic:
                w.phonetic = phonetic
    r.status = "approved"
    await db.commit()
    if not _gen_state["running"]:
        asyncio.create_task(_run_gen([wid]))
    return True


async def reject_review(db: AsyncSession, *, review_id: uuid.UUID) -> bool:
    from app.models.d28_vocab_review import VocabReview
    r = await db.get(VocabReview, review_id)
    if r is None or r.status != "pending":
        return False
    r.status = "rejected"
    await db.commit()
    return True
