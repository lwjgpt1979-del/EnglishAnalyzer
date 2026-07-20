"""错题关系网(以词为中心):把每道错题的选项按角色落库——answer(主:正确答案)/ distractor(次:干扰项);
再从任一词拉出它的主/次错题 + 该词全局考点(供辐射图关系词 + tab)。选项级归一、无 LLM,查看即生成 + 幂等。
"""
from __future__ import annotations

import re
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d5_learning import VocabularyWord
from app.models.d16_question_domain import WrongRecord
from app.models.d18_vocab_kg import StudentWrongWord
from app.services.wrong_relation_service import _wrong_options   # 复用选项解析(结构化/题干内联)

_LETTER = "ABCD"
_PREFIX = re.compile(r'^[A-Da-d][.、)．]\s*')


def _norm_opt(text: str) -> str:
    """选项文本 → 去字母前缀、去首尾标点空白。"""
    return _PREFIX.sub("", str(text or "")).strip().strip(".;,、。 ").strip()


def _answer_index(options: list[str], correct_answer: str) -> int:
    """判断正确答案是第几个选项。correct_answer 可能是字母(B)或选项文本。找不到→-1。"""
    ca = (correct_answer or "").strip()
    if not ca or not options:
        return -1
    if len(ca) == 1 and ca.upper() in _LETTER:
        idx = _LETTER.index(ca.upper())
        return idx if idx < len(options) else -1
    cal = _norm_opt(ca).lower()
    if not cal:
        return -1
    for i, o in enumerate(options):
        ol = _norm_opt(o).lower()
        if ol and (ol == cal or cal in ol or ol in cal):
            return i
    return -1


async def _word_id_of(db: AsyncSession, text: str, *, create: bool) -> uuid.UUID | None:
    """选项文本 → vocabulary_words id。命中 lower(word) 复用;create=True(仅答案词)时未命中入库。"""
    t = (text or "").strip()
    if not t:
        return None
    row = (await db.execute(
        sa.select(VocabularyWord.id).where(sa.func.lower(VocabularyWord.word) == t.lower()).limit(1))).first()
    if row:
        return row[0]
    if not create:
        return None
    wid = uuid.uuid4()
    db.add(VocabularyWord(id=wid, word=t, definitions=[], difficulty=3,
                          type=("phrase" if " " in t else "word"), source="wrong"))
    await db.flush()
    return wid


async def index_wrong_record(db: AsyncSession, *, student_id: uuid.UUID, wrong_record_id: uuid.UUID) -> None:
    """把一道错题的选项按 主(答案)/次(干扰) 落 student_wrong_word。无 LLM。幂等(已有行即跳过)。
    答案词未命中词库则入库;干扰项只链已有词(不为杂项造词条)。"""
    done = (await db.execute(
        sa.select(StudentWrongWord.id).where(
            StudentWrongWord.wrong_record_id == wrong_record_id,
            StudentWrongWord.student_id == student_id).limit(1))).first()
    if done:
        return
    wr = await db.get(WrongRecord, wrong_record_id)
    if wr is None or wr.student_id != student_id:
        return
    _stem, opts = await _wrong_options(db, wr)
    if not opts:
        # 填空题(无选项):正确答案本身即"主"词;多空按分隔符拆(每个都算 answer,无干扰项)
        parts = re.split(r'[;,、/，；|]|\s{2,}', wr.correct_answer or "")
        rows: list[dict] = []
        seen: set = set()
        for p in parts:
            a = _norm_opt(p)
            if not a or len(a) > 40 or len(a.split()) > 4:   # 太长/太多词→像句子答案,跳过
                continue
            wid = await _word_id_of(db, a, create=True)
            if wid and wid not in seen:
                seen.add(wid)
                rows.append({"id": uuid.uuid4(), "student_id": student_id, "word_id": wid,
                             "wrong_record_id": wrong_record_id, "role": "answer"})
        if rows:
            await db.execute(pg_insert(StudentWrongWord).values(rows)
                             .on_conflict_do_nothing(index_elements=["student_id", "word_id", "wrong_record_id"]))
            await db.commit()
        return
    ai = _answer_index(opts, wr.correct_answer or "")
    rows: list[dict] = []
    seen: set = set()
    for i, o in enumerate(opts):
        role = "answer" if i == ai else "distractor"
        wid = await _word_id_of(db, _norm_opt(o), create=(role == "answer"))
        if wid is None or wid in seen:
            continue
        seen.add(wid)
        rows.append({"id": uuid.uuid4(), "student_id": student_id, "word_id": wid,
                     "wrong_record_id": wrong_record_id, "role": role})
    if rows:
        await db.execute(pg_insert(StudentWrongWord).values(rows)
                         .on_conflict_do_nothing(index_elements=["student_id", "word_id", "wrong_record_id"]))
    await db.commit()


