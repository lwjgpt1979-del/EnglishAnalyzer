"""WordNet 词汇关系校验(P2):用权威词库**确认** LLM 出的近义/反义是否真实,确认的升为高置信。
不从 WordNet 生成(其近义常含生僻/跨义噪音,如 happy→felicitous/lionize),只做"校验器"。
nltk / wordnet 语料缺失时优雅降级(返回空集 → 不升级,退回 P4 命中词库判定)。
部署需:pip install nltk + `python -m nltk.downloader wordnet omw-1.4`。"""
from __future__ import annotations

import functools

try:
    from nltk.corpus import wordnet as _wn
    _wn.synsets("test")   # 触发语料加载,缺数据即抛 → 降级
    _HAS_WORDNET = True
except Exception:   # noqa: BLE001
    _HAS_WORDNET = False

# 我方义项词性 → WordNet 词性;prep/conj 等 WordNet 无 → None(不校验)
_POS = {"verb": "v", "noun": "n", "adj": "a", "adjective": "a", "adv": "r", "adverb": "r"}


def _wn_pos(pos: str) -> str | None:
    p = (pos or "").strip().lower()
    for k, v in _POS.items():
        if p.startswith(k):
            return v
    return None


@functools.lru_cache(maxsize=4096)
def synonyms(word: str, pos: str) -> frozenset[str]:
    """WordNet 里该词(按词性)的近义词集合(小写、去自身、下划线转空格)。"""
    if not _HAS_WORDNET:
        return frozenset()
    wp = _wn_pos(pos)
    w = word.strip().lower()
    out: set[str] = set()
    try:
        for ss in _wn.synsets(w, pos=wp):
            for lm in ss.lemmas():
                n = lm.name().replace("_", " ").lower()
                if n and n != w:
                    out.add(n)
    except Exception:   # noqa: BLE001
        return frozenset()
    return frozenset(out)


@functools.lru_cache(maxsize=4096)
def antonyms(word: str, pos: str) -> frozenset[str]:
    """WordNet 里该词(按词性)的反义词集合。"""
    if not _HAS_WORDNET:
        return frozenset()
    wp = _wn_pos(pos)
    w = word.strip().lower()
    out: set[str] = set()
    try:
        for ss in _wn.synsets(w, pos=wp):
            for lm in ss.lemmas():
                for a in lm.antonyms():
                    out.add(a.name().replace("_", " ").lower())
    except Exception:   # noqa: BLE001
        return frozenset()
    return frozenset(out)


def confirm(word: str, pos: str, kind: str, candidate: str) -> bool:
    """WordNet 是否确认 candidate 是 word 的 近义(kind='synonym')/反义(kind='antonym')。"""
    c = (candidate or "").strip().lower()
    if not c:
        return False
    pool = synonyms(word, pos) if kind == "synonym" else antonyms(word, pos)
    return c in pool
