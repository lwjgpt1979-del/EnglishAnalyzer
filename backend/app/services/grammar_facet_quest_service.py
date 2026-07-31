"""课程语法细目闯关(Q+ 一句三练):同句挖空→改错→选用;缺教材句走 S2 示范句缓存。

挖空/改错/选用默认规则出题不调 LLM。仅当细目无可用句时 ensure 示范句(feature=grammar_facet_demo)。
"""
from __future__ import annotations

import hashlib
import logging
import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError

_log = logging.getLogger(__name__)

# 每细目最多用几句做三练
_SENTENCES_PER_FACET = 2

# 优先匹配的考点形态(长的在前,避免 isn't 被拆成 is)
_CLOZE_FORMS = (
    "aren't", "isn't", "wasn't", "weren't", "don't", "doesn't", "didn't",
    "won't", "can't", "cannot", "am not", "is not", "are not", "was not", "were not",
    "do not", "does not", "did not",
    "I'm", "you're", "we're", "they're", "he's", "she's", "it's",
    "am", "is", "are", "was", "were", "do", "does", "did", "can", "may", "will",
)
_FORM_RE = re.compile(
    r"(?i)\b(" + "|".join(re.escape(f) for f in _CLOZE_FORMS) + r")\b"
)
_BE_POOL = ["am", "is", "are", "isn't", "aren't", "am not", "is not", "are not"]
_DO_POOL = ["do", "does", "did", "don't", "doesn't", "didn't"]
_MODAL_POOL = ["can", "may", "will", "can't", "won't"]

_SRC_TEXTBOOK = "textbook"
_SRC_AI_DEMO = "ai_demo"


def _pool_for(ans: str) -> list[str]:
    a = ans.lower()
    if a in {x.lower() for x in _BE_POOL} or "n't" in a or " not" in a:
        if any(x in a for x in ("do", "does", "did")):
            return list(_DO_POOL)
        if any(x in a for x in ("can", "may", "will")):
            return list(_MODAL_POOL)
        return list(_BE_POOL)
    if a in {x.lower() for x in _DO_POOL}:
        return list(_DO_POOL)
    if a in {x.lower() for x in _MODAL_POOL}:
        return list(_MODAL_POOL)
    return list(_BE_POOL)


def _usable_sentence(text: str) -> bool:
    """过滤元说明/超长段,只保留适合挖空的短原句。"""
    t = (text or "").strip()
    if len(t) < 6 or len(t) > 140:
        return False
    low = t.lower()
    if low.startswith("here are all") or "textbook" in low or "original english sentences" in low:
        return False
    if t.count(".") + t.count("!") + t.count("?") > 3:
        return False
    return True


def _rotate(opts: list[str], seed: str) -> list[str]:
    if not opts:
        return opts
    rot = sum(ord(c) for c in seed) % len(opts)
    return opts[rot:] + opts[:rot]


def _answer_index(options: list[str], answer: str) -> int:
    """正确答案在选项中的下标;找不到返回 -1。"""
    for i, o in enumerate(options):
        if o == answer:
            return i
    return -1


def _place_answer_at(options: list[str], answer: str, target: int) -> list[str]:
    """旋转选项,使正确答案落在 target 下标。"""
    if not options or answer not in options:
        return options
    n = len(options)
    cur = options.index(answer)
    t = target % n
    k = (cur - t) % n
    return options[k:] + options[:k]


def _find_form(raw: str) -> re.Match[str] | None:
    return _FORM_RE.search(raw)


def build_cloze_from_sentence(text: str, *, facet_name: str = "") -> dict[str, Any] | None:
    """从一句教材/示范句生成单选挖空题;无法定位考点则返回 None。"""
    raw = (text or "").strip()
    if not _usable_sentence(raw):
        return None
    m = _find_form(raw)
    if not m:
        return None
    ans = m.group(1)
    stem = raw[: m.start()] + "______" + raw[m.end() :]
    pool = _pool_for(ans)
    opts: list[str] = [ans]
    for cand in pool:
        if cand.lower() == ans.lower():
            continue
        if cand not in opts:
            opts.append(cand)
        if len(opts) >= 4:
            break
    for cand in ("is", "are", "am", "isn't", "aren't"):
        if len(opts) >= 4:
            break
        if cand.lower() != ans.lower() and cand not in opts:
            opts.append(cand)
    if len(opts) < 2:
        return None
    options = _rotate(opts, ans)
    fn = (facet_name or "本细目").strip()
    return {
        "kind": "cloze",
        "stem": stem,
        "options": options,
        "answer": ans,
        "explanation": (
            f"本题来自细目「{fn}」。空缺处应为「{ans}」。请对照原句：{raw}"
        ),
        "source_sentence": raw,
    }


