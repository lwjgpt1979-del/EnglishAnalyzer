"""平台题选项挂词(主·考 / 次·干扰):程序从 options+answer 抽取,无 LLM。

铁律:
- 人工尽量 0:抽得出就挂、抽不出不挡解析采纳。
- 与批量解析共用:suggest 预览 + confirm 落库同一套 extract。
- link_kind=correct|distractor 写 vocab_question(q_scope=platform)。
"""
from __future__ import annotations

import re
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d5_learning import VocabularyWord
from app.models.d16_question_domain import PlatformQuestion
from app.models.d18_vocab_kg import VocabQuestion
from app.services.question_analysis_service import (
    _effective_options, parse_options_lettered, _norm_option_letter,
    parse_given_from_stem, stem_looks_word_fill,
)

_LETTER = "ABCD"
_PREFIX = re.compile(r"^[A-Da-d][.、)．]\s*")
_SEP = re.compile(r"[;,、；，/|]|\s{2,}")

# 适合挂选项词的解析 kind / 题型(阅读理解 excluded:考 rc 技能,不做主考/干扰词边)
_KIND_OK = frozenset({"cloze", "grammar_mc", "word_fill", "passage_fill"})
_SKIP_KIND = frozenset({"writing", "sentence", "reading"})
_QTYPE_OK = frozenset({"单选", "完型", "完形", "填空"})


def _empty_vocab_preview() -> dict:
    return {"correct": [], "distractor": [], "unresolved": False}


def _is_reading_question(
    q: PlatformQuestion, analysis: dict | None = None,
) -> bool:
    """阅读理解/任务型阅读等:不挂主考·干扰词边。"""
    ana = analysis if analysis is not None else analysis_payload_of(q)
    if isinstance(ana, dict):
        if ana.get("kind") == "reading" or ana.get("rc_code"):
            return True
    qt = (q.question_type or "").strip()
    if qt == "阅读":
        return True
    sec = q.section or ""
    if "阅读" in sec and not re.search(r"完形|完型", sec):
        return True
    return False


def _norm_opt(text: str) -> str:
    return _PREFIX.sub("", str(text or "")).strip().strip(".;,、。 ").strip()


def _split_points(text: str) -> list[str]:
    """选项/答案 → 词或短语点(≤4 词、≤40 字符)。

    不做 function-word 过滤:语法单选常考 can/must/of 等虚词本身,滤掉会抽空主考。
    """
    out: list[str] = []
    for part in _SEP.split(_norm_opt(text)):
        p = _norm_opt(part)
        if not p or len(p) > 40 or len(p.split()) > 4:
            continue
        if len(p) < 1:
            continue
        out.append(p)
    return out


def _answer_index(options: list[str], correct_answer: str) -> int:
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


_QUOTE_WORD = re.compile(
    r"[''\"「『]([A-Za-z][A-Za-z'\-]*(?:\s+[A-Za-z][A-Za-z'\-]*){0,3})[''\"」』]"
)


def _distractor_filled(distractors: dict, letter: str) -> bool:
    v = distractors.get(letter) or distractors.get(letter.lower())
    if not isinstance(v, dict):
        return bool(v)
    return bool((str(v.get("meaning") or "").strip()
                 or str(v.get("why_wrong") or "").strip()))


def infer_answer_letter_from_distractors(
    distractors: dict | None, *, lettered: dict[str, str] | None = None,
) -> str | None:
    """干扰项有内容的字母=错项;ABCD 四档中恰好缺一封 = 正确项。

    有 distractors 时固定按 A–D 四档(不随 stem 拆出 3 项就缩成 ABC)。
    """
    if not isinstance(distractors, dict):
        return None
    keys = {_norm_option_letter(str(k)) for k in distractors}
    keys = {k for k in keys if k in _LETTER}
    if not keys:
        return None
    # 标准四选一:字母域始终 A–D(避免只拆出 3 项时 ABC 全填导致无法推出 D)
    letters = list(_LETTER)
    if lettered:
        for L in lettered:
            if L in _LETTER and L not in letters:
                letters.append(L)
    filled = {L for L in letters if _distractor_filled(distractors, L)}
    missing = [L for L in letters if L not in filled]
    return missing[0] if len(missing) == 1 else None


