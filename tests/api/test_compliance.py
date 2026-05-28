"""合规两项测试：年龄核验 + 协议确认 + 账号注销。"""
from app.schemas.compliance import (
    CURRENT_AGREEMENT_VERSION,
    CancelAccountConfirm,
    CompleteProfileRequest,
)


def test_agreement_version_defined():
    assert CURRENT_AGREEMENT_VERSION == "v1.0"


def test_complete_profile_request():
    req = CompleteProfileRequest(birth_year=2010, agreement_version="v1.0")
    assert req.birth_year == 2010
    assert req.guardian_phone is None


def test_cancel_account_confirm_validates_code_length():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        CancelAccountConfirm(code="123")
