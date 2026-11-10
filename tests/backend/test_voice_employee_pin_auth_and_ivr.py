import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from sqlalchemy.orm import Session

from backend.app.voice.auth import VoiceCallerAuth, normalized_phone, validate_voice_pin
from backend.app.models import (
    Company,
    CompanyMembership,
    User,
    UserRole,
    VoiceBusinessConfig,
    VoiceCall,
    VoiceCallerCredential,
)
from backend.app.core.security import hash_password, verify_password
from shared.ai_engine.contracts import TenantContext
from backend.app.config.settings import Settings
from tests.backend.test_voice_tts_and_dynamic_retail_sync import _setup_multi_tenant_db


def test_normalized_phone():
    assert normalized_phone("+15142955720") == "+15142955720"
    assert normalized_phone("5142955720") == "+15142955720"
    assert normalized_phone("(514) 295-5720") == "+15142955720"
    assert normalized_phone("1-514-295-5720") == "+15142955720"
    assert normalized_phone("+33612345678") == "+33612345678"
    assert normalized_phone("") is None
    assert normalized_phone(None) is None
    assert normalized_phone("123") is None


def test_validate_voice_pin():
    assert validate_voice_pin("839201") == "839201"
    assert validate_voice_pin("948205183") == "948205183"
    with pytest.raises(ValueError):
        validate_voice_pin("123")  # Too short (< 6)
    with pytest.raises(ValueError):
        validate_voice_pin("1234567890123")  # Too long (> 12)
    with pytest.raises(ValueError):
        validate_voice_pin("123456")  # Trivial sequential
    with pytest.raises(ValueError):
        validate_voice_pin("111111")  # Trivial repeated
    with pytest.raises(ValueError):
        validate_voice_pin("abcdef")  # Non-digit


def test_voice_auth_set_pin_and_verify_gather_e2e(tmp_path):
    engine, session, company_a, config_a, user_a, company_b, config_b, user_b = _setup_multi_tenant_db(tmp_path)
    phone = "+15142955720"
    user_a.phone = phone
    session.commit()

    settings = Settings(AUTH_JWT_SECRET="test-secret-key-32-chars-minimum--")
    tenant = TenantContext(company_id=company_a.id, user_id=user_a.id)
    auth = VoiceCallerAuth(session, settings)

    # 1. Set PIN (6 digits)
    cred = auth.set_pin(tenant, "USER", user_a.id, "839201", phone_number=phone)
    session.commit()

    assert cred.enabled is True
    assert cred.phone_number == phone
    assert cred.failed_attempts == 0
    assert cred.locked_until is None

    # 2. Inbound call from the employee's phone
    call = VoiceCall(
        id=uuid4(),
        company_id=company_a.id,
        config_id=config_a.id,
        caller_phone=phone,
        status="in_progress",
        verification_attempts=0,
    )
    session.add(call)
    session.commit()

    # 3. Verify with correct PIN and # terminator
    res = auth.verify_gather(call, "839201#")
    assert res["success"] is True
    assert res["authenticated"] is True
    assert call.caller_type == "OWNER"
    assert call.authenticated_user_id == user_a.id

    # 4. Verify with incorrect PIN -> failed
    call2 = VoiceCall(
        id=uuid4(),
        company_id=company_a.id,
        config_id=config_a.id,
        caller_phone=phone,
        status="in_progress",
        verification_attempts=0,
    )
    session.add(call2)
    session.commit()

    res_fail = auth.verify_gather(call2, "948205#")
    assert res_fail["authenticated"] is False
    assert call2.verification_attempts == 1
    assert cred.failed_attempts == 1

    # 5. Fallback verification: caller calls from different number (office phone or blocked CID)
    call_unknown = VoiceCall(
        id=uuid4(),
        company_id=company_a.id,
        config_id=config_a.id,
        caller_phone="+14389999999",
        status="in_progress",
        verification_attempts=0,
    )
    session.add(call_unknown)
    session.commit()

    res_unknown = auth.verify_gather(call_unknown, "839201#")
    assert res_unknown["success"] is True
    assert res_unknown["authenticated"] is True
    assert call_unknown.caller_type == "OWNER"
    assert call_unknown.authenticated_user_id == user_a.id


def test_ivr_pronunciation_formatting():
    config = VoiceBusinessConfig(
        id=uuid4(),
        company_id=uuid4(),
        business_name="Produits_Ero",
        voice_display_name="Produits Éro",
        custom_pronunciation='{"company": "Produit Éro"}',
        enabled=True,
    )
    assert config.effective_voice_name == "Produit Éro"
