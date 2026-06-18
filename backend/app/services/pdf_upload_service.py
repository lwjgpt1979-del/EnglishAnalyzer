"""教材 PDF 上传 + 文本提取 + 单元自动检测（M3）。

流程：
  1. save_upload()       — 保存 bytes 到 uploads/pdfs/<file_id>.pdf
  2. extract_pages()     — pdfplumber 逐页提取文本，返回 list[str]（index 0 = 第 1 页）
  3. auto_detect_units() — 扫描页文本识别单元分界，返回 list[dict] | None
  4. get_unit_text()     — 拼接指定页范围文本，供 AI 生成使用
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

UPLOAD_DIR = Path(__file__).parent.parent.parent / "uploads" / "pdfs"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 常见单元标题匹配模式
_UNIT_PATTERNS = [
    re.compile(r"\bUnit\s+(\d+)\b", re.IGNORECASE),
    re.compile(r"\bUnit\s+(One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten)\b", re.IGNORECASE),
    re.compile(r"第\s*([一二三四五六七八九十\d]+)\s*单元"),
    re.compile(r"\bStarter\s+Unit\b", re.IGNORECASE),
]

_WORD_TO_INT: dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_CN_TO_INT: dict[str, int] = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}


# ─── 文件存储 ─────────────────────────────────────────────────────────────────

def save_upload(file_bytes: bytes) -> str:
    """保存上传文件，返回 file_id（hex UUID，不含扩展名）。"""
    file_id = uuid.uuid4().hex
    (UPLOAD_DIR / f"{file_id}.pdf").write_bytes(file_bytes)
    return file_id


def delete_upload(file_id: str) -> None:
    """生成完成后清理临时文件（optional）。"""
    (UPLOAD_DIR / f"{file_id}.pdf").unlink(missing_ok=True)


# ─── 文本提取 ─────────────────────────────────────────────────────────────────

def extract_pages(file_id: str) -> list[str]:
    """逐页提取文本，返回 list（index 0 = 第 1 页）。需要 pdfplumber。"""
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError("pdfplumber 未安装，请 pip install pdfplumber") from exc

    path = UPLOAD_DIR / f"{file_id}.pdf"
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {file_id}")

    pages: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages.append(text.strip())
    return pages


# ─── 单元自动检测 ─────────────────────────────────────────────────────────────

def _parse_unit_no(m: re.Match) -> int | None:
    """从正则匹配提取单元编号（整数）；Starter Unit → None（调用方处理）。"""
    if not m.lastindex:
        return None  # Starter Unit 等无编号模式
    raw = m.group(1)
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    raw_lower = raw.lower() if isinstance(raw, str) else ""
    if raw_lower in _WORD_TO_INT:
        return _WORD_TO_INT[raw_lower]
    if raw in _CN_TO_INT:
        return _CN_TO_INT[raw]
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


# 末单元尾部常跟 Workbook / 词汇表 / 不规则动词表 / 附录 等非单元正文 → 据此裁剪末单元结束页。
_BACKMATTER_PATTERNS = [
    re.compile(r"\bWorkbook\b", re.I),
    re.compile(r"\bWord\s?list\b", re.I),
    re.compile(r"\bVocabulary\b", re.I),
    re.compile(r"\bIrregular\s+verbs\b", re.I),
    re.compile(r"\bGrammar\s+reference\b", re.I),
    re.compile(r"\bAppendix\b", re.I),
    re.compile(r"词汇表|不规则动词|附\s*录"),
]


def _backmatter_start(pages: list[str], after_page: int) -> int | None:
    """从 after_page(1-based,不含)之后找首个后置附录页(Workbook/词汇表/附录…),返回其 1-based 页码。"""
    for idx in range(after_page, len(pages)):   # idx 0-based → 1-based 页 = idx+1 > after_page
        head = (pages[idx] or "")[:120]
        if any(pat.search(head) for pat in _BACKMATTER_PATTERNS):
            return idx + 1
    return None


def auto_detect_units(pages: list[str]) -> list[dict] | None:
    """
    扫描各页文本，识别单元起始页。

    返回 list[dict(unit_no, start_page, end_page, detected_title)]，
    页码均为 1-based；若识别单元数 < 2 则返回 None（触发人工辅助流程）。

    检测策略：只看每页前 500 字符，避免被正文内容的 "Unit" 字样误触发。
    """
    hits: list[tuple[int, int, str]] = []  # (page_1based, unit_no, title_snippet)

    for idx, text in enumerate(pages):
        page_no = idx + 1
        first_line = (text.split("\n")[0][:80] if text else "").strip()
        head = text[:500]
        for pat in _UNIT_PATTERNS:
            m = pat.search(head)
            if m:
                unit_no = _parse_unit_no(m)
                if unit_no is None:
                    unit_no = 0  # Starter Unit → 暂存为 0，后续重排
                # 同一单元只保留首次出现的页
                if not any(h[1] == unit_no for h in hits):
                    hits.append((page_no, unit_no, first_line))
                break

    if len(hits) < 2:
        return None

    hits.sort(key=lambda h: h[0])
    total = len(pages)

    # 重排 unit_no，保证连续（处理 Starter Unit = 0 的情况）
    for i, (pg, uno, title) in enumerate(hits):
        if uno == 0:
            hits[i] = (pg, i + 1, title)

    segments = []
    for i, (start, unit_no, title) in enumerate(hits):
        if i + 1 < len(hits):
            end = hits[i + 1][0] - 1
        else:
            # 末单元:没有下一单元兜底 → 默认到总页数,会把 Workbook/词汇表/附录/封底算进来。
            # 裁剪到首个后置附录页之前(找不到则保持总页数,留人工调整)。
            bm = _backmatter_start(pages, start)
            end = (bm - 1) if bm else total
        segments.append({
            "unit_no": unit_no,
            "start_page": start,
            "end_page": max(start, end),
            "detected_title": title or None,
        })
    return segments


# ─── 文本拼接 ─────────────────────────────────────────────────────────────────

def get_unit_text(file_id: str, start_page: int, end_page: int) -> str:
    """返回指定页范围（1-based 含首尾）的拼接文本，用于 AI 生成上下文。"""
    pages = extract_pages(file_id)
    selected = pages[start_page - 1: end_page]
    return "\n\n---\n\n".join(p for p in selected if p)


def get_page_previews(file_id: str) -> list[dict]:
    """返回每页摘要（前 200 字），供人工选区使用。"""
    pages = extract_pages(file_id)
    return [
        {"page_no": i + 1, "text_snippet": p[:200]}
        for i, p in enumerate(pages)
    ]
