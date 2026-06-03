"""微信订阅消息 dev-mock 测试（D-108）。"""
import pytest

from app.services import wechat_subscribe_service


@pytest.mark.asyncio
async def test_send_checkin_reminder_dev_mock():
    # 默认 placeholder provider → dev mock，返回 True 不抛错
    ok = await wechat_subscribe_service.send_checkin_reminder(openid="ox_test", streak_days=3)
    assert ok is True


def test_is_dev_default():
    assert wechat_subscribe_service._is_dev() is True
