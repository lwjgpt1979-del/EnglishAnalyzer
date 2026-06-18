"""backend/tests 共享 fixture。

强制所有 AI 服务走 dev-mock(各 service 看对应 key 的占位前缀),
避免 KP-First 测试意外调真实 API(.env 可能配了真实 key)。
与 repo-root tests/api/conftest.py 的同名 fixture 做法一致。
R7:补 doubao(OCR/Vision)+ tencent_aiart(图)+ tts,覆盖 ocr_ingest 等用到豆包的测试。
"""
from __future__ import annotations

import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def _force_llm_dev_mode(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-placeholder-for-test")
    monkeypatch.setattr(settings, "doubao_api_key", "placeholder-doubao-dev")
    if hasattr(settings, "tencent_aiart_secret_key"):
        monkeypatch.setattr(settings, "tencent_aiart_secret_key", "placeholder")
    if hasattr(settings, "tts_access_token"):
        monkeypatch.setattr(settings, "tts_access_token", "tts-placeholder")
