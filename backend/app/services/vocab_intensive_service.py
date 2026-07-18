"""单词精讲(作业精讲/课程精讲 的「单词」模块)取数。

- 作业:学生「加入待学习」的词(student_vocab_candidates,带 source_paper_id)→ 按【卷=批次】归组;
- 课程:学生当前教材(preferred_textbook_version)的单元词(curriculum_words)→ 按【年级→册→单元】归组;
- 词的详解统一取词库 VocabularyWord(word/phonetic/definitions);词库缺词走 vocab_review 审核(见 vocab_review_service)。
"""
from __future__ import annotations

import uuid

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d1_users import User
from app.models.d4_knowledge import CurriculumUnit, CurriculumWord
from app.models.d5_learning import VocabularyWord, StudentVocabCandidate, VocabularyLearning
from app.models.d13_v2_user_papers import UserUploadedPaper


def _word_out(w: VocabularyWord) -> dict:
    # 列表行 + 单词卡片:图/中文意思/发音/例句。媒体按「已发布」门控(和学生端一致)
    pub = str(w.media_status) == "published"
    imgs = w.image_urls if (pub and isinstance(w.image_urls, list)) else None
    exs = w.examples if (pub and isinstance(w.examples, list)) else None
    return {"word_id": str(w.id), "word": w.word, "phonetic": w.phonetic,
            "definitions": w.definitions,
            "image_url": (imgs[0] if imgs else None),
            "word_audio_url": (w.word_audio_url if pub else None),
            "en_description": (w.en_description if pub else None),
            "example": (exs[0] if exs else None)}


# ── 作业精讲 · 单词:按卷(批次)──────────────────────────────────────────────
async def homework_batches(db: AsyncSession, *, student_id: uuid.UUID) -> list[dict]:
    """学生加入待学习的词,按来源卷(批次)归组;每批次带卷名/日期/词数。年月日倒序。"""
    rows = (await db.execute(
        select(StudentVocabCandidate.source_paper_id, func.count(func.distinct(StudentVocabCandidate.word_id)),
               # 已学过的词数(该生该词有 VocabularyLearning 行)= studied
               func.count(func.distinct(case(
                   (VocabularyLearning.id.isnot(None), StudentVocabCandidate.word_id)))),
               UserUploadedPaper.title, UserUploadedPaper.created_at)
        .join(UserUploadedPaper, UserUploadedPaper.id == StudentVocabCandidate.source_paper_id)
        .outerjoin(VocabularyLearning,
                   (VocabularyLearning.word_id == StudentVocabCandidate.word_id)
                   & (VocabularyLearning.student_id == student_id))
        .where(StudentVocabCandidate.student_id == student_id,
               StudentVocabCandidate.source_paper_id.isnot(None))
        .group_by(StudentVocabCandidate.source_paper_id, UserUploadedPaper.title,
                  UserUploadedPaper.created_at)
        .order_by(UserUploadedPaper.created_at.desc()))).all()
    return [{"paper_id": str(pid), "title": title or "未命名试卷",
             "date": created_at.strftime("%Y-%m-%d") if created_at else "",
             "word_count": int(cnt), "studied": int(st)}
            for pid, cnt, st, title, created_at in rows]


async def homework_words(db: AsyncSession, *, student_id: uuid.UUID,
                         paper_id: uuid.UUID) -> list[dict]:
    """某批次(卷)里加入待学习的词 + 词库详解;带 studied(该词是否已学=有 VocabularyLearning 行)。"""
    rows = (await db.execute(
        select(VocabularyWord)
        .join(StudentVocabCandidate, StudentVocabCandidate.word_id == VocabularyWord.id)
        .where(StudentVocabCandidate.student_id == student_id,
               StudentVocabCandidate.source_paper_id == paper_id)
        .order_by(StudentVocabCandidate.created_at.desc()))).scalars().all()
    studied_ids = set((await db.execute(
        select(VocabularyLearning.word_id)
        .where(VocabularyLearning.student_id == student_id,
               VocabularyLearning.word_id.in_([w.id for w in rows] or [None])))).scalars().all())
    return [{**_word_out(w), "studied": w.id in studied_ids} for w in rows]