def _lettered_options(
    q: PlatformQuestion | None, stem: str | None, options: list[str] | None,
) -> dict[str, str]:
    """题干字母选项优先;否则 options 列按序映射 A-D。"""
    lettered = parse_options_lettered(stem or "")
    if lettered:
        return lettered
    if q is not None and not lettered:
        lettered = parse_options_lettered(q.stem or "")
    if lettered:
        return lettered
    opts = [str(o) for o in (options or []) if str(o).strip()]
    return {_LETTER[i]: opts[i] for i in range(min(len(opts), len(_LETTER)))}


def _answer_is_letter_only(answer: str | None) -> bool:
    a = (answer or "").strip()
    return len(a) == 1 and a.upper() in _LETTER


def extract_option_vocab_from_word_fill(
    *,
    analysis: dict | None,
    stem: str | None = None,
    answer: str | None = None,
) -> list[dict]:
    """词形/动词填空:主·考=目标形式,次·干扰=所给原形(无 distractors 轴)。"""
    ana = analysis or {}
    given = (str(ana.get("given") or "").strip()
             or parse_given_from_stem(stem or "") or "")
    target = (str(ana.get("target_form") or "").strip()
              or str(ana.get("answer_word") or "").strip())
    if not target and answer and not _answer_is_letter_only(answer):
        target = answer.strip()
    rows: list[dict] = []
    if target:
        for p in _split_points(target):
            rows.append({"text": p, "link_kind": "correct", "option_key": None})
    if given and given.lower() != (target or "").lower():
        for p in _split_points(given):
            if not any(r["text"].lower() == p.lower() for r in rows):
                rows.append({"text": p, "link_kind": "distractor", "option_key": None})
    return rows


def extract_option_vocab_from_passage_fill(
    *,
    analysis: dict | None,
    stem: str | None = None,
    options: list[str] | None = None,
    answer: str | None = None,
    question: PlatformQuestion | None = None,
) -> list[dict]:
    """开放填空/首字母:主·考=answer_word;选词填空若卷面有 A-D 则走 options 轴。"""
    ana = analysis or {}
    st = stem or (question.stem if question else "") or ""
    opts = options if options is not None else (_effective_options(question) if question else None)
    lettered = parse_options_lettered(st)
    if len(lettered) >= 2:
        mcq = extract_option_vocab_from_analysis(
            analysis=ana, stem=st, options=opts, answer=answer, question=question)
        if mcq:
            return mcq
    target = (str(ana.get("answer_word") or "").strip()
              or (str(answer or "").strip() if not _answer_is_letter_only(answer) else ""))
    rows: list[dict] = []
    if target:
        for p in _split_points(target):
            rows.append({"text": p, "link_kind": "correct", "option_key": None})
    return rows


def _use_distractors_axis(analysis: dict | None, stem: str | None) -> bool:
    """仅当真有四选一选项卷面时才走 distractors 主轴。"""
    dss = (analysis or {}).get("distractors")
    if not isinstance(dss, dict) or not dss:
        return False
    if stem_looks_word_fill(stem or ""):
        return False
    return len(parse_options_lettered(stem or "")) >= 2


