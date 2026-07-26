"""单词释义补全:填 vocabulary_words 缺失的 definitions(+音标)。

分层(免费准 → 兜底):① dict_ecdict(ECDICT·MIT 英汉词典,768k 词条)命中即用;
② 命中不到 → LLM 兜底生成(vocab_definition_gen 快档)。结果落 definitions(天然缓存)。
用于:存量回填(backfill_empty)+ 运行时「查看即生成」(ensure_word_definition,接进 ensure_word_media)。
"""
from __future__ import annotations

import re

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d5_learning import VocabularyWord
from app.services import llm_provider

# 释义行首词性 token(词典 translation 用):vt./vi./n./a./adj./ad./conj./prep./art./pron./num./int./aux./…
_POS_RE = re.compile(r"^\s*((?:[a-z]{1,5}\.)+)\s*", re.I)


def _parse_translation(translation: str, *, max_senses: int = 2) -> list[dict]:
    """ECDICT translation(多义分隔:字面 \\n 或真换行,行首带词性)→ [{pos, meaning}]。取前 max_senses 义。"""
    out: list[dict] = []
    for line in re.split(r"\\n|\n", translation or ""):
        line = line.strip()
        if not line:
            continue
        m = _POS_RE.match(line)
        pos = (m.group(1) if m else "").strip()
        meaning = (line[m.end():] if m else line).strip(" ,;；")
        if meaning:
            out.append({"pos": pos, "meaning": meaning[:120]})
        if len(out) >= max_senses:
            break
    return out


def _lemma_candidates(word: str) -> list[str]:
    """轻量词形还原候选(免 spaCy 加载):原形 + 常见去屈折。词典先精确、再候选匹配。"""
    w = word.lower().strip()
    cands = [w]
    if len(w) > 4 and w.endswith("ies"):
        cands.append(w[:-3] + "y")
    if len(w) > 3 and w.endswith("es"):
        cands.append(w[:-2])
    if len(w) > 3 and w.endswith("s"):
        cands.append(w[:-1])
    if len(w) > 4 and w.endswith("ing"):
        cands += [w[:-3], w[:-3] + "e"]
    if len(w) > 4 and w.endswith("ed"):
        cands += [w[:-2], w[:-1], w[:-2] + "e"]
    seen, uniq = set(), []
    for c in cands:
        if c and c not in seen:
            seen.add(c); uniq.append(c)
    return uniq


async def dict_lookup(db: AsyncSession, word: str) -> dict | None:
    """查 dict_ecdict:精确 word_lower 优先,再按去屈折候选。返回 {phonetic, translation, tag} 或 None。"""
    cands = _lemma_candidates(word)
    row = (await db.execute(sa.text(
        "SELECT phonetic, translation, tag FROM dict_ecdict "
        "WHERE word_lower = ANY(:cands) AND translation IS NOT NULL "
        "ORDER BY array_position(:cands, word_lower) LIMIT 1"
    ), {"cands": cands})).first()
    if row is None:
        return None
    return {"phonetic": row[0], "translation": row[1], "tag": row[2]}


async def _gen_definition_llm(word: str) -> list[dict]:
    """LLM 兜底:词典没有的词,快档生成中文释义(1-2 义,带词性)。"""
    if llm_provider.is_llm_dev_mode():
        return [{"pos": "", "meaning": f"(dev){word} 的释义"}]
    data = await llm_provider.complete_json(
        system_prompt=(
            "你是英汉词典。给出该英文词的中文释义,只返回 JSON:"
            '{"senses":[{"pos":"词性缩写如 n./v./adj.(无则空串)","meaning":"简洁中文释义"}]}。'
            "最多 2 个主要义项;meaning 用中文,简洁准确。"),
        user_prompt=f"英文词:{word}", max_tokens=200,
        model=llm_provider.fast_model(), disable_thinking=True,
        feature="vocab_definition_gen") or {}
    out = []
    for s in (data.get("senses") or [])[:2]:
        mn = str(s.get("meaning") or "").strip()
        if mn:
            out.append({"pos": str(s.get("pos") or "").strip(), "meaning": mn[:120]})
    return out


def _has_defs(w: VocabularyWord) -> bool:
    return isinstance(w.definitions, list) and len(w.definitions) > 0


async def ensure_word_definition(db: AsyncSession, w: VocabularyWord, *, allow_llm: bool = True) -> bool:
    """补该词释义(已有则跳过)。dict 优先,未命中且 allow_llm 时 LLM 兜底。
    顺带补音标(缺则填)+ 考纲 tag 反哺留待上层。返回是否新填。不 commit(由调用方)。"""
    if _has_defs(w):
        return False
    defs, src_phonetic = [], None
    hit = await dict_lookup(db, w.word)
    if hit:
        defs = _parse_translation(hit["translation"])
        src_phonetic = hit.get("phonetic")
    if not defs and allow_llm:
        defs = await _gen_definition_llm(w.word)
    if not defs:
        return False
    w.definitions = defs
    if src_phonetic and not (w.phonetic or "").strip():
        w.phonetic = src_phonetic
    return True


async def backfill_empty(db: AsyncSession, *, limit: int = 100000, allow_llm: bool = False) -> dict:
    """存量回填空释义词:dict_ecdict 优先(免费);allow_llm=False 时批量只用词典、不烧 LLM。
    返回 {scanned, filled, dict_hit, llm_filled, miss}。miss=词典没有、留给运行时 LLM 兜底。"""
    ids = [r[0] for r in (await db.execute(sa.text(
        "SELECT id FROM vocabulary_words WHERE definitions IS NULL "
        "OR (jsonb_typeof(definitions)='array' AND jsonb_array_length(definitions)=0) LIMIT :lim"
    ), {"lim": limit})).all()]
    scanned = filled = dict_hit = llm_filled = miss = 0
    for i in range(0, len(ids), 500):
        batch = ids[i:i + 500]
        rows = (await db.execute(
            sa.select(VocabularyWord).where(VocabularyWord.id.in_(batch)))).scalars().all()
        for w in rows:
            scanned += 1
            hit = await dict_lookup(db, w.word)
            if hit:
                defs = _parse_translation(hit["translation"])
                if defs:
                    w.definitions = defs
                    if hit.get("phonetic") and not (w.phonetic or "").strip():
                        w.phonetic = hit["phonetic"]
                    filled += 1; dict_hit += 1
                    continue
            if allow_llm and await ensure_word_definition(db, w, allow_llm=True):
                filled += 1; llm_filled += 1
            else:
                miss += 1
        await db.commit()
    return {"scanned": scanned, "filled": filled, "dict_hit": dict_hit,
            "llm_filled": llm_filled, "miss": miss}
