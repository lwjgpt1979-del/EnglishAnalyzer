"""作业大题·规范题型枚举(方案 1′ P0)。

单一真源:原卷大题名 / OCR 噪声 → 规范键 section_type → 交互族路由。
- 路径① 有标题:resolve_section_type(label)
- 路径② 无标题:infer_section_type(signals) 规则 α
- β 预留:classify_section_cached —— P0 不调 LLM,恒返回 None
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# ── 规范键(与 user_paper_sections.section_type 对齐;旧键兼容见 LEGACY_MAP)────

KEY_MCQ = "mcq"
KEY_CLOZE = "cloze"
KEY_READING = "reading"
KEY_TASK_READING = "task_reading"
KEY_CHOICE_FILL = "choice_fill"
KEY_VOCAB_USE = "vocab_use"
KEY_VERB_FILL = "verb_fill"
KEY_PASSAGE_FILL = "passage_fill"
KEY_SENTENCE = "sentence_complete"
KEY_READING_FILL = "reading_fill"
KEY_READING_EXPR = "reading_expr"
KEY_READING_QA = "reading_qa"
KEY_WRITING = "writing"
KEY_LISTENING = "listening"
KEY_INFO_RESTORE = "info_restore"
KEY_TRANSLATE = "translate"
KEY_SPELLING = "spelling"
KEY_TRANSFORM = "transform"
KEY_DIALOGUE = "dialogue"
KEY_OTHER = "other"

# P0 深做路由:这些键走选择/语篇+选择分解
P0_ROUTE_KEYS = frozenset({KEY_MCQ, KEY_CLOZE, KEY_READING, KEY_TASK_READING, KEY_CHOICE_FILL})


@dataclass(frozen=True)
class CanonType:
    """规范题型一条。"""
    key: str
    label: str
    family: str          # A|B|C|D|E|other
    aliases: tuple[str, ...] = ()


# 判定顺序敏感:更长/更具体的别名优先(见 resolve 扫描顺序)
CANONICAL_TYPES: tuple[CanonType, ...] = (
    CanonType(KEY_LISTENING, "听力理解", "other", ("听力",)),
    CanonType(KEY_WRITING, "书面表达", "E", ("书面表达", "写作", "作文")),
    CanonType(KEY_CLOZE, "完形填空", "B", ("完形填空", "完型填空", "完形", "完型")),
    CanonType(KEY_INFO_RESTORE, "信息还原", "A", ("信息还原", "还原信息", "还原句子", "信息匹配")),
    CanonType(KEY_TASK_READING, "任务型阅读", "B", ("任务型阅读",)),
    CanonType(KEY_READING_QA, "阅读回答问题", "E",
              ("阅读与回答问题", "阅读并回答问题", "阅读回答问题", "阅读回答")),
    CanonType(KEY_READING_EXPR, "阅读表达", "E", ("阅读表达", "阅读与表达", "读写综合")),
    CanonType(KEY_READING_FILL, "阅读填空", "C", ("阅读填空", "阅读填词")),
    CanonType(KEY_READING, "阅读理解", "B", ("阅读理解",)),
    CanonType(KEY_VERB_FILL, "动词填空", "D", ("动词填空", "所给动词")),
    CanonType(KEY_VOCAB_USE, "词汇运用", "C",
              ("词汇运用", "词语运用", "词汇检测", "词汇应用", "词汇适用", "词汇言运用")),
    CanonType(KEY_PASSAGE_FILL, "短文填空", "C",
              ("短文填空", "缺词填空", "综合填空", "首字母", "选词填空")),
    CanonType(KEY_SENTENCE, "完成句子", "D", ("完成句子", "根据所给中文", "根据所给汉语")),
    CanonType(KEY_TRANSLATE, "句子翻译", "D", ("句子翻译", "翻译句子", "译成英语")),
    CanonType(KEY_SPELLING, "单词拼写", "D", ("单词拼写",)),
    CanonType(KEY_TRANSFORM, "句型转换", "D", ("句型转换",)),
    CanonType(KEY_DIALOGUE, "补全对话", "D", ("补全对话", "对话填空")),
    CanonType(KEY_CHOICE_FILL, "选择填空", "A", ("选择填空",)),
    CanonType(KEY_MCQ, "单项选择", "A",
              ("单项选择", "单项填空", "单项选择题", "单选题", "选择题")),
    CanonType(KEY_OTHER, "其它", "other", ("其它", "其他")),
)

_BY_KEY = {c.key: c for c in CANONICAL_TYPES}
_BY_LABEL = {c.label: c for c in CANONICAL_TYPES}

# 旧 section_type → 新键
LEGACY_MAP = {
    "fill": KEY_VOCAB_USE,
    "单选": KEY_MCQ,
    "完型": KEY_CLOZE,
    "阅读": KEY_READING,
    "写作": KEY_WRITING,
    "填空": KEY_VOCAB_USE,
}


def whitelist_labels() -> list[str]:
    """学生「改题型」白名单(中文 label)。"""
    return [c.label for c in CANONICAL_TYPES]


def label_of(key: str | None) -> str:
    """规范键 → 展示名。"""
    if not key:
        return _BY_KEY[KEY_OTHER].label
    c = _BY_KEY.get(key) or _BY_KEY.get(LEGACY_MAP.get(key or "", ""), None)
    return c.label if c else _BY_KEY[KEY_OTHER].label


def _norm_blob(text: str) -> str:
    s = (text or "").strip()
    s = s.replace("　", "").replace(" ", "")
    s = s.replace("完型", "完形").replace("阅谈", "阅读").replace("衰达", "表达")
    s = s.replace("完形埂空", "完形填空").replace("词汇言运用", "词汇运用")
    s = s.replace("词汇适用", "词汇运用").replace("词汇应用", "词汇运用")
    return s


def resolve_section_type(label: str | None) -> str:
    """路径①:大题标题 / 改题型白名单 → 规范键。识别不到 → other。"""
    raw = (label or "").strip()
    if not raw:
        return KEY_OTHER
    if raw in _BY_LABEL:
        return _BY_LABEL[raw].key
    if raw in LEGACY_MAP:
        return LEGACY_MAP[raw]
    if raw in _BY_KEY:
        return raw

    blob = _norm_blob(raw)
    # 去「第×部分」等前缀噪声再匹配
    blob2 = re.sub(
        r"^(?:[一二三四五六七八九十\d]+|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+)?部分?", "", blob)
    # 「非选择题」含「选择题」子串 → 先挖掉再匹配
    if "非选择" in blob:
        blob, blob2 = blob.replace("非选择题", ""), blob2.replace("非选择题", "")
    for c in CANONICAL_TYPES:
        if c.key == KEY_OTHER:
            continue
        for a in (c.label, *c.aliases):
            if a and a in blob2:
                return c.key
        for a in (c.label, *c.aliases):
            if a and a in blob:
                return c.key
    # 宽一点的阅读兜底(「阅读短文」等)
    if "阅读" in blob and "听力" not in blob:
        if "填空" in blob or "填词" in blob:
            return KEY_READING_FILL
        if "表达" in blob:
            return KEY_READING_EXPR
        if "回答" in blob:
            return KEY_READING_QA
        return KEY_READING
    if "词汇" in blob:
        return KEY_VOCAB_USE
    if "填空" in blob and "动词" in blob:
        return KEY_VERB_FILL
    if "填空" in blob:
        return KEY_PASSAGE_FILL
    return KEY_OTHER


def is_p0_choice_route(key: str | None) -> bool:
    """P0:是否走选择/语篇选择分解(含解析标签+错题按钮族)。"""
    k = LEGACY_MAP.get(key or "", key or "")
    return k in P0_ROUTE_KEYS or k in (KEY_INFO_RESTORE,)


def is_passage_route(key: str | None) -> bool:
    """有语篇工具条/阅读精讲倾向的键。"""
    k = LEGACY_MAP.get(key or "", key or "")
    return k in (KEY_READING, KEY_TASK_READING, KEY_CLOZE, KEY_READING_FILL,
                 KEY_READING_EXPR, KEY_READING_QA, KEY_PASSAGE_FILL, KEY_INFO_RESTORE)


def is_reading_intensive(key: str | None) -> bool:
    """可加入「阅读理解精讲」的板块。"""
    k = LEGACY_MAP.get(key or "", key or "")
    return k in (KEY_READING, KEY_TASK_READING)


@dataclass
class InferSignals:
    """无标题推断用信号。"""
    has_passage: bool = False
    passage_len: int = 0
    blank_count: int = 0          # ____ / 空位
    has_options: bool = False
    question_count: int = 1
    stem_blob: str = ""


def infer_section_type(signals: InferSignals) -> tuple[str, float]:
    """路径② α:题面特征 → (规范键, 置信度 0~1)。"""
    blob = _norm_blob(signals.stem_blob)
    # 写作
    if re.search(r"写一篇|不少于\s*\d+\s*词|书面表达", blob) or (
            signals.passage_len == 0 and "作文" in blob):
        return KEY_WRITING, 0.75
    # 动词填空
    if "所给动词" in blob or ("动词" in blob and "填空" in blob) or re.search(
            r"\([A-Za-z]+\)", signals.stem_blob or ""):
        if signals.has_passage and signals.blank_count >= 3:
            pass  # 可能是语篇动词,仍往下看
        elif not signals.has_options:
            return KEY_VERB_FILL, 0.7
    # 完形:语篇 + 多空 + 选项
    if signals.has_passage and signals.passage_len >= 80:
        if signals.blank_count >= 4 and signals.has_options:
            return KEY_CLOZE, 0.85
        if signals.blank_count >= 5:
            return KEY_CLOZE, 0.7
        if signals.has_options or signals.question_count >= 2:
            return KEY_READING, 0.8
        if signals.blank_count >= 2:
            return KEY_PASSAGE_FILL, 0.65
        return KEY_READING, 0.55
    # 单选
    if signals.has_options and not signals.has_passage:
        return KEY_MCQ, 0.8
    if signals.has_options:
        return KEY_MCQ, 0.6
    return KEY_OTHER, 0.3


async def classify_section_cached(
    db: Any, *, text: str, exam_level: str | None = None,
) -> str | None:
    """β 预留:按文本 md5 查缓存 / 调 LLM 分类。P0 不调 LLM,恒返回 None。

    接通时:feature=section_type_classify,写 section_type_cache,开关 section_type_llm_enabled。
    """
    _ = (db, text, exam_level)
    return None


def suggest_label_and_type(
    *, question_type: str | None, has_passage: bool,
    blank_count: int = 0, has_options: bool = False,
    stem_blob: str = "", question_count: int = 1, passage_len: int = 0,
) -> tuple[str, str, bool]:
    """无原卷大题名时:推断 (label, section_type, is_suggested)。"""
    # 粗 question_type 先映射一把,再被 signals 覆盖
    qt_map = {
        "单选": KEY_MCQ, "完型": KEY_CLOZE, "阅读": KEY_READING,
        "写作": KEY_WRITING, "填空": KEY_VOCAB_USE, "词汇运用": KEY_VOCAB_USE,
    }
    base = qt_map.get(question_type or "")
    sig = InferSignals(
        has_passage=has_passage or passage_len > 0,
        passage_len=passage_len or (200 if has_passage else 0),
        blank_count=blank_count,
        has_options=has_options,
        question_count=question_count,
        stem_blob=stem_blob or "",
    )
    key, conf = infer_section_type(sig)
    if base and conf < 0.6:
        key = base
    if has_passage and key == KEY_OTHER:
        key = KEY_READING
    return label_of(key), key, True