def _swap_be_not(raw: str, form: str) -> str | None:
    """把 is not / aren't 等打成 not is / are n't 错序。"""
    low = form.lower()
    if " not" in low:
        parts = form.split()
        if len(parts) == 2:
            wrong = f"{parts[1]} {parts[0]}"
            return re.sub(re.escape(form), wrong, raw, count=1, flags=re.I)
    if "n't" in low:
        base = form.replace("n't", "").replace("N'T", "")
        # aren't → are not 再错序;或 not are
        if base:
            return re.sub(
                re.escape(form), f"not {base}", raw, count=1, flags=re.I)
    return None


def _wrong_be_agreement(raw: str, form: str) -> str | None:
    """主谓不一致干扰。"""
    mapping = {
        "is": "are", "are": "is", "am": "is",
        "isn't": "aren't", "aren't": "isn't",
        "was": "were", "were": "was",
        "do": "does", "does": "do",
        "don't": "doesn't", "doesn't": "don't",
    }
    repl = mapping.get(form.lower())
    if not repl:
        return None
    # 保持原大小写风格:句首大写则首字母大写
    if form[0].isupper():
        repl = repl[0].upper() + repl[1:]
    return re.sub(re.escape(form), repl, raw, count=1, flags=re.I)


def _extra_not_tail(raw: str) -> str | None:
    t = raw.rstrip()
    if t.endswith((".", "!", "?")):
        return t[:-1] + " not" + t[-1]
    return t + " not"


def _wrong_variants(raw: str, form: str) -> list[str]:
    """规则生成完整错句干扰项。"""
    out: list[str] = []
    for fn in (
        lambda: _swap_be_not(raw, form),
        lambda: _wrong_be_agreement(raw, form),
        lambda: _extra_not_tail(raw),
    ):
        w = fn()
        if w and w.strip() != raw.strip() and w not in out:
            out.append(w.strip())
    # 再补一条简单错序
    if " " in raw and len(out) < 3:
        toks = raw.split()
        if len(toks) >= 3:
            alt = toks[:]
            alt[1], alt[2] = alt[2], alt[1]
            w = " ".join(alt)
            if w != raw and w not in out:
                out.append(w)
    return out[:3]


def build_error_fix_from_sentence(
    text: str, *, facet_name: str = "",
) -> dict[str, Any] | None:
    """改错单选:哪句正确?"""
    raw = (text or "").strip()
    if not _usable_sentence(raw):
        return None
    m = _find_form(raw)
    if not m:
        return None
    form = m.group(1)
    wrongs = _wrong_variants(raw, form)
    if not wrongs:
        return None
    opts = [raw] + wrongs
    options = _rotate(opts[:4], form + "|err")
    fn = (facet_name or "本细目").strip()
    return {
        "kind": "error_fix",
        "stem": "哪句正确？",
        "options": options,
        "answer": raw,
        "explanation": f"细目「{fn}」的正确说法是：{raw}",
        "source_sentence": raw,
    }


def build_choose_from_sentence(
    text: str, *, facet_name: str = "", zh_hint: str = "",
) -> dict[str, Any] | None:
    """选用单选:按中文提示或细目名选完整正确句。"""
    raw = (text or "").strip()
    if not _usable_sentence(raw):
        return None
    m = _find_form(raw)
    if not m:
        return None
    form = m.group(1)
    wrongs = _wrong_variants(raw, form)
    if not wrongs:
        return None
    opts = [raw] + wrongs
    options = _rotate(opts[:4], form + "|choose")
    fn = (facet_name or "本细目").strip()
    hint = (zh_hint or "").strip()
    if hint:
        stem = f"中文意思：{hint}\n选完整正确句"
    else:
        stem = f"选正确表达细目「{fn}」的完整句"
    return {
        "kind": "choose",
        "stem": stem,
        "options": options,
        "answer": raw,
        "explanation": f"正确句是：{raw}。对应细目「{fn}」。",
        "source_sentence": raw,
        "zh_hint": hint or None,
    }