# ── 课程精讲 · 单词:按教材单元 ────────────────────────────────────────────────
async def course_units(db: AsyncSession, *, student_id: uuid.UUID,
                       grade: str | None = None, semester: str | None = None) -> dict:
    """学生当前教材某学期的单元(默认聚焦 preferred 当前学期)+ 每单元词数/已学数,
    含闯关顺序解锁(unlocked)+ 本学期通关(semester_done)+ 下学期(next_semester)。
    未设教材版本 → 空。"""
    from app.services.course_intensive_util import decorate_units, next_semester, resolve_semester
    student = await db.get(User, student_id)
    tv = student.preferred_textbook_version if student else None
    if not tv:
        return {"version": None, "grade": None, "semester": None, "units": [],
                "semester_done": False, "next_semester": None}
    g, s = await resolve_semester(db, tv, student, grade, semester)
    rows = (await db.execute(
        select(CurriculumUnit.id, CurriculumUnit.grade, CurriculumUnit.semester,
               CurriculumUnit.unit_no, CurriculumUnit.unit_title,
               func.count(func.distinct(CurriculumWord.word_id)),
               # 已学词数 = 该生该词有 VocabularyLearning 行
               func.count(func.distinct(case(
                   (VocabularyLearning.id.isnot(None), CurriculumWord.word_id)))))
        .join(CurriculumWord, CurriculumWord.unit_id == CurriculumUnit.id)
        .outerjoin(VocabularyLearning,
                   (VocabularyLearning.word_id == CurriculumWord.word_id)
                   & (VocabularyLearning.student_id == student_id))
        .where(CurriculumUnit.textbook_version == tv,
               CurriculumUnit.grade == g, CurriculumUnit.semester == s)
        .group_by(CurriculumUnit.id, CurriculumUnit.grade, CurriculumUnit.semester,
                  CurriculumUnit.unit_no, CurriculumUnit.unit_title)
        .order_by(CurriculumUnit.unit_no))).all()
    units = [{"unit_id": str(uid), "grade": gr, "semester": sem, "unit_no": uno,
              "unit_title": title or f"Unit {uno}", "word_count": int(cnt),
              "total": int(cnt), "studied": int(st)}
             for uid, gr, sem, uno, title, cnt, st in rows]
    done = decorate_units(units)
    return {"version": tv, "grade": g, "semester": s, "units": units,
            "semester_done": done,
            "next_semester": await next_semester(db, tv, g, s) if done else None}


async def course_words(db: AsyncSession, *, unit_id: uuid.UUID,
                       student_id: uuid.UUID | None = None) -> list[dict]:
    """某教材单元的词 + 词库详解;传 student_id 则每词带 studied(有无 VocabularyLearning)。"""
    rows = (await db.execute(
        select(VocabularyWord)
        .join(CurriculumWord, CurriculumWord.word_id == VocabularyWord.id)
        .where(CurriculumWord.unit_id == unit_id)
        .order_by(VocabularyWord.word))).scalars().all()
    studied_ids: set = set()
    if student_id is not None and rows:
        studied_ids = set((await db.execute(
            select(VocabularyLearning.word_id).where(
                VocabularyLearning.student_id == student_id,
                VocabularyLearning.word_id.in_([w.id for w in rows])))).scalars().all())
    return [{**_word_out(w), "studied": w.id in studied_ids} for w in rows]


# ── 精讲「完整词力通流程」:某单元/批次的 word_id 列表(供限定词集版 daily-task)──────
async def course_word_ids(db: AsyncSession, *, unit_id: uuid.UUID) -> list[uuid.UUID]:
    """某教材单元的词 id(保持与 course_words 相同顺序)。"""
    return [uuid.UUID(w["word_id"]) for w in await course_words(db, unit_id=unit_id)]


async def homework_word_ids(db: AsyncSession, *, student_id: uuid.UUID,
                            paper_id: uuid.UUID) -> list[uuid.UUID]:
    """某批次(卷)加入待学习的词 id(顺序同 homework_words)。"""
    return [uuid.UUID(w["word_id"])
            for w in await homework_words(db, student_id=student_id, paper_id=paper_id)]


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


import re as _re

# 免费粗筛:必须字母开头、可含空格/连字符/撇号、长度 2-40(挡住 OCR 乱码/纯符号/超长残片)
_WORD_SHAPE = _re.compile(r"[A-Za-z][A-Za-z '\-]{1,39}")


async def _word_validity_gate(word: str) -> bool:
    """有效性闸门:判定是否**真实、适合中学生学习的英文单词/词组**(排除 OCR 乱码、专有名词、残片)。
    先免费正则粗筛,再 LLM(fast 档)判定;dev-mock 放行(便于本地跑)。"""
    from app.services.llm_provider import complete_json, fast_model, is_llm_dev_mode
    w = (word or "").strip()
    if not w or not _WORD_SHAPE.fullmatch(w):
        return False
    if is_llm_dev_mode():
        return True
    d = await complete_json(
        system_prompt=(
            "你是英语词典编纂助手。判断给定字符串是否是一个**真实、适合中学生学习的英文单词或常用词组**。"
            "判 false 的情形:拼写错误/OCR 乱码、专有名词(人名/地名/品牌/机构)、无意义字母组合、句子残片。"
            '只返回 JSON:{"valid": true|false, "reason":"简短理由"}。'),
        user_prompt=f"字符串:{w}\n返回 JSON:",
        max_tokens=100, model=fast_model(), feature="vocab_validity_gate",
        validate=lambda x: "valid" in x)
    return bool(d and d.get("valid"))


