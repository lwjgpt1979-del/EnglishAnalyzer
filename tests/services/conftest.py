"""tests/services 全局 dev-mock 隔离。

根 tests/api/conftest.py 的 `_force_all_ai_dev_mode` 只覆盖 api 树；本目录不在其
范围内。backend/.env 配了**真实**的 LLM / 图片 key，会让 is_llm_dev_mode() /
is_image_dev_mode() 返回 False，导致媒体相关 service 测试联网、变慢且不确定。
这里统一把 LLM(deepseek/doubao)、腾讯混元生图、TTS 的 key monkeypatch 成
placeholder，使 is_*_dev_mode() 恒为 True、测试离线确定。
"""
import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def _force_media_dev_mock(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-placeholder-for-test")
    monkeypatch.setattr(settings, "doubao_api_key", "placeholder-doubao-dev")
    monkeypatch.setattr(settings, "tencent_aiart_secret_key", "placeholder-aiart-dev")
    monkeypatch.setattr(settings, "tts_api_key", "tts-placeholder")
