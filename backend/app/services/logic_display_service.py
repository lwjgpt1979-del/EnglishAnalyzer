"""单独逻辑题展示:语境句 + 空位/选项 + 答案。

LLM 同次返回 logic_stem(完形/短文填空可按原文改写生成自足句);
程序校验(含空/不填答案/扎根原文) + compose 兜底合成。
"""
from __future__ import annotations

import re

from app.models.d16_question_domain import PlatformQuestion
from app.services.question_analysis_service import (
    _effective_options,
    parse_options_lettered,
    parse_given_from_stem,
    stem_looks_word_fill,
)

_BLANK = "____"
_BLANK_MARKER = re.compile(r"_{2,}\s*\d*\s*_{2,}")
_BLANK_TOKEN = "__BLANK__"


def _format_options_line(lettered: dict[str, str]) -> str:
    parts = []
    for L in "ABCD":
        if L in lettered and lettered[L]:
            parts.append(f"{L}. {lettered[L]}")
    return "  ".join(parts)


def _lettered_from_question(q: PlatformQuestion) -> dict[str, str]:
    stem = q.stem or ""
    lettered = parse_options_lettered(stem)
    if lettered:
        return lettered
    opts = _effective_options(q)
    if opts:
        return {L: opts[i] for i, L in enumerate("ABCD") if i < len(opts)}
    return {}


def _blank_word_in_text(text: str, words: list[str]) -> str | None:
    """在 text 中将首个匹配的 answer 词替换为 ____。"""
    if not text or not words:
        return None
    for w in words:
        w = (w or "").strip()
        if not w or len(w) < 1:
            continue
        pat = re.compile(rf"\b{re.escape(w)}\b", re.I)
        if pat.search(text):
            return pat.sub(_BLANK, text, count=1)
    return None


def _normalize_blank_markers(text: str) -> str | None:
    """clue/短文里已有 ____12____ 类空位 → 规范为 ____。"""
    if not text or not _BLANK_MARKER.search(text):
        return None
    out = _BLANK_MARKER.sub(_BLANK, text)
    out = re.sub(r"_+", _BLANK, out)
    return out.strip()


def _sentence_with_blank_from_passage(passage: str, question_no: str | None) -> str | None:
    """从短文截取含本空编号空位的一句(线索句不含空位时用)。"""
    if not passage or not question_no:
        return None
    qn = re.sub(r"\D", "", str(question_no))
    if not qn:
        return None
    marker = re.compile(rf"_{2,}\s*{re.escape(qn)}\s*_{2,}", re.I)
    # 按句切分,找含该空位标记的句子
    chunks = re.split(r"(?<=[.!?])\s+|\n+", passage)
    for ch in chunks:
        if marker.search(ch):
            return _normalize_blank_markers(ch.strip()) or ch.strip()
    # 兜底:空位不在句界内时取含标记的窗口
    m = marker.search(passage)
    if not m:
        return None
    start = max(0, passage.rfind(".", 0, m.start()) + 1)
    end = passage.find(".", m.end())
    if end < 0:
        end = min(len(passage), m.end() + 80)
    snippet = passage[start:end].strip()
    return _normalize_blank_markers(snippet) or snippet


def canonicalize_logic_stem(text: str) -> str:
    """规范 AI/程序 logic_stem:空位标记 → ____。"""
    if not text:
        return ""
    t = text.strip()
    norm = _normalize_blank_markers(t)
    if norm:
        return norm
    if _BLANK in t:
        return re.sub(r"_{4,}", _BLANK, t)
    return t


def _canon_blanks_for_match(text: str) -> str:
    """比对用:各类空位统一为占位 token。"""
    s = _BLANK_MARKER.sub(f" {_BLANK_TOKEN} ", text or "")
    s = re.sub(r"_{4,}", f" {_BLANK_TOKEN} ", s)
    return s


