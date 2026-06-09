"""TDD: GET /diagnosis/export-pdf — 学情报告 PDF 导出（V2 M37）。

测试策略：
  1. 未认证 → 401
  2. 无错题用户 → 200，返回 pdf_base64 字段（空数据也能导出）
  3. 返回的 base64 解码后是合法 PDF 二进制（以 %PDF- 开头）
"""
from __future__ import annotations

import base64

import pytest


@pytest.mark.asyncio
async def test_export_pdf_requires_auth(client):
    resp = await client.get("/api/v1/diagnosis/export-pdf")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_export_pdf_returns_200_for_empty_student(client, student_token):
    resp = await client.get(
        "/api/v1/diagnosis/export-pdf",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert "pdf_base64" in data
    assert "filename" in data
    assert data["filename"].endswith(".pdf")


@pytest.mark.asyncio
async def test_export_pdf_base64_is_valid_pdf(client, student_token):
    """解码后的 bytes 应以 b'%PDF-' 开头（合法 PDF 文件头）。"""
    resp = await client.get(
        "/api/v1/diagnosis/export-pdf",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert resp.status_code == 200
    b64 = resp.json()["data"]["pdf_base64"]
    raw = base64.b64decode(b64)
    assert raw[:5] == b"%PDF-", f"Expected PDF header, got: {raw[:10]}"
