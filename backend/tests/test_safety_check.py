"""生产环境配置安全检查（D-077 + 上线硬化）。"""
from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.safety import _list_issues, run_production_safety_check


def test_dev_mode_skips_check():
    # debug=True 不做检查（_list_issues 仍可调，但 run 应直接放行）
    run_production_safety_check(Settings(debug=True))  # 不抛即通过


def test_prod_flags_placeholder_secrets():
    # 显式构造典型 dev placeholder 生产配置（不依赖 .env）
    s = Settings(
        debug=False,
        jwt_secret_key="dev-secret-change-in-production",
        field_encryption_key="",
        cors_allow_origins="*",
        auto_approve_teacher_cert=True,
    )
    keys = {i.key for i in _list_issues(s)}
    for k in ("JWT_SECRET_KEY", "FIELD_ENCRYPTION_KEY", "CORS_ALLOW_ORIGINS",
              "AUTO_APPROVE_TEACHER_CERT"):
        assert k in keys, f"{k} 应被生产安全检查拦截"


def test_prod_passes_when_configured():
    s = Settings(
        debug=False,
        jwt_secret_key="x" * 40,
        field_encryption_key="y" * 44,
        cors_allow_origins="https://admin.example.com",
        auto_approve_teacher_cert=False,
        wechat_appid="wxrealappid123456",
        wechat_appsecret="realsecret" + "z" * 20,
        deepseek_api_key="sk-real-key-123",
        aliyun_ocr_access_key_id="LTAIrealkey",
        tencent_ocr_secret_id="AKIDreal",
        cos_secret_id="AKIDrealcos",
        wechat_pay_mch_id="1600000000",
        wechat_pay_api_key_v3="r" * 32,
        sms_provider="aliyun",
    )
    keys = {i.key for i in _list_issues(s)}
    # FEK / CORS 已配 → 不应再命中
    assert "FIELD_ENCRYPTION_KEY" not in keys
    assert "CORS_ALLOW_ORIGINS" not in keys
    assert "JWT_SECRET_KEY" not in keys


def test_field_encryption_key_too_short_flagged():
    keys = {i.key for i in _list_issues(Settings(debug=False, field_encryption_key="short"))}
    assert "FIELD_ENCRYPTION_KEY" in keys