def extract_option_vocab_from_analysis(
    *,
    analysis: dict | None,
    stem: str | None = None,
    options: list[str] | None = None,
    answer: str | None = None,
    question: PlatformQuestion | None = None,
) -> list[dict]:
    """主轴:解析 distractors + 题干字母选项 → 主考/干扰;词形填空走 given/target。"""
    ana = analysis or {}
    if (ana.get("change_type") or ana.get("target_form")
            or stem_looks_word_fill(stem or (question.stem if question else ""))):
        wf = extract_option_vocab_from_word_fill(
            analysis=ana, stem=stem or (question.stem if question else None), answer=answer)
        if wf:
            return wf
    dss = ana.get("distractors") if isinstance(ana, dict) else None
    if not _use_distractors_axis(ana, stem or (question.stem if question else "")):
        if isinstance(dss, dict) and dss and stem_looks_word_fill(stem or ""):
            return extract_option_vocab_from_word_fill(
                analysis=ana, stem=stem, answer=answer)
        return extract_option_vocab(options=options, answer=answer)

    lettered = _lettered_options(question, stem, options)
    correct_letter = infer_answer_letter_from_distractors(dss, lettered=lettered)
    if not correct_letter and answer:
        ai = _answer_index(list(lettered.get(L, "") for L in _LETTER if L in lettered), answer)
        if ai >= 0:
            correct_letter = _LETTER[ai]
        elif len((answer or "").strip()) == 1 and answer.strip().upper() in _LETTER:
            correct_letter = answer.strip().upper()
    if not correct_letter:
        inferred = infer_answer_from_analysis(
            analysis, list(lettered.values()) or options, stem=stem or (question.stem if question else None))
        if inferred and len(inferred.strip()) == 1 and inferred.upper() in _LETTER:
            correct_letter = inferred.upper()

    if not lettered and not correct_letter:
        return extract_option_vocab(options=options, answer=answer)

    rows: list[dict] = []
    seen_lower: dict[str, str] = {}

    def _push(text: str, kind: str, key: str | None):
        t = text.strip()
        if not t:
            return
        k = t.lower()
        prev = seen_lower.get(k)
        if prev == "correct":
            return
        if prev == "distractor" and kind == "distractor":
            return
        seen_lower[k] = kind
        if prev == "distractor" and kind == "correct":
            rows[:] = [r for r in rows if r["text"].lower() != k]
        rows.append({"text": t, "link_kind": kind, "option_key": key})

    for letter in _LETTER:
        text = lettered.get(letter)
        if not text:
            continue
        if letter == correct_letter:
            kind = "correct"
        elif _distractor_filled(dss, letter):
            kind = "distractor"
        else:
            continue
        for p in _split_points(text):
            _push(p, kind, letter)

    if rows:
        return rows
    return extract_option_vocab(options=options or list(lettered.values()), answer=answer)


def infer_answer_from_analysis(
    analysis: dict | None, options: list[str] | None,
    *, stem: str | None = None,
) -> str | None:
    """从解析反推答案(优先字母)。distractors 缺席字母 > 答案依据引号词 > answer_word。"""
    if not analysis:
        return None
    opts = [str(o) for o in (options or []) if str(o).strip()]
    lettered = parse_options_lettered(stem or "") if stem else {}
    letter = infer_answer_letter_from_distractors(
        analysis.get("distractors"), lettered=lettered or None)
    if letter:
        return letter
    reason = str(analysis.get("answer_reason") or "")
    quoted = _QUOTE_WORD.findall(reason)
    if opts and quoted:
        hits: list[int] = []
        for qw in quoted:
            qi = _answer_index(opts, qw)
            if qi >= 0 and qi not in hits:
                hits.append(qi)
        if len(hits) == 1:
            i = hits[0]
            return _LETTER[i] if i < len(_LETTER) else opts[i]
    for k in ("answer_word", "target_form"):
        v = str(analysis.get(k) or "").strip()
        if v:
            return v
    return None


def analysis_payload_of(q: PlatformQuestion) -> dict | None:
    """已确认解析优先,否则暂存草稿。"""
    meta = q.meta or {}
    if isinstance(meta.get("analysis"), dict):
        return meta["analysis"]
    draft = meta.get("analysis_draft") or {}
    ana = draft.get("analysis") if isinstance(draft, dict) else None
    return ana if isinstance(ana, dict) else None


