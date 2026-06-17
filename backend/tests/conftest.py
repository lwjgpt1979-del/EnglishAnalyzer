"""backend/tests 共享 fixture。

强制所有 AI 服务走 dev-mock(is_llm_dev_mode 看 deepseek_api_key 前缀),
避免 KP-First 测试意外调真实 DeepSeek API(.env 可能配了真实 key)。
与 repo-root tests/api/conftest.py 的同名 fixture 做法一致。
"""
from __future__ import annotations

import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def _force_llm_dev_mode(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-placeholder-for-test")