def logic_stem_in_context(logic_stem: str, context_text: str) -> bool:
    """logic_stem(含 ____) 是否能在原文中定位(空位归一后子串比对)。"""
    from app.services.question_analysis_service import _norm

    ls = (logic_stem or "").strip()
    ctx = (context_text or "").strip()
    if not ls or not ctx:
        return False
    ls_c = _canon_blanks_for_match(canonicalize_logic_stem(ls))
    ctx_c = _canon_blanks_for_match(ctx)
    if _norm(ls_c) in _norm(ctx_c):
        return True
    # 兜底:去掉空位后的片段仍连续出现在原文
    plain = re.sub(r"_{2,}", " ", ls).strip()
    parts = [p.strip() for p in re.split(r"\s+____\s+|_{4,}", plain) if p.strip()]
    if len(parts) >= 2:
        pos = 0
        nctx = _norm(ctx)
        for part in parts:
            idx = nctx.find(_norm(part), pos)
            if idx < 0:
                return False
            pos = idx + len(_norm(part))
        return True
    return _norm(plain) in _norm(ctx)


def validate_word_fill_logic_stem(
    analysis: dict,
    *,
    stem_text: str,
    answer_words: list[str] | None = None,
) -> list[str]:
    """词形填空 logic_stem:允许 (given)→____ 与题干形态差异。"""
    aw = list(answer_words or [])
    tf = (analysis.get("target_form") or "").strip()
    if tf and tf not in aw:
        aw.append(tf)
    errs = validate_analysis_logic_stem(
        analysis, context_text=stem_text, answer_words=aw, require_blank=True,
        require_substring=True, require_grounded=False)
    if any("不是原文子串" in e for e in errs) and stem_text:
        given = (analysis.get("given") or "").strip()
        relaxed = stem_text
        if given:
            # 半角/全角括号 + 括号内空格:（ wide） / (stay)
            relaxed = re.sub(
                rf"[（(]\s*{re.escape(given)}\s*[）)]",
                "____",
                stem_text,
                count=1,
                flags=re.I,
            )
        if logic_stem_in_context((analysis.get("logic_stem") or ""), relaxed):
            errs = [e for e in errs if "不是原文子串" not in e]
    return errs


_STOPWORDS = {
    "a", "an", "the", "to", "of", "in", "on", "at", "for", "and", "or", "but",
    "is", "are", "was", "were", "be", "been", "being", "it", "its", "they", "them",
    "this", "that", "these", "those", "she", "he", "her", "his", "him", "we", "you",
    "with", "from", "as", "by", "into", "about", "like", "so", "if", "than", "then",
}


def _content_tokens(text: str) -> set[str]:
    return {
        t for t in re.findall(r"[A-Za-z']+", (text or "").lower())
        if len(t) > 2 and t not in _STOPWORDS
    }


