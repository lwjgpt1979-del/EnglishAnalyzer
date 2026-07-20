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
from app.models.d18_vocab_kg import StudentWrongWord, VocabWordSense
from app.services.wrong_relation_service import _wrong_options   # 复用选项解析(结构化/题干内联)

_LETTER = "ABCD"
_PREFIX = re.compile(r'^[A-Da-d][.、)．]\s*')


def _norm_opt(text: str) -> str:
    """选项文本 → 去字母前缀、去首尾标点空白。"""
    return _PREFIX.sub("", str(text or "")).strip().strip(".;,、。 ").strip()


_SEP = re.compile(r'[;,、；，/|]|\s{2,}')


def _split_points(text: str) -> list[str]:
    """把一个答案/选项拆成多个「正确点/考点」(按 ; , 、 / | 或多空格分隔);
    如 'May; can't'→['May',"can't"]、'more cheerful, funnier'→['more cheerful','funnier']。
    去空、去过长(>40 字符或 >4 词,像句子答案)。"""
    out = []
    for part in _SEP.split(_norm_opt(text)):
        p = _norm_opt(part)
        if p and len(p) <= 40 and len(p.split()) <= 4:
            out.append(p)
    return out


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
    rows: list[dict] = []
    seen: set = set()

    async def _add(text: str, role: str):
        wid = await _word_id_of(db, text, create=(role == "answer"))
        if wid is not None and wid not in seen:
            seen.add(wid)
            rows.append({"id": uuid.uuid4(), "student_id": student_id, "word_id": wid,
                         "wrong_record_id": wrong_record_id, "role": role})

    if not opts:
        # 填空题:正确答案的每个「正确点」= 主(多空/多值各成一词,无干扰项)
        for p in _split_points(wr.correct_answer or ""):
            await _add(p, "answer")
    else:
        ai = _answer_index(opts, wr.correct_answer or "")
        # 先答案选项的各正确点(May; can't → May + can't,均 answer,优先占坑)
        if 0 <= ai < len(opts):
            for p in _split_points(opts[ai]):
                await _add(p, "answer")
        # 再干扰选项的各点(拆成 distractor)
        for i, o in enumerate(opts):
            if i == ai:
                continue
            for p in _split_points(o):
                await _add(p, "distractor")
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


async def _classify_sense(db: AsyncSession, *, word: str, senses: list[VocabWordSense], wr: WrongRecord) -> uuid.UUID | None:
    """LLM 判该错题考目标词的哪个义项。senses 已按 sort 排;单义/dev-mock→首义项。"""
    if not senses:
        return None
    if len(senses) == 1:
        return senses[0].id
    from app.services.llm_provider import complete_json, fast_model, is_llm_dev_mode
    if is_llm_dev_mode():
        return senses[0].id
    listing = "\n".join(f"{i}. {s.gloss_zh}({s.pos or ''})" for i, s in enumerate(senses))
    system = ("给定一道英语题的题干/正确答案/解析,和目标词的若干义项(带编号),判断**这道题考的是目标词的哪个义项**。"
              "只输出 JSON:{\"sense\": 编号}。")
    d = await complete_json(
        system_prompt=system,
        user_prompt=f"目标词:{word}\n题干:{(wr.stem or '')[:200]}\n正确答案:{wr.correct_answer or ''}\n"
                    f"解析:{(wr.explanation or '')[:200]}\n义项:\n{listing}\n返回 JSON:",
        max_tokens=100, model=fast_model(), feature="wrong_sense_match",
        validate=lambda x: isinstance(x.get("sense"), int))
    if d and isinstance(d.get("sense"), int) and 0 <= d["sense"] < len(senses):
        return senses[d["sense"]].id
    return senses[0].id


