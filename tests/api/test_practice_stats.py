"""V2 M16 — 练习统计接口测试。"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_practice_stats_returns_expected_fields(client: AsyncClient, student_token: str):
    """GET /practice/stats 返回 total_practiced、total_correct、correct_rate 字段。"""
    headers = {"Authorization": f"Bearer {student_token}"}
    r = await client.get("/api/v1/practice/stats", headers=headers)
    assert r.status_code == 200
    data = r.json().get("data") or {}
    assert "total_practiced" in data
    assert "total_correct" in data
    assert "correct_rate" in data
    assert isinstance(data["total_practiced"], int)
    assert isinstance(data["correct_rate"], float)
