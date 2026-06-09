"""TDD: sms_service — 阿里云短信接入 (V2 M24)。

测试策略：通过 sys.modules 注入 mock SDK，无需实际安装阿里云包即可验证调用逻辑。
"""
from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings


def _make_aliyun_mocks():
    """创建 alibabacloud SDK 的 mock 模块树，注入 sys.modules。"""
    # alibabacloud_dysmsapi20170525
    mock_client_cls = MagicMock(name="Client")
    mock_req_cls = MagicMock(name="SendSmsRequest")

    client_mod = types.ModuleType("alibabacloud_dysmsapi20170525.client")
    client_mod.Client = mock_client_cls
    models_mod = types.ModuleType("alibabacloud_dysmsapi20170525.models")
    models_mod.SendSmsRequest = mock_req_cls
    pkg_mod = types.ModuleType("alibabacloud_dysmsapi20170525")
    pkg_mod.client = client_mod
    pkg_mod.models = models_mod

    # alibabacloud_tea_openapi
    mock_config_cls = MagicMock(name="Config")
    tea_models_mod = types.ModuleType("alibabacloud_tea_openapi.models")
    tea_models_mod.Config = mock_config_cls
    tea_pkg_mod = types.ModuleType("alibabacloud_tea_openapi")
    tea_pkg_mod.models = tea_models_mod

    mocks = {
        "alibabacloud_dysmsapi20170525": pkg_mod,
        "alibabacloud_dysmsapi20170525.client": client_mod,
        "alibabacloud_dysmsapi20170525.models": models_mod,
        "alibabacloud_tea_openapi": tea_pkg_mod,
        "alibabacloud_tea_openapi.models": tea_models_mod,
    }
    return mocks, mock_client_cls, mock_req_cls, mock_config_cls


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def aliyun_mode(monkeypatch):
    """将 sms_provider 切到 aliyun 模式。"""
    monkeypatch.setattr(settings, "sms_provider", "aliyun")
    monkeypatch.setattr(settings, "sms_access_key_id", "test-key-id")
    monkeypatch.setattr(settings, "sms_access_key_secret", "test-key-secret")
    monkeypatch.setattr(settings, "sms_sign_name", "engGramer")
    monkeypatch.setattr(settings, "sms_template_code_verify", "SMS_VERIFY_001")
    monkeypatch.setattr(settings, "sms_template_code_invite", "SMS_INVITE_001")


@pytest.fixture
def dev_mode(monkeypatch):
    """确保 sms_provider 为 placeholder（dev mock）。"""
    monkeypatch.setattr(settings, "sms_provider", "placeholder-dev")


# ── tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_sms_code_dev_mode_does_not_call_sdk(dev_mode):
    """dev 模式下 send_sms_code 不调用真实 SDK。"""
    from app.services import sms_service

    with patch.object(sms_service, "_send_real_sms", new_callable=AsyncMock) as mock_real:
        await sms_service.send_sms_code(phone="13800138000", code="123456", purpose="guardian_verify")
        mock_real.assert_not_called()


@pytest.mark.asyncio
async def test_send_sms_code_prod_mode_calls_sdk(aliyun_mode):
    """aliyun 模式下 send_sms_code 调用 _send_real_sms，参数正确传递。"""
    from app.services import sms_service

    with patch.object(sms_service, "_send_real_sms", new_callable=AsyncMock) as mock_real:
        await sms_service.send_sms_code(phone="13800138000", code="654321", purpose="guardian_verify")
        mock_real.assert_called_once_with(phone="13800138000", code="654321", purpose="guardian_verify")


def _inject_sdk_mocks(mocks: dict):
    """将 mock 模块注入 sys.modules，返回原始值供恢复。"""
    orig = {k: sys.modules.get(k) for k in mocks}
    sys.modules.update(mocks)
    return orig


def _restore_sdk_mocks(orig: dict):
    for k, v in orig.items():
        if v is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v


@pytest.mark.asyncio
async def test_send_real_sms_calls_aliyun_client(aliyun_mode):
    """_send_real_sms 使用正确参数构造阿里云 Client 并调用 send_sms。"""
    from app.services import sms_service

    mocks, MockClient, MockReq, MockConfig = _make_aliyun_mocks()

    mock_resp_body = MagicMock()
    mock_resp_body.code = "OK"
    mock_resp_body.message = "OK"
    mock_resp = MagicMock()
    mock_resp.body = mock_resp_body
    mock_client_instance = MagicMock()
    mock_client_instance.send_sms = MagicMock(return_value=mock_resp)
    MockClient.return_value = mock_client_instance

    orig = _inject_sdk_mocks(mocks)
    try:
        await sms_service._send_real_sms(phone="13900139000", code="888888", purpose="guardian_verify")
    finally:
        _restore_sdk_mocks(orig)

    MockClient.assert_called_once()
    # 验证 Config 构造参数
    MockConfig.assert_called_once()
    cfg_kwargs = MockConfig.call_args[1]
    assert cfg_kwargs["access_key_id"] == "test-key-id"
    assert cfg_kwargs["access_key_secret"] == "test-key-secret"
    assert cfg_kwargs["endpoint"] == "dysmsapi.aliyuncs.com"

    MockReq.assert_called_once()
    req_kwargs = MockReq.call_args[1]
    assert req_kwargs["phone_numbers"] == "13900139000"
    assert req_kwargs["sign_name"] == "engGramer"
    assert req_kwargs["template_code"] == "SMS_VERIFY_001"
    assert '"code":"888888"' in req_kwargs["template_param"]

    mock_client_instance.send_sms.assert_called_once()


@pytest.mark.asyncio
async def test_send_real_sms_invite_uses_invite_template(aliyun_mode):
    """purpose=invite_teacher 时使用邀请模板。"""
    from app.services import sms_service

    mocks, MockClient, MockReq, MockConfig = _make_aliyun_mocks()

    mock_resp_body = MagicMock()
    mock_resp_body.code = "OK"
    mock_resp = MagicMock()
    mock_resp.body = mock_resp_body
    mock_client_instance = MagicMock()
    mock_client_instance.send_sms = MagicMock(return_value=mock_resp)
    MockClient.return_value = mock_client_instance

    orig = _inject_sdk_mocks(mocks)
    try:
        await sms_service._send_real_sms(phone="13700137000", code="111111", purpose="invite_teacher")
    finally:
        _restore_sdk_mocks(orig)

    req_kwargs = MockReq.call_args[1]
    assert req_kwargs["template_code"] == "SMS_INVITE_001"


@pytest.mark.asyncio
async def test_send_sms_code_sdk_error_raises_app_error(aliyun_mode):
    """SDK 返回非 OK code 时，抛出 AppError。"""
    from app.core.exceptions import AppError
    from app.services import sms_service

    mocks, MockClient, MockReq, MockConfig = _make_aliyun_mocks()

    mock_resp_body = MagicMock()
    mock_resp_body.code = "isv.BUSINESS_LIMIT_CONTROL"
    mock_resp_body.message = "触发分钟级流控"
    mock_resp = MagicMock()
    mock_resp.body = mock_resp_body
    mock_client_instance = MagicMock()
    mock_client_instance.send_sms = MagicMock(return_value=mock_resp)
    MockClient.return_value = mock_client_instance

    orig = _inject_sdk_mocks(mocks)
    try:
        with pytest.raises(AppError) as exc_info:
            await sms_service._send_real_sms(phone="13600136000", code="222222", purpose="guardian_verify")
    finally:
        _restore_sdk_mocks(orig)

    assert exc_info.value.code == 503
    assert "触发分钟级流控" in exc_info.value.message
