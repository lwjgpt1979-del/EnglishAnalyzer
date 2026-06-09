"""PDF 上传 & 单元生成 schemas（M3）。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class UnitSegment(BaseModel):
    """一个单元对应的页码范围（1-based）。"""
    unit_no: int = Field(..., ge=1)
    start_page: int = Field(..., ge=1)
    end_page: int = Field(..., ge=1)
    detected_title: str | None = None


class PdfUploadOut(BaseModel):
    file_id: str
    filename: str
    total_pages: int
    auto_split_success: bool
    auto_segments: list[UnitSegment]


class PagePreview(BaseModel):
    page_no: int
    text_snippet: str  # 前 200 字，供人工选区参考


class PdfPageListOut(BaseModel):
    file_id: str
    total_pages: int
    pages: list[PagePreview]


class GenerateFromPdfRequest(BaseModel):
    textbook_version: str = Field(..., min_length=1)
    grade: str = Field(..., min_length=1)
    semester: str = Field(..., pattern=r"^[上下]$")
    segments: list[UnitSegment] = Field(..., min_length=1)
    content_status: str = "published"


class UnitGenerateResult(BaseModel):
    unit_no: int
    unit_title: str
    kp_count: int
    word_count: int
    status: str  # "ok" | "error"
    error: str | None = None


class GenerateFromPdfOut(BaseModel):
    results: list[UnitGenerateResult]
    success_count: int
    error_count: int