def build_triple_from_sentence(
    text: str, *, facet_name: str = "", zh_hint: str = "",
    source: str = _SRC_TEXTBOOK, sid: str = "0",
) -> dict[str, Any] | None:
    """同句三练:挖空→改错→选用;任一步失败则整组丢弃。

    改错与选用的正确答案不得落在同一选项位(避免连点同一字母蒙对)。
    """
    cloze = build_cloze_from_sentence(text, facet_name=facet_name)
    err = build_error_fix_from_sentence(text, facet_name=facet_name)
    choose = build_choose_from_sentence(
        text, facet_name=facet_name, zh_hint=zh_hint)
    if not cloze or not err or not choose:
        return None

    err_i = _answer_index(err["options"], err["answer"])
    choose_i = _answer_index(choose["options"], choose["answer"])
    n_ch = len(choose["options"] or [])
    if err_i >= 0 and choose_i >= 0 and n_ch > 1 and err_i == choose_i:
        # 选用正确项挪到与改错不同位(优先 +1,再试其它位)
        for delta in range(1, n_ch):
            target = (err_i + delta) % n_ch
            choose["options"] = _place_answer_at(
                list(choose["options"]), choose["answer"], target)
            if _answer_index(choose["options"], choose["answer"]) != err_i:
                break

    raw = cloze["source_sentence"]
    steps = []
    for i, item in enumerate((cloze, err, choose)):
        steps.append({
            "id": f"{sid}-s{i + 1}",
            **item,
            "source": source,
        })
    return {
        "source_sentence": raw,
        "source": source,
        "zh_hint": (zh_hint or "").strip() or None,
        "steps": steps,
    }


def _triples_from_pool(
    sentences: list[str],
    *,
    facet_name: str,
    source: str,
    zh_hints: list[str] | None = None,
    prefix: str = "t",
) -> list[dict[str, Any]]:
    """从句子池抽最多 _SENTENCES_PER_FACET 组三练。"""
    hints = zh_hints or []
    triples: list[dict[str, Any]] = []
    for i, s in enumerate(sentences):
        if len(triples) >= _SENTENCES_PER_FACET:
            break
        hint = hints[i] if i < len(hints) else ""
        t = build_triple_from_sentence(
            s, facet_name=facet_name, zh_hint=hint,
            source=source, sid=f"{prefix}{len(triples)}",
        )
        if t:
            triples.append(t)
    return triples


def _demo_cache_md5(point_name: str, facet_name: str) -> str:
    raw = f"v1|{(point_name or '').strip()}|{(facet_name or '').strip()}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _template_demo(facet_name: str) -> tuple[list[str], list[str]]:
    """规则兜底示范句(均可挖空);LLM 失败时落库,避免下次再付费重试。"""
    fn = (facet_name or "").strip()
    fl = fn.lower()
    if "三单" in fn and ("否" in fn or "doesn" in fl or "don't" in fl or "not" in fl):
        return (
            ["She does not like coffee.", "He does not play football."],
            ["她不喜欢咖啡。", "他不踢足球。"],
        )
    if "三单" in fn:
        return (
            ["He does homework every day.", "She does her homework."],
            ["他每天做作业。", "她做她的作业。"],
        )
    if "否" in fn or "don't" in fl or "doesn" in fl:
        return (
            ["I do not like coffee.", "They do not watch TV."],
            ["我不喜欢咖啡。", "他们不看电视。"],
        )
    if "疑问" in fn or "问" in fn:
        return (
            ["Do you like music?", "Does he play football?"],
            ["你喜欢音乐吗？", "他踢足球吗？"],
        )
    if "祈使" in fn:
        return (
            ["Please be quiet.", "Be careful on the road."],
            ["请安静。", "路上小心。"],
        )
    if "否" not in fn and ("肯定" in fn or "非三单" in fn):
        return (
            ["I do my homework.", "They do sports after school."],
            ["我做作业。", "他们放学后做运动。"],
        )
    return (
        ["He is a student.", "They are ready."],
        ["他是一名学生。", "他们准备好了。"],
    )


