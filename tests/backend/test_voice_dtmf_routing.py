"""Integration tests for Phase 8.3: Live Inbound DTMF Company Routing and Voice AI."""

from __future__ import annotations

import base64
import hashlib
import time
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config.settings import Settings
from backend.app.database.session import SessionLocal
from backend.main import create_application
from backend.app.models.audit_log import AuditLogEntry
from backend.app.models.billing import BillingAccount
from backend.app.models.company import Company
from backend.app.models.company_membership import CompanyMembership
from backend.app.models.company_module import CompanyModule
from backend.app.models.user import User, UserRole
from backend.app.models.voice import CompanyRoutingNip, VoiceBusinessConfig, VoiceCall
from backend.app.services.company_routing_service import CompanyRoutingNipService
from backend.app.voice.providers import TelnyxClient


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def setup_tenants(db_session: Session):
    """Create two test companies in Sandbox DB with Voice module enabled."""
    co_a = Company(
        id=uuid4(),
        name="Clinique Physio Sandbox A",
        slug=f"physio-sandbox-{uuid4().hex[:8]}",
        email=f"contact.{uuid4().hex[:6]}@physio.ca",
        preferred_language="fr",
        country="Canada",
        timezone="America/Toronto",
        industry="Healthcare",
        subscription_plan="professional",
    )
    co_b = Company(
        id=uuid4(),
        name="Boutique Mode Sandbox B",
        slug=f"mode-sandbox-{uuid4().hex[:8]}",
        email=f"contact.{uuid4().hex[:6]}@mode.ca",
        preferred_language="en",
        country="Canada",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="professional",
    )
    db_session.add_all([co_a, co_b])

    # Users
    user_a = User(
        id=uuid4(),
        company_id=co_a.id,
        email=f"admin.a.{uuid4().hex[:6]}@avenqo.ca",
        password_hash="hashed_pw_test",
        first_name="Admin",
        last_name="Physio",
        role=UserRole.ADMIN,
        is_active=True,
    )
    user_b = User(
        id=uuid4(),
        company_id=co_b.id,
        email=f"admin.b.{uuid4().hex[:6]}@avenqo.ca",
        password_hash="hashed_pw_test",
        first_name="Admin",
        last_name="Mode",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add_all([user_a, user_b])

    # Memberships
    mem_a = CompanyMembership(id=uuid4(), company_id=co_a.id, user_id=user_a.id, role=UserRole.ADMIN, is_active=True)
    mem_b = CompanyMembership(id=uuid4(), company_id=co_b.id, user_id=user_b.id, role=UserRole.ADMIN, is_active=True)
    db_session.add_all([mem_a, mem_b])

    # Billing accounts
    bill_a = BillingAccount(id=uuid4(), company_id=co_a.id, plan_code="professional", status="active")
    bill_b = BillingAccount(id=uuid4(), company_id=co_b.id, plan_code="professional", status="active")
    db_session.add_all([bill_a, bill_b])

    # Voice configs
    cfg_a = VoiceBusinessConfig(
        id=uuid4(),
        company_id=co_a.id,
        business_name="Clinique Physio Sandbox A",
        preferred_language="fr",
        greeting_message="Bienvenue chez Clinique Physio. Comment puis-je vous aider ?",
        enabled=True,
        voice_api_key_hash=hashlib.sha256(uuid4().bytes).hexdigest(),
        voice_api_key_last4=uuid4().hex[:4],
    )
    cfg_b = VoiceBusinessConfig(
        id=uuid4(),
        company_id=co_b.id,
        business_name="Boutique Mode Sandbox B",
        preferred_language="en",
        greeting_message="Welcome to Boutique Mode Sandbox. How can I help you?",
        enabled=True,
        voice_api_key_hash=hashlib.sha256(uuid4().bytes).hexdigest(),
        voice_api_key_last4=uuid4().hex[:4],
    )
    db_session.add_all([cfg_a, cfg_b])
    db_session.commit()

    from shared.ai_engine.contracts import TenantContext
    from backend.app.services.module_entitlement_service import ModuleEntitlementService
    ModuleEntitlementService(db_session).activate_module(TenantContext(co_a.id), "voice")
    ModuleEntitlementService(db_session).activate_module(TenantContext(co_b.id), "voice")
    db_session.commit()

    try:
        yield {
            "co_a": co_a, "user_a": user_a, "cfg_a": cfg_a,
            "co_b": co_b, "user_b": user_b, "cfg_b": cfg_b,
        }
    finally:
        from sqlalchemy import delete
        db_session.execute(delete(Company).where(Company.id.in_([co_a.id, co_b.id])))
        db_session.commit()


def test_nip_generation_and_validation(db_session: Session, setup_tenants: dict):
    """Test generating, validating and rotating company routing NIPs."""
    settings = Settings()
    service = CompanyRoutingNipService(db_session, settings)
    co_a = setup_tenants["co_a"]
    user_a = setup_tenants["user_a"]

    # 1. Generate random NIP
    nip = service.configure_or_rotate_nip(co_a.id, user_a.id)
    assert nip is not None
    assert nip.status == "ACTIVE"
    assert len(nip.routing_code) == 5
    assert nip.routing_code.isdigit()

    # 2. Verify active NIP lookup
    active = service.get_active_nip(co_a.id)
    assert active is not None
    assert active.id == nip.id
    assert active.routing_code == nip.routing_code

    # 3. Test non-triviality validation
    with pytest.raises(ValueError, match="séquence triviale"):
        service.configure_or_rotate_nip(co_a.id, user_a.id, custom_code="12345")

    with pytest.raises(ValueError, match="un seul chiffre répété"):
        service.configure_or_rotate_nip(co_a.id, user_a.id, custom_code="88888")

    with pytest.raises(ValueError, match="entre 4 et 8 chiffres"):
        service.configure_or_rotate_nip(co_a.id, user_a.id, custom_code="12")

    # 4. Set valid custom NIP
    custom_nip = service.configure_or_rotate_nip(co_a.id, user_a.id, custom_code="49271")
    assert custom_nip.routing_code == "49271"
    assert custom_nip.status == "ACTIVE"

    # Previous NIP must now be ROTATED
    old = db_session.get(CompanyRoutingNip, nip.id)
    assert old is not None
    assert old.status == "ROTATED"
    assert old.rotated_at is not None

    # Audit log check: masked code, no credential leak
    audit_logs = db_session.scalars(
        select(AuditLogEntry)
        .where(AuditLogEntry.company_id == co_a.id, AuditLogEntry.target_type == "company_routing_nip")
    ).all()
    assert len(audit_logs) >= 2
    for log in audit_logs:
        assert "49271" not in str(log.safe_metadata)  # Full code never in audit log!
        assert "code_last2" in log.safe_metadata


def test_nip_collision_prevention_across_companies(db_session: Session, setup_tenants: dict):
    """Test that two companies cannot have the same active routing code."""
    settings = Settings()
    service = CompanyRoutingNipService(db_session, settings)
    co_a = setup_tenants["co_a"]
    user_a = setup_tenants["user_a"]
    co_b = setup_tenants["co_b"]
    user_b = setup_tenants["user_b"]

    # Company A chooses code 73915
    service.configure_or_rotate_nip(co_a.id, user_a.id, custom_code="73915")

    # Company B tries to choose the same code -> conflict!
    with pytest.raises(ValueError, match="déjà utilisé par une autre entreprise"):
        service.configure_or_rotate_nip(co_b.id, user_b.id, custom_code="73915")


def test_tenant_resolution_via_nip(db_session: Session, setup_tenants: dict):
    """Test resolving tenant company_id from DTMF input."""
    settings = Settings()
    service = CompanyRoutingNipService(db_session, settings)
    co_a = setup_tenants["co_a"]
    user_a = setup_tenants["user_a"]

    nip = service.configure_or_rotate_nip(co_a.id, user_a.id, custom_code="81642")

    # Resolve with terminating # as sent by telephone keypad
    resolved_id, err = service.resolve_tenant_by_nip("81642#")
    assert err is None
    assert resolved_id == co_a.id

    # Resolve with whitespace
    resolved_id, err = service.resolve_tenant_by_nip(" 81642 ")
    assert err is None
    assert resolved_id == co_a.id

    # Unknown code
    resolved_id, err = service.resolve_tenant_by_nip("99999")
    assert resolved_id is None
    assert err == "NOT_FOUND"


def test_nip_revocation(db_session: Session, setup_tenants: dict):
    """Test revoking an active routing NIP."""
    settings = Settings()
    service = CompanyRoutingNipService(db_session, settings)
    co_a = setup_tenants["co_a"]
    user_a = setup_tenants["user_a"]

    nip = service.configure_or_rotate_nip(co_a.id, user_a.id, custom_code="62947")
    assert service.get_active_nip(co_a.id) is not None

    revoked = service.revoke_nip(co_a.id, user_a.id)
    assert revoked is True
    assert service.get_active_nip(co_a.id) is None

    # Cannot resolve revoked NIP
    resolved_id, err = service.resolve_tenant_by_nip("62947")
    assert resolved_id is None
    assert err == "NOT_FOUND"


@pytest.mark.asyncio
async def test_e2e_telnyx_dispatcher_dtmf_routing(db_session: Session, setup_tenants: dict, monkeypatch):
    """Full E2E test of telephone flow dialed into target number +1 438-607-5438.
    
    1. Caller dials +1 438-607-5438 -> call.initiated -> answered by dispatcher.
    2. call.answered -> greets caller and starts DTMF collection (gather_using_speak).
    3. Caller enters invalid NIP -> call.gather.ended -> generic rejection, anti-enumeration, hangs up.
    4. Caller enters valid NIP -> call.gather.ended -> resolves tenant, creates tenant VoiceCall, starts media stream.
    5. call.hangup -> gracefully terminates call session and records duration.
    """
    import json
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    from unittest.mock import AsyncMock
    from backend.app.database import get_db
    from backend.app.config.settings import get_settings
    from fastapi import FastAPI
    import backend.app.routers.voice as voice_router

    co_a = setup_tenants["co_a"]
    user_a = setup_tenants["user_a"]

    # Configure active NIP for Company A
    nip_service = CompanyRoutingNipService(db_session, Settings())
    nip = nip_service.configure_or_rotate_nip(co_a.id, user_a.id, custom_code="58392")
    assert nip.routing_code == "58392"

    # Setup Ed25519 signed Telnyx webhook harness
    private_key = Ed25519PrivateKey.generate()
    public_bytes = private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)

    settings = Settings()
    settings.telnyx_api_key = "test-telnyx-key"
    settings.telnyx_public_key = base64.b64encode(public_bytes).decode()
    settings.telnyx_voice_connection_id = "test-voice-conn-id"
    settings.voice_shared_dispatcher_number = "+14386075438"
    settings.telnyx_media_enabled = True
    settings.telnyx_media_inbound_enabled = True
    settings.telnyx_media_stream_base_url = "wss://api.avenqo.ca"
    settings.rate_limit_enabled = False

    # Mock provider actions to record calls
    mock_telnyx = AsyncMock(spec=TelnyxClient)
    mock_telnyx.answer_call = AsyncMock()
    mock_telnyx.gather_using_speak = AsyncMock()
    mock_telnyx.speak = AsyncMock()
    mock_telnyx.hangup = AsyncMock()
    mock_telnyx.start_media_stream = AsyncMock()
    monkeypatch.setattr(voice_router, "TelnyxClient", lambda _settings: mock_telnyx)

    test_app = FastAPI()
    test_app.include_router(voice_router.router, prefix="/api/v1")
    test_app.dependency_overrides[get_db] = lambda: db_session
    test_app.dependency_overrides[get_settings] = lambda: settings

    call_control_id = f"cc-e2e-{uuid4().hex[:8]}"

    def send_webhook(event_type: str, **payload):
        body_dict = {
            "data": {
                "id": str(uuid4()),
                "event_type": event_type,
                "payload": {
                    "call_control_id": call_control_id,
                    "connection_id": "test-voice-conn-id",
                    "direction": "incoming",
                    "from": "+15149876543",
                    "to": "+14386075438",
                    **payload,
                },
            }
        }
        body_bytes = json.dumps(body_dict).encode("utf-8")
        stamp = str(int(time.time()))
        sig = private_key.sign(stamp.encode() + b"|" + body_bytes)
        with TestClient(test_app) as client:
            return client.post(
                "/api/v1/voice/telnyx/webhook",
                content=body_bytes,
                headers={
                    "content-type": "application/json",
                    "telnyx-timestamp": stamp,
                    "telnyx-signature-ed25519": base64.b64encode(sig).decode(),
                },
            )

    # Step 1: Inbound call initiated to +1 438-607-5438
    res1 = send_webhook("call.initiated")
    assert res1.status_code == 200
    assert res1.json()["status"] == "DISPATCHER_ANSWERED"
    assert mock_telnyx.answer_call.called

    # Step 2: Call answered -> greet caller & collect DTMF
    res2 = send_webhook("call.answered")
    assert res2.status_code == 200
    assert res2.json()["status"] == "DISPATCHER_GATHER_STARTED"
    assert mock_telnyx.gather_using_speak.called

    # Step 3: Caller enters invalid NIP
    res3 = send_webhook("call.gather.ended", digits="99999#")
    assert res3.status_code == 200
    assert res3.json()["status"] == "INVALID_NIP"
    assert mock_telnyx.speak.called
    assert mock_telnyx.hangup.called

    # Step 4: Caller enters valid NIP for Clinique Physio (58392#)
    res4 = send_webhook("call.gather.ended", digits="58392#")
    assert res4.status_code == 200
    assert res4.json()["status"] == "MEDIA_STREAM_STARTED"
    assert res4.json()["routed"] is True
    assert res4.json()["company_id"] == str(co_a.id)

    # Verify VoiceCall created in DB and strictly tenant-isolated
    call_record = db_session.scalar(select(VoiceCall).where(VoiceCall.telnyx_call_control_id == call_control_id))
    assert call_record is not None
    assert call_record.company_id == co_a.id
    assert call_record.status == "routed"
    assert call_record.source_context.get("dispatcher_routing") is True

    # Step 5: Call hangup
    res5 = send_webhook("call.hangup")
    assert res5.status_code == 200
    db_session.refresh(call_record)
    assert call_record.status == "ended"
    assert call_record.ended_at is not None