def effective_answer(
    q: PlatformQuestion, analysis: dict | None = None,
) -> str | None:
    """列上 answer 优先;空则从解析(传入或 meta)反推。"""
    if (q.answer or "").strip() and not _answer_is_letter_only(q.answer):
        return q.answer.strip()
    ana = analysis if analysis is not None else analysis_payload_of(q)
    if ana and (ana.get("change_type") or ana.get("target_form")
                or stem_looks_word_fill(q.stem or "")):
        t = (str(ana.get("target_form") or "").strip()
             or str(ana.get("answer_word") or "").strip())
        if t:
            return t
    if (q.answer or "").strip():
        return q.answer.strip()
    return infer_answer_from_analysis(ana, _effective_options(q), stem=q.stem or "")


def _extract_items(
    q: PlatformQuestion, analysis: dict | None = None,
) -> list[dict]:
    """统一抽取入口(阅读理解 excluded)。"""
    if _is_reading_question(q, analysis):
        return []
    ana = analysis if analysis is not None else analysis_payload_of(q)
    opts = _effective_options(q)
    kind = (ana or {}).get("kind") if isinstance(ana, dict) else None
    if kind == "passage_fill" or (
            isinstance(ana, dict) and ana.get("clue_type") and "distractors" not in ana):
        pf = extract_option_vocab_from_passage_fill(
            analysis=ana, stem=q.stem, options=opts, answer=q.answer, question=q)
        if pf:
            return pf
    return extract_option_vocab_from_analysis(
        analysis=ana, stem=q.stem, options=opts, answer=q.answer, question=q,
    )


def extract_option_vocab(
    *, options: list[str] | None, answer: str | None,
) -> list[dict]:
    """纯函数:options+answer → [{text, link_kind, option_key}]。

    link_kind ∈ correct|distractor。同一 text 若既在正确又在干扰 → 保留 correct。
    双空/多正确点:答案拆点与选项文本相交的均标 correct。
    对不齐正确项时:不把全部选项误标为 distractor(避免「全是次·干扰」)。
    """
    opts = [str(o) for o in (options or []) if str(o).strip()]
    rows: list[dict] = []
    seen_lower: dict[str, str] = {}

    def _push(text: str, kind: str, key: str | None):
        t = text.strip()
        if not t:
            return
        k = t.lower()
        prev = seen_lower.get(k)
        if prev == "correct":
            return
        if prev == "distractor" and kind == "distractor":
            return
        seen_lower[k] = kind
        if prev == "distractor" and kind == "correct":
            rows[:] = [r for r in rows if r["text"].lower() != k]
        rows.append({"text": t, "link_kind": kind, "option_key": key})

    answer_pts = _split_points(answer or "")
    answer_l = {p.lower() for p in answer_pts}

    if opts:
        correct_idx: set[int] = set()
        ai = _answer_index(opts, answer or "")
        if ai >= 0:
            correct_idx.add(ai)
        if answer_l:
            for i, o in enumerate(opts):
                if any(p.lower() in answer_l for p in _split_points(o)):
                    correct_idx.add(i)
        if not correct_idx:
            # 对不齐:仅当答案拆点含字母/汉字时挂为 correct;不把四选项全标干扰
            for p in answer_pts:
                if re.search(r"[A-Za-z\u4e00-\u9fff]", p):
                    _push(p, "correct", None)
            return rows
        for i, o in enumerate(opts):
            key = _LETTER[i] if i < len(_LETTER) else str(i + 1)
            kind = "correct" if i in correct_idx else "distractor"
            for p in _split_points(o):
                _push(p, kind, key)
    else:
        for p in answer_pts:
            _push(p, "correct", None)
    return rows


def preview_option_vocab(
    q: PlatformQuestion, analysis: dict | None = None,
) -> dict:
    """供列表/弹窗只读 chip。analysis 可显式传入(suggest 刚生成的未写 meta 前)。"""
    if _is_reading_question(q, analysis):
        return _empty_vocab_preview()
    items = _extract_items(q, analysis)
    correct = [x["text"] for x in items if x["link_kind"] == "correct"]
    distractor = [x["text"] for x in items if x["link_kind"] == "distractor"]
    opts = _effective_options(q) or list(parse_options_lettered(q.stem or "").values())
    has_opts = bool(opts) or bool(parse_given_from_stem(q.stem or ""))
    return {
        "correct": correct,
        "distractor": distractor,
        "unresolved": has_opts and not correct,
    }


