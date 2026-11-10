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


def test_voice_store_pickup_reservation_and_crm_services(tmp_path):
    from backend.app.models.crm import CRMService
    from backend.app.services.company_intelligence_service import CompanyIntelligenceService
    from backend.app.services.module_entitlement_service import ModuleEntitlementService
    from backend.app.voice.telnyx_media import PublicInboundConversation

    engine, session, company_a, config_a, user_a, company_b, config_b, user_b = _setup_multi_tenant_db(tmp_path)
    
    # Activate CRM for company_a
    ModuleEntitlementService(session).activate_module(TenantContext(company_a.id), "crm", auto_init_voice=False)

    # Add store pickup service to company_a
    pickup_svc = CRMService(
        id=uuid4(),
        company_id=company_a.id,
        name="Cueillette en magasin (Réservation de produit)",
        description="Réservation et cueillette de produit en boutique",
        duration_minutes=15,
        price=0.0,
        currency="CAD",
        is_active=True,
        is_published=True,
        is_approved_by_owner=True,
    )
    session.add(pickup_svc)
    session.commit()

    intel = CompanyIntelligenceService(session)
    profile = intel.get_profile(company_a.id)

    assert profile.has_crm_booking is True
    assert len(profile.configured_crm_services) >= 1
    assert any("Cueillette" in s["name"] for s in profile.configured_crm_services)

    # Test keyword fallback in require_service
    matched = intel.require_service(company_a.id, service_name="Je veux reserver un snowboard pour cueillette en magasin")
    assert matched["id"] == str(pickup_svc.id)

    # Add routing NIP for company_a
    from backend.app.models.voice import CompanyRoutingNip
    session.add(CompanyRoutingNip(
        id=uuid4(),
        company_id=company_a.id,
        routing_code="58392",
        routing_code_hash="hash",
        status="ACTIVE",
        created_by_user_id=user_a.id,
    ))
    session.commit()

    # Test PublicVoiceConversation intent recognition
    call = VoiceCall(
        id=uuid4(),
        company_id=company_a.id,
        config_id=config_a.id,
        caller_phone="+15149999999",
        telnyx_call_control_id="v3:test-control-pickup-123",
        source_context={"dispatcher_routing": True},
        status="in_progress",
        locale="fr-CA",
    )
    session.add(call)
    session.commit()

    pub = PublicInboundConversation(session, Settings(AUTH_JWT_SECRET="test-secret-key-32-chars-minimum--", TELNYX_MEDIA_INBOUND_ENABLED=True, TELNYX_MEDIA_ENABLED=True), call.id)

    # Test product pickup reservation question
    resp = pub.public_answer("Bonjour, est-ce que je peux réserver une planche pour venir la chercher en magasin ?")
    assert resp["status"] == "success"
    assert "ramassage" in resp["answer"].lower() or "cueillette" in resp["answer"].lower()
    assert (call.source_context or {}).get("public_appointment_request") is True

    # Test general appointment question
    resp2 = pub.public_answer("Je voudrais prendre un rendez-vous pour demain")
    assert resp2["status"] == "success"
    assert (call.source_context or {}).get("public_appointment_request") is True

