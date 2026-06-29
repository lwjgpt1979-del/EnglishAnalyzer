"""V2 课程浏览 service（D-079 / M2）。

职责：
1. persist_unit() — 把 curriculum_ai_service 输出 upsert 入 6 张表（幂等）
2. is_unit_locked() — unit_no=1 永远免费，其余按 PurchasedSemester 判断
3. list_units / get_unit_detail / get_kp_contents — 给 API 用的 read 函数
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.d4_knowledge import (
    CurriculumUnit,
    CurriculumUnitPassage,
    KnowledgePoint,
    UnitKnowledgePoint,
    CurriculumWord,
)
from app.models.d5_learning import VocabularyWord
from app.schemas.curriculum import (
    AIGeneratedUnit,
    KnowledgePointOut,
    KPContentOut,
    UnitDetailOut,
    UnitOut,
    WordOut,
)
from app.services import semester_service


# ─── Persist ────────────────────────────────────────────────────────────────

async def _park_pending_content(
    db: AsyncSession, *, norm: str, dimension: str, content_md: str, unit_id: uuid.UUID,
) -> None:
    """E2:未命中树上节点时,把该 KP 名某维讲解暂存(按 norm+dim 覆盖),
    待人工把候选挂到树上后 _materialize_pending_content 物化为 node_resource。"""
    from app.models.d11_v2_curriculum import PendingKpContent
    existing = (await db.execute(
        select(PendingKpContent).where(
            PendingKpContent.kp_name_norm == norm,
            PendingKpContent.dimension == dimension)
    )).scalar_one_or_none()
    if existing is not None:
        existing.content_md = content_md
        existing.source_unit_id = unit_id
    else:
        db.add(PendingKpContent(
            id=uuid.uuid4(), kp_name_norm=norm, dimension=dimension,
            content_md=content_md, source_unit_id=unit_id, generated_by="ai_full"))
    await db.flush()


async def persist_unit_passages(db: AsyncSession, *, unit_id: uuid.UUID, passages: list) -> int:
    """落库单元析出的短文(听力/阅读/写作)。整体覆盖该单元的旧短文(重生成幂等)。"""
    from sqlalchemy import delete
    await db.execute(delete(CurriculumUnitPassage).where(CurriculumUnitPassage.unit_id == unit_id))
    n = 0
    for i, p in enumerate(passages):
        text = (getattr(p, "text", "") or "").strip()
        if not text:
            continue
        db.add(CurriculumUnitPassage(
            id=uuid.uuid4(), unit_id=unit_id, kind=p.kind,
            title=(getattr(p, "title", None) or None), text=text, sort_order=i))
        n += 1
    await db.flush()
    return n


async def persist_unit_structured(db: AsyncSession, *, unit_id: uuid.UUID, parsed: dict) -> dict:
    """落库单元结构化解析(语法点+分级句 / 听力考点+句组 / 作文要求+正文)。整体覆盖该单元(幂等)。

    每句用 long_sentence_service.syntactic_complexity 算 0–100 难度。node_id 留空,第二步关联图谱再填。
    返回各块计数。
    """
    from sqlalchemy import delete
    from app.models.d22_unit_structured import UnitSection, UnitSectionSentence
    from app.services.long_sentence_service import syntactic_complexity, detect_syntax_points

    await db.execute(delete(UnitSection).where(UnitSection.unit_id == unit_id))  # 级联删句子

    def _add_sentences(section_id: uuid.UUID, sents: list) -> int:
        n = 0
        for i, raw in enumerate(sents or []):
            txt = (raw or "").strip() if isinstance(raw, str) else ""
            if not txt:
                continue
            try:
                comp = syntactic_complexity(txt)
                diff, pts = comp.get("difficulty"), detect_syntax_points(txt)
            except Exception:  # noqa: BLE001
                diff, pts = None, None
            db.add(UnitSectionSentence(
                id=uuid.uuid4(), section_id=section_id, text=txt,
                difficulty=diff, syntax_points=pts or None, sort_order=i))
            n += 1
        return n

    counts = {"grammar": 0, "listening": 0, "writing": 0, "sentences": 0}
    order = 0
    for kind, key in (("grammar", "grammar"), ("listening", "listening")):
        for blk in (parsed.get(key) or []):
            name = (blk.get("point") or "").strip() if isinstance(blk, dict) else ""
            if not name:
                continue
            sec = UnitSection(id=uuid.uuid4(), unit_id=unit_id, kind=kind,
                              point_name=name[:200], sort_order=order)
            db.add(sec)
            await db.flush()
            counts["sentences"] += _add_sentences(sec.id, blk.get("sentences"))
            counts[kind] += 1
            order += 1

    w = parsed.get("writing")
    if isinstance(w, dict) and ((w.get("requirement") or "").strip() or (w.get("text") or "").strip()):
        db.add(UnitSection(
            id=uuid.uuid4(), unit_id=unit_id, kind="writing",
            requirement=(w.get("requirement") or None), body_text=(w.get("text") or None),
            sort_order=order))
        counts["writing"] = 1

    await db.flush()
    return counts


# ── 分词打分匹配(关联知识图谱,不走 LLM)────────────────────────────────
# 无中文分词器,用「字符 bigram + ASCII 词」做词元,Dice 系数打分,取最高分自动挂靠。
import re as _re


def kp_match_tokens(raw: str) -> set[str]:
    """把考点名切成词元集合:ASCII 字母数字整词 + CJK 字符 bigram(单字时退化为单字)。"""
    import unicodedata as _ud
    s = _ud.normalize("NFKC", raw or "").lower()
    toks: set[str] = set()
    # ASCII 词(present perfect / be / v-ing 等)
    for w in _re.findall(r"[a-z0-9]+", s):
        toks.add(w)
    # CJK 串 → bigram
    for run in _re.findall(r"[一-鿿]+", s):
        if len(run) == 1:
            toks.add(run)
        else:
            for i in range(len(run) - 1):
                toks.add(run[i:i + 2])
    return toks


def kp_match_score(a: set[str], b: set[str]) -> float:
    """Dice 系数:2|A∩B| / (|A|+|B|)。两边都空→0。"""
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return (2.0 * inter) / (len(a) + len(b))


# 自动挂靠阈值:Dice ≥ 0.6 才回填(可区分「一般疑问句 vs 特殊疑问句」=0.5 不误挂)
KP_AUTO_LINK_THRESHOLD = 0.6


async def link_unit_sections(db: AsyncSession, *, unit_id: uuid.UUID,
                             only_unlinked: bool = True) -> dict:
    """第二步「关联知识图谱」:把单元结构化里的
      - 语法点 → 词法(cf)/句法(jf)子树
      - 听力考点 → 听力(lt)子树
    受控匹配:别名精确命中或高相似度模糊命中 → 回填 node_id/node_code;
    未命中 → 留待人工(手动挂靠 / 新建节点)。返回计数。

    匹配方式:**纯分词打分,不走 LLM**。候选 = 允许子树内所有节点(名称 + 别名),
    把考点名与候选名都切成「ASCII 词 + CJK bigram」词元,算 Dice 系数,取最高分;
    ≥ KP_AUTO_LINK_THRESHOLD 即自动挂靠到分值最高的节点。
    """
    import sqlalchemy as _sa
    from app.models.d22_unit_structured import UnitSection
    from app.models.d15_knowledge_graph import KnowledgeNode, NodeAlias
    from app.services.kp_normalize import normalize_kp_name
    from app.services.kp_suggest_service import _descendant_node_ids

    async def _subtree(codes: list[str]) -> set:
        ids = (await db.execute(
            _sa.select(KnowledgeNode.id).where(KnowledgeNode.code.in_(codes)))).scalars().all()
        return await _descendant_node_ids(db, list(ids)) or set()

    allowed = {"grammar": await _subtree(["cf", "jf"]), "listening": await _subtree(["lt"])}

    async def _candidates(ids: set) -> list[dict]:
        """候选项 = 子树内每个节点的(名称 + 别名)各自一条:{node_id, code, norm, tokens}。"""
        if not ids:
            return []
        cands: list[dict] = []
        # 节点名本身
        nodes = list((await db.execute(
            _sa.select(KnowledgeNode.id, KnowledgeNode.code, KnowledgeNode.name)
            .where(KnowledgeNode.id.in_(ids)))).all())
        for n in nodes:
            cands.append({"node_id": n.id, "code": n.code,
                          "norm": normalize_kp_name(n.name or ""), "tokens": kp_match_tokens(n.name or "")})
        # 别名(有 alias_norm,可还原一个可分词的串)
        aliases = list((await db.execute(
            _sa.select(NodeAlias.alias, NodeAlias.alias_norm, NodeAlias.node_id, KnowledgeNode.code)
            .join(KnowledgeNode, KnowledgeNode.id == NodeAlias.node_id)
            .where(NodeAlias.node_id.in_(ids)))).all())
        for a in aliases:
            base = a.alias or a.alias_norm or ""
            cands.append({"node_id": a.node_id, "code": a.code,
                          "norm": a.alias_norm or "", "tokens": kp_match_tokens(base)})
        return cands

    cand_map = {k: await _candidates(v) for k, v in allowed.items()}

    secs = (await db.execute(_sa.select(UnitSection).where(
        UnitSection.unit_id == unit_id,
        UnitSection.kind.in_(["grammar", "listening"])))).scalars().all()

    out = {"linked": 0, "unmatched": 0, "skipped": 0}
    for s in secs:
        if only_unlinked and s.node_id is not None:
            out["skipped"] += 1
            continue
        name = s.point_name or ""
        norm = normalize_kp_name(name)
        cands = cand_map.get(s.kind, [])
        if not norm or not cands:
            out["unmatched"] += 1
            continue
        q_tokens = kp_match_tokens(name)
        # 归一化完全相同 → 直接 1.0;否则按分词 Dice 取最高
        best, best_score = None, 0.0
        for c in cands:
            score = 1.0 if (c["norm"] and c["norm"] == norm) else kp_match_score(q_tokens, c["tokens"])
            if score > best_score:
                best, best_score = c, score
        if best is not None and best_score >= KP_AUTO_LINK_THRESHOLD:
            s.node_id, s.node_code = best["node_id"], best["code"]
            out["linked"] += 1
        else:
            out["unmatched"] += 1            # 未命中:留待人工(手动挂靠 / 新建节点)
    await db.flush()
    return out


async def manual_link_section(db: AsyncSession, *, section_id: uuid.UUID,
                              node_id: uuid.UUID) -> dict:
    """人工把某板块挂靠到知识图谱里**已存在**的节点(限本类允许子树:语法→cf/jf、听力→lt)。"""
    import sqlalchemy as _sa
    from app.models.d22_unit_structured import UnitSection
    from app.models.d15_knowledge_graph import KnowledgeNode
    from app.services.kp_suggest_service import _descendant_node_ids

    sec = (await db.execute(_sa.select(UnitSection).where(UnitSection.id == section_id))).scalar_one_or_none()
    if sec is None:
        raise AppError(code=404, message="板块不存在")
    roots = ["cf", "jf"] if sec.kind == "grammar" else (["lt"] if sec.kind == "listening" else [])
    root_ids = (await db.execute(_sa.select(KnowledgeNode.id).where(KnowledgeNode.code.in_(roots)))).scalars().all()
    allowed = await _descendant_node_ids(db, list(root_ids)) or set()
    node = (await db.execute(_sa.select(KnowledgeNode).where(KnowledgeNode.id == node_id))).scalar_one_or_none()
    if node is None or node.id not in allowed:
        raise AppError(code=400, message="所选节点不在该板块允许的目录范围(语法→词法/句法,听力→听力)")
    sec.node_id, sec.node_code = node.id, node.code
    await db.flush()
    return {"node_id": str(node.id), "node_code": node.code, "name": node.name}


async def new_node_for_section(db: AsyncSession, *, section_id: uuid.UUID,
                               parent_id: uuid.UUID, name: str, created_by: uuid.UUID) -> dict:
    """目录里没有对应考点时:在所选父分类下**新建知识图谱节点(手工标签)**并挂靠。

    父分类须在本类允许子树内(语法→cf/jf、听力→lt)。新节点 source=manual、status=active,建别名。
    """
    import uuid as _uuid
    import sqlalchemy as _sa
    from app.models.d22_unit_structured import UnitSection
    from app.models.d15_knowledge_graph import KnowledgeNode, NodeAlias
    from app.services.kp_normalize import normalize_kp_name
    from app.services.kp_suggest_service import _descendant_node_ids

    nm = (name or "").strip()
    if not nm:
        raise AppError(code=400, message="节点名不能为空")
    sec = (await db.execute(_sa.select(UnitSection).where(UnitSection.id == section_id))).scalar_one_or_none()
    if sec is None:
        raise AppError(code=404, message="板块不存在")
    roots = ["cf", "jf"] if sec.kind == "grammar" else (["lt"] if sec.kind == "listening" else [])
    root_ids = (await db.execute(_sa.select(KnowledgeNode.id).where(KnowledgeNode.code.in_(roots)))).scalars().all()
    allowed = await _descendant_node_ids(db, list(root_ids)) or set()
    parent = (await db.execute(_sa.select(KnowledgeNode).where(KnowledgeNode.id == parent_id))).scalar_one_or_none()
    if parent is None or parent.id not in allowed:
        raise AppError(code=400, message="父分类不在该板块允许的目录范围")
    code = f"m-{_uuid.uuid4().hex[:10]}"
    node = KnowledgeNode(
        id=_uuid.uuid4(), axis="knowledge", parent_id=parent.id, name=nm[:120], code=code,
        status="active", source="manual", applicable_stages=parent.applicable_stages)
    db.add(node)
    await db.flush()
    db.add(NodeAlias(id=_uuid.uuid4(), node_id=node.id, alias=nm[:120],
                     alias_norm=normalize_kp_name(nm), source="manual"))
    sec.node_id, sec.node_code = node.id, node.code
    await db.flush()
    return {"node_id": str(node.id), "node_code": code, "name": nm}


async def textbook_word_stats(db: AsyncSession, *, textbook: str | None = None,
                              grade: str | None = None, top: int = 200) -> dict:
    """教材高频词统计:某教材版+年级下,每个词出现在多少个单元(出现单元数=教材内词频)。

    返回 {totals:{词数,高频词数(≥2单元),最高出现单元数}, items:[{word,unit_count,gloss,star}], options}。
    """
    import sqlalchemy as _sa
    from app.models.d5_learning import VocabularyWord
    uq = _sa.select(CurriculumUnit.id)
    if textbook:
        uq = uq.where(CurriculumUnit.textbook_version == textbook)
    if grade:
        uq = uq.where(CurriculumUnit.grade == grade)
    rows = (await db.execute(
        _sa.select(CurriculumWord.word_id, _sa.func.count(_sa.distinct(CurriculumWord.unit_id)))
        .where(CurriculumWord.unit_id.in_(uq))
        .group_by(CurriculumWord.word_id))).all()
    wc = {wid: int(c) for wid, c in rows}
    # 选项:教材版/年级(取有词的)
    opt_rows = (await db.execute(
        _sa.select(CurriculumUnit.textbook_version, CurriculumUnit.grade).distinct()
        .where(CurriculumUnit.id.in_(_sa.select(CurriculumWord.unit_id).distinct())))).all()
    options = {
        "textbooks": sorted({t for t, _g in opt_rows}),
        "grades": sorted({g for _t, g in opt_rows}),
    }
    if not wc:
        return {"totals": {"words": 0, "high_freq": 0, "max_units": 0}, "items": [], "options": options}
    info = (await db.execute(_sa.select(
        VocabularyWord.id, VocabularyWord.word, VocabularyWord.definitions, VocabularyWord.star)
        .where(VocabularyWord.id.in_(list(wc))))).all()

    def _gloss(defs) -> str:
        if isinstance(defs, list) and defs:
            d0 = defs[0]
            if isinstance(d0, dict):
                return f"{d0.get('pos', '')} {d0.get('meaning', '')}".strip()
        return ""

    items = [{"word": w, "unit_count": wc.get(wid, 0), "gloss": _gloss(defs), "star": int(star or 0)}
             for wid, w, defs, star in info]
    items.sort(key=lambda x: (-x["unit_count"], x["word"].lower()))
    totals = {"words": len(items),
              "high_freq": sum(1 for it in items if it["unit_count"] >= 2),
              "max_units": max((it["unit_count"] for it in items), default=0)}
    return {"totals": totals, "items": items[:top], "options": options}


async def persist_unit(
    db: AsyncSession,
    *,
    ai_unit: AIGeneratedUnit,
    content_status: str = "draft",
) -> CurriculumUnit:
    """把 AI 生成的单元结构 upsert 入 6 张表，返回 CurriculumUnit。幂等。

    content_status 默认 "draft"（M5 审核闸门）：新生成的知识点内容先进草稿，
    需运营审核后才对学生可见；seed 脚本 / 可信内容可显式传 "published"。
    """
    # 1. curriculum_units（按 textbook+grade+semester+unit_no 唯一）
    cu_q = await db.execute(
        select(CurriculumUnit).where(
            CurriculumUnit.textbook_version == ai_unit.textbook_version,
            CurriculumUnit.grade == ai_unit.grade,
            CurriculumUnit.semester == ai_unit.semester,
            CurriculumUnit.unit_no == ai_unit.unit_no,
        )
    )
    cu = cu_q.scalar_one_or_none()
    if cu is None:
        cu = CurriculumUnit(
            id=uuid.uuid4(),
            textbook_version=ai_unit.textbook_version,
            grade=ai_unit.grade,
            semester=ai_unit.semester,  # type: ignore[arg-type]
            unit_no=ai_unit.unit_no,
            unit_title=ai_unit.unit_title,
        )
        db.add(cu)
        await db.flush()
    else:
        cu.unit_title = ai_unit.unit_title

    # 2. 知识点 → E2 受控映射:AI 知识点名 match_kp 到受控树上的既有节点。
    #    命中 → 建 unit_node 边 + 版本化挂讲解;未命中 → 落候选(附 unit 来源)+ 暂存六维内容,
    #    待人工把候选挂到树上后物化。**不再自建节点**(知识点骨架由后台受控树定义)。
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.models.d17_curriculum_kg import UnitNode
    from app.services import node_resource_service as nrs
    from app.services import curriculum_kp_service as ckp
    from app.services.kp_match_service import match_kp
    from app.services.kp_normalize import stages_from_grades, normalize_kp_name
    stages = stages_from_grades([ai_unit.grade])
    stage = stages[0] if stages else None
    for kp_in in ai_unit.knowledge_points:
        if not kp_in.name or not kp_in.name.strip():
            continue
        dims = [(d, md) for d, md in kp_in.contents.items() if d in nrs._DIMENSIONS]
        r = await match_kp(
            db, raw_name=kp_in.name, axis_hint="knowledge", stage_hint=stage,
            source_type="textbook", source_ref={"unit_ids": [str(cu.id)]})
        if r.node_id is not None:                       # 命中受控树节点 → 挂内容 + 建边
            await db.execute(
                pg_insert(UnitNode)
                .values(unit_id=cu.id, node_id=r.node_id, source="ai_extract")
                .on_conflict_do_nothing(index_elements=["unit_id", "node_id"]))
            for dim, md in dims:
                await nrs.submit_lecture_version(
                    db, node_id=r.node_id, dimension=dim, content_md=md,
                    source="ai_full", status_if_new=content_status,
                    origin_ref={"flow": "generate", "unit_id": str(cu.id)})
        elif r.candidate_id is not None:                # 未命中 → 候选 + 暂存内容,待人工挂树
            await ckp._attach_unit_to_candidate(db, r.candidate_id, cu.id)
            norm = normalize_kp_name(kp_in.name)
            for dim, md in dims:
                await _park_pending_content(db, norm=norm, dimension=dim, content_md=md, unit_id=cu.id)

    # 5. vocabulary_words + 6. curriculum_words
    for w_in in ai_unit.words:
        w_q = await db.execute(
            select(VocabularyWord).where(VocabularyWord.word == w_in.word)
        )
        w = w_q.scalar_one_or_none()
        if w is None:
            # 教材原文提取的新词:写进词力通全局词表，但标 source="textbook"，
            # 与人工维护的词区分（词力通页面可据此筛选/隔离教材词）。
            w = VocabularyWord(
                id=uuid.uuid4(),
                word=w_in.word,
                phonetic=w_in.phonetic,
                definitions=w_in.definitions,
                examples=w_in.examples,
                difficulty=w_in.difficulty,
                source="textbook",
            )
            db.add(w)
            await db.flush()

        cw_q = await db.execute(
            select(CurriculumWord).where(
                CurriculumWord.unit_id == cu.id,
                CurriculumWord.word_id == w.id,
            )
        )
        if cw_q.scalar_one_or_none() is None:
            db.add(CurriculumWord(
                unit_id=cu.id,
                word_id=w.id,
                is_core=w_in.is_core,
            ))

    return cu


async def upsert_unit_shell(
    db: AsyncSession,
    *,
    textbook_version: str,
    grade: str,
    semester: str,
    unit_no: int,
    unit_title: str,
    source_text: str | None = None,
) -> CurriculumUnit:
    """只 upsert curriculum_units 主表（按 textbook+grade+semester+unit_no 唯一），
    不生成知识点/词/讲解/短文。供「只拆 PDF」批量流使用；AI 内容由单元「生成内容」按需补。
    """
    cu = (await db.execute(
        select(CurriculumUnit).where(
            CurriculumUnit.textbook_version == textbook_version,
            CurriculumUnit.grade == grade,
            CurriculumUnit.semester == semester,
            CurriculumUnit.unit_no == unit_no,
        )
    )).scalar_one_or_none()
    if cu is None:
        cu = CurriculumUnit(
            id=uuid.uuid4(),
            textbook_version=textbook_version,
            grade=grade,
            semester=semester,  # type: ignore[arg-type]
            unit_no=unit_no,
            unit_title=unit_title,
        )
        db.add(cu)
    else:
        cu.unit_title = unit_title
    if source_text is not None:
        cu.source_text = source_text   # 存原文,供单元「生成内容」按需重生成
    await db.flush()
    return cu


# ─── Admin：批量生成 ────────────────────────────────────────────────────────

async def reset_semester(
    db: AsyncSession,
    *,
    textbook_version: str,
    grade: str,
    semester: str,
) -> int:
    """删除指定学期的所有单元（按 FK 顺序先删子表再删主表）。

    返回删除的单元数。用于重新生成前清场。
    """
    # 先查出目标单元 ID，复用 delete_units 做连带删除（单一来源,避免级联顺序分叉）
    unit_ids = list((await db.execute(
        select(CurriculumUnit.id).where(
            CurriculumUnit.textbook_version == textbook_version,
            CurriculumUnit.grade == grade,
            CurriculumUnit.semester == semester,
        )
    )).scalars().all())
    return await delete_units(db, unit_ids=unit_ids)


async def delete_units(db: AsyncSession, *, unit_ids: list[uuid.UUID]) -> int:
    """批量删除单元 + 连带其所有关联(知识图谱边 / 单词通词表 / 短文及其考点边)。

    删的是「单元↔X」的关联,不动 X 本身(知识节点/旧知识点/词汇主表均为全局共享,保留)。
    顺序:先删无 DB 级联的子表(否则 FK violation),最后删主表;主表删除时
    DB 会自动级联 curriculum_unit_passages(ondelete=CASCADE)→ unit_passage_kp。
    返回实际删除的单元数。
    """
    import sqlalchemy as _sa
    from app.models.d4_knowledge import CurriculumWord, UnitKnowledgePoint
    from app.models.d6_ai_questions import AiQuestion
    from app.models.d17_curriculum_kg import UnitNode

    if not unit_ids:
        return 0

    # 实际存在的单元(过滤无效 id,返回真实删除数)
    existing = list((await db.execute(
        select(CurriculumUnit.id).where(CurriculumUnit.id.in_(unit_ids))
    )).scalars().all())
    if not existing:
        return 0

    # AI 练习题引用单元(FK 无级联,且属生成内容)→ 解联保留题目,而非删题
    await db.execute(
        _sa.update(AiQuestion).where(AiQuestion.unit_id.in_(existing))
        .values(unit_id=None)
    )
    # 知识图谱关联:新边(unit_node)+ 旧桥(unit_knowledge_points)——只删边,留节点
    await db.execute(_sa.delete(UnitNode).where(UnitNode.unit_id.in_(existing)))
    await db.execute(
        _sa.delete(UnitKnowledgePoint).where(UnitKnowledgePoint.unit_id.in_(existing)))
    # 单词通关联:单元词表(curriculum_words)——只删关联,留 vocabulary_words 主表
    await db.execute(_sa.delete(CurriculumWord).where(CurriculumWord.unit_id.in_(existing)))
    # 主表(级联删短文 curriculum_unit_passages → unit_passage_kp)
    await db.execute(_sa.delete(CurriculumUnit).where(CurriculumUnit.id.in_(existing)))
    await db.flush()
    return len(existing)


async def generate_semester(
    db: AsyncSession,
    *,
    textbook_version: str,
    grade: str,
    semester: str,
    unit_count: int = 6,
    content_status: str = "published",
    reset: bool = True,
) -> list[dict]:
    """清场后用真实 AI 生成指定学期全部单元（M2）。

    返回逐单元结果列表：[{unit_no, unit_title, kp_count, status}, ...]
    content_status="published" 让内容立即对学生可见（管理员已做质量担保）。
    """
    from app.services import curriculum_ai_service

    if reset:
        deleted = await reset_semester(
            db, textbook_version=textbook_version, grade=grade, semester=semester,
        )

    results = []
    for unit_no in range(1, unit_count + 1):
        ai_unit = await curriculum_ai_service.generate_unit(
            textbook_version=textbook_version,
            grade=grade,
            semester=semester,
            unit_no=unit_no,
        )
        cu = await persist_unit(db, ai_unit=ai_unit, content_status=content_status)
        await db.flush()
        # R1:生成后自动对齐知识图谱(防御式,失败不阻断生成)
        from app.services import curriculum_kp_service
        await curriculum_kp_service.extract_for_ai_unit(db, unit_id=cu.id, ai_unit=ai_unit)
        results.append({
            "unit_no": unit_no,
            "unit_title": ai_unit.unit_title,
            "kp_count": len(ai_unit.knowledge_points),
            "word_count": len(ai_unit.words),
            "status": "ok",
        })

    return results


# ─── Paywall ────────────────────────────────────────────────────────────────

async def is_unit_locked(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    textbook_version: str,
    grade: str,
    semester: str,
    unit_no: int,
) -> bool:
    """unit_no=1 永远免费；其余按 PurchasedSemester 判断。"""
    if unit_no == 1:
        return False
    ok, _, _ = await semester_service.query_access(
        db, user_id=user_id,
        textbook_version=textbook_version, grade=grade, semester=semester,
    )
    return not ok


# ─── Read APIs ──────────────────────────────────────────────────────────────

async def list_units(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    textbook_version: str,
    grade: str,
    semester: str,
) -> list[UnitOut]:
    r = await db.execute(
        select(CurriculumUnit).where(
            CurriculumUnit.textbook_version == textbook_version,
            CurriculumUnit.grade == grade,
            CurriculumUnit.semester == semester,
        ).order_by(CurriculumUnit.unit_no)
    )
    units = list(r.scalars().all())

    from app.models.d17_curriculum_kg import UnitNode
    out: list[UnitOut] = []
    for u in units:
        kp_count = (await db.execute(
            select(func.count()).select_from(UnitNode).where(UnitNode.unit_id == u.id)
        )).scalar_one()
        locked = await is_unit_locked(
            db, user_id=user_id,
            textbook_version=textbook_version, grade=grade, semester=semester,
            unit_no=u.unit_no,
        )
        out.append(UnitOut(
            id=u.id,
            textbook_version=u.textbook_version,
            grade=u.grade,
            semester=str(u.semester),
            unit_no=u.unit_no,
            unit_title=u.unit_title,
            locked=locked,
            kp_count=kp_count,
        ))
    return out


async def get_unit_detail(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    unit_id: uuid.UUID,
) -> UnitDetailOut:
    u = (await db.execute(
        select(CurriculumUnit).where(CurriculumUnit.id == unit_id)
    )).scalar_one_or_none()
    if u is None:
        raise AppError(code=404, message="单元不存在")

    locked = await is_unit_locked(
        db, user_id=user_id,
        textbook_version=u.textbook_version, grade=u.grade, semester=str(u.semester),
        unit_no=u.unit_no,
    )
    if locked:
        raise AppError(code=403, message="该单元需购买学期会员后解锁")

    # R8.4:知识点来自 unit_node → knowledge_nodes(id 即 node_id),不再读旧 knowledge_points
    from app.models.d15_knowledge_graph import KnowledgeNode
    from app.models.d17_curriculum_kg import UnitNode
    node_rows = (await db.execute(
        select(KnowledgeNode).join(UnitNode, UnitNode.node_id == KnowledgeNode.id)
        .where(UnitNode.unit_id == u.id)
        .order_by(KnowledgeNode.sort_order, KnowledgeNode.code)
    )).scalars().all()
    kps = [KnowledgePointOut(
        id=n.id, code=n.code, name=n.name,
        category=str(n.node_kind or ""), description=n.description,
    ) for n in node_rows]

    w_rows = (await db.execute(
        select(VocabularyWord).join(
            CurriculumWord, CurriculumWord.word_id == VocabularyWord.id,
        ).where(CurriculumWord.unit_id == u.id)
        .order_by(CurriculumWord.sort_order, VocabularyWord.word)
    )).scalars().all()
    words = [WordOut(
        id=w.id, word=w.word, phonetic=w.phonetic,
        definitions=w.definitions or [], difficulty=w.difficulty,
    ) for w in w_rows]

    return UnitDetailOut(
        id=u.id,
        textbook_version=u.textbook_version,
        grade=u.grade,
        semester=str(u.semester),
        unit_no=u.unit_no,
        unit_title=u.unit_title,
        locked=False,
        kp_count=len(kps),
        knowledge_points=kps,
        words=words,
    )


async def get_kp_contents(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    node_id: uuid.UUID,
) -> list[KPContentOut]:
    """返回某知识 node 的六维讲解(R8.4:入参为 node_id)。受其所属单元的锁约束。"""
    from app.models.d17_curriculum_kg import UnitNode
    from app.models.d19_node_resource import NodeResource

    cu = (await db.execute(
        select(CurriculumUnit).join(
            UnitNode, UnitNode.unit_id == CurriculumUnit.id,
        ).where(UnitNode.node_id == node_id)
        .order_by(CurriculumUnit.unit_no)
    )).scalars().first()
    if cu is not None:
        locked = await is_unit_locked(
            db, user_id=user_id,
            textbook_version=cu.textbook_version, grade=cu.grade,
            semester=str(cu.semester), unit_no=cu.unit_no,
        )
        if locked:
            raise AppError(code=403, message="该知识点所属单元需购买学期会员后解锁")

    contents = (await db.execute(
        select(NodeResource).where(
            NodeResource.node_id == node_id,
            NodeResource.resource_type == "lecture",
            NodeResource.status == "published",
        )
    )).scalars().all()
    return [KPContentOut(
        dimension=str(c.dimension or ""),
        content_md=c.content_md or "",
        audio_url=c.media_url,
    ) for c in contents]


# ─── 运营审核/编辑 ──────────────────────────────────────────────────────────────
# 旧 knowledge_point_contents 内容审核已退役:内容生成直写 node_resource(lecture),
# 审核统一走 NodeResources 后台页(node_resource_service.list_for_review/review)。


async def search_kps(
    db: AsyncSession,
    *,
    q: str,
    limit: int = 10,
) -> list[KnowledgePoint]:
    """按名称模糊搜索知识点（ILIKE）。q 为空则不过滤，返回前 limit 条。"""
    stmt = select(KnowledgePoint).order_by(KnowledgePoint.name)
    if q:
        stmt = stmt.where(KnowledgePoint.name.ilike(f"%{q}%"))
    stmt = stmt.limit(limit)
    return list((await db.execute(stmt)).scalars().all())


@dataclass
class UnitContentStat:
    """单个课程单元的「短文关联考点」进度统计。"""
    unit_id: uuid.UUID
    textbook_version: str
    grade: str
    semester: str
    unit_no: int
    unit_title: str
    kp_count: int          # 单元考点数 = 各短文已关联考点去重汇总
    content_count: int     # 已关联考点的短文数
    content_rate: float    # 已关联短文 / 短文总数，0-1
    passage_count: int = 0  # 短文总数
    unit_pdf_url: str | None = None   # 拆出的单元独立 PDF(COS)


async def list_units_with_stats(db: AsyncSession) -> list[UnitContentStat]:
    """列出所有课程单元及内容完成度，供 Admin 课程管理页使用。"""
    units = (await db.execute(
        select(CurriculumUnit).order_by(
            CurriculumUnit.textbook_version,
            CurriculumUnit.grade,
            CurriculumUnit.semester,
            CurriculumUnit.unit_no,
        )
    )).scalars().all()

    if not units:
        return []

    unit_ids = [u.id for u in units]

    # 「短文关联考点」进度(替代旧的单元级六维填充率):
    #   短文总数 / 已关联考点的短文数 / 单元考点数(各短文关联考点去重汇总)。
    from app.models.d4_knowledge import CurriculumUnitPassage, UnitPassageKp

    passage_total: dict[uuid.UUID, int] = dict((await db.execute(
        select(CurriculumUnitPassage.unit_id, func.count())
        .where(CurriculumUnitPassage.unit_id.in_(unit_ids))
        .group_by(CurriculumUnitPassage.unit_id)
    )).all())

    linked_passages: dict[uuid.UUID, int] = dict((await db.execute(
        select(CurriculumUnitPassage.unit_id,
               func.count(func.distinct(CurriculumUnitPassage.id)))
        .join(UnitPassageKp, UnitPassageKp.passage_id == CurriculumUnitPassage.id)
        .where(CurriculumUnitPassage.unit_id.in_(unit_ids))
        .group_by(CurriculumUnitPassage.unit_id)
    )).all())

    kp_rollup: dict[uuid.UUID, int] = dict((await db.execute(
        select(CurriculumUnitPassage.unit_id,
               func.count(func.distinct(UnitPassageKp.node_id)))
        .join(UnitPassageKp, UnitPassageKp.passage_id == CurriculumUnitPassage.id)
        .where(CurriculumUnitPassage.unit_id.in_(unit_ids))
        .group_by(CurriculumUnitPassage.unit_id)
    )).all())

    result: list[UnitContentStat] = []
    for u in units:
        ptot = passage_total.get(u.id, 0)
        plinked = linked_passages.get(u.id, 0)
        kc = kp_rollup.get(u.id, 0)
        rate = round(plinked / ptot, 4) if ptot > 0 else 0.0
        result.append(UnitContentStat(
            unit_id=u.id,
            textbook_version=u.textbook_version,
            grade=str(u.grade),
            semester=str(u.semester),
            unit_no=u.unit_no,
            unit_title=u.unit_title or "",
            kp_count=kc,
            content_count=plinked,
            passage_count=ptot,
            content_rate=min(rate, 1.0),
            unit_pdf_url=u.unit_pdf_url,
        ))
    return result