async def get_demo_from_cache(
    db: AsyncSession, *, point_name: str, facet_name: str,
) -> dict[str, Any] | None:
    """只读物理缓存,不调 LLM。"""
    from app.models.d28_grammar_facet_quest import GrammarFacetDemoCache

    pn = (point_name or "").strip()[:120] or "语法点"
    fn = (facet_name or "").strip()[:80] or "细目"
    hit = await db.get(GrammarFacetDemoCache, _demo_cache_md5(pn, fn))
    if hit is None:
        return None
    sents = [str(s).strip() for s in (hit.sentences or []) if str(s).strip()]
    if not sents:
        return None
    hints = hit.zh_hints if isinstance(hit.zh_hints, list) else []
    return {
        "sentences": sents[:2],
        "zh_hints": [str(h).strip() for h in hints][:2],
        "cached": True,
        "source": _SRC_AI_DEMO,
    }


async def _write_demo_cache(
    db: AsyncSession, *, point_name: str, facet_name: str,
    sentences: list[str], zh_hints: list[str],
) -> None:
    from app.models.d28_grammar_facet_quest import GrammarFacetDemoCache

    pn = (point_name or "").strip()[:120] or "语法点"
    fn = (facet_name or "").strip()[:80] or "细目"
    md5 = _demo_cache_md5(pn, fn)
    sents = sentences[:2]
    hints = (zh_hints + [""] * 2)[: len(sents)]
    await db.execute(
        pg_insert(GrammarFacetDemoCache)
        .values(
            input_md5=md5, point_name=pn, facet_name=fn,
            sentences=sents, zh_hints=hints,
        )
        .on_conflict_do_update(
            index_elements=[GrammarFacetDemoCache.input_md5],
            set_={"sentences": sents, "zh_hints": hints},
        )
    )
    await db.flush()


async def ensure_facet_demo_sentences(
    db: AsyncSession, *, point_name: str, facet_name: str,
) -> dict[str, Any]:
    """缺教材句时取/生成示范句;命中物理缓存不二次付费;失败写模板兜底并落库。"""
    from app.services.llm_provider import complete_json, fast_model, is_llm_dev_mode

    pn = (point_name or "").strip()[:120] or "语法点"
    fn = (facet_name or "").strip()[:80] or "细目"
    hit = await get_demo_from_cache(db, point_name=pn, facet_name=fn)
    if hit is not None and _triples_from_pool(
        hit["sentences"], facet_name=fn, source=_SRC_AI_DEMO,
        zh_hints=hit.get("zh_hints") or [],
    ):
        return hit
    # 无缓存或缓存句不可挖空 → 继续生成/模板覆盖

    system = (
        "你是初中英语语法示范句生成器。为指定挂靠点+细目生成 2 句短英文。\n"
        "要求:每句≤10词;必须含 do/does/don't/doesn't/is/are 等可挖空词;"
        "用词简单;紧扣细目。\n"
        '只输出 JSON:{"sentences":["...","..."],"zh_hints":["...","..."]}'
    )
    user = f"挂靠点:{pn}\n细目:{fn}\nJSON:"
    sents: list[str] = []
    hints: list[str] = []
    cached = False

    if is_llm_dev_mode():
        sents, hints = _template_demo(fn)
    else:
        data = await complete_json(
            system_prompt=system, user_prompt=user, max_tokens=256,
            model=fast_model(), feature="grammar_facet_demo",
            validate=lambda x: isinstance(x, dict)
            and isinstance(x.get("sentences"), list)
            and len([s for s in (x.get("sentences") or []) if str(s).strip()]) >= 1,
        ) or {}
        sents = [str(s).strip() for s in (data.get("sentences") or []) if str(s).strip()]
        hints = [str(h).strip() for h in (data.get("zh_hints") or []) if str(h).strip()]

    # LLM 空/不可挖空 → 模板兜底(仍落库,避免下次再打 LLM)
    if not sents or not _triples_from_pool(
        sents, facet_name=fn, source=_SRC_AI_DEMO, zh_hints=hints,
    ):
        _log.warning("grammar_facet_demo fallback template for %s / %s", pn, fn)
        sents, hints = _template_demo(fn)

    await _write_demo_cache(
        db, point_name=pn, facet_name=fn, sentences=sents, zh_hints=hints)
    return {
        "sentences": sents[:2],
        "zh_hints": (hints + [""] * 2)[:2],
        "cached": cached,
        "source": _SRC_AI_DEMO,
    }


_demo_warmup_tasks: set = set()


