"""paper_section_taxonomy 单元测试(路径①/②)。"""
from app.services.paper_section_taxonomy import (
    InferSignals,
    infer_section_type,
    resolve_section_type,
    whitelist_labels,
)


def test_resolve_p0_headers():
    assert resolve_section_type("单项选择") == "mcq"
    assert resolve_section_type("完型填空") == "cloze"
    assert resolve_section_type("第三部分 阅读理解") == "reading"
    assert resolve_section_type("任务型阅读") == "task_reading"
    assert resolve_section_type("词汇运用") == "vocab_use"
    assert resolve_section_type("书面表达") == "writing"


def test_resolve_non_choice_not_mcq():
    assert resolve_section_type("第二部分 非选择题") == "other"


def test_infer_alpha():
    k, _ = infer_section_type(InferSignals(
        has_passage=True, passage_len=300, blank_count=10, has_options=True, question_count=10))
    assert k == "cloze"
    k, _ = infer_section_type(InferSignals(
        has_passage=True, passage_len=400, blank_count=0, has_options=True, question_count=5))
    assert k == "reading"
    k, _ = infer_section_type(InferSignals(has_passage=False, has_options=True))
    assert k == "mcq"


def test_whitelist_contains_p0():
    wl = set(whitelist_labels())
    assert {"单项选择", "完形填空", "阅读理解", "其它"} <= wl
