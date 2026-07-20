"""错题关系网(每学生私有):错题选项 → 语义块 → 归一 word_id → 两两建边。

边关系来源:① 先查全局考点(vocab_word_relation 已有该对关系)→ source=global;
② 无则 LLM 一次判所有两两(source=llm),判出的语义关系**回写全局考点**(反哺);
③ 同题共现但无语义关系 → relation='cooccur'。
查看即生成 + 幂等缓存(按 student+wrong_record,已建过直接返回)。词/词组共用全局考点。
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d5_learning import VocabularyWord
from app.models.d16_question_domain import PlatformQuestion, WrongRecord
from app.models.d18_vocab_kg import StudentWrongRelation, VocabWordRelation

# 会回写全局考点的语义关系(cooccur 不回写)
_SEMANTIC = ("synonym", "antonym", "confusion", "ambiguity", "related")
_MAX_BLOCKS = 12   # 单题参与建网的块上限(约束两两规模/成本)


async def _wrong_options(db: AsyncSession, wr: WrongRecord) -> tuple[str, list[str]]:
    """取错题的题干 + 选项文本列表。platform 从 platform_question.options;uploaded 无结构选项→[](靠题干)。"""
    stem = wr.stem or ""
    opts: list[str] = []
    if wr.q_scope == "platform":
        pq = await db.get(PlatformQuestion, wr.question_id)
        if pq is not None:
            if isinstance(pq.options, list):
                opts = [str(o).strip() for o in pq.options if str(o).strip()]
            if pq.stem and not stem:
                stem = pq.stem
    return stem, opts


async def _extract_blocks(stem: str, options: list[str]) -> list[dict]:
    """LLM 把选项拆成独立语义块(词/词组)。返回 [{text, is_phrase, zh}]。dev-mock 空。"""
    from app.services.llm_provider import complete_json, fast_model, is_llm_dev_mode
    if is_llm_dev_mode():
        return []
    opt_txt = "\n".join(f"- {o}" for o in options) if options else "(选项在题干中)"
    system = (
        "你是英语题目分析专家。给定一道选择题的题干和各选项,把**每个选项**拆成其中的独立语义块"
        "(一个块=一个考点单位:单词或固定词组;去掉 A./B. 等选项编号与多余标点)。同一选项可能含多个块。\n"
        "严格输出 JSON:{\"blocks\":[{\"text\":\"英文词或词组(原形/小写)\",\"is_phrase\":true或false,\"zh\":\"中文\"}]}\n"
        "只保留有考查价值的英文实义词/词组;同义合并去重;不臆造。")
    d = await complete_json(
        system_prompt=system, user_prompt=f"题干:{stem}\n选项:\n{opt_txt}\n返回 JSON:",
        max_tokens=900, model=fast_model(), feature="wrong_option_split",
        validate=lambda x: isinstance(x.get("blocks"), list))
    blocks = []
    seen = set()
    for b in (d or {}).get("blocks") or []:
        if not isinstance(b, dict):
            continue
        t = str(b.get("text") or "").strip()
        if not t or t.lower() in seen:
            continue
        seen.add(t.lower())
        blocks.append({"text": t, "is_phrase": bool(b.get("is_phrase")), "zh": str(b.get("zh") or "").strip()})
        if len(blocks) >= _MAX_BLOCKS:
            break
    return blocks


async def _ensure_word_id(db: AsyncSession, text: str, is_phrase: bool, zh: str) -> uuid.UUID | None:
    """块文本 → vocabulary_words id(命中 lower(word) 取用;未命中入库,source='wrong')。"""
    t = (text or "").strip()
    if not t:
        return None
    row = (await db.execute(
        sa.select(VocabularyWord.id).where(sa.func.lower(VocabularyWord.word) == t.lower()).limit(1))).first()
    if row:
        return row[0]
    wid = uuid.uuid4()
    db.add(VocabularyWord(
        id=wid, word=t, definitions=([{"meaning": zh}] if zh else []), difficulty=3,
        type=("phrase" if is_phrase else "word"), source="wrong"))
    await db.flush()
    return wid


async def _judge_pairs(blocks: list[dict], stem: str) -> dict:
    """LLM 一次判所有两两关系。返回 {(i,j): relation}(i<j,relation∈_SEMANTIC)。dev-mock 空。"""
    from app.services.llm_provider import complete_json, fast_model, is_llm_dev_mode
    if is_llm_dev_mode() or len(blocks) < 2:
        return {}
    listing = "\n".join(f"{i}. {b['text']}({b.get('zh', '')})" for i, b in enumerate(blocks))
    system = (
        "你是英语词汇关系分析专家。下面是同一道题选项里的若干词/词组(带编号)。判断**每一对**之间的语义关系,"
        "只用这些标签:synonym(近义)/antonym(反义)/confusion(易混:形近或义近易错)/"
        "ambiguity(歧义:多义混淆)/related(其他相关)/none(无明显语义关系)。\n"
        "严格输出 JSON:{\"pairs\":[{\"a\":编号,\"b\":编号,\"relation\":\"标签\"}]},只列有关系(非 none)的对,不臆造。")
    d = await complete_json(
        system_prompt=system, user_prompt=f"题干:{stem}\n词表:\n{listing}\n返回 JSON:",
        max_tokens=900, model=fast_model(), feature="wrong_pair_relation",
        validate=lambda x: isinstance(x.get("pairs"), list))
    out: dict = {}
    n = len(blocks)
    for p in (d or {}).get("pairs") or []:
        if not isinstance(p, dict):
            continue
        try:
            a, b = int(p["a"]), int(p["b"])
        except (KeyError, ValueError, TypeError):
            continue
        rel = str(p.get("relation") or "").strip()
        if rel in _SEMANTIC and a != b and 0 <= a < n and 0 <= b < n:
            out[(min(a, b), max(a, b))] = rel
    return out


async def build_wrong_relations(db: AsyncSession, *, student_id: uuid.UUID, wrong_record_id: uuid.UUID) -> None:
    """建该错题的个人关系网(幂等:已建过直接返回)。"""
    exists = (await db.execute(
        sa.select(StudentWrongRelation.id).where(
            StudentWrongRelation.student_id == student_id,
            StudentWrongRelation.wrong_record_id == wrong_record_id).limit(1))).first()
    if exists:
        return
    wr = await db.get(WrongRecord, wrong_record_id)
    if wr is None or wr.student_id != student_id:
        return
    stem, opts = await _wrong_options(db, wr)
    blocks = await _extract_blocks(stem, opts)
    ids = [await _ensure_word_id(db, b["text"], b["is_phrase"], b["zh"]) for b in blocks]
    valid = [(i, wid) for i, wid in enumerate(ids) if wid is not None]
    if len(valid) < 2:
        await db.commit()   # 落库新建的词(即便无边)
        return
    vblocks = [blocks[i] for i, _ in valid]
    vids = [wid for _, wid in valid]

    # 全局已有关系(该对在 vocab_word_relation 有语义边)→ frozenset(word_id 对) → relation
    grows = (await db.execute(
        sa.select(VocabWordRelation.word_id, VocabWordRelation.related_word_id, VocabWordRelation.relation)
        .where(VocabWordRelation.word_id.in_(vids),
               VocabWordRelation.related_word_id.in_(vids)))).all()
    global_rel: dict = {}
    for a, b, rel in grows:
        if b is not None and rel in _SEMANTIC:
            global_rel[frozenset((a, b))] = rel

    judged = await _judge_pairs(vblocks, stem)   # (p,q) 位置索引 → relation

    rows: list[dict] = []
    writeback: list[tuple] = []
    for p in range(len(vids)):
        for q in range(p + 1, len(vids)):
            a_id, b_id = vids[p], vids[q]
            key = frozenset((a_id, b_id))
            if key in global_rel:
                rel, src = global_rel[key], "global"
            elif (p, q) in judged:
                rel, src = judged[(p, q)], "llm"
                writeback.append((a_id, b_id, rel, vblocks[q]))   # 回写全局 a→b
            else:
                rel, src = "cooccur", "cooccur"
            # a/b 按 id 字符串归一,防同边反向重复
            a_norm, b_norm = (a_id, b_id) if str(a_id) < str(b_id) else (b_id, a_id)
            rows.append({"id": uuid.uuid4(), "student_id": student_id, "a_word_id": a_norm,
                         "b_word_id": b_norm, "relation": rel, "source": src,
                         "wrong_record_id": wrong_record_id})
    if rows:
        await db.execute(pg_insert(StudentWrongRelation).values(rows)
                         .on_conflict_do_nothing(
                             index_elements=["student_id", "a_word_id", "b_word_id", "relation"]))
    # 决策③:LLM 判定的语义关系反哺全局考点(vocab_word_relation)
    for a_id, b_id, rel, bblock in writeback:
        await db.execute(pg_insert(VocabWordRelation).values(
            id=uuid.uuid4(), word_id=a_id, relation=rel, related_word_id=b_id,
            related_text=bblock["text"], related_zh=(bblock.get("zh") or None), note=None)
            .on_conflict_do_nothing(index_elements=["word_id", "relation", "related_text"]))
    await db.commit()


async def wrong_relation_net(db: AsyncSession, *, student_id: uuid.UUID, wrong_record_id: uuid.UUID) -> dict:
    """该错题的个人关系网:{nodes:[{word_id,word,zh,is_phrase}], edges:[{a_word_id,b_word_id,relation,source}]}。
    查看即生成(先 build);节点 = 本题选项块,边 = 本题产生的关系。"""
    await build_wrong_relations(db, student_id=student_id, wrong_record_id=wrong_record_id)
    edges = (await db.execute(
        sa.select(StudentWrongRelation).where(
            StudentWrongRelation.student_id == student_id,
            StudentWrongRelation.wrong_record_id == wrong_record_id))).scalars().all()
    node_ids: set = set()
    edge_out = []
    for e in edges:
        node_ids.add(e.a_word_id)
        node_ids.add(e.b_word_id)
        edge_out.append({"a_word_id": str(e.a_word_id), "b_word_id": str(e.b_word_id),
                         "relation": e.relation, "source": e.source})
    nodes = []
    if node_ids:
        words = (await db.execute(
            sa.select(VocabularyWord).where(VocabularyWord.id.in_(node_ids)))).scalars().all()
        for w in words:
            defs = w.definitions if isinstance(w.definitions, list) else []
            zh = next((str(d.get("meaning")) for d in defs if isinstance(d, dict) and d.get("meaning")), "")
            nodes.append({"word_id": str(w.id), "word": w.word, "zh": zh, "is_phrase": w.type == "phrase"})
    return {"nodes": nodes, "edges": edge_out}
