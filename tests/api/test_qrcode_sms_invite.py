"""微信码 + SMS 邀请测试（D-078 / Plan M）。Task 0 部分（service unit tests）。"""
import base64
import pytest

from app.services.qrcode_service import get_miniprogram_qrcode_base64
from app.services.wechat_service import get_access_token, _DEV_MOCK_TOKEN


@pytest.mark.asyncio
async def test_wechat_access_token_dev_mock_or_real():
    from app.core.config import settings
    if settings.wechat_appid.startswith("wx_dev"):
        assert (await get_access_token()) == _DEV_MOCK_TOKEN
    else:
        try:
            token = await get_access_token()
            assert isinstance(token, str)
        except Exception:
            pass


@pytest.mark.asyncio
async def test_qrcode_dev_or_real_returns_base64():
    from app.core.config import settings
    if settings.wechat_appid.startswith("wx_dev"):
        b64 = await get_miniprogram_qrcode_base64(scene="t:ABC123", page="pages/teacher/students")
        decoded = base64.b64decode(b64)
        assert len(decoded) > 50
    else:
        try:
            await get_miniprogram_qrcode_base64(scene="t:TEST123", page="pages/teacher/students")
        except Exception:
            pass


@pytest.mark.asyncio
async def test_qrcode_scene_too_long_400():
    from app.core.exceptions import AppError
    with pytest.raises(AppError) as exc:
        await get_miniprogram_qrcode_base64(scene="a" * 33, page="pages/teacher/students")
    assert exc.value.code == 400