async def ensure_indexed(db: AsyncSession, *, student_id: uuid.UUID) -> None:
    """索引该生所有尚未索引的错题(无 LLM,批量;支持'拉出某词全部错题')。"""
    indexed = sa.select(StudentWrongWord.wrong_record_id).where(
        StudentWrongWord.student_id == student_id).distinct().scalar_subquery()
    recs = (await db.execute(
        sa.select(WrongRecord.id).where(
            WrongRecord.student_id == student_id,
            WrongRecord.id.notin_(indexed)))).scalars().all()
    for rid in recs:
        try:
            await index_wrong_record(db, student_id=student_id, wrong_record_id=rid)
        except Exception:   # noqa: BLE001
            await db.rollback()


def _zh(w: VocabularyWord | None) -> str:
    if w is None:
        return ""
    defs = w.definitions if isinstance(w.definitions, list) else []
    return next((str(d.get("meaning")) for d in defs if isinstance(d, dict) and d.get("meaning")), "")


def _brief(w: WrongRecord) -> dict:
    return {"wrong_record_id": str(w.id), "stem": (w.stem or "")[:90],
            "student_answer": w.student_answer or "", "correct_answer": w.correct_answer or "",
            "source": w.source_label or "", "question_type": w.question_type or ""}


async def word_wrong_net(db: AsyncSession, *, student_id: uuid.UUID, word_id: uuid.UUID) -> dict:
    """以词为中心的错题网:该词全局考点(dims,含关系词供辐射图)+ 主错题(role=answer)+ 次错题(role=distractor)。"""
    await ensure_indexed(db, student_id=student_id)
    rows = (await db.execute(
        sa.select(StudentWrongWord).where(
            StudentWrongWord.student_id == student_id,
            StudentWrongWord.word_id == word_id))).scalars().all()
    role_by_rec = {r.wrong_record_id: r.role for r in rows}
    recs: dict = {}
    if role_by_rec:
        wrs = (await db.execute(
            sa.select(WrongRecord).where(WrongRecord.id.in_(list(role_by_rec.keys()))))).scalars().all()
        recs = {w.id: w for w in wrs}
    main = [_brief(recs[rid]) for rid, role in role_by_rec.items() if role == "answer" and rid in recs]
    secondary = [_brief(recs[rid]) for rid, role in role_by_rec.items() if role == "distractor" and rid in recs]

    w = await db.get(VocabularyWord, word_id)
    from app.services import word_kp_service
    kp = await word_kp_service.word_kp_out(db, word_id=word_id, student_id=student_id)
    return {"word_id": str(word_id), "word": w.word if w else "", "zh": _zh(w),
            "is_phrase": (w.type == "phrase") if w else False,
            "dims": kp.get("dims", []), "main": main, "secondary": secondary}


async def word_net_for_record(db: AsyncSession, *, student_id: uuid.UUID, wrong_record_id: uuid.UUID) -> dict:
    """从一道错题进入:中心 = 该题答案词。索引本题 → 定位答案词 → 出以词为中心的网。"""
    await index_wrong_record(db, student_id=student_id, wrong_record_id=wrong_record_id)
    ans = (await db.execute(
        sa.select(StudentWrongWord.word_id).where(
            StudentWrongWord.student_id == student_id,
            StudentWrongWord.wrong_record_id == wrong_record_id,
            StudentWrongWord.role == "answer").limit(1))).first()
    center = ans[0] if ans else None
    if center is None:
        wr = await db.get(WrongRecord, wrong_record_id)
        center = wr.vocab_word_id if wr else None
    if center is None:
        return {"word_id": None, "word": "", "zh": "", "is_phrase": False,
                "dims": [], "main": [], "secondary": []}
    return await word_wrong_net(db, student_id=student_id, word_id=center)
