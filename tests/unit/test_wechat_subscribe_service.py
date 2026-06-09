"""TDD: wechat_subscribe_service — 微信订阅消息真实接入（V2 M29）。

测试策略：mock httpx.AsyncClient，验证请求参数和错误处理。
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def wechat_mode(monkeypatch):
    """切换到生产微信模式。"""
    monkeypatch.setattr(settings, "wechat_subscribe_provider", "wechat")
    monkeypatch.setattr(settings, "wechat_appid", "wx_test_appid")
    monkeypatch.setattr(settings, "wechat_appsecret", "test_secret")
    monkeypatch.setattr(settings, "wechat_subscribe_template_checkin", "AT0000_CHECKIN_TPL")


@pytest.fixture(autouse=True)
def reset_token_cache():
    """每次测试前清空 token 缓存，避免跨测试污染。"""
    from app.services import wechat_subscribe_service
    wechat_subscribe_service._token_cache["token"] = ""
    wechat_subscribe_service._token_cache["expires_at"] = 0.0
    yield
    wechat_subscribe_service._token_cache["token"] = ""
    wechat_subscribe_service._token_cache["expires_at"] = 0.0


def _mock_http_get(json_data: dict):
    """构造 mock httpx GET 响应。"""
    mock_resp = MagicMock()
    mock_resp.json = MagicMock(return_value=json_data)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_resp)
    return mock_client


def _mock_http_post(json_data: dict):
    """构造 mock httpx POST 响应。"""
    mock_resp = MagicMock()
    mock_resp.json = MagicMock(return_value=json_data)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_resp)
    return mock_client


# ── tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_checkin_reminder_dev_mock():
    """dev-mock 模式：返回 True，不调 httpx。"""
    from app.services import wechat_subscribe_service

    with patch("httpx.AsyncClient") as MockClient:
        ok = await wechat_subscribe_service.send_checkin_reminder(openid="ox_test", streak_days=3)
    assert ok is True
    MockClient.assert_not_called()


def test_is_dev_default():
    from app.services import wechat_subscribe_service
    assert wechat_subscribe_service._is_dev() is True


@pytest.mark.asyncio
async def test_get_access_token_calls_wechat_api(wechat_mode):
    """_get_access_token 调用正确 URL 和参数。"""
    from app.services import wechat_subscribe_service

    mock_client = _mock_http_get({"access_token": "TEST_TOKEN_123", "expires_in": 7200})

    with patch("httpx.AsyncClient", return_value=mock_client):
        token = await wechat_subscribe_service._get_access_token()

    assert token == "TEST_TOKEN_123"
    mock_client.get.assert_called_once()
    call_kwargs = mock_client.get.call_args
    url = call_kwargs[0][0] if call_kwargs[0] else call_kwargs[1].get("url", "")
    assert "cgi-bin/token" in url
    params = call_kwargs[1].get("params", {}) if call_kwargs[1] else {}
    assert params.get("appid") == "wx_test_appid"
    assert params.get("secret") == "test_secret"
    assert params.get("grant_type") == "client_credential"


@pytest.mark.asyncio
async def test_get_access_token_caches_result(wechat_mode):
    """access_token 缓存命中时不重复请求微信 API。"""
    from app.services import wechat_subscribe_service

    mock_client = _mock_http_get({"access_token": "CACHED_TOKEN", "expires_in": 7200})

    with patch("httpx.AsyncClient", return_value=mock_client):
        t1 = await wechat_subscribe_service._get_access_token()
        t2 = await wechat_subscribe_service._get_access_token()

    assert t1 == t2 == "CACHED_TOKEN"
    # 只调用了一次 GET（第二次命中缓存）
    assert mock_client.get.call_count == 1


@pytest.mark.asyncio
async def test_send_real_subscribe_message_success(wechat_mode):
    """errcode=0 时返回 True。"""
    from app.services import wechat_subscribe_service

    # 预填 token 缓存，避免额外 GET 调用
    import time
    wechat_subscribe_service._token_cache["token"] = "PREFILLED_TOKEN"
    wechat_subscribe_service._token_cache["expires_at"] = time.time() + 7000

    mock_client = _mock_http_post({"errcode": 0, "errmsg": "ok"})

    with patch("httpx.AsyncClient", return_value=mock_client):
        ok = await wechat_subscribe_service._send_real_subscribe_message(
            openid="openid_abc", streak_days=7
        )

    assert ok is True
    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    payload = call_args[1].get("json", {})
    assert payload["touser"] == "openid_abc"
    assert payload["template_id"] == "AT0000_CHECKIN_TPL"
    assert "7 天" in payload["data"]["thing1"]["value"]


@pytest.mark.asyncio
async def test_send_real_subscribe_message_fail_returns_false(wechat_mode):
    """errcode 非 0 时返回 False，不抛错。"""
    from app.services import wechat_subscribe_service

    import time
    wechat_subscribe_service._token_cache["token"] = "PREFILLED_TOKEN"
    wechat_subscribe_service._token_cache["expires_at"] = time.time() + 7000

    mock_client = _mock_http_post({"errcode": 40001, "errmsg": "invalid credential"})

    with patch("httpx.AsyncClient", return_value=mock_client):
        ok = await wechat_subscribe_service._send_real_subscribe_message(
            openid="openid_xyz", streak_days=1
        )

    assert ok is False


@pytest.mark.asyncio
async def test_send_real_subscribe_message_unsubscribed_returns_false(wechat_mode):
    """errcode=43101（用户未订阅）时返回 False，不记 warning 日志。"""
    from app.services import wechat_subscribe_service

    import time
    wechat_subscribe_service._token_cache["token"] = "PREFILLED_TOKEN"
    wechat_subscribe_service._token_cache["expires_at"] = time.time() + 7000

    mock_client = _mock_http_post({"errcode": 43101, "errmsg": "user refuse to accept the msg"})

    with patch("httpx.AsyncClient", return_value=mock_client):
        ok = await wechat_subscribe_service._send_real_subscribe_message(
            openid="openid_nosub", streak_days=3
        )

    assert ok is False


@pytest.mark.asyncio
async def test_send_checkin_reminder_prod_calls_real(wechat_mode):
    """生产模式 send_checkin_reminder 调用真实 API 路径。"""
    from app.services import wechat_subscribe_service

    with patch.object(
        wechat_subscribe_service,
        "_send_real_subscribe_message",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_real:
        ok = await wechat_subscribe_service.send_checkin_reminder(openid="ox_prod", streak_days=5)

    assert ok is True
    mock_real.assert_called_once_with(openid="ox_prod", streak_days=5)


# ── M33: send_bind_notification ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_bind_notification_dev_mock():
    """dev-mock 模式：返回 True，不调 httpx。"""
    from app.services import wechat_subscribe_service

    with patch("httpx.AsyncClient") as MockClient:
        ok = await wechat_subscribe_service.send_bind_notification(
            openid="ox_student", relative_nickname="张妈妈", relationship="母亲"
        )
    assert ok is True
    MockClient.assert_not_called()


@pytest.mark.asyncio
async def test_send_bind_notification_prod_success(wechat_mode, monkeypatch):
    """生产模式绑定通知成功推送。"""
    from app.services import wechat_subscribe_service
    import time

    monkeypatch.setattr(settings, "wechat_subscribe_template_bind", "AT0000_BIND_TPL")
    wechat_subscribe_service._token_cache["token"] = "PREFILLED_TOKEN"
    wechat_subscribe_service._token_cache["expires_at"] = time.time() + 7000

    mock_client = _mock_http_post({"errcode": 0, "errmsg": "ok"})

    with patch("httpx.AsyncClient", return_value=mock_client):
        ok = await wechat_subscribe_service.send_bind_notification(
            openid="ox_student", relative_nickname="李爸爸", relationship="父亲"
        )

    assert ok is True
    mock_client.post.assert_called_once()
    payload = mock_client.post.call_args[1].get("json", {})
    assert payload["touser"] == "ox_student"
    assert payload["template_id"] == "AT0000_BIND_TPL"
    assert "李爸爸" in payload["data"]["thing1"]["value"]
    assert "父亲" in payload["data"]["thing1"]["value"]


@pytest.mark.asyncio
async def test_send_bind_notification_prod_unsubscribed_returns_false(wechat_mode, monkeypatch):
    """43101 未订阅时返回 False，不抛错。"""
    from app.services import wechat_subscribe_service
    import time

    monkeypatch.setattr(settings, "wechat_subscribe_template_bind", "AT0000_BIND_TPL")
    wechat_subscribe_service._token_cache["token"] = "PREFILLED_TOKEN"
    wechat_subscribe_service._token_cache["expires_at"] = time.time() + 7000

    mock_client = _mock_http_post({"errcode": 43101, "errmsg": "user refuse to accept the msg"})

    with patch("httpx.AsyncClient", return_value=mock_client):
        ok = await wechat_subscribe_service.send_bind_notification(
            openid="ox_nosub", relative_nickname="王奶奶", relationship="祖母"
        )

    assert ok is False


@pytest.mark.asyncio
async def test_send_bind_notification_prod_calls_real(wechat_mode):
    """生产模式 send_bind_notification 调用真实 API 路径。"""
    from app.services import wechat_subscribe_service

    with patch.object(
        wechat_subscribe_service,
        "_send_real_bind_notification",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_real:
        ok = await wechat_subscribe_service.send_bind_notification(
            openid="ox_p", relative_nickname="陈叔叔", relationship="叔叔"
        )

    assert ok is True
    mock_real.assert_called_once_with(
        openid="ox_p", relative_nickname="陈叔叔", relationship="叔叔"
    )


# ── M35: send_assignment_notification ────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_assignment_notification_dev_mock():
    """dev-mock 模式：返回 True，不调 httpx。"""
    from app.services import wechat_subscribe_service

    with patch("httpx.AsyncClient") as MockClient:
        ok = await wechat_subscribe_service.send_assignment_notification(
            openid="ox_student", assignment_title="期末复习卷", teacher_name="李老师", due_at_str="06月15日 23:59"
        )
    assert ok is True
    MockClient.assert_not_called()


@pytest.mark.asyncio
async def test_send_assignment_notification_prod_success(wechat_mode, monkeypatch):
    """生产模式作业通知成功推送，payload 包含正确字段。"""
    from app.services import wechat_subscribe_service
    import time

    monkeypatch.setattr(settings, "wechat_subscribe_template_assignment", "AT0000_ASSIGN_TPL")
    wechat_subscribe_service._token_cache["token"] = "PREFILLED_TOKEN"
    wechat_subscribe_service._token_cache["expires_at"] = time.time() + 7000

    mock_client = _mock_http_post({"errcode": 0, "errmsg": "ok"})

    with patch("httpx.AsyncClient", return_value=mock_client):
        ok = await wechat_subscribe_service.send_assignment_notification(
            openid="ox_s1", assignment_title="语法专项练习", teacher_name="王老师", due_at_str="06月20日 18:00"
        )

    assert ok is True
    payload = mock_client.post.call_args[1].get("json", {})
    assert payload["touser"] == "ox_s1"
    assert payload["template_id"] == "AT0000_ASSIGN_TPL"
    assert payload["data"]["thing1"]["value"] == "语法专项练习"
    assert payload["data"]["thing2"]["value"] == "王老师"
    assert payload["data"]["time3"]["value"] == "06月20日 18:00"


@pytest.mark.asyncio
async def test_send_assignment_notification_prod_calls_real(wechat_mode):
    """生产模式 send_assignment_notification 调用真实 API 路径。"""
    from app.services import wechat_subscribe_service

    with patch.object(
        wechat_subscribe_service,
        "_send_real_assignment_notification",
        new_callable=AsyncMock,
        return_value=True,
    ) as mock_real:
        ok = await wechat_subscribe_service.send_assignment_notification(
            openid="ox_p2", assignment_title="阅读理解", teacher_name="张老师", due_at_str="无截止时间"
        )

    assert ok is True
    mock_real.assert_called_once_with(
        openid="ox_p2", assignment_title="阅读理解", teacher_name="张老师", due_at_str="无截止时间"
    )
