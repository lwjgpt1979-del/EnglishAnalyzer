"""KP 搜索 API 集成测试（TDD）。"""
from __future__ import annotations
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_kp_search_returns_200(client: AsyncClient):
    """GET /curriculum/kps/search 无参数时返回 200 + list。"""
    resp = await client.get("/api/v1/curriculum/kps/search")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_kp_search_with_keyword(client: AsyncClient):
    """q 参数被接受，返回 200。"""
    resp = await client.get("/api/v1/curriculum/kps/search", params={"q": "完成时"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_kp_search_limit_validation(client: AsyncClient):
    """limit > 20 时返回 422。"""
    resp = await client.get("/api/v1/curriculum/kps/search", params={"limit": 25})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_kp_search_no_answer_leak(client: AsyncClient):
    """返回数据不含敏感字段。"""
    resp = await client.get("/api/v1/curriculum/kps/search")
    assert resp.status_code == 200
    for item in resp.json()["data"]:
        assert "answer" not in item
        assert "content_md" not in item
