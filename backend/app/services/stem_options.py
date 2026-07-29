"""选择题干内联选项拆分(上传作业题选项常混在 stem 里)。

返回 (纯题干, ["A. …","B. …",…]);拆不出则 (原 stem, None)。
供落库 / 存量批刷 / 错题选项解析共用。
"""
from __future__ import annotations

import re

_MARK = re.compile(r"(?:(?<=\s)|^)([A-D])[.、)．]\s*")


def parse_inline_options(text: str) -> tuple[str, list[str] | None]:
    """从题干解析「A. .. B. .. C. .. D. ..」。
    至少 A/B/C 依序出现才认定;选项写成带字母前缀的列表便于展示。"""
    if not text:
        return "", None
    ms = list(_MARK.finditer(text))
    letters = [m.group(1) for m in ms]
    if len(letters) < 3 or letters[:3] != ["A", "B", "C"]:
        return text, None
    stem = text[: ms[0].start()].strip()
    opts: list[str] = []
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(text)
        body = text[m.end() : end].strip().rstrip(".;,、。")
        if not body:
            continue
        letter = m.group(1)
        opts.append(f"{letter}. {body}" if not body.upper().startswith(f"{letter}.") else body)
    if len(opts) < 3:
        return text, None
    return (stem or text), opts


def split_stem_for_store(stem: str | None) -> tuple[str | None, list[str] | None]:
    """落库用:能拆则题干去选项 + options;否则原样、options=None。"""
    if stem is None:
        return None, None
    clean, opts = parse_inline_options(stem)
    return clean, opts
