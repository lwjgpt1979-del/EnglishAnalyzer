"""M3 — PDF 上传解析单元测试（无 HTTP client，直接测 service 层）。"""
from __future__ import annotations

import io
import pytest
from unittest.mock import patch, MagicMock


# ─── pdf_upload_service 测试 ──────────────────────────────────────────────────

def _make_mock_pdf_bytes() -> bytes:
    """用 fpdf2 生成一个带 Unit 标题的迷你 PDF，用于测试。"""
    try:
        from fpdf import FPDF
        pdf = FPDF()
        for i in range(1, 4):
            pdf.add_page()
            pdf.set_font("helvetica", size=16)
            pdf.cell(0, 10, f"Unit {i} Test Title", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("helvetica", size=10)
            pdf.multi_cell(0, 6, f"This is the content of Unit {i}. " * 20)
        return pdf.output()
    except Exception:
        # fpdf2 不可用时跳过
        return b""


def test_save_and_delete_upload(tmp_path, monkeypatch):
    """save_upload 写文件、delete_upload 删文件。"""
    from app.services import pdf_upload_service

    monkeypatch.setattr(pdf_upload_service, "UPLOAD_DIR", tmp_path)
    fid = pdf_upload_service.save_upload(b"fake pdf content")
    assert (tmp_path / f"{fid}.pdf").exists()
    pdf_upload_service.delete_upload(fid)
    assert not (tmp_path / f"{fid}.pdf").exists()


def test_auto_detect_units_english():
    """auto_detect_units 能识别 'Unit N' 格式的分界。"""
    from app.services.pdf_upload_service import auto_detect_units

    pages = [
        "Unit 1\nHello World\nSome content here.",
        "Page 2 content of unit 1.",
        "Page 3 still unit 1.",
        "Unit 2\nA new student\nMore content.",
        "Page 5 still unit 2.",
        "Unit 3\nOur animal friends",
    ]
    segs = auto_detect_units(pages)
    assert segs is not None
    assert len(segs) == 3
    assert segs[0]["unit_no"] == 1
    assert segs[0]["start_page"] == 1
    assert segs[0]["end_page"] == 3
    assert segs[1]["unit_no"] == 2
    assert segs[1]["start_page"] == 4
    assert segs[2]["unit_no"] == 3
    assert segs[2]["start_page"] == 6
    assert segs[2]["end_page"] == 6


def test_auto_detect_units_trims_last_unit_backmatter():
    """末单元结束页裁剪到 Workbook/词汇表/附录之前,不把附录算进末单元(修复 Unit8 偏大)。"""
    from app.services.pdf_upload_service import auto_detect_units

    pages = [
        "Unit 1\nIntro",          # 1
        "unit 1 content",         # 2
        "Unit 2\nIntro",          # 3 末单元起始
        "unit 2 content",         # 4 末单元正文
        "Unit 2 Assessment",      # 5 末单元真实末页
        "Workbook Unit 1 ...",    # 6 后置附录起点 → 应被裁掉
        "Irregular verbs ...",    # 7 附录
        "back cover 定价",         # 8 封底
    ]
    segs = auto_detect_units(pages)
    assert segs is not None
    assert len(segs) == 2
    assert segs[0]["start_page"] == 1 and segs[0]["end_page"] == 2
    # 末单元 3-5(到 Workbook 之前),而非旧逻辑的 3-8(含附录+封底)
    assert segs[1]["start_page"] == 3 and segs[1]["end_page"] == 5


def test_auto_detect_units_last_unit_no_backmatter_keeps_total():
    """末单元后无附录标记 → 结束页保持总页数(不误裁)。"""
    from app.services.pdf_upload_service import auto_detect_units

    pages = [
        "Unit 1\nIntro", "content", "Unit 2\nIntro", "content", "more content",
    ]
    segs = auto_detect_units(pages)
    assert segs is not None and len(segs) == 2
    assert segs[1]["start_page"] == 3 and segs[1]["end_page"] == 5


def test_auto_detect_units_too_few_returns_none():
    """少于 2 个单元分界时返回 None（触发人工辅助流程）。"""
    from app.services.pdf_upload_service import auto_detect_units

    pages = [
        "Unit 1\nContent only one unit.",
        "Page 2 no more units here.",
    ]
    result = auto_detect_units(pages)
    assert result is None


def test_auto_detect_units_chinese():
    """auto_detect_units 能识别中文单元格式。"""
    from app.services.pdf_upload_service import auto_detect_units

    pages = [
        "第一单元\n内容",
        "第一单元第2页",
        "第二单元\n更多内容",
        "第三单元\n内容",
    ]
    segs = auto_detect_units(pages)
    assert segs is not None
    assert len(segs) == 3


def test_get_unit_text(tmp_path, monkeypatch):
    """get_unit_text 返回指定页范围的拼接文本。"""
    from app.services import pdf_upload_service

    monkeypatch.setattr(pdf_upload_service, "UPLOAD_DIR", tmp_path)

    pages_content = ["Page one text.", "Page two text.", "Page three text.", "Page four text."]

    fid = "testfile"
    with patch.object(pdf_upload_service, "extract_pages", return_value=pages_content):
        text = pdf_upload_service.get_unit_text(fid, start_page=2, end_page=3)

    assert "Page two text." in text
    assert "Page three text." in text
    assert "Page one text." not in text
    assert "Page four text." not in text


# ─── curriculum_ai_service.generate_unit_from_text 测试 ──────────────────────

@pytest.mark.asyncio
async def test_generate_unit_from_text_dev_mode():
    """dev 模式下 generate_unit_from_text 返回 mock 数据，不调用 LLM。"""
    from unittest.mock import patch as _patch
    from app.services import curriculum_ai_service

    with _patch("app.services.curriculum_ai_service.is_llm_dev_mode", return_value=True):
        result = await curriculum_ai_service.generate_unit_from_text(
            textbook_version="测试版",
            grade="小学5年级",
            semester="上",
            unit_no=1,
            unit_text="Unit 1 Hello World",
            detected_title="Hello World",
        )

    assert result.unit_no == 1
    assert len(result.knowledge_points) >= 1
    assert len(result.words) >= 1


def test_detect_page_offset_votes_consistent_offset():
    """每页含自己的印刷页码 → 投票得出固定偏移(印刷 = PDF − offset)。"""
    from app.services.pdf_upload_service import detect_page_offset
    pages = ["封面", "版权", "目录"]              # 前 3 页无印刷页码
    for printed in range(1, 28):                  # PDF 第 4..30 页 = 印刷 1..27
        pages.append(f"content exercise 5 page {printed} more text")
    assert detect_page_offset(pages) == 3


def test_detect_page_offset_unclear_returns_zero():
    """页码无一致序列 → 不确定,返回 0(按 PDF 页序显示)。"""
    from app.services.pdf_upload_service import detect_page_offset
    assert detect_page_offset(["random 99", "blah 12", "x 3"]) == 0