def _eligible(q: PlatformQuestion, *, analysis_kind: str | None = None) -> bool:
    if analysis_kind in _SKIP_KIND:
        return False
    if _is_reading_question(q):
        return False
    if analysis_kind and analysis_kind not in _KIND_OK:
        return False
    qt = (q.question_type or "").strip()
    if qt and qt not in _QTYPE_OK and analysis_kind not in _KIND_OK:
        if not _effective_options(q) and not (q.answer or "").strip():
            return False
    return True


async def _ensure_word(db: AsyncSession, text: str) -> uuid.UUID | None:
    t = (text or "").strip()
    if not t:
        return None
    # 单字符无意义(除 a/I 可能作考点)
    if len(t) == 1 and t.lower() not in ("a", "i"):
        return None
    row = (await db.execute(
        sa.select(VocabularyWord.id).where(sa.func.lower(VocabularyWord.word) == t.lower()).limit(1)
    )).first()
    if row:
        return row[0]
    wid = uuid.uuid4()
    db.add(VocabularyWord(
        id=wid, word=t, definitions=[], difficulty=3,
        type=("phrase" if " " in t else "word"), source="exam",
    ))
    await db.flush()
    return wid


async def attach_platform_option_vocab(
    db: AsyncSession, *, question: PlatformQuestion, analysis_kind: str | None = None,
    analysis: dict | None = None, writeback_answer: bool = False,
) -> dict:
    """确认解析后挂边。best-effort:失败/抽空不抛。返回 {attached, correct, distractor}。

    writeback_answer=True 且列上无 answer 时,把反推字母写回 question.answer。
    """
    empty = {"attached": 0, "correct": 0, "distractor": 0}
    if question is None or not _eligible(question, analysis_kind=analysis_kind):
        return empty
    opts = _effective_options(question)
    ans = effective_answer(question, analysis)
    if writeback_answer and not (question.answer or "").strip() and ans:
        question.answer = ans
    items = _extract_items(question, analysis=analysis or analysis_payload_of(question))
    if not items:
        return empty

    # 清掉本提旧的 correct/distractor,再写入(幂等重挂)
    await db.execute(
        sa.delete(VocabQuestion).where(
            VocabQuestion.q_scope == "platform",
            VocabQuestion.question_id == question.id,
            VocabQuestion.link_kind.in_(("correct", "distractor")),
        )
    )

    n_ok = n_bad = 0
    for it in items:
        wid = await _ensure_word(db, it["text"])
        if wid is None:
            continue
        await db.execute(
            pg_insert(VocabQuestion).values(
                word_id=wid, q_scope="platform", question_id=question.id,
                source="option", link_kind=it["link_kind"],
                option_key=it.get("option_key"),
            ).on_conflict_do_update(
                index_elements=["word_id", "q_scope", "question_id"],
                set_={
                    "link_kind": it["link_kind"],
                    "option_key": it.get("option_key"),
                    "source": "option",
                },
            )
        )
        if it["link_kind"] == "correct":
            n_ok += 1
        else:
            n_bad += 1
    await db.flush()
    return {"attached": n_ok + n_bad, "correct": n_ok, "distractor": n_bad}


