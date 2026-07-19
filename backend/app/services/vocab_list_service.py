"""R5 通用词库(平台域,超管维护):导入权威考纲表 + 真题/教材频率增强。

词条共享 d5.VocabularyWord(import 来的词 source='import');词库元数据 vocab_list,
库内属性(rank/frequency/star)在 vocab_list_item。
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d5_learning import VocabularyWord
from app.models.d18_vocab_kg import VocabList, VocabListItem, VocabQuestion


async def create_list(
    db: AsyncSession, *, name: str, exam_level: str | None = None,
    source_type: str | None = None, maintained_by: uuid.UUID | None = None,
    status: str = "draft",
) -> VocabList:
    exists = (await db.execute(sa.select(VocabList).where(VocabList.name == name))).scalar_one_or_none()
    if exists is not None:
        raise AppError(code=409, message="同名词库已存在")
    vl = VocabList(id=uuid.uuid4(), name=name, exam_level=exam_level,
                   source_type=source_type, maintained_by=maintained_by, status=status)
    db.add(vl)
    await db.flush()
    return vl


async def list_lists(db: AsyncSession, *, status: str | None = None) -> list[VocabList]:
    stmt = sa.select(VocabList)
    if status is not None:
        stmt = stmt.where(VocabList.status == status)
    return list((await db.execute(stmt.order_by(VocabList.created_at.desc()))).scalars().all())


async def _get_or_create_word(db: AsyncSession, word: str) -> uuid.UUID:
    """按词形找词条(忽略大小写);无则建 import 占位词条(媒体/释义后续补)。"""
    wid = (await db.execute(
        sa.select(VocabularyWord.id).where(sa.func.lower(VocabularyWord.word) == word.lower())
    )).scalar_one_or_none()
    if wid is not None:
        return wid
    new_id = uuid.uuid4()
    db.add(VocabularyWord(id=new_id, word=word, definitions=[], difficulty=3,
                          type="word", source="import"))
    await db.flush()
    return new_id


async def add_items(db: AsyncSession, *, list_id: uuid.UUID, items: list[dict]) -> int:
    """批量加入词库条目。items: [{word|word_id, rank?, frequency?, star?, verified?}]。幂等。返回处理数。"""
    n = 0
    for it in items:
        wid = it.get("word_id") or await _get_or_create_word(db, it["word"])
        await db.execute(
            pg_insert(VocabListItem)
            .values(list_id=list_id, word_id=wid, rank=it.get("rank"),
                    frequency=it.get("frequency"), star=it.get("star", 0),
                    verified=it.get("verified", False))
            .on_conflict_do_update(
                index_elements=["list_id", "word_id"],
                set_={"rank": it.get("rank"), "frequency": it.get("frequency"),
                      "star": it.get("star", 0)},
            )
        )
        n += 1
    await db.flush()
    return n


_BAND_STAR = {"high": 3, "mid": 2, "low": 1, "none": 0}
_ITEM_SORT = {
    "freq": (VocabListItem.frequency.desc().nullslast(), VocabListItem.rank.asc().nullslast()),
    "rank": (VocabListItem.rank.asc().nullslast(), VocabListItem.frequency.desc().nullslast()),
    "word": (sa.func.lower(VocabularyWord.word).asc(),),
}


def _item_conds(list_id, *, q=None, band=None, source=None, verified=None):
    conds = [VocabListItem.list_id == list_id]
    if q and q.strip():
        conds.append(VocabularyWord.word.ilike(f"%{q.strip()}%"))
    if band in _BAND_STAR:
        conds.append(VocabListItem.star == _BAND_STAR[band])
    if source == "exam":
        conds.append(VocabListItem.added_from_exam.is_(True))
    elif source == "syllabus":
        conds.append(VocabListItem.added_from_exam.is_(False))
    if verified is not None:
        conds.append(VocabListItem.verified.is_(verified))
    return conds


# ── 词力通·考试出词(轨=词库:单词轨=考纲词汇库、短语轨=短语库;各库内按 star 分频档;P2)──
async def resolve_word_list(db: AsyncSession, *, exam_level: str) -> uuid.UUID | None:
    """单词轨:该考试目标(junior/senior)已上架的考纲词库 id;优先官方考纲。"""
    rows = (await db.execute(
        sa.select(VocabList.id, VocabList.source_type)
        .where(VocabList.exam_level == exam_level,
               VocabList.source_type != "phrase", VocabList.status == "published")
        .order_by(VocabList.updated_at.desc()))).all()
    if not rows:
        return None
    for lid, st in rows:
        if st == "official_syllabus":
            return lid
    return rows[0][0]


async def resolve_phrase_list(db: AsyncSession, *, exam_level: str) -> uuid.UUID | None:
    """短语轨:该考试目标的已上架短语库(source_type='phrase')。优先 exam_level 命中;
    短语库历史上 exam_level 常为空 → 回退按库名含「中考/高考」匹配(中考=junior/高考=senior)。"""
    rows = (await db.execute(
        sa.select(VocabList.id, VocabList.exam_level, VocabList.name)
        .where(VocabList.source_type == "phrase", VocabList.status == "published")
        .order_by(VocabList.updated_at.desc()))).all()
    for lid, lvl, _ in rows:
        if lvl == exam_level:
            return lid
    kw = "高考" if exam_level == "senior" else "中考"
    for lid, lvl, name in rows:
        if (lvl is None) and kw in (name or ""):
            return lid
    return None


def _band_case():
    """VocabListItem.star → 频档标签(3/2/1=高/中/低;其余=none 未分档兜底,防未反哺词库空屏)。"""
    return sa.case(
        (VocabListItem.star == 3, "high"),
        (VocabListItem.star == 2, "mid"),
        (VocabListItem.star == 1, "low"),
        else_="none")


def _band_star_cond(band: str):
    """频档 → star 条件。none=未分档(star 不在 1/2/3 或为空,含高考未反哺的 star0 词)。"""
    if band == "none":
        return sa.or_(VocabListItem.star.notin_([1, 2, 3]), VocabListItem.star.is_(None))
    if band in _BAND_STAR:
        return VocabListItem.star == _BAND_STAR[band]
    return None


async def exam_band_overview(db: AsyncSession, *, list_id: uuid.UUID, student_id: uuid.UUID) -> dict:
    """某词库(整库=一条轨)按频档(high/mid/low/none)汇总 {total, studied}。
    不按 vocabulary_words.type 切(短语库里多数条目 type=word,轨由「哪个库」决定)。
    studied = 该生该词有 VocabularyLearning 行(与课程/作业同口径)。"""
    from app.models.d5_learning import VocabularyLearning
    band = _band_case()
    learned = sa.case((VocabularyLearning.id.isnot(None), VocabListItem.word_id), else_=None)
    rows = (await db.execute(
        sa.select(band.label("band"),
                  sa.func.count(sa.func.distinct(VocabListItem.word_id)),
                  sa.func.count(sa.func.distinct(learned)))
        .outerjoin(VocabularyLearning,
                   (VocabularyLearning.word_id == VocabListItem.word_id)
                   & (VocabularyLearning.student_id == student_id))
        .where(VocabListItem.list_id == list_id)
        .group_by(band))).all()
    out: dict = {b: {"total": 0, "studied": 0} for b in ("high", "mid", "low", "none")}
    for b, total, studied in rows:
        if b in out:
            out[b] = {"total": int(total), "studied": int(studied)}
    return out


async def band_word_ids(db: AsyncSession, *, list_id: uuid.UUID, band: str) -> list[uuid.UUID]:
    """某词库 × 频档 的 word_id 列表(供 daily-task 限定词集;不按 type 过滤)。"""
    cond = _band_star_cond(band)
    if cond is None:
        return []
    rows = (await db.execute(
        sa.select(VocabListItem.word_id)
        .where(VocabListItem.list_id == list_id, cond))).scalars().all()
    return list(rows)


async def list_items(
    db: AsyncSession, *, list_id: uuid.UUID, skip: int = 0, limit: int = 100,
    q: str | None = None, band: str | None = None, source: str | None = None,
    verified: bool | None = None, sort: str = "freq",
) -> tuple[list[dict], int]:
    """搜索/筛选/排序/分页 列词条,返回 (items, 筛选后总数)。

    q=词模糊; band=high|mid|low|none(频档 star 3/2/1/0); source=syllabus|exam(考纲原生/真题补录);
    verified=已核; sort=freq(真题频次降)|rank(考纲排名升)|word(字母)。
    """
    conds = _item_conds(list_id, q=q, band=band, source=source, verified=verified)
    total = int((await db.execute(
        sa.select(sa.func.count())
        .select_from(VocabListItem)
        .join(VocabularyWord, VocabularyWord.id == VocabListItem.word_id)
        .where(*conds))).scalar_one())
    order = _ITEM_SORT.get(sort, _ITEM_SORT["freq"])
    rows = (await db.execute(
        sa.select(VocabListItem.word_id, VocabularyWord.word, VocabListItem.rank,
                  VocabListItem.frequency, VocabListItem.star, VocabListItem.verified,
                  VocabListItem.added_from_exam)
        .join(VocabularyWord, VocabularyWord.id == VocabListItem.word_id)
        .where(*conds).order_by(*order).offset(skip).limit(limit)
    )).all()
    items = [
        {"word_id": wid, "word": w, "rank": rank, "frequency": freq, "star": star,
         "verified": v, "added_from_exam": afe}
        for wid, w, rank, freq, star, v, afe in rows
    ]
    return items, total


async def list_stats(db: AsyncSession, *, list_id: uuid.UUID) -> dict:
    """词表统计:总词/有真题频次/真题补录/高中低频/已核 数。供页面统计条。"""
    r = (await db.execute(
        sa.select(
            sa.func.count(),
            sa.func.count().filter(VocabListItem.frequency > 0),
            sa.func.count().filter(VocabListItem.added_from_exam.is_(True)),
            sa.func.count().filter(VocabListItem.star == 3),
            sa.func.count().filter(VocabListItem.star == 2),
            sa.func.count().filter(VocabListItem.star == 1),
            sa.func.count().filter(VocabListItem.verified.is_(True)),
        ).where(VocabListItem.list_id == list_id))).one()
    total, with_freq, added, high, mid, low, verified = (int(x or 0) for x in r)
    return {"total": total, "with_freq": with_freq, "added": added,
            "high": high, "mid": mid, "low": low, "verified": verified}


async def delete_item(db: AsyncSession, *, list_id: uuid.UUID, word_id: uuid.UUID) -> None:
    """从词表移除一个词条(不删全局 VocabularyWord 主词)。"""
    await db.execute(sa.delete(VocabListItem).where(
        VocabListItem.list_id == list_id, VocabListItem.word_id == word_id))
    await db.flush()


# ─── 真题词频反哺(选中真题 → 分词/词形还原 → 频次 → 反哺考纲词表)───────────────

_LEMMA_NLP = None


def _get_lemma_nlp():
    """spaCy en_core_web_sm(带 lemmatizer,去掉 parser/ner 提速)。模块级缓存。"""
    global _LEMMA_NLP
    if _LEMMA_NLP is None:
        import spacy
        _LEMMA_NLP = spacy.load("en_core_web_sm", disable=["parser", "ner"])
    return _LEMMA_NLP


# 高/中/低频档阈值(出现在多少份不同真题卷);后续可挪到 system_configs
_FREQ_HIGH = 10
_FREQ_MID = 3
_ADD_MIN_FREQ = 3   # 补录门槛默认:出现 <3 卷的新词多为人名/OCR 噪声,不补录(可经参数下调)


def _bin_star(freq: int) -> int:
    if freq >= _FREQ_HIGH:
        return 3          # 高频
    if freq >= _FREQ_MID:
        return 2          # 中频
    if freq >= 1:
        return 1          # 低频
    return 0


def _paper_lemmas(nlp, text: str) -> tuple[set[str], set[str]]:
    """一份真题文本 → (全部实义 lemma 去重, 其中内容词 lemma)。

    内容词 = 名/动/形/副(用于补录候选,排除虚词/人名 PROPN)。全部集合用于给考纲词匹配频次
    (考纲含 about/and 等虚词,不能只留内容词)。人名(PROPN)一律排除。
    """
    alls: set[str] = set()
    content: set[str] = set()
    doc = nlp(text[:900_000])   # spaCy 单文档上限保护
    for t in doc:
        if not t.is_alpha or t.pos_ == "PROPN":
            continue
        lm = t.lemma_.lower().strip()
        if len(lm) < 2:
            continue
        alls.add(lm)
        if t.pos_ in ("NOUN", "VERB", "ADJ", "ADV"):
            content.add(lm)
    return alls, content


def _lemma_one(nlp, word: str) -> str:
    doc = nlp(word.strip())
    for t in doc:
        if t.is_alpha:
            return t.lemma_.lower()
    return word.strip().lower()


async def rebuild_exam_frequency(
    db: AsyncSession, *, exam_type: str = "中考", list_name: str = "中考考纲词汇(1600)",
    add_min_freq: int | None = None,
) -> dict:
    """选中(全部)某考试真题 → 词形还原统计词频(整卷去重防重算)→ 反哺对应考纲词表:
    给命中的考纲词写「真题卷频次(frequency)+高/中/低频档(star)」,真题里出现但考纲未收录的词
    (≥add_min_freq 卷、内容词、非人名)补录进该表(added_from_exam=true)。返回统计摘要。

    add_min_freq:补录门槛,不传用默认 _ADD_MIN_FREQ(=3,更去噪);调低会多补但夹带更多人名/OCR 噪声。
    """
    import hashlib
    import re as _re
    from collections import Counter
    from app.models.d16_question_domain import PlatformQuestion, PlatformPaper

    add_min = add_min_freq if add_min_freq and add_min_freq >= 1 else _ADD_MIN_FREQ

    vl = (await db.execute(sa.select(VocabList).where(VocabList.name == list_name))).scalar_one_or_none()
    if vl is None:
        raise AppError(code=404, message=f"未找到词表「{list_name}」")

    # 1) 取该考试所有真题(type='real')题面,按 paper 归并。
    #    只取「题干 stem + 选项 options」= 真题实际内容;不含 explanation(那是解析版编者注,非真题原词)。
    rows = (await db.execute(
        sa.select(PlatformQuestion.paper_id, PlatformPaper.name,
                  PlatformQuestion.stem, PlatformQuestion.options)
        .join(PlatformPaper, PlatformPaper.id == PlatformQuestion.paper_id)
        .where(PlatformQuestion.type == "real", PlatformPaper.exam_type == exam_type)
    )).all()
    paper_parts: dict = {}
    paper_name: dict = {}
    for pid, name, stem, opts in rows:
        paper_name.setdefault(pid, name or "")
        buf = paper_parts.setdefault(pid, [])
        if stem:
            buf.append(stem)
        if isinstance(opts, list):
            buf.extend(str(o) for o in opts)

    # 2) 去重防重复计算:同一场考试的「原卷版/解析版/重复上传」只算一份。
    #    主键 = 归一化卷名(去括号版本标记 + 空白 + 真题/英语/试题 填充);卷名空时退回内容 hash。
    def _norm_name(nm: str) -> str:
        s = _re.sub(r"[（(].*?[)）]", "", nm.lower())          # 去(原卷版)/(解析版)/(word版)…
        s = _re.sub(r"[\s\-_·]+", "", s)
        for junk in ("真题", "英语", "试题", "试卷", "版"):
            s = s.replace(junk, "")
        return s
    seen: set[str] = set()
    unique_texts: list[str] = []
    for pid, parts in paper_parts.items():
        full = "\n".join(parts)
        key = _norm_name(paper_name.get(pid, "")) or hashlib.md5(
            _re.sub(r"\s+", "", full).lower().encode("utf-8")).hexdigest()
        if not key or key in seen:
            continue
        seen.add(key)
        unique_texts.append(full)

    # 空卷防护:该考试没有真题就直接报错、不动词表(否则下面复位会把已有考纲频次清空)
    if not unique_texts:
        raise AppError(code=400, message=f"「{exam_type}」暂无真题(platform_question type='real'),未做任何改动")

    # 2.5) 复位:清掉该表本轮真题频次状态,保证可重复执行(幂等,不累积陈旧补录)。
    #      考纲原生词只清 frequency/star;上轮真题补录的词直接删除(合格的会在下面重新补回)。
    await db.execute(
        sa.update(VocabListItem)
        .where(VocabListItem.list_id == vl.id, VocabListItem.added_from_exam.is_(False))
        .values(frequency=None, star=0))
    await db.execute(
        sa.delete(VocabListItem)
        .where(VocabListItem.list_id == vl.id, VocabListItem.added_from_exam.is_(True)))
    await db.flush()

    # 3) 逐卷分词+词形还原,累计「出现卷数」= 词频;并留一份归一化整卷文本供多词词条精确匹配
    nlp = _get_lemma_nlp()
    freq: Counter = Counter()
    content_lemmas: set[str] = set()
    norm_texts: list[str] = []
    for txt in unique_texts:
        alls, content = _paper_lemmas(nlp, txt)
        for lm in alls:
            freq[lm] += 1
        content_lemmas |= content
        norm_texts.append(_re.sub(r"\s+", " ", txt.lower()))

    # 4) 载入考纲词表条目,与真题频次匹配。
    #    单词条:按词形还原后的 lemma 命中真题频次;多词词条(如 The Great Wall):按「整卷是否包含该短语」
    #    精确统计出现卷数(不能用首词 lemma,否则会误命中 the/a 等虚词导致频次爆表)。
    items = (await db.execute(
        sa.select(VocabListItem.word_id, VocabularyWord.word)
        .join(VocabularyWord, VocabularyWord.id == VocabListItem.word_id)
        .where(VocabListItem.list_id == vl.id)
    )).all()
    covered: set[str] = set()
    matched = 0
    high = mid = low = 0
    for wid, w in items:
        wl = w.strip().lower()
        if " " in wl:                       # 多词短语/专名 → 整卷精确包含计数
            needle = _re.sub(r"\s+", " ", wl)
            f = sum(1 for nt in norm_texts if needle in nt)
            covered.add(wl)
        else:                               # 单词 → lemma 频次
            lm = _lemma_one(nlp, w)
            covered.add(lm)
            covered.add(wl)
            f = freq.get(lm, 0) or freq.get(wl, 0)
        star = _bin_star(f)
        await db.execute(
            sa.update(VocabListItem)
            .where(VocabListItem.list_id == vl.id, VocabListItem.word_id == wid)
            .values(frequency=f, star=star))
        if f > 0:
            matched += 1
            high += star == 3
            mid += star == 2
            low += star == 1

    # 5) 补录:真题里有、考纲没有、内容词、非人名、≥门槛卷
    added = 0
    for lm, f in freq.items():
        if lm in covered or lm not in content_lemmas or f < add_min:
            continue
        wid = await _get_or_create_word(db, lm)
        star = _bin_star(f)
        await db.execute(
            pg_insert(VocabListItem)
            .values(list_id=vl.id, word_id=wid, frequency=f, star=star, added_from_exam=True)
            .on_conflict_do_update(
                index_elements=["list_id", "word_id"],
                set_={"frequency": f, "star": star, "added_from_exam": True}))
        added += 1
        high += star == 3
        mid += star == 2
        low += star == 1
    await db.flush()

    return {
        "list_name": list_name, "exam_type": exam_type,
        "papers_total": len(paper_parts), "papers_unique": len(unique_texts),
        "papers_duplicated": len(paper_parts) - len(unique_texts),
        "exam_word_forms": len(freq),
        "syllabus_words": len(items), "matched": matched, "added": added,
        "freq_high": high, "freq_mid": mid, "freq_low": low,
        "thresholds": {"high": _FREQ_HIGH, "mid": _FREQ_MID, "add_min": add_min},
    }


async def recompute_star_from_questions(db: AsyncSession, *, list_id: uuid.UUID) -> int:
    """真题频率增强:按词在 vocab_question 的出现次数给库内 star 打分(0–5)。返回更新条目数。"""
    counts = dict((await db.execute(
        sa.select(VocabQuestion.word_id, sa.func.count())
        .join(VocabListItem, VocabListItem.word_id == VocabQuestion.word_id)
        .where(VocabListItem.list_id == list_id)
        .group_by(VocabQuestion.word_id)
    )).all())
    updated = 0
    for wid, cnt in counts.items():
        star = min(5, int(cnt))
        await db.execute(
            sa.update(VocabListItem)
            .where(VocabListItem.list_id == list_id, VocabListItem.word_id == wid)
            .values(star=star)
        )
        updated += 1
    await db.flush()
    return updated