def schedule_demo_warmups(items: list[tuple[str, str]]) -> None:
    """后台异步生成示范句并落物理缓存;不阻塞进页。"""
    import asyncio

    async def _one(pn: str, fn: str) -> None:
        from app.core.database import _async_session_factory
        try:
            async with _async_session_factory() as s:
                await ensure_facet_demo_sentences(s, point_name=pn, facet_name=fn)
                await s.commit()
        except Exception as exc:  # noqa: BLE001
            _log.warning("demo warmup failed %s/%s: %s", pn, fn, exc)

    for pn, fn in items:
        t = asyncio.create_task(_one(pn, fn))
        _demo_warmup_tasks.add(t)
        t.add_done_callback(_demo_warmup_tasks.discard)


def _pack_facet(
    *, fname: str, sentences_fallback: list[str], triples: list[dict],
    sentence_items: list[dict], source_kind: str, passed: bool,
    need_demo: bool, prefix: str,
) -> dict:
    cloze_compat = []
    questions_flat = []
    for t in triples:
        for step in t["steps"]:
            questions_flat.append(step)
        if t["steps"]:
            cloze_compat.append({
                k: t["steps"][0][k]
                for k in ("id", "stem", "options", "answer",
                          "explanation", "source_sentence")
                if k in t["steps"][0]
            })
    return {
        "name": fname,
        "sentences": [x["text"] for x in sentence_items] or list(sentences_fallback),
        "sentence_items": sentence_items,
        "source": source_kind,
        "need_demo": need_demo,
        "triples": triples,
        "questions": questions_flat,
        "cloze": cloze_compat,
        "passed": passed,
        "locked": False,
    }


def _items_from_demo(demo: dict, *, facet_name: str, prefix: str) -> tuple[list, list, str]:
    triples = _triples_from_pool(
        demo["sentences"], facet_name=facet_name,
        source=_SRC_AI_DEMO, zh_hints=demo.get("zh_hints") or [],
        prefix=prefix,
    )
    items = []
    for j, s in enumerate(demo["sentences"]):
        items.append({
            "text": s,
            "source": _SRC_AI_DEMO,
            "zh_hint": (demo.get("zh_hints") or [None] * 8)[j]
            if j < len(demo.get("zh_hints") or []) else None,
        })
    return triples, items, _SRC_AI_DEMO


