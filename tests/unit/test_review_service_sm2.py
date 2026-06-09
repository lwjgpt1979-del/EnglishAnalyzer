"""TDD: review_service — SM-2 算法单元测试（V2 M36）。

测试策略：
  1. 纯算法 sm2_update() 与 DB 无关，直接单元测试
  2. get_today_review_queue / submit_review 用 DB fixture 集成测试
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest


# ── 纯算法测试（无 DB）────────────────────────────────────────────────────────

def _sm2(quality, review_count=0, ef="2.50", interval=1, today=None):
    from app.services.review_service import sm2_update
    return sm2_update(
        quality=quality,
        review_count=review_count,
        easiness_factor=Decimal(ef),
        review_interval_days=interval,
        today=today or date(2026, 6, 9),
    )


def test_sm2_quality_below_3_resets_count():
    """质量 < 3：review_count 重置为 0，间隔 = 1 天。"""
    r = _sm2(quality=2, review_count=5, ef="2.50", interval=30)
    assert r.review_count == 0
    assert r.review_interval_days == 1
    assert r.next_review_at == date(2026, 6, 10)


def test_sm2_quality_below_3_preserves_ef():
    """质量 < 3：easiness_factor 不变（遗忘不惩罚难度系数）。"""
    r = _sm2(quality=1, review_count=3, ef="2.50", interval=10)
    assert r.easiness_factor == Decimal("2.50")


def test_sm2_first_review_interval_1():
    """首次复习（review_count=0）质量 ≥ 3：interval = 1 天。"""
    r = _sm2(quality=4, review_count=0)
    assert r.review_interval_days == 1
    assert r.review_count == 1


def test_sm2_second_review_interval_6():
    """第二次复习（review_count=1）质量 ≥ 3：interval = 6 天。"""
    r = _sm2(quality=4, review_count=1, interval=1)
    assert r.review_interval_days == 6
    assert r.review_count == 2


def test_sm2_third_review_uses_ef():
    """第三次复习（review_count=2）：interval = round(prev_interval * new_ef)。
    quality=5 时 ef 会先提升再用于计算间隔。"""
    r = _sm2(quality=5, review_count=2, ef="2.50", interval=6)
    # new_ef = 2.50 + 0.10 = 2.60；interval = round(6 * 2.60) = 16
    assert r.review_interval_days == round(6 * float(r.easiness_factor))
    assert r.review_count == 3


def test_sm2_perfect_quality_increases_ef():
    """quality=5（完全掌握）：easiness_factor 提升。"""
    r = _sm2(quality=5, review_count=2, ef="2.50", interval=6)
    assert r.easiness_factor > Decimal("2.50")


def test_sm2_low_quality_3_decreases_ef():
    """quality=3（勉强记得）：easiness_factor 降低，但不低于 1.30。"""
    r = _sm2(quality=3, review_count=3, ef="1.40", interval=10)
    assert Decimal("1.30") <= r.easiness_factor < Decimal("1.40")


def test_sm2_ef_floor_at_1_30():
    """easiness_factor 最低不低于 1.30。"""
    r = _sm2(quality=3, review_count=10, ef="1.30", interval=5)
    assert r.easiness_factor >= Decimal("1.30")


def test_sm2_invalid_quality_raises():
    """quality 超出范围 (0-5) 应抛出 ValueError。"""
    with pytest.raises(ValueError):
        _sm2(quality=6)
    with pytest.raises(ValueError):
        _sm2(quality=-1)


def test_sm2_next_review_at_correct_date():
    """next_review_at = today + interval_days。"""
    today = date(2026, 6, 9)
    r = _sm2(quality=4, review_count=1, interval=1, today=today)
    assert r.review_interval_days == 6
    assert r.next_review_at == today + timedelta(days=6)


# ── API 集成测试（轻量）──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_review_queue_endpoint_requires_auth(client):
    from httpx import AsyncClient
    resp = await client.get("/api/v1/wrong-questions/review-queue")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_review_queue_empty_for_new_user(client):
    """新用户无错题 → review-queue 返回 200，due_items 为空。"""
    from unittest.mock import AsyncMock, patch
    import uuid

    async def _login():
        with patch("app.services.auth_service.wechat_code2session", new_callable=AsyncMock) as m:
            m.return_value = {"openid": f"review_test_{uuid.uuid4().hex[:8]}"}
            resp = await client.post("/api/v1/auth/wx-login", json={"code": "test"})
        return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}

    h = await _login()
    resp = await client.get("/api/v1/wrong-questions/review-queue", headers=h)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "due_items" in data
    assert "stats" in data
    assert data["due_items"] == []
    assert data["stats"]["due_today"] == 0
