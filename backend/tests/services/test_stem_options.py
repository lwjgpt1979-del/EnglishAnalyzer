"""stem_options 内联选项拆分单元测试。"""
from app.services.stem_options import parse_inline_options, split_stem_for_store


def test_parse_reading_mcq():
    stem = (
        "Why was the Chinese alligator rescue project passed? "
        "A. To make them endangered. B. To change their living areas. "
        "C. To save natural environment. D. To protect wild Chinese alligators."
    )
    clean, opts = parse_inline_options(stem)
    assert clean.startswith("Why was")
    assert "A." not in clean
    assert opts is not None and len(opts) == 4
    assert opts[0].startswith("A.")
    assert "protect" in opts[3]


def test_parse_no_options():
    clean, opts = parse_inline_options("Just a sentence without choices.")
    assert opts is None
    assert "Just a sentence" in clean


def test_split_for_store():
    s, o = split_stem_for_store("Q? A. one B. two C. three D. four")
    assert s == "Q?"
    assert o and len(o) == 4