async def get_facet_quest(
    db: AsyncSession, *, student_id: uuid.UUID, unit_id: uuid.UUID, node_id: uuid.UUID,
    warmup: bool = True,
) -> dict:
    """取细目 + 一句三练。进页不调 LLM:教材句 → 物理缓存;缺则 need_demo 并异步预热。"""
    from app.models.d22_unit_structured import UnitSection
    from app.models.d28_grammar_facet_quest import StudentGrammarFacetPass
    from app.models.d15_knowledge_graph import KnowledgeNode
    from app.services.kp_title_rewrite_service import display_label

    node = (await db.execute(
        select(KnowledgeNode).where(KnowledgeNode.id == node_id)
    )).scalar_one_or_none()
    if node is None:
        raise AppError(code=404, message="知识点不存在")

    sec = (await db.execute(
        select(UnitSection).where(
            UnitSection.unit_id == unit_id,
            UnitSection.kind == "grammar",
            UnitSection.node_id == node_id,
        ).order_by(UnitSection.sort_order)
    )).scalars().first()
    if sec is None:
        raise AppError(code=404, message="本单元未挂靠该语法点")

    point_name = (sec.point_name or "").strip() or display_label(node.name, node.description)
    facets_raw = sec.facets if isinstance(sec.facets, list) else []
    facets_in: list[dict] = []
    for f in facets_raw:
        if not isinstance(f, dict):
            continue
        name = (f.get("name") or "").strip()
        sents = [t.strip() for t in (f.get("sentences") or [])
                 if isinstance(t, str) and t.strip()]
        if name:
            facets_in.append({"name": name, "sentences": sents})

    if not facets_in:
        from app.models.d22_unit_structured import UnitSectionSentence
        rows = (await db.execute(
            select(UnitSectionSentence.text).where(
                UnitSectionSentence.section_id == sec.id
            ).order_by(UnitSectionSentence.sort_order)
        )).scalars().all()
        sents = [t.strip() for t in rows if t and t.strip()]
        facets_in = [{"name": "例句", "sentences": sents}]

    passed = set((await db.execute(
        select(StudentGrammarFacetPass.facet_name).where(
            StudentGrammarFacetPass.student_id == student_id,
            StudentGrammarFacetPass.unit_id == unit_id,
            StudentGrammarFacetPass.node_id == node_id,
        )
    )).scalars().all())

    facets_out = []
    pending_warm: list[tuple[str, str]] = []
    for i, f in enumerate(facets_in):
        fname = f["name"]
        triples = _triples_from_pool(
            f["sentences"], facet_name=fname, source=_SRC_TEXTBOOK, prefix=f"f{i}-",
        )
        sentence_items: list[dict] = []
        source_kind = _SRC_TEXTBOOK
        need_demo = False

        if triples:
            for t in triples:
                sentence_items.append({
                    "text": t["source_sentence"],
                    "source": _SRC_TEXTBOOK,
                })
        else:
            demo = await get_demo_from_cache(
                db, point_name=point_name, facet_name=fname)
            if demo is not None:
                triples, sentence_items, source_kind = _items_from_demo(
                    demo, facet_name=fname, prefix=f"f{i}d-")
                if not triples:
                    need_demo = True
                    pending_warm.append((point_name, fname))
            else:
                need_demo = True
                source_kind = _SRC_AI_DEMO
                pending_warm.append((point_name, fname))

        facets_out.append(_pack_facet(
            fname=fname, sentences_fallback=list(f["sentences"]),
            triples=triples, sentence_items=sentence_items,
            source_kind=source_kind, passed=fname in passed,
            need_demo=need_demo, prefix=f"f{i}",
        ))

    unlocked = True
    for f in facets_out:
        f["locked"] = not unlocked
        if not f["passed"]:
            unlocked = False

    if warmup and pending_warm:
        # 去重后异步预热
        uniq = list(dict.fromkeys(pending_warm))
        schedule_demo_warmups(uniq)

    all_passed = bool(facets_out) and all(f["passed"] for f in facets_out)
    return {
        "unit_id": str(unit_id),
        "node_id": str(node_id),
        "point_name": point_name,
        "facets": facets_out,
        "passed_count": sum(1 for f in facets_out if f["passed"]),
        "total": len(facets_out),
        "all_passed": all_passed,
    }


async def ensure_facet_quest_demo(
    db: AsyncSession, *, student_id: uuid.UUID, unit_id: uuid.UUID,
    node_id: uuid.UUID, facet_name: str,
) -> dict:
    """点进细目时同步 ensure 示范句(可付费一次)并落库,返回最新闯关态。"""
    name = (facet_name or "").strip()
    if not name:
        raise AppError(code=400, message="细目名不能为空")
    # 先拿 point_name
    q0 = await get_facet_quest(
        db, student_id=student_id, unit_id=unit_id, node_id=node_id, warmup=False)
    await ensure_facet_demo_sentences(
        db, point_name=q0["point_name"], facet_name=name)
    await db.commit()
    return await get_facet_quest(
        db, student_id=student_id, unit_id=unit_id, node_id=node_id, warmup=False)


async def mark_facet_passed(
    db: AsyncSession, *, student_id: uuid.UUID, unit_id: uuid.UUID,
    node_id: uuid.UUID, facet_name: str,
) -> dict:
    """标记某细目一句三练闯关通过(幂等)。"""
    from app.models.d22_unit_structured import UnitSection
    from app.models.d28_grammar_facet_quest import StudentGrammarFacetPass

    name = (facet_name or "").strip()
    if not name:
        raise AppError(code=400, message="细目名不能为空")
    sec = (await db.execute(
        select(UnitSection.id).where(
            UnitSection.unit_id == unit_id,
            UnitSection.kind == "grammar",
            UnitSection.node_id == node_id,
        )
    )).scalar_one_or_none()
    if sec is None:
        raise AppError(code=404, message="本单元未挂靠该语法点")

    await db.execute(
        pg_insert(StudentGrammarFacetPass).values(
            id=uuid.uuid4(),
            student_id=student_id,
            unit_id=unit_id,
            node_id=node_id,
            facet_name=name[:80],
        ).on_conflict_do_nothing(
            constraint="uq_student_grammar_facet_pass")
    )
    await db.flush()
    return await get_facet_quest(
        db, student_id=student_id, unit_id=unit_id, node_id=node_id)