async def _bg_gen_media_missing(word_id: uuid.UUID) -> None:
    """缺词收录后台补媒体(②仅 1 张候选省 t2i)+ 接收探针;独立 session,失败不阻断。
    与 ensure_word_media 共用 vocab_media_service._media_inflight 闸,防并发重复出图。"""
    import logging
    from app.core.database import _async_session_factory
    from app.services import vocab_media_service as vms, vocab_probe_service
    if word_id in vms._media_inflight:
        return
    vms._media_inflight.add(word_id)
    try:
        async with _async_session_factory() as db:
            w = (await db.execute(
                select(VocabularyWord).where(VocabularyWord.id == word_id))).scalar_one_or_none()
            if w is None:
                return
            try:
                await vms.generate_for_word(db, word_id=word_id, candidates=1)   # ② 单张候选
                w.media_status = ("published" if (isinstance(w.image_urls, list) and w.image_urls)
                                  else "draft")
                await db.commit()
            except Exception:  # noqa: BLE001
                await db.rollback()
                logging.getLogger(__name__).exception("bg media gen failed wid=%s", word_id)
            try:
                w2 = (await db.execute(
                    select(VocabularyWord).where(VocabularyWord.id == word_id))).scalar_one_or_none()
                if w2 is not None:
                    await vocab_probe_service.ensure_probes(db, w2)
                    await db.commit()
            except Exception:  # noqa: BLE001
                await db.rollback()
    finally:
        vms._media_inflight.discard(word_id)


async def ensure_missing_word(db: AsyncSession, *, word: str, student_id: uuid.UUID,
                              paper_id: uuid.UUID | None = None,
                              add_to_study: bool = True) -> dict:
    """缺词「查看即生成」:学生在作业里点开一个词库没有的词 → 有效性闸门 → 通过则**即时**建词条
    (source='auto',media_origin='student' 供后台复核)+ 补文本要素 + 出媒体(双闸门)+ published
    直接可学;不通过 → 落人工审核队列(pending),不建词。可选加入学生待学习(按来源卷归批次)。
    返回 {status:'created'|'exists'|'queued', word: StudyWord|None}。第三方付费天然落库,同词不二次付费。"""
    from app.services import vocab_media_service, vocab_probe_service, vocab_pin_service
    from app.models.d28_vocab_review import VocabReview
    norm = (word or "").strip().lower()
    disp = (word or "").strip()
    if not norm:
        return {"status": "queued", "word": None}
    existing = (await db.execute(
        select(VocabularyWord).where(func.lower(VocabularyWord.word) == norm).limit(1))).scalar_one_or_none()
    created = False
    if existing is None:
        # 有效性闸门:不过 → 落人工审核,不建词(避免 OCR 乱码/专有名词污染词库)
        if not await _word_validity_gate(disp):
            await report_missing_words(db, words=[norm], source="paper")
            return {"status": "queued", "word": None}
        # 建词条(source='auto')+ 同步补文本要素(卡片展示 + 媒体词意闸门都需 definitions)
        t = await _enrich_word_text(disp)
        w = VocabularyWord(id=uuid.uuid4(), word=disp,
                           definitions=(t["definitions"] or []),
                           phonetic=(t["phonetic"] or None),
                           examples=(t["examples"] or None),
                           phrases=(t["phrases"] or None),
                           difficulty=t["difficulty"], source="auto",
                           media_origin="student")
        db.add(w)
        await db.flush()
        existing = w
        created = True
        # 缺词审核行:标 status='auto'(已自动入库待复核,区别于 pending 未入库)
        rev = (await db.execute(
            select(VocabReview).where(VocabReview.word_norm == norm).limit(1))).scalar_one_or_none()
        if rev is not None:
            rev.status = "auto"
        else:
            db.add(VocabReview(id=uuid.uuid4(), word_norm=norm, word=disp, source="paper", status="auto"))
        await db.commit()
        await db.refresh(existing)
        # ① 媒体(配图/发音)+ 接收探针 后台异步生成 → 词条秒回可学(有释义/音标);图随后补。
        #   ②按需路径出图只 1 张候选省 t2i;与「查看即生成」共用 inflight 闸防并发重复出图。
        import asyncio
        asyncio.create_task(_bg_gen_media_missing(existing.id))
    # 加入学生待学习(按来源卷归批次)——复用 add_paper_candidates 幂等 upsert
    if add_to_study and paper_id is not None:
        await vocab_pin_service.add_paper_candidates(
            db, student_id=student_id, word_ids=[existing.id], source_paper_id=paper_id)
        await db.commit()
    out = _word_out(existing)
    out["in_vocab"] = True
    out["word_added"] = bool(add_to_study and paper_id is not None)
    return {"status": "created" if created else "exists", "word": out}


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
