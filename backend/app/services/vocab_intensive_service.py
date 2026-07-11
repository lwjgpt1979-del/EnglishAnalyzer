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


async def approve_review(db: AsyncSession, *, review_id: uuid.UUID,
                         phonetic: str | None = None, definitions=None) -> bool:
    """admin:审核通过 → 词加入词库 VocabularyWord + 标 approved。definitions 由 admin 填(缺省空列表)。"""
    from app.models.d28_vocab_review import VocabReview
    r = await db.get(VocabReview, review_id)
    if r is None or r.status != "pending":
        return False
    # 词库已存在则不重复建
    exists = (await db.execute(
        select(VocabularyWord.id).where(func.lower(VocabularyWord.word) == r.word_norm).limit(1))).first()
    if exists is None:
        db.add(VocabularyWord(id=uuid.uuid4(), word=r.word,
                              phonetic=phonetic, definitions=definitions or []))
    r.status = "approved"
    await db.commit()
    return True


async def reject_review(db: AsyncSession, *, review_id: uuid.UUID) -> bool:
    from app.models.d28_vocab_review import VocabReview
    r = await db.get(VocabReview, review_id)
    if r is None or r.status != "pending":
        return False
    r.status = "rejected"
    await db.commit()
    return True