def logic_stem_grounded_in_context(logic_stem: str, context_text: str, *, min_hits: int = 2) -> bool:
    """改写句须扎根原文:题干实词与短文有足够重叠(防完全跑题)。"""
    stem_toks = _content_tokens(re.sub(r"_+", " ", logic_stem or ""))
    ctx_toks = _content_tokens(context_text or "")
    if not stem_toks or not ctx_toks:
        return False
    hits = len(stem_toks & ctx_toks)
    need = min(min_hits, max(1, len(stem_toks) // 3))
    return hits >= need


def validate_analysis_logic_stem(
    analysis: dict,
    *,
    context_text: str = "",
    answer_words: list[str] | None = None,
    require_blank: bool = True,
    require_substring: bool = False,
    require_grounded: bool = True,
) -> list[str]:
    """校验 LLM 同次返回的 logic_stem。

    完形/短文填空:logic_stem 允许根据原文**改写生成自足句**,默认不要求原文子串,
    但要求含空、不填答案、实词与短文有重叠(扎根原文)。
    """
    errs: list[str] = []
    raw = (analysis.get("logic_stem") or "").strip()
    if not raw:
        errs.append("缺少 logic_stem(单独逻辑题挖空句)")
        return errs
    canon = canonicalize_logic_stem(raw)
    if require_blank and _BLANK not in canon and not _BLANK_MARKER.search(raw):
        errs.append("logic_stem 须含挖空 ____")
    if len(re.sub(r"_+", "", raw)) < 12:
        errs.append("logic_stem 过短,须为完整自足句")
    for w in answer_words or []:
        w = (w or "").strip()
        if not w:
            continue
        if re.search(rf"\b{re.escape(w)}\b", raw, re.I):
            errs.append(f"logic_stem 不得填入答案词「{w}」")
    if require_substring and context_text and not logic_stem_in_context(canon or raw, context_text):
        errs.append("logic_stem 不是原文子串(疑似改写/幻觉)")
    elif require_grounded and context_text and not logic_stem_grounded_in_context(canon or raw, context_text):
        errs.append("logic_stem 与原文关联过弱(疑似跑题)")
    return errs


def ensure_analysis_logic_stem(
    q: PlatformQuestion,
    analysis: dict,
    *,
    passage: str | None = None,
    vocab_preview: dict | None = None,
    context_text: str | None = None,
) -> bool:
    """方案 A:保证 analysis['logic_stem'] 可用。

    优先保留校验通过的 LLM 句(logic_stem_source=llm);
    缺/不合格则程序 compose 回写(source=compose)。
    返回是否已有可用 logic_stem。
    """
    if not isinstance(analysis, dict):
        return False
    kind = (analysis.get("kind") or "").strip()
    if kind in ("grammar_mc", "reading", "writing", "sentence"):
        return True
    needs = (
        kind in ("cloze", "word_fill", "passage_fill")
        or bool(analysis.get("clue_type"))
        or bool(analysis.get("change_type"))
    )
    if not needs:
        return True

    aw: list[str] = []
    for w in list((vocab_preview or {}).get("correct") or []):
        if w and str(w).strip():
            aw.append(str(w).strip())
    for k in ("answer_word", "target_form"):
        w = (analysis.get(k) or "").strip()
        if w:
            aw.append(w)
    al = (analysis.get("answer_letter") or "").strip().upper()
    lettered = _lettered_from_question(q)
    if al in lettered and lettered[al]:
        aw.append(lettered[al])
    # 去重
    seen: set[str] = set()
    aw_u: list[str] = []
    for w in aw:
        k = w.lower()
        if k not in seen:
            seen.add(k)
            aw_u.append(w)
    aw = aw_u

    ctx = (context_text or passage or "").strip()
    is_word_fill = kind == "word_fill" or bool(analysis.get("change_type"))
    stem_ctx = (q.stem or "") if is_word_fill else ctx

    raw = (analysis.get("logic_stem") or "").strip()
    if raw:
        if is_word_fill:
            verrs = validate_word_fill_logic_stem(
                analysis, stem_text=stem_ctx or ctx, answer_words=aw)
        else:
            verrs = validate_analysis_logic_stem(
                analysis, context_text=ctx, answer_words=aw)
        if not verrs:
            analysis.setdefault("logic_stem_source", "llm")
            return True

    saved = analysis.pop("logic_stem", None)
    analysis.pop("logic_stem_source", None)
    vp = vocab_preview if vocab_preview is not None else {"correct": aw}
    ld = compose_logic_display(q, analysis, passage=passage, vocab_preview=vp)
    stem = (ld.get("logic_stem") or "").strip()
    if stem and ld.get("ready"):
        analysis["logic_stem"] = canonicalize_logic_stem(stem)
        analysis["logic_stem_source"] = "compose"
        return True
    if saved:
        analysis["logic_stem"] = saved
    return False


def _resolve_logic_stem_from_analysis(
    analysis: dict,
    *,
    fallback: str | None,
) -> str | None:
    """优先采用 analysis.logic_stem(AI 同次输出),否则程序兜底。"""
    raw = (analysis.get("logic_stem") or "").strip()
    if raw:
        canon = canonicalize_logic_stem(raw)
        if canon and (_BLANK in canon or _BLANK_MARKER.search(raw)):
            return canon
    return fallback


def _cloze_logic_stem(
    clue: str, words: list[str], *, passage: str | None, question_no: str | None,
) -> str | None:
    """完形逻辑题干:优先 clue 内空位/答案词,否则回短文找 ____N____。"""
    if clue:
        hit = _blank_word_in_text(clue, words)
        if hit:
            return hit
        norm = _normalize_blank_markers(clue)
        if norm:
            return norm
    if passage:
        from_passage = _sentence_with_blank_from_passage(passage, question_no)
        if from_passage:
            return from_passage
    # 线索句仅为语境、空在别句:用 clue + 显式空位(仍可做四选一)
    if clue and words:
        return f"{clue.rstrip('.')} {_BLANK}."
    if clue and _BLANK_MARKER.search(clue):
        return _normalize_blank_markers(clue)
    return None


def _answer_letter_and_text(
    q: PlatformQuestion, analysis: dict | None, lettered: dict[str, str],
    *, correct_words: list[str] | None = None,
) -> tuple[str | None, str | None]:
    from app.services.option_vocab_service import (
        effective_answer, infer_answer_letter_from_distractors, _answer_index, _norm_opt,
    )
    ana = analysis or {}
    ans = effective_answer(q, ana)
    if not ans:
        cw = (correct_words or [None])[0]
        ans = cw
    if ans and len(ans.strip()) == 1 and ans.strip().upper() in "ABCD":
        L = ans.strip().upper()
        return L, lettered.get(L) or ans
    ai = _answer_index(list(lettered.values()), ans or "")
    if ai >= 0:
        L = "ABCD"[ai]
        return L, _norm_opt(list(lettered.values())[ai])
    dss = ana.get("distractors") if isinstance(ana, dict) else None
    L = infer_answer_letter_from_distractors(dss, lettered=lettered or None)
    if L:
        return L, lettered.get(L)
    if correct_words:
        return None, correct_words[0]
    return None, (ans or "").strip() or None


def compose_logic_display(
    q: PlatformQuestion,
    analysis: dict | None = None,
    *,
    passage: str | None = None,
    vocab_preview: dict | None = None,
) -> dict:
    """合成单独逻辑题。ready=False 时不可进统计(如 clue 无法挖空)。"""
    ana = analysis if isinstance(analysis, dict) else {}
    kind = (ana.get("kind") or "").strip()
    correct = list((vocab_preview or {}).get("correct") or [])
    lettered = _lettered_from_question(q)
    opts_line = _format_options_line(lettered)
    opt_list = [lettered[L] for L in "ABCD" if L in lettered]

    base: dict = {
        "ready": False,
        "logic_type": "mcq",
        "logic_stem": "",
        "logic_options": opt_list,
        "logic_options_line": opts_line,
        "logic_answer": None,
        "logic_answer_text": None,
    }

    # 语法单选:题干即逻辑题
    if kind == "grammar_mc" or (
            not kind and not ana.get("clue_type") and lettered and not stem_looks_word_fill(q.stem or "")):
        stem = (q.stem or "").strip()
        if not stem:
            return base
        L, atext = _answer_letter_and_text(q, ana, lettered, correct_words=correct)
        base.update({
            "ready": bool(atext or L),
            "logic_type": "mcq",
            "logic_stem": stem,
            "logic_options": opt_list,
            "logic_options_line": opts_line,
            "logic_answer": L,
            "logic_answer_text": atext,
        })
        return base

    # 完形 / 有 distractors 的四选一
    if kind == "cloze" or (ana.get("clue_type") and ana.get("distractors")):
        clue = (ana.get("clue") or "").strip()
        if not clue:
            return base
        L, atext = _answer_letter_and_text(q, ana, lettered, correct_words=correct)
        words = correct or ([atext] if atext else [])
        logic_stem = _resolve_logic_stem_from_analysis(
            ana,
            fallback=_cloze_logic_stem(
                clue, words, passage=passage, question_no=q.question_no),
        )
        if not logic_stem:
            return base
        base.update({
            "ready": True,
            "logic_type": "mcq",
            "logic_stem": logic_stem,
            "logic_options": opt_list,
            "logic_options_line": opts_line,
            "logic_answer": L,
            "logic_answer_text": atext or (correct[0] if correct else None),
        })
        return base

    # 词形填空
    if kind == "word_fill" or stem_looks_word_fill(q.stem or ""):
        stem = (q.stem or "").strip()
        given = (ana.get("given") or parse_given_from_stem(stem) or "").strip()
        target = (ana.get("target_form") or ana.get("answer_word") or "").strip()
        if not target and correct:
            target = correct[0]
        if not stem:
            return base
        prog_stem = stem
        if given and target and given.lower() != target.lower():
            prog_stem = re.sub(
                rf"\(\s*{re.escape(given)}\s*\)", f"({_BLANK})", stem, count=1, flags=re.I)
            if prog_stem == stem:
                prog_stem = _blank_word_in_text(stem, [target]) or stem
        logic_stem = _resolve_logic_stem_from_analysis(ana, fallback=prog_stem)
        base.update({
            "ready": bool(target),
            "logic_type": "fill",
            "logic_stem": logic_stem,
            "logic_options": [],
            "logic_options_line": "",
            "logic_answer": None,
            "logic_answer_text": target,
        })
        return base

    # 开放缺词 / 首字母
    if kind == "passage_fill" or (ana.get("clue_type") and "distractors" not in ana):
        clue = (ana.get("clue") or "").strip()
        answer_word = (ana.get("answer_word") or "").strip()
        if not answer_word and correct:
            answer_word = correct[0]
        if len(lettered) >= 2:
            L, atext = _answer_letter_and_text(q, ana, lettered, correct_words=correct)
            prog_stem = _blank_word_in_text(clue, [atext or answer_word]) if clue else ""
            logic_stem = _resolve_logic_stem_from_analysis(ana, fallback=prog_stem or None)
            if logic_stem:
                base.update({
                    "ready": True,
                    "logic_type": "mcq",
                    "logic_stem": logic_stem,
                    "logic_options": opt_list,
                    "logic_options_line": opts_line,
                    "logic_answer": L,
                    "logic_answer_text": atext or answer_word,
                })
            return base
        if clue and answer_word:
            prog_stem = _blank_word_in_text(clue, [answer_word])
            logic_stem = _resolve_logic_stem_from_analysis(ana, fallback=prog_stem)
            if logic_stem:
                base.update({
                    "ready": True,
                    "logic_type": "fill",
                    "logic_stem": logic_stem,
                    "logic_options": [],
                    "logic_options_line": "",
                    "logic_answer": None,
                    "logic_answer_text": answer_word,
                })
        return base

    # fallback:仅有选项行
    if lettered:
        L, atext = _answer_letter_and_text(q, ana, lettered, correct_words=correct)
        base.update({
            "ready": bool(correct or atext),
            "logic_type": "mcq",
            "logic_stem": (q.stem or opts_line)[:300],
            "logic_answer": L,
            "logic_answer_text": atext,
        })
    return base


def logic_display_from_meta(analysis: dict | None) -> dict | None:
    """已确认解析中缓存的 logic_display。"""
    if not isinstance(analysis, dict):
        return None
    ld = analysis.get("logic_display")
    return ld if isinstance(ld, dict) else None


def option_vocab_ready_from_analysis(analysis: dict | None) -> bool:
    if not isinstance(analysis, dict):
        return False
    if analysis.get("validation_skipped"):
        return False
    if analysis.get("option_vocab_ready") is True:
        return True
    return False