async def list_platform_questions_for_word(
    db: AsyncSession, *, word_id: uuid.UUID,
    link_kind: str | None = None, role: str | None = None,
    pool: str | None = None, exam_type: str | None = None,
    region_code: str | None = None,
    limit: int = 50, skip: int = 0,
) -> tuple[list[dict], int, str | None]:
    """按词反查真题:role/link_kind=correct|distractor|any;pool=standalone_word_mcq 等。"""
    from app.services import region_service
    from app.services.option_vocab_stats_service import pool_analysis_kinds, POOL_OPTION_VOCAB_SLOT

    rk = role or link_kind or "correct"
    if rk == "any":
        kinds = ("correct", "distractor")
    elif rk in ("correct", "distractor"):
        kinds = (rk,)
    else:
        return [], 0, None

    vq, pq = VocabQuestion, PlatformQuestion
    pool_key = pool or POOL_OPTION_VOCAB_SLOT
    kind_set = pool_analysis_kinds(pool_key)
    filters = [
        vq.word_id == word_id,
        vq.q_scope == "platform",
        vq.link_kind.in_(kinds),
        pq.type == "real",
        pq.meta["analysis"]["option_vocab_ready"].as_boolean().is_(True),
    ]
    if kind_set:
        filters.append(pq.meta["analysis"]["kind"].astext.in_(list(kind_set)))
    if exam_type:
        filters.append(pq.exam_type == exam_type)
    if region_code:
        filters.append(pq.region_code.like(f"{region_code}%"))

    join = sa.and_(vq.question_id == pq.id, *filters[3:])
    base = sa.select(vq).join(pq, join).where(
        vq.word_id == word_id, vq.q_scope == "platform", vq.link_kind.in_(kinds))

    total = int((await db.execute(
        sa.select(sa.func.count()).select_from(base.subquery())
    )).scalar_one())

    rows = (await db.execute(
        sa.select(pq, vq.link_kind, vq.option_key)
        .select_from(vq)
        .join(pq, join)
        .where(vq.word_id == word_id, vq.q_scope == "platform", vq.link_kind.in_(kinds))
        .order_by(pq.created_at.desc())
        .offset(skip).limit(limit)
    )).all()

    word_text = (await db.execute(
        sa.select(VocabularyWord.word).where(VocabularyWord.id == word_id)
    )).scalar_one_or_none()

    codes = [str(q.region_code) for q, _, _ in rows if q.region_code]
    bd = await region_service.region_breakdowns(db, codes) if codes else {}

    items = []
    for q, lk, ok in rows:
        rc = q.region_code or ""
        info = bd.get(rc, {})
        ana = analysis_payload_of(q)
        ld = (ana or {}).get("logic_display") if isinstance(ana, dict) else None
        items.append({
            "question_id": str(q.id),
            "paper_id": str(q.paper_id) if q.paper_id else None,
            "question_no": q.question_no,
            "section": q.section,
            "stem": (q.stem or "")[:200],
            "link_kind": lk,
            "option_key": ok,
            "analysis_kind": (ana or {}).get("kind") if isinstance(ana, dict) else None,
            "logic_display": ld if isinstance(ld, dict) else None,
            "region_code": rc or None,
            "region_name": info.get("city") or info.get("province") or q.region_name,
            "exam_type": q.exam_type,
            "option_vocab": preview_option_vocab(q),
        })
    return items, total, word_text


async def option_vocab_for_questions(
    db: AsyncSession, questions: list[PlatformQuestion],
) -> dict[uuid.UUID, dict]:
    """题 → {correct, distractor, unresolved}。优先已落库边,否则实时预览。"""
    ids = [q.id for q in questions]
    out: dict[uuid.UUID, dict] = {
        qid: {"correct": [], "distractor": [], "unresolved": False} for qid in ids
    }
    if not ids:
        return out
    r = await db.execute(
        sa.select(VocabQuestion, VocabularyWord.word)
        .join(VocabularyWord, VocabularyWord.id == VocabQuestion.word_id)
        .where(
            VocabQuestion.q_scope == "platform",
            VocabQuestion.question_id.in_(ids),
            VocabQuestion.link_kind.in_(("correct", "distractor")),
        )
    )
    by_q: dict[uuid.UUID, dict] = {}
    for vq, w in r.all():
        slot = by_q.setdefault(vq.question_id, {"correct": [], "distractor": []})
        bucket = slot["correct"] if vq.link_kind == "correct" else slot["distractor"]
        if w and w not in bucket:
            bucket.append(w)
    for q in questions:
        if q.id in by_q and (by_q[q.id]["correct"] or by_q[q.id]["distractor"]):
            out[q.id] = {**by_q[q.id], "unresolved": False}
        elif _is_reading_question(q):
            out[q.id] = _empty_vocab_preview()
        else:
            out[q.id] = preview_option_vocab(q)
    return out
