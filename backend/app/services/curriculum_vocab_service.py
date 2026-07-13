"""单元「重点单词」↔ 词力通(vocabulary_words)关联 service。

复用既有 junction 表 curriculum_words(unit_id, word_id, is_core, sort_order):
  - 列出单元已挂的重点词(连词力通词条的释义/音标);
  - 按词形 get-or-create 词条(无则在词力通新建,source=textbook);
  - 多图 OCR 解析出的「单词/词组」批量挂到单元(命中复用、缺失新建)。
单词与词组都落 vocabulary_words(type=word|phrase),词组即多词条目。
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d4_knowledge import CurriculumWord
from app.models.d5_learning import VocabularyWord


def _first_meaning(defs) -> str | None:
    """从 definitions 取首个中文释义(带词性前缀)。统一格式 {meaning,pos};兼容旧 {zh,part_of_speech}。"""
    if not defs or not isinstance(defs, list):
        return None
    d0 = defs[0] or {}
    zh = (d0.get("meaning") or d0.get("zh") or "").strip()
    pos = (d0.get("pos") or d0.get("part_of_speech") or "").strip()
    if not zh:
        return None
    return f"{pos} {zh}".strip() if pos else zh


async def list_unit_words(db: AsyncSession, *, unit_id: uuid.UUID) -> list[dict]:
    """单元已挂的重点词:[{word_id, word, phonetic, meaning, type, is_core, sort_order}]。"""
    rows = (await db.execute(
        sa.select(CurriculumWord.word_id, CurriculumWord.is_core, CurriculumWord.sort_order,
                  VocabularyWord.word, VocabularyWord.phonetic,
                  VocabularyWord.definitions, VocabularyWord.type)
        .join(VocabularyWord, VocabularyWord.id == CurriculumWord.word_id)
        .where(CurriculumWord.unit_id == unit_id)
        .order_by(CurriculumWord.sort_order, VocabularyWord.word))).all()
    return [{
        "word_id": str(r.word_id), "word": r.word, "phonetic": r.phonetic,
        "meaning": _first_meaning(r.definitions), "type": r.type or "word",
        "is_core": bool(r.is_core), "sort_order": r.sort_order,
    } for r in rows]


async def _get_or_create_word(db: AsyncSession, *, word: str, phonetic: str | None,
                              meaning: str | None, pos: str | None, wtype: str) -> tuple[uuid.UUID, bool]:
    """按词形(忽略大小写)找词条;无则在词力通新建。返回 (word_id, created)。"""
    norm = word.strip()
    existing = (await db.execute(
        sa.select(VocabularyWord).where(sa.func.lower(VocabularyWord.word) == norm.lower())
        .limit(1))).scalar_one_or_none()
    if existing is not None:
        # 补全:原词条无音标/释义而本次 OCR 带了,则回填(不覆盖已有)
        changed = False
        if phonetic and not existing.phonetic:
            existing.phonetic = phonetic; changed = True
        if meaning and not existing.definitions:
            existing.definitions = [{"meaning": meaning, "pos": pos or ""}]; changed = True
        if changed:
            await db.flush()
        return existing.id, False
    new_id = uuid.uuid4()
    defs = [{"meaning": meaning, "pos": pos or ""}] if meaning else []
    db.add(VocabularyWord(id=new_id, word=norm, phonetic=(phonetic or None),
                          definitions=defs, difficulty=3,
                          type=("phrase" if wtype == "phrase" else "word"), source="textbook"))
    await db.flush()
    return new_id, True


async def link_unit_words(db: AsyncSession, *, unit_id: uuid.UUID, items: list[dict],
                          is_core: bool = True) -> dict:
    """把一批 {word, phonetic?, meaning?, pos?, type?} 挂到单元(命中复用、缺失新建)。幂等。"""
    # 起始 sort_order = 当前最大 + 1
    base = (await db.execute(sa.select(sa.func.coalesce(sa.func.max(CurriculumWord.sort_order), -1))
                             .where(CurriculumWord.unit_id == unit_id))).scalar_one()
    order = int(base) + 1
    linked = created = 0
    seen: set[uuid.UUID] = set()
    for it in items:
        word = (it.get("word") or "").strip()
        if not word:
            continue
        wid, was_new = await _get_or_create_word(
            db, word=word, phonetic=(it.get("phonetic") or None),
            meaning=(it.get("meaning") or None), pos=(it.get("pos") or None),
            wtype=(it.get("type") or "word"))
        if was_new:
            created += 1
        if wid in seen:
            continue
        seen.add(wid)
        cw = (await db.execute(sa.select(CurriculumWord).where(
            CurriculumWord.unit_id == unit_id, CurriculumWord.word_id == wid))).scalar_one_or_none()
        if cw is None:
            db.add(CurriculumWord(unit_id=unit_id, word_id=wid, is_core=is_core, sort_order=order))
            order += 1
            linked += 1
        elif is_core and not cw.is_core:
            cw.is_core = True
    await db.flush()
    return {"linked": linked, "created": created, "total": len(seen)}


async def unlink_unit_word(db: AsyncSession, *, unit_id: uuid.UUID, word_id: uuid.UUID) -> None:
    """解除某词与单元的挂靠(只删 junction,词力通词条保留)。"""
    res = await db.execute(sa.delete(CurriculumWord).where(
        CurriculumWord.unit_id == unit_id, CurriculumWord.word_id == word_id))
    if res.rowcount == 0:
        raise AppError(code=404, message="该词未挂在此单元")
    await db.flush()


_TEXT_PARSE_SYS = (
    "你是英语教材词汇整理助手。用户会粘贴一段【单词表/词组文本】(可能含音标、词性、中文释义,"
    "排版杂乱、含页码/标题/例句)。请抽出其中的英文单词与词组,严格输出 JSON。"
)


async def parse_words_from_text(text: str) -> list[dict]:
    """粘贴的单词表文本 → LLM 抽出结构化单词/词组 [{word, phonetic, pos, meaning, type}]。按词形去重。"""
    import json
    from app.services.llm_provider import chat_completion, is_llm_dev_mode, fast_model
    body = (text or "").strip()
    if not body or is_llm_dev_mode():
        return []
    user = (
        f"下面是单词表文本:\n{body[:6000]}\n\n"
        '抽出所有英文单词与词组,输出 JSON:'
        '{"items":[{"word":"英文(原形)","phonetic":"音标(无则空串)",'
        '"pos":"词性缩写如 n./v./adj.(无则空串)","meaning":"中文释义(无则空串)",'
        '"type":"word 或 phrase(多词为 phrase)"}]}。'
        "只取词条,忽略例句/标题/页码;不要臆造不存在的词。只返回纯 JSON。")
    try:
        resp = await chat_completion(system_prompt=_TEXT_PARSE_SYS, user_prompt=user,
                                     model=fast_model(), max_tokens=8192,
                                     response_format={"type": "json_object"})
        data = json.loads(resp.choices[0].message.content or "{}")
    except Exception:  # noqa: BLE001
        return []
    items = data.get("items") if isinstance(data, dict) else None
    out: list[dict] = []
    seen: set[str] = set()
    for it in (items or []):
        if not isinstance(it, dict):
            continue
        w = (it.get("word") or "").strip()
        if not w or w.lower() in seen:
            continue
        seen.add(w.lower())
        out.append({
            "word": w, "phonetic": (it.get("phonetic") or "").strip() or None,
            "meaning": (it.get("meaning") or "").strip() or None,
            "pos": (it.get("pos") or "").strip() or None,
            "type": "phrase" if (it.get("type") == "phrase" or " " in w) else "word",
        })
    return out


async def ocr_words_from_images(image_urls: list[str]) -> list[dict]:
    """多张图片 → 视觉解析出单词/词组;跨图按词形去重。返回 [{word, phonetic, meaning, pos, type}]。"""
    from app.services.doubao_vision_service import recognize_word_list
    out: list[dict] = []
    seen: set[str] = set()
    for url in image_urls:
        try:
            parsed = await recognize_word_list(url)
        except Exception:  # noqa: BLE001
            parsed = []
        for it in parsed:
            w = (it.get("word") or "").strip()
            if not w or w.lower() in seen:
                continue
            seen.add(w.lower())
            out.append({
                "word": w, "phonetic": (it.get("phonetic") or "").strip() or None,
                "meaning": (it.get("meaning") or "").strip() or None,
                "pos": (it.get("pos") or "").strip() or None,
                "type": "phrase" if (it.get("type") == "phrase" or " " in w) else "word",
            })
    return out
