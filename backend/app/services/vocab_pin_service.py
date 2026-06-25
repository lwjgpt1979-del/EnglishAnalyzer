"""R9.6 优先学清单 + 拍照加词。

学生主动把词提到"最优先学"(student_vocab_candidates.priority>0),排在所有系统来源之前。
两种加入:① 从各来源库挑选(pin_words)② 拍照上传 OCR 抽词(pin_from_photo,复用豆包视觉)。
选词侧已在 vocabulary_service._ordered_new_words 接 P(-1) 档。
"""
from __future__ import annotations

import logging
import re
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d5_learning import VocabularyWord, StudentVocabCandidate
from app.models.d4_knowledge import CurriculumUnit, CurriculumWord
from app.models.d1_users import User

_log = logging.getLogger(__name__)

_DEFAULT_PRIORITY = 1


def _words_from_text(text: str) -> list[str]:
    """从 OCR 文本里抽英文词(小写、去重、长度≥2、限量)。"""
    seen, out = set(), []
    for tok in re.findall(r"[A-Za-z][A-Za-z'-]+", text or ""):
        w = tok.lower().strip("'-")
        if len(w) >= 2 and w not in seen:
            seen.add(w)
            out.append(w)
    return out[:60]


async def _upsert_pin(db: AsyncSession, *, student_id: uuid.UUID, word_id: uuid.UUID,
                      source: str, priority: int) -> None:
    """加入/更新优先学(unique student+word → 冲突则升级 priority)。"""
    await db.execute(
        pg_insert(StudentVocabCandidate)
        .values(id=uuid.uuid4(), student_id=student_id, word_id=word_id, source=source, priority=priority)
        .on_conflict_do_update(
            index_elements=["student_id", "word_id"],
            set_={"priority": priority}))


async def pin_words(db: AsyncSession, *, student_id: uuid.UUID, word_ids: list,
                    priority: int = _DEFAULT_PRIORITY) -> dict:
    """从来源库挑选加入优先学。返回 {pinned}。"""
    n = 0
    for wid in word_ids:
        try:
            wid = wid if isinstance(wid, uuid.UUID) else uuid.UUID(str(wid))
        except (ValueError, TypeError):
            continue
        if (await db.execute(sa.select(VocabularyWord.id).where(VocabularyWord.id == wid))).scalar_one_or_none() is None:
            continue
        await _upsert_pin(db, student_id=student_id, word_id=wid, source="pick", priority=max(1, priority))
        n += 1
    await db.flush()
    return {"pinned": n}


async def set_priority(db: AsyncSession, *, student_id: uuid.UUID, word_id: uuid.UUID, priority: int) -> None:
    """调整某词的优先级别(priority<=0 视为移出优先学)。"""
    await db.execute(
        sa.update(StudentVocabCandidate)
        .where(StudentVocabCandidate.student_id == student_id, StudentVocabCandidate.word_id == word_id)
        .values(priority=max(0, priority)))
    await db.flush()


async def unpin(db: AsyncSession, *, student_id: uuid.UUID, word_id: uuid.UUID) -> None:
    """移出优先学(保留为普通候选,priority=0)。"""
    await set_priority(db, student_id=student_id, word_id=word_id, priority=0)


async def list_pins(db: AsyncSession, *, student_id: uuid.UUID) -> list[dict]:
    """优先学清单(priority>0),级别高的在前。"""
    rows = (await db.execute(
        sa.select(StudentVocabCandidate.priority, StudentVocabCandidate.source, VocabularyWord)
        .join(VocabularyWord, VocabularyWord.id == StudentVocabCandidate.word_id)
        .where(StudentVocabCandidate.student_id == student_id, StudentVocabCandidate.priority > 0)
        .order_by(StudentVocabCandidate.priority.desc(), StudentVocabCandidate.created_at))).all()
    return [{"word_id": str(w.id), "word": w.word, "phonetic": w.phonetic,
             "definitions": w.definitions, "priority": pr, "source": src} for pr, src, w in rows]


async def pinnable_words(db: AsyncSession, *, student_id: uuid.UUID, limit: int = 200) -> list[dict]:
    """可挑选加入优先学的词:本人候选词(作业/试卷/错题)+ 当前学期教材词;标注是否已 pin。"""
    student = (await db.execute(sa.select(User).where(User.id == student_id))).scalar_one()
    pinned = set((await db.execute(
        sa.select(StudentVocabCandidate.word_id).where(
            StudentVocabCandidate.student_id == student_id, StudentVocabCandidate.priority > 0))).scalars().all())
    out: dict = {}
    # 候选词(各来源)
    for src, w in (await db.execute(
        sa.select(StudentVocabCandidate.source, VocabularyWord)
        .join(VocabularyWord, VocabularyWord.id == StudentVocabCandidate.word_id)
        .where(StudentVocabCandidate.student_id == student_id).limit(limit))).all():
        out[w.id] = {"word_id": str(w.id), "word": w.word, "origin": src, "pinned": w.id in pinned}
    # 当前学期教材词
    pref = (student.preferred_textbook_version, student.preferred_grade, student.preferred_semester)
    if all(pref):
        rows = (await db.execute(
            sa.select(VocabularyWord)
            .join(CurriculumWord, CurriculumWord.word_id == VocabularyWord.id)
            .join(CurriculumUnit, CurriculumUnit.id == CurriculumWord.unit_id)
            .where(CurriculumUnit.textbook_version == pref[0], CurriculumUnit.grade == pref[1],
                   CurriculumUnit.semester == pref[2]).limit(limit))).scalars().all()
        for w in rows:
            out.setdefault(w.id, {"word_id": str(w.id), "word": w.word, "origin": "textbook", "pinned": w.id in pinned})
    return list(out.values())


async def pin_from_photo(db: AsyncSession, *, student_id: uuid.UUID, image_url: str,
                         priority: int = _DEFAULT_PRIORITY) -> dict:
    """拍照加词:豆包视觉 OCR 图片 → 抽英文词 → 词典命中者加入优先学。
    返回 {recognized, pinned:[词], not_found:[词]}。"""
    from app.services import doubao_vision_service as dv
    from app.services import upload_service
    # 桶对象私有 → 转预签名 GET,豆包才拉得到图
    text = await dv.recognize_page_text(upload_service.make_fetch_url(image_url))
    words = _words_from_text(text)
    if not words:
        return {"recognized": 0, "pinned": [], "not_found": []}
    hit = {w.word.lower(): w.id for w in (await db.execute(
        sa.select(VocabularyWord).where(sa.func.lower(VocabularyWord.word).in_(words)))).scalars().all()}
    pinned, not_found = [], []
    for w in words:
        if w in hit:
            await _upsert_pin(db, student_id=student_id, word_id=hit[w], source="photo", priority=max(1, priority))
            pinned.append(w)
        else:
            not_found.append(w)
    await db.flush()
    return {"recognized": len(words), "pinned": pinned, "not_found": not_found}
