"""英文词形生成(形态学打底,P1):时态/单复数/比较级用 **lemminflect** 确定性生成,不让 LLM 猜。
lemminflect 未装时优雅降级到规则 + 常见不规则表(与 spaCy 同款"缺库不崩"策略)。
返回 [(词形, 中文标签)];派生(derivation)不可规则化,不在此处理(仍 LLM)。"""
from __future__ import annotations

try:
    from lemminflect import getInflection as _inflect
    _HAS_LEMMINFLECT = True
except Exception:   # noqa: BLE001
    _HAS_LEMMINFLECT = False

# —— 降级用:最常见不规则(仅 lemminflect 未装时兜底)——
_IRREG_VERB: dict[str, tuple[str, str]] = {   # word: (过去式, 过去分词)
    "be": ("was", "been"), "have": ("had", "had"), "do": ("did", "done"), "go": ("went", "gone"),
    "get": ("got", "gotten"), "make": ("made", "made"), "take": ("took", "taken"), "see": ("saw", "seen"),
    "come": ("came", "come"), "know": ("knew", "known"), "give": ("gave", "given"), "find": ("found", "found"),
    "think": ("thought", "thought"), "tell": ("told", "told"), "become": ("became", "become"),
    "leave": ("left", "left"), "feel": ("felt", "felt"), "put": ("put", "put"), "bring": ("brought", "brought"),
    "begin": ("began", "begun"), "keep": ("kept", "kept"), "write": ("wrote", "written"), "run": ("ran", "run"),
    "eat": ("ate", "eaten"), "speak": ("spoke", "spoken"), "read": ("read", "read"), "buy": ("bought", "bought"),
    "sing": ("sang", "sung"), "swim": ("swam", "swum"), "teach": ("taught", "taught"), "catch": ("caught", "caught"),
}
_IRREG_PLURAL = {"child": "children", "man": "men", "woman": "women", "foot": "feet", "tooth": "teeth",
                 "goose": "geese", "mouse": "mice", "person": "people", "sheep": "sheep", "fish": "fish"}
_IRREG_ADJ = {"good": ("better", "best"), "bad": ("worse", "worst"), "far": ("farther", "farthest"),
              "little": ("less", "least"), "many": ("more", "most"), "much": ("more", "most")}


def _v_regular(w: str) -> tuple[str, str, str]:
    """规则动词:(过去式=过去分词, 现在分词)。"""
    if w.endswith("e"):
        past, ing = w + "d", w[:-1] + "ing"
    elif len(w) > 1 and w[-1] == "y" and w[-2] not in "aeiou":
        past, ing = w[:-1] + "ied", w + "ing"
    else:
        past, ing = w + "ed", w + "ing"
    return past, past, ing


def _n_regular(w: str) -> str:
    if w.endswith(("s", "x", "z", "ch", "sh")):
        return w + "es"
    if len(w) > 1 and w[-1] == "y" and w[-2] not in "aeiou":
        return w[:-1] + "ies"
    return w + "s"


def _adj_regular(w: str) -> tuple[str, str]:
    if w.endswith("e"):
        return w + "r", w + "st"
    if len(w) > 1 and w[-1] == "y" and w[-2] not in "aeiou":
        return w[:-1] + "ier", w[:-1] + "iest"
    return w + "er", w + "est"


def _dedupe(pairs: list[tuple[str, str]], base: str) -> list[tuple[str, str]]:
    out, seen = [], {base.lower()}
    for form, label in pairs:
        f = (form or "").strip()
        if f and f.lower() not in seen:
            seen.add(f.lower())
            out.append((f, label))
    return out


def verb_tenses(word: str) -> list[tuple[str, str]]:
    """动词 → [(过去式,'过去式'), (过去分词,'过去分词'), (现在分词,'现在分词')]。"""
    w = word.strip().lower()
    if " " in w or not w.isalpha():
        return []
    if _HAS_LEMMINFLECT:
        vbd = _inflect(w, "VBD"); vbn = _inflect(w, "VBN"); vbg = _inflect(w, "VBG")
        past, part, ing = (vbd[0] if vbd else ""), (vbn[0] if vbn else ""), (vbg[0] if vbg else "")
    else:
        (past, part, ing) = ((*_IRREG_VERB[w], _v_regular(w)[2]) if w in _IRREG_VERB else _v_regular(w))
    pairs = []
    if past:
        pairs.append((past, "过去式"))
    if part and part != past:
        pairs.append((part, "过去分词"))
    if ing:
        pairs.append((ing, "现在分词"))
    return _dedupe(pairs, w)


def noun_plural(word: str) -> list[tuple[str, str]]:
    w = word.strip().lower()
    if " " in w or not w.isalpha():
        return []
    if _HAS_LEMMINFLECT:
        nns = _inflect(w, "NNS")
        pl = nns[0] if nns else _n_regular(w)
    else:
        pl = _IRREG_PLURAL.get(w) or _n_regular(w)
    return _dedupe([(pl, "复数")], w)


def adj_forms(word: str) -> list[tuple[str, str]]:
    """形容词/副词 → [(比较级,'比较级'), (最高级,'最高级')]。长词(多音节)一般 more/most,不强出。"""
    w = word.strip().lower()
    if " " in w or not w.isalpha():
        return []
    if _HAS_LEMMINFLECT:
        jjr = _inflect(w, "JJR"); jjs = _inflect(w, "JJS")
        comp, sup = (jjr[0] if jjr else ""), (jjs[0] if jjs else "")
    elif w in _IRREG_ADJ:
        comp, sup = _IRREG_ADJ[w]
    else:
        comp, sup = _adj_regular(w)
    return _dedupe([(comp, "比较级"), (sup, "最高级")], w)


# pos(LLM 输出 verb/noun/adj/adv/…)→ 维度键 + 生成函数
def forms_for_pos(word: str, pos: str) -> tuple[str, list[tuple[str, str]]] | None:
    """按词性返回 (dim_key, [(词形,标签)]);不适用则 None。"""
    p = (pos or "").strip().lower()
    if p.startswith("verb") or p in ("v", "v."):
        return ("tense", verb_tenses(word))
    if p.startswith("noun") or p in ("n", "n."):
        return ("plural", noun_plural(word))
    if p.startswith("adj") or p.startswith("adv") or p in ("a", "adj.", "adv."):
        return ("comparative", adj_forms(word))
    return None