async def _ensure_record_sense(db: AsyncSession, *, student_id: uuid.UUID,
                               wrong_record_id: uuid.UUID, word_id: uuid.UUID) -> uuid.UUID | None:
    """定位并缓存该错题考中心词的哪个义项(student_wrong_word.sense_id);已缓存直接返回。"""
    row = (await db.execute(
        sa.select(StudentWrongWord).where(
            StudentWrongWord.student_id == student_id,
            StudentWrongWord.word_id == word_id,
            StudentWrongWord.wrong_record_id == wrong_record_id).limit(1))).scalar_one_or_none()
    if row is not None and row.sense_id is not None:
        return row.sense_id
    from app.services import word_kp_service
    await word_kp_service.ensure_word_kp(db, word_id=word_id)   # 保证义项已生成
    senses = (await db.execute(
        sa.select(VocabWordSense).where(VocabWordSense.word_id == word_id)
        .order_by(VocabWordSense.sort))).scalars().all()
    wr = await db.get(WrongRecord, wrong_record_id)
    sid = await _classify_sense(db, word=(wr.correct_answer or "").strip() or "", senses=senses, wr=wr) if wr else None
    if sid is not None and row is not None:
        row.sense_id = sid
        await db.commit()
    return sid


async def word_wrong_net(db: AsyncSession, *, student_id: uuid.UUID, word_id: uuid.UUID,
                         sense_id: uuid.UUID | None = None) -> dict:
    """以词为中心的错题网:该词考点(按 sense_id 定的义项,缺则主义项)+ 主错题(role=answer)+ 次错题(role=distractor)。"""
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
    kp = await word_kp_service.word_kp_out(db, word_id=word_id, sense_id=sense_id, student_id=student_id)
    return {"word_id": str(word_id), "word": w.word if w else "", "zh": _zh(w),
            "is_phrase": (w.type == "phrase") if w else False,
            "sense_id": kp["senses"][0]["sense_id"] if kp.get("senses") else None,
            "gloss": kp.get("gloss", ""), "senses": [{"sense_id": s["sense_id"], "gloss": s["gloss"], "pos": s["pos"]} for s in kp.get("senses", [])],
            "dims": kp.get("dims", []), "main": main, "secondary": secondary}


async def word_net_for_record(db: AsyncSession, *, student_id: uuid.UUID, wrong_record_id: uuid.UUID) -> dict:
    """从一道错题进入:中心 = 该题第一个答案词;返回本题全部答案词(多空/多正确点供前端切换),
    考点限定为该题命中的义项。"""
    await index_wrong_record(db, student_id=student_id, wrong_record_id=wrong_record_id)
    ans_ids = (await db.execute(
        sa.select(StudentWrongWord.word_id).where(
            StudentWrongWord.student_id == student_id,
            StudentWrongWord.wrong_record_id == wrong_record_id,
            StudentWrongWord.role == "answer").order_by(StudentWrongWord.created_at))).scalars().all()
    center = ans_ids[0] if ans_ids else None
    if center is None:
        wr = await db.get(WrongRecord, wrong_record_id)
        center = wr.vocab_word_id if wr else None
    if center is None:
        return {"word_id": None, "word": "", "zh": "", "is_phrase": False, "sense_id": None,
                "gloss": "", "senses": [], "dims": [], "main": [], "secondary": [], "answers": []}
    sid = await _ensure_record_sense(db, student_id=student_id, wrong_record_id=wrong_record_id, word_id=center)
    net = await word_wrong_net(db, student_id=student_id, word_id=center, sense_id=sid)
    # 本题全部答案词(供前端 chip 切换;单答案则一个)
    answers = []
    if ans_ids:
        ws = (await db.execute(sa.select(VocabularyWord).where(VocabularyWord.id.in_(ans_ids)))).scalars().all()
        wmap = {w.id: w for w in ws}
        answers = [{"word_id": str(wid), "word": wmap[wid].word, "zh": _zh(wmap.get(wid))}
                   for wid in ans_ids if wid in wmap]
    net["answers"] = answers
    return net
