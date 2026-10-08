import audioop
import asyncio
import base64
import hashlib
import hmac
import re
from types import SimpleNamespace
from uuid import uuid4
from datetime import datetime, timedelta, timezone
import jwt
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from typing import Any, cast
import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.voice.telnyx_media import InvalidMediaFrame, TelnyxAudioCodec, TelnyxMediaBridge, PublicInboundConversation, media_call_context, media_transport_context, issue_media_client_state, claim_media_start, release_media_session, TelnyxAudioReorderBuffer
from backend.app.config.settings import Settings
from backend.app.models import BillingAccount, CompanyMembership, User, UserRole, VoicePhoneNumber, VoiceToolAction
from backend.app.models import VoiceBusinessConfig, VoiceCallerCredential, VoiceCall
from backend.app.voice.auth import VoiceCallerAuth
from backend.app.voice.auth import validate_voice_pin
from tests.backend.test_voice_agent import _voice_database
from tests.backend.test_voice_agent import signed_telnyx_webhook
from backend.app.core.permissions import permissions_for
from backend.app.core.rate_limit import reset_rate_limiter
from backend.app.services.module_entitlement_service import ModuleEntitlementService
import backend.app.voice.telnyx_media as media_module
from backend.app.voice.providers import TelnyxClient
from backend.app.database import get_db
from backend.app.config.settings import get_settings
from backend.app.dependencies.central_ai import get_central_ai_service
from backend.app.dependencies.ai_engine import get_prediction_service
from shared.ai_engine.contracts import TenantContext


@pytest.mark.parametrize("pin", ["000000", "111111", "123456", "654321", "012345", "987654", "121212", "123123", "12345", "12ab34", "１２３４５６"])
def test_voice_pin_creation_rejects_trivial_or_invalid_values(pin):
    from backend.app.schemas.voice import VoicePinRequest
    with pytest.raises(ValueError):
        validate_voice_pin(pin)
    with pytest.raises(ValueError):
        VoicePinRequest(pin=pin)


def test_voice_pin_creation_accepts_nontrivial_secret_without_revealing_it():
    from backend.app.schemas.voice import VoicePinRequest
    secret = "907182"
    assert validate_voice_pin(secret) == secret
    request = VoicePinRequest(pin=SecretStr(secret))
    assert secret not in repr(request) + request.model_dump_json()


def test_telnyx_codec_converts_streaming_pcmu_and_pcm_without_audio_files():
    codec = TelnyxAudioCodec()
    incoming = base64.b64encode(b"\xff" * 160).decode()
    first = codec.inbound_pcm(incoming)
    second = codec.inbound_pcm(incoming)
    assert len(first) == 956 and len(second) == 960
    assert audioop.rms(first + second, 2) == 0
    outbound = codec.outbound_pcm(base64.b64encode(b"\x00\x00" * 480).decode())
    assert outbound == b"\xff" * 160
    codec.reset()
    assert codec.inbound_pcm(incoming) == first


@pytest.mark.parametrize("payload", [None, 1, "", "%%%", "A" * 10000])
def test_telnyx_codec_rejects_invalid_or_unbounded_input(payload):
    with pytest.raises(InvalidMediaFrame):
        TelnyxAudioCodec().inbound_pcm(payload)


def test_telnyx_codec_rejects_odd_pcm_length():
    with pytest.raises(InvalidMediaFrame):
        TelnyxAudioCodec().outbound_pcm(base64.b64encode(b"\x00").decode())


def test_media_transport_disabled_by_default_before_database_or_provider_access():
    settings = Settings()
    assert settings.telnyx_media_enabled is False
    with pytest.raises(PermissionError, match="disabled"):
        media_call_context(cast(Session, None), settings, uuid4())


def test_voice_setup_creates_disabled_config_and_links_owned_number_locally(signed_telnyx_webhook):
    import backend.app.routers.voice as voice_router
    from sqlalchemy import func
    env = signed_telnyx_webhook
    env.binding.config_id = None
    env.session.delete(env.config); env.session.commit()
    owner = User(company_id=env.company.id, first_name="Owner", last_name="Setup", email="setup-local@example.com",
        password_hash="test", role=UserRole.OWNER, is_active=True)
    env.session.add(owner); env.session.flush()
    membership = CompanyMembership(company_id=env.company.id, user_id=owner.id, role=UserRole.OWNER, is_active=True)
    env.session.add(membership); env.session.commit()
    env.client.app.dependency_overrides[voice_router.get_current_identity] = lambda: SimpleNamespace(user=owner)
    env.client.app.dependency_overrides[voice_router.get_active_ai_membership] = lambda: membership
    body = {"number_id": str(env.binding.id), "confirmed": True}
    unconfirmed = env.client.post("/api/v1/voice/setup", json={**body, "confirmed": False})
    assert unconfirmed.json()["status"] == "READY_FOR_OWNER_ACTION"
    assert env.session.scalar(select(func.count(VoiceBusinessConfig.id))) == 0
    response = env.client.post("/api/v1/voice/setup", json=body)
    assert response.status_code == 200 and response.json()["status"] == "AUDIO_CONFIGURATION_REQUIRED"
    configuration = response.json()["configuration"]
    assert configuration["business_name"] == env.company.name and configuration["enabled"] is False
    assert configuration["retell_agent_id"] is None and configuration["retell_sip_uri"] is None
    env.session.refresh(env.binding)
    assert str(env.binding.config_id) == configuration["id"]
    replay = env.client.post("/api/v1/voice/setup", json=body)
    assert replay.json()["configuration"]["id"] == configuration["id"]
    assert env.session.scalar(select(func.count(VoiceBusinessConfig.id))) == 1
    assert env.service.telnyx.commands == [] and env.service.telnyx.media_streams == []


@pytest.mark.parametrize("secret", ["000000", "111111", "123456", "654321", "907182"])
def test_pin_api_authenticated_creation_masks_secrets_and_rejects_trivial_pin(authorized_media_call, secret, caplog):
    import backend.app.routers.voice as voice_router
    from backend.app.core.exception_handlers import register_exception_handlers
    env = authorized_media_call
    app = FastAPI(); register_exception_handlers(app); app.include_router(voice_router.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: env.db
    app.dependency_overrides[get_settings] = lambda: env.settings
    app.dependency_overrides[voice_router.get_current_identity] = lambda: SimpleNamespace(user=env.user)
    app.dependency_overrides[voice_router.get_active_ai_membership] = lambda: env.membership
    with TestClient(app) as client:
        response = client.put("/api/v1/voice/auth/pin", json={"pin": secret})
    assert response.status_code == (200 if secret == "907182" else 422)
    assert secret not in response.text + caplog.text
    credential = env.db.scalar(select(VoiceCallerCredential).where(VoiceCallerCredential.company_id == env.company.id))
    if secret == "907182":
        assert credential.principal_id == env.user.id and credential.pin_hash.startswith("$argon2")
        assert secret not in credential.pin_hash
    else:
        assert credential is None


def test_voice_setup_rejects_foreign_number_without_creating_configuration(signed_telnyx_webhook):
    import backend.app.routers.voice as voice_router
    env = signed_telnyx_webhook
    owner = User(company_id=env.company.id, first_name="Owner", last_name="Scope", email="scope-local@example.com",
        password_hash="test", role=UserRole.OWNER, is_active=True)
    env.session.add(owner); env.session.flush()
    membership = CompanyMembership(company_id=env.company.id, user_id=owner.id, role=UserRole.OWNER, is_active=True)
    env.session.add(membership); env.session.commit()
    env.client.app.dependency_overrides[voice_router.get_current_identity] = lambda: SimpleNamespace(user=owner)
    env.client.app.dependency_overrides[voice_router.get_active_ai_membership] = lambda: membership
    response = env.client.post("/api/v1/voice/setup", json={"number_id": str(uuid4()), "confirmed": True})
    assert response.status_code == 404


@pytest.fixture
def authorized_media_call(tmp_path):
    engine, db, company, config, _key, orchestrator = _voice_database(tmp_path)
    settings = Settings()
    settings.auth_jwt_secret = "media-test-secret-at-least-32-characters"
    settings.telnyx_media_enabled = True
    settings.telnyx_voice_connection_id = "verified-connection"
    config.enabled = False; config.retell_agent_id = None; config.retell_sip_uri = None
    user = User(company_id=company.id, first_name="Owner", last_name="Media", email="media-owner@example.com",
        password_hash="test", phone="+15145550123", role=UserRole.OWNER, is_active=True)
    db.add(user); db.flush()
    membership = CompanyMembership(company_id=company.id, user_id=user.id, role=UserRole.OWNER, is_active=True)
    number = VoicePhoneNumber(company_id=company.id, config_id=config.id, phone_number=config.telnyx_phone_number,
        country_code="CA", provider="telnyx", provider_number_id="owned-media-id", provider_connection_id="verified-connection",
        number_type="local", status="ACTIVE", capabilities=["voice"])
    account = BillingAccount(company_id=company.id, plan_code="professional", status="active")
    db.add_all([membership, number, account]); db.commit()
    # Keep production authorization strict: this fixture must explicitly activate Voice.
    ModuleEntitlementService(db).activate_module(TenantContext(company.id), "voice")
    db.commit()
    call = orchestrator.record_inbound(config, {"call_control_id": "control-test", "from": user.phone})
    call.status = "in_progress"; call.caller_type = "OWNER"; call.authenticated_user_id = user.id
    auth = VoiceCallerAuth(db, settings).establish(call)
    db.commit()
    yield SimpleNamespace(db=db, settings=settings, call=call, config=config, company=company, user=user,
        membership=membership, number=number, account=account, auth=auth)
    db.close(); engine.dispose()


def test_media_ticket_scoped_single_use_and_never_stored_raw(authorized_media_call):
    env = authorized_media_call
    state = issue_media_client_state(env.db, env.settings, env.call.id)
    event = {"call_control_id": env.call.telnyx_call_control_id, "to": env.config.telnyx_phone_number, "client_state": state}
    rows = env.db.scalars(select(VoiceToolAction).where(VoiceToolAction.tool_name == "telnyx_media_ticket")).all()
    assert state not in str([row.result for row in rows])
    assert base64.b64decode(state).decode() not in str([row.result for row in rows])
    claim_media_start(env.db, env.settings, env.call.id, event)
    with pytest.raises(PermissionError, match="consumed"):
        claim_media_start(env.db, env.settings, env.call.id, event)


def test_media_call_allows_only_one_active_stream_and_release_is_owner_scoped(authorized_media_call):
    env = authorized_media_call
    first = issue_media_client_state(env.db, env.settings, env.call.id)
    second = issue_media_client_state(env.db, env.settings, env.call.id)
    event = {"call_control_id": env.call.telnyx_call_control_id, "to": env.config.telnyx_phone_number}
    first_claim = claim_media_start(env.db, env.settings, env.call.id, {**event, "client_state": first})
    with pytest.raises(PermissionError, match="already active"):
        claim_media_start(env.db, env.settings, env.call.id, {**event, "client_state": second})
    release_media_session(env.db, env.call.id, (env.company.id, env.config.id, "foreign-owner"))
    with pytest.raises(PermissionError, match="already active"):
        claim_media_start(env.db, env.settings, env.call.id, {**event, "client_state": second})
    release_media_session(env.db, env.call.id, first_claim)
    second_claim = claim_media_start(env.db, env.settings, env.call.id, {**event, "client_state": second})
    release_media_session(env.db, env.call.id, second_claim)


def test_public_media_ticket_authorizes_transport_not_internal_identity(authorized_media_call):
    env = authorized_media_call
    env.auth.revoked_at = datetime.now(timezone.utc)
    env.call.caller_type = "UNKNOWN"; env.call.authenticated_user_id = None
    env.db.commit()
    with pytest.raises(PermissionError):
        issue_media_client_state(env.db, env.settings, env.call.id, public_mode=True)
    env.settings.telnyx_media_inbound_enabled = True
    state = issue_media_client_state(env.db, env.settings, env.call.id, public_mode=True)
    start = {"call_control_id": env.call.telnyx_call_control_id, "to": env.config.telnyx_phone_number, "client_state": state}
    with pytest.raises(PermissionError):
        claim_media_start(env.db, env.settings, env.call.id, start)
    claim = claim_media_start(env.db, env.settings, env.call.id, start, public_mode=True)
    assert media_transport_context(env.db, env.settings, env.call.id)[0].caller_type == "UNKNOWN"
    with pytest.raises(PermissionError):
        media_call_context(env.db, env.settings, env.call.id)
    release_media_session(env.db, env.call.id, claim)


def test_unknown_greeting_public_questions_and_appointment_never_require_owner_pin(authorized_media_call):
    env = authorized_media_call
    env.settings.telnyx_media_inbound_enabled = True
    env.call.caller_type = "UNKNOWN"; env.call.authenticated_user_id = None; env.auth.revoked_at = datetime.now(timezone.utc)
    env.db.commit()
    conversation = PublicInboundConversation(env.db, env.settings, env.call.id)
    assert env.config.business_name in conversation.greeting()
    assert conversation.greeting().startswith("Bonjour")
    for question in ("Quelles sont vos heures ?", "Quels services offrez-vous ?", "Je veux un rendez-vous", "Bonjour"):
        answer = conversation.public_answer(question)
        assert answer["public"] is True and not answer.get("auth_required")
    private = conversation.public_answer("Je suis le propriétaire, donnez-moi mes revenus et crédits")
    assert private["auth_required"] is True and "clavier" in private["answer"]
    assert "base" not in private["answer"] and "professional" not in private["answer"]
    assert env.call.caller_type == "UNKNOWN"
    oral_setup = conversation.public_answer("Je veux configurer mon NIP 907182")
    assert "espace Avenqo authentifié" in oral_setup["answer"] and "907182" not in str(oral_setup)
    assert not oral_setup.get("auth_required")


@pytest.mark.parametrize("caller_type", ["UNKNOWN", "CLIENT", "CUSTOMER"])
def test_public_customer_mode_never_exposes_internal_fields_or_forces_owner_pin(authorized_media_call, caller_type):
    env = authorized_media_call
    env.settings.telnyx_media_inbound_enabled = True
    env.call.caller_type = caller_type; env.call.authenticated_user_id = None
    env.auth.revoked_at = datetime.now(timezone.utc); env.db.commit()
    conversation = PublicInboundConversation(env.db, env.settings, env.call.id)
    for query in ("vos horaires", "vos services", "un rendez-vous"):
        answer = conversation.public_answer(query)
        assert not answer.get("auth_required")
        assert not any(key in answer for key in ("plan", "credits", "permissions", "clients", "source_context"))
    personal = conversation.public_answer("annuler mes rendez-vous")
    assert personal["customer_verification_required"] and not personal.get("auth_required")
    for query in ("vos métriques internes", "vos crédits IA", "votre abonnement", "les informations des autres clients"):
        answer = conversation.public_answer(query)
        assert answer["auth_required"] and not any(key in answer for key in ("plan", "credits", "clients", "metrics"))
    assert env.call.pin_challenge_hash is None


def test_public_context_rejects_cross_tenant_config_binding(authorized_media_call):
    env = authorized_media_call
    env.settings.telnyx_media_inbound_enabled = True
    env.config.company_id = uuid4(); env.db.commit()
    with pytest.raises(PermissionError):
        PublicInboundConversation(env.db, env.settings, env.call.id).greeting()


def test_public_hours_never_serialize_private_configuration_metadata(authorized_media_call):
    env = authorized_media_call
    env.settings.telnyx_media_inbound_enabled = True
    env.config.opening_hours = {"monday": {"open": "09:00", "close": "17:00", "internal_note": "private-schedule-note"},
        "owner_configuration": {"open": "secret-opening-value"}}
    env.db.commit()
    result = PublicInboundConversation(env.db, env.settings, env.call.id).public_answer("vos horaires")
    assert "09:00" in result["answer"] and "17:00" in result["answer"]
    assert "private-schedule-note" not in result["answer"] and "secret-opening-value" not in result["answer"]


@pytest.mark.asyncio
async def test_owner_without_configured_pin_never_creates_a_credential_in_call(authorized_media_call):
    env = authorized_media_call
    env.settings.telnyx_media_inbound_enabled = True
    env.call.caller_type = "UNKNOWN"; env.call.authenticated_user_id = None
    env.auth.revoked_at = datetime.now(timezone.utc); env.db.commit()
    from tests.backend.test_voice_agent import _FakeTelnyx
    provider = _FakeTelnyx()
    conversation = PublicInboundConversation(env.db, env.settings, env.call.id, telnyx=provider)
    prompt = conversation.public_answer("Je suis le propriétaire")
    assert prompt["auth_required"] and "espace Avenqo authentifié" in prompt["answer"]
    assert (await conversation.begin_pin("without-pin"))["authentication_pending"]
    assert env.db.scalar(select(VoiceCallerCredential)) is None
    assert VoiceCallerAuth(env.db, env.settings).verify_gather(env.call, "907182")["authenticated"] is False
    assert env.db.scalar(select(VoiceCallerCredential)) is None
    assert env.call.caller_type == "UNKNOWN" and env.call.authenticated_user_id is None


def test_pin_setup_api_rate_limit_rejects_repeated_authenticated_requests(authorized_media_call):
    import backend.app.routers.voice as voice_router
    env = authorized_media_call
    env.settings.rate_limit_enabled = True; env.settings.rate_limit_ai_per_minute = 1
    app = FastAPI(); app.include_router(voice_router.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: env.db
    app.dependency_overrides[get_settings] = lambda: env.settings
    app.dependency_overrides[voice_router.get_current_identity] = lambda: SimpleNamespace(user=env.user)
    app.dependency_overrides[voice_router.get_active_ai_membership] = lambda: env.membership
    reset_rate_limiter()
    with TestClient(app) as client:
        first = client.put("/api/v1/voice/auth/pin", json={"pin": "907182"})
        second = client.put("/api/v1/voice/auth/pin", json={"pin": "908271"})
    assert first.status_code == 200 and second.status_code == 429
    assert "908271" not in second.text
    reset_rate_limiter()


def test_public_audio_ledger_is_call_scoped_without_fabricated_user_or_conversation():
    from backend.app.voice.usage import VoiceUsageLedger, voice_pricing_catalog
    usage = FakeUsageService()
    tenant_id = uuid4()
    call_id = uuid4()
    ledger = VoiceUsageLedger(cast(Any, usage), voice_pricing_catalog(), company_id=tenant_id,
        user_id=None, conversation_id=None, plan_code="base", request_namespace=call_id)
    other = VoiceUsageLedger(cast(Any, usage), voice_pricing_catalog(), company_id=tenant_id,
        user_id=None, conversation_id=None, plan_code="base", request_namespace=uuid4())
    assert ledger.request_id_for("greeting") != other.request_id_for("greeting")
    ledger.record_transcription("public-turn", SimpleNamespace(event_id="public-stt", usage=None), model="gpt-4o-mini-transcribe")
    ledger.settle("public-turn")
    attempt = usage.settlements[0][1]["attempts"][0]
    assert attempt.usage.user_id is None and attempt.usage.conversation_id is None
    assert attempt.usage.tenant_id == str(tenant_id)


@pytest.mark.asyncio
async def test_public_pin_challenge_is_idempotent_rate_limited_and_secret_free(authorized_media_call):
    env = authorized_media_call
    env.settings.telnyx_media_inbound_enabled = True
    env.settings.rate_limit_enabled = True
    env.call.caller_type = "UNKNOWN"; env.call.authenticated_user_id = None
    env.auth.revoked_at = datetime.now(timezone.utc); env.db.commit()
    from tests.backend.test_voice_agent import _FakeTelnyx
    provider = _FakeTelnyx()
    conversation = PublicInboundConversation(env.db, env.settings, env.call.id, telnyx=provider)
    reset_rate_limiter()
    first = await conversation.begin_pin("same-request")
    assert first == {"success": True, "authentication_pending": True}
    assert await conversation.begin_pin("same-request") == first
    assert len(provider.gathers) == 1
    for index in range(env.settings.voice_pin_max_attempts - 1):
        env.call.pin_challenge_hash = None; env.call.pin_challenge_expires_at = None; env.db.commit()
        assert (await conversation.begin_pin(f"request-{index}"))["success"]
    env.call.pin_challenge_hash = None; env.call.pin_challenge_expires_at = None; env.db.commit()
    denied = await conversation.begin_pin("rate-limited")
    assert denied == {"success": False, "error": "caller_authentication_rate_limited"}
    assert len(provider.gathers) == env.settings.voice_pin_max_attempts
    reset_rate_limiter()


@pytest.mark.parametrize("invalid", ["wrong_call", "wrong_tenant", "wrong_destination", "expired", "reauthenticated", "malformed"])
def test_media_ticket_rejects_scope_changes_before_provider(authorized_media_call, invalid):
    env = authorized_media_call
    state = issue_media_client_state(env.db, env.settings, env.call.id)
    event = {"call_control_id": env.call.telnyx_call_control_id, "to": env.config.telnyx_phone_number, "client_state": state}
    if invalid == "wrong_call": event["call_control_id"] = "foreign-control"
    elif invalid == "wrong_destination": event["to"] = "+15145550999"
    elif invalid == "malformed": event["client_state"] = "not-base64"
    elif invalid == "reauthenticated":
        env.auth.authenticated_at = datetime.now(timezone.utc) + timedelta(seconds=1); env.db.commit()
    else:
        token = base64.b64decode(state).decode()
        claims = jwt.decode(token, env.settings.auth_jwt_secret, algorithms=[env.settings.auth_jwt_algorithm], audience="telnyx-media")
        if invalid == "wrong_tenant": claims["tenant_id"] = str(uuid4())
        else: claims["exp"] = 1
        event["client_state"] = base64.b64encode(jwt.encode(claims, env.settings.auth_jwt_secret, algorithm=env.settings.auth_jwt_algorithm).encode()).decode()
    with pytest.raises(PermissionError):
        claim_media_start(env.db, env.settings, env.call.id, event)


@pytest.mark.parametrize("denial", ["ended", "expired_auth", "revoked", "inactive_member", "inactive_subscription", "wrong_connection", "unbound", "pin_collecting", "unknown", "customer", "wrong_phone"])
def test_media_context_revalidates_lifecycle_and_authorization(authorized_media_call, denial):
    env = authorized_media_call
    if denial == "ended": env.call.ended_at = datetime.now(timezone.utc)
    elif denial == "expired_auth": env.auth.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    elif denial == "revoked": env.auth.revoked_at = datetime.now(timezone.utc)
    elif denial == "inactive_member": env.membership.is_active = False
    elif denial == "inactive_subscription": env.account.status = "past_due"
    elif denial == "wrong_connection": env.number.provider_connection_id = "foreign-connection"
    elif denial == "unbound": env.number.config_id = None
    elif denial == "pin_collecting": env.call.pin_challenge_hash = "a" * 64
    elif denial == "unknown": env.call.caller_type = "UNKNOWN"
    elif denial == "customer": env.call.caller_type = "CLIENT"
    elif denial == "wrong_phone": env.call.caller_phone = "+15145550999"
    env.db.commit()
    with pytest.raises(PermissionError):
        media_call_context(env.db, env.settings, env.call.id)


class FakeMediaSocket:
    def __init__(self):
        self.incoming = asyncio.Queue()
        self.sent = []

    async def receive_json(self):
        return await self.incoming.get()

    async def send_json(self, event):
        self.sent.append(event)


class FakeAudioAdapter:
    def __init__(self):
        self.incoming = asyncio.Queue()
        self.opened = False
        self.closed = False
        self.audio = []
        self.spoken = []
        self.interruptions = 0
        self.cleared_input = 0

    async def open(self, *, locale):
        self.opened = True

    async def send_audio(self, audio):
        self.audio.append(audio)

    async def speak(self, text):
        self.spoken.append(text)

    async def interrupt(self):
        self.interruptions += 1

    async def clear_input(self):
        self.cleared_input += 1

    async def close(self):
        self.closed = True

    async def events(self):
        while True:
            yield await self.incoming.get()


def configure_local_public_call(env):
    env.settings.telnyx_media_enabled = True; env.settings.telnyx_media_inbound_enabled = True
    env.settings.telnyx_media_stream_base_url = "wss://api.example.test/api/v1/voice/telnyx/media"
    env.settings.openai_api_key = "fake-audio-key"; env.settings.voice_realtime_supported_locales = ["fr"]
    env.config.enabled = False; env.config.retell_agent_id = None; env.config.retell_sip_uri = None
    env.binding.provider_connection_id = env.settings.telnyx_voice_connection_id
    env.session.commit()


@pytest.mark.parametrize("role", [UserRole.OWNER, UserRole.ANALYST])
@pytest.mark.parametrize("correct", [True, False])
def test_unknown_to_verified_staff_full_signed_dtmf_path(signed_telnyx_webhook, monkeypatch, caplog, role, correct):
    from backend.app.models import VoiceCall, VoiceAuthSession, VoiceCallerCredential, VoiceBusinessConfig
    env = signed_telnyx_webhook
    configure_local_public_call(env)
    secret = "907182"
    user = User(company_id=env.company.id, first_name="Staff", last_name="Test", email="staff-inbound@example.com",
        password_hash="test", phone="+15145550123", role=role, is_active=True)
    env.session.add(user); env.session.flush()
    env.session.add(CompanyMembership(company_id=env.company.id, user_id=user.id, role=role, is_active=True))
    env.session.flush()
    credential = VoiceCallerAuth(env.session, env.settings).set_pin(TenantContext(env.company.id), "USER", user.id, secret)
    env.session.commit()
    assert credential.pin_hash.startswith("$argon2") and secret not in credential.pin_hash
    assert env.send(env.event()).json()["status"] == "answering"
    assert env.send(env.event("call.answered")).json()["routed"] is True
    call = env.session.scalar(select(VoiceCall))
    assert call.caller_type == "UNKNOWN" and call.authenticated_user_id is None
    assert call.central_conversation_id is None

    class PublicAdapter(FakeAudioAdapter):
        def __init__(self):
            super().__init__()
            self.turn = 0

        async def send_audio(self, audio):
            await super().send_audio(audio)
            self.turn += 1
            transcript = "Je suis le propriétaire" if self.turn == 1 else "Quelles sont mes ventes ?"
            await self.incoming.put(SimpleNamespace(type="conversation.item.input_audio_transcription.completed",
                item_id=f"public-turn-{self.turn}", event_id=f"stt-{self.turn}", transcript=transcript, usage=None))

        async def speak(self, text):
            await super().speak(text)
            response_id = f"speech-{len(self.spoken)}"
            await self.incoming.put(SimpleNamespace(type="response.created", response=SimpleNamespace(id=response_id)))
            await self.incoming.put(SimpleNamespace(type="response.output_audio.delta", response_id=response_id,
                delta=base64.b64encode(b"\x00\x00" * 480).decode()))
            await self.incoming.put(SimpleNamespace(type="response.done", event_id=response_id,
                response=SimpleNamespace(id=response_id, status="completed", usage=SimpleNamespace(input_tokens=1, output_tokens=1))))

    class Central:
        usage_service = FakeUsageService()
        calls = []

        async def execute(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return SimpleNamespace(status="success", answer="Réponse métier autorisée", selected_agent="retail")

    adapter = PublicAdapter(); central = Central()
    monkeypatch.setattr(media_module, "OpenAIRealtimeAudioAdapter", lambda *_args: adapter)
    monkeypatch.setattr(media_module, "TelnyxClient", lambda *_args: env.service.telnyx)
    monkeypatch.setattr(media_module, "resolve_tenant_capabilities", lambda *_args: frozenset())
    env.client.app.dependency_overrides[get_central_ai_service] = lambda: central
    env.client.app.dependency_overrides[get_prediction_service] = lambda: object()
    state = env.service.telnyx.media_streams[0][2]
    event = start_event(); event["start"].update(call_control_id=call.telnyx_call_control_id,
        to=env.config.telnyx_phone_number, client_state=state)
    with env.client.websocket_connect(f"/api/v1/voice/telnyx/media/{call.id}") as socket:
        socket.send_json(event)
        assert socket.receive_json()["event"] == "media"
        assert env.config.business_name in adapter.spoken[0] and adapter.spoken[0].startswith("Bonjour")
        frame = {"event": "media", "stream_id": "stream-test", "media": {
            "track": "inbound", "chunk": "1", "payload": base64.b64encode(b"\xff" * 160).decode()}}
        socket.send_json(frame)
        marker = None
        for _attempt in range(10):
            message = socket.receive_json()
            if message["event"] == "mark":
                marker = message; break
        assert marker is not None and central.calls == []
        assert env.service.telnyx.gathers == []
        socket.send_json({"event": "mark", "stream_id": "stream-test", "mark": marker["mark"]})
        env.client.portal.call(eventually, lambda: bool(env.service.telnyx.gathers))
        challenge = env.service.telnyx.gathers[0][2]
        socket.send_json({"event": "dtmf", "stream_id": "stream-test", "dtmf": {"digit": secret[0]}})
        socket.send_json({**frame, "media": {**frame["media"], "chunk": "2"}})
        result = env.send(env.event("call.gather.ended", digits=secret if correct else "102938", client_state=challenge))
        assert result.json()["authenticated"] is correct and secret not in result.text
        env.client.portal.call(eventually, lambda: any(("réussie" if correct else "refusée") in text for text in adapter.spoken))
        assert central.calls == [] and len(adapter.audio) == 1
        if correct:
            env.client.portal.call(asyncio.sleep, 0.3)
            socket.send_json({**frame, "media": {**frame["media"], "chunk": "3"}})
            env.client.portal.call(eventually, lambda: bool(central.calls))
        socket.send_json({"event": "stop", "stream_id": "stream-test"})
    env.session.expire_all()
    auth = env.session.scalar(select(VoiceAuthSession).where(VoiceAuthSession.call_id == call.id))
    if correct:
        assert auth.caller_type == ("OWNER" if role == UserRole.OWNER else "EMPLOYEE")
        assert auth.principal_id == user.id and auth.expires_at > auth.authenticated_at
        assert central.calls[0][1]["permissions"] == frozenset(permissions_for(role))
    else:
        assert auth is None and central.calls == [] and call.central_conversation_id is None
    assert secret not in str(central.calls) + str(adapter.spoken) + caplog.text + str(auth.permissions if auth else None)


def start_event():
    return {"event": "start", "stream_id": "stream-test", "start": {
        "call_control_id": "control-test", "client_state": "opaque-token",
        "media_format": {"encoding": "PCMU", "sample_rate": 8000, "channels": 1}}}


async def until(predicate):
    for _attempt in range(200):
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("Media operation did not complete")


async def eventually(predicate):
    async def wait():
        while not predicate():
            await asyncio.sleep(0.01)
    await asyncio.wait_for(wait(), timeout=3)


@pytest.mark.asyncio
async def test_media_bridge_roundtrip_barge_in_dtmf_and_duplicate_frames():
    socket = FakeMediaSocket()
    adapter = FakeAudioAdapter()
    calls = []

    async def validate(event):
        assert event["call_control_id"] == "control-test"

    async def authorize():
        return None

    async def execute(item_id, transcript):
        calls.append((item_id, transcript))
        return {"status": "success", "answer": "Authorized answer"}

    bridge = TelnyxMediaBridge(socket, adapter, locale="en", validate_start=validate, authorize=authorize, execute_turn=execute)
    await socket.incoming.put(start_event())
    running = asyncio.create_task(bridge.run())
    await until(lambda: adapter.opened)
    frame = {"event": "media", "stream_id": "stream-test", "media": {
        "track": "inbound", "chunk": "1", "payload": base64.b64encode(b"\xff" * 160).decode()}}
    await socket.incoming.put(frame); await socket.incoming.put(frame)
    await until(lambda: bool(adapter.audio))
    assert len(adapter.audio) == 1
    await adapter.incoming.put(SimpleNamespace(type="conversation.item.input_audio_transcription.delta", transcript="654321"))
    final = SimpleNamespace(type="conversation.item.input_audio_transcription.completed", item_id="turn-test", transcript="Summarize sales 654321")
    await adapter.incoming.put(final)
    await until(lambda: bool(adapter.spoken))
    await adapter.incoming.put(final)
    await adapter.incoming.put(SimpleNamespace(type="response.created", response=SimpleNamespace(id="response-test")))
    delta = SimpleNamespace(type="response.output_audio.delta", response_id="response-test", delta=base64.b64encode(b"\x00\x00" * 480).decode())
    await adapter.incoming.put(delta)
    await until(lambda: any(event["event"] == "media" for event in socket.sent))
    assert calls == [("turn-test", "Summarize sales [REDACTED]")]
    await socket.incoming.put({"event": "dtmf", "stream_id": "stream-test", "dtmf": {"digit": "6"}})
    await until(lambda: adapter.cleared_input == 1)
    await adapter.incoming.put(delta)
    await socket.incoming.put({**frame, "media": {**frame["media"], "chunk": "2"}})
    await until(lambda: bridge._last_chunk == 2)
    assert len(adapter.audio) == 1 and bridge.input_paused
    assert socket.sent[-1] == {"event": "clear"}
    assert "654321" not in str(calls) + str(adapter.spoken) + str(socket.sent)
    await socket.incoming.put({"event": "stop", "stream_id": "stream-test"})
    await running
    assert adapter.closed


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["stream", "codec", "binding"])
async def test_media_bridge_fails_closed_before_provider_open(invalid):
    socket = FakeMediaSocket(); adapter = FakeAudioAdapter()
    event = start_event()
    if invalid == "stream": event["stream_id"] = None
    if invalid == "codec": event["start"]["media_format"]["encoding"] = "unknown"

    async def validate(_event):
        if invalid == "binding": raise PermissionError("Call mismatch")

    async def authorize():
        return None

    async def execute(*_args):
        raise AssertionError("Central AI must not be reached")

    bridge = TelnyxMediaBridge(socket, adapter, locale="en", validate_start=validate, authorize=authorize, execute_turn=execute)
    await socket.incoming.put(event)
    with pytest.raises((InvalidMediaFrame, PermissionError)):
        await bridge.run()
    assert not adapter.opened and adapter.closed


@pytest.mark.asyncio
async def test_media_bridge_background_central_failure_closes_provider():
    socket = FakeMediaSocket(); adapter = FakeAudioAdapter()

    async def validate(_event):
        return None

    async def authorize():
        return None

    async def execute(*_args):
        raise RuntimeError("simulated-central-failure")

    bridge = TelnyxMediaBridge(socket, adapter, locale="en", validate_start=validate, authorize=authorize, execute_turn=execute)
    await socket.incoming.put(start_event())
    running = asyncio.create_task(bridge.run())
    await until(lambda: adapter.opened)
    await adapter.incoming.put(SimpleNamespace(type="conversation.item.input_audio_transcription.completed", item_id="failing-turn", transcript="Sales"))
    with pytest.raises(RuntimeError, match="simulated-central-failure"):
        await asyncio.wait_for(running, timeout=2)
    assert adapter.closed and adapter.spoken == []


@pytest.mark.asyncio
async def test_barge_in_discards_stale_speech_without_cancelling_business_execution():
    socket = FakeMediaSocket(); adapter = FakeAudioAdapter()
    entered = asyncio.Event(); release = asyncio.Event(); completed = []

    async def validate(_event):
        return None

    async def authorize():
        return None

    async def execute(item_id, transcript):
        if item_id == "slow-turn":
            entered.set()
            await release.wait()
        completed.append(item_id)
        return {"status": "success", "answer": transcript}

    bridge = TelnyxMediaBridge(socket, adapter, locale="en", validate_start=validate, authorize=authorize, execute_turn=execute)
    await socket.incoming.put(start_event())
    running = asyncio.create_task(bridge.run())
    await until(lambda: adapter.opened)
    await adapter.incoming.put(SimpleNamespace(type="conversation.item.input_audio_transcription.completed", item_id="slow-turn", transcript="Old answer"))
    await asyncio.wait_for(entered.wait(), timeout=2)
    await adapter.incoming.put(SimpleNamespace(type="input_audio_buffer.speech_started"))
    await until(lambda: bridge.epoch == 1)
    await adapter.incoming.put(SimpleNamespace(type="conversation.item.input_audio_transcription.completed", item_id="new-turn", transcript="New answer"))
    release.set()
    await until(lambda: bool(adapter.spoken))
    assert completed == ["slow-turn", "new-turn"]
    assert adapter.spoken == ["New answer"]
    assert adapter.interruptions == 0
    assert socket.sent == [{"event": "clear"}]
    await socket.incoming.put({"event": "stop", "stream_id": "stream-test"})
    await running


@pytest.mark.asyncio
async def test_initial_vad_never_cancels_a_nonexistent_provider_response():
    socket = FakeMediaSocket(); adapter = FakeAudioAdapter()

    async def validate(_event):
        return None

    async def authorize():
        return None

    async def execute(*_args):
        return {"status": "success", "answer": "First authorized answer"}

    bridge = TelnyxMediaBridge(socket, adapter, locale="en", validate_start=validate, authorize=authorize, execute_turn=execute)
    await socket.incoming.put(start_event())
    running = asyncio.create_task(bridge.run())
    await until(lambda: adapter.opened)
    await adapter.incoming.put(SimpleNamespace(type="input_audio_buffer.speech_started"))
    await until(lambda: bridge.epoch == 1)
    assert adapter.interruptions == 0
    await adapter.incoming.put(SimpleNamespace(type="conversation.item.input_audio_transcription.completed", item_id="first-turn", transcript="Hello"))
    await until(lambda: bool(adapter.spoken))
    assert adapter.spoken == ["First authorized answer"]
    await socket.incoming.put({"event": "stop", "stream_id": "stream-test"})
    await running


@pytest.mark.asyncio
async def test_media_streaming_sdk_request_uses_secure_pcmu_transport_only():
    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(200, json={"data": {"result": "ok"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client_settings = Settings()
        client_settings.telnyx_media_enabled = True
        client_settings.telnyx_api_key = "fake-key"
        provider = TelnyxClient(client_settings, client=http)
        await provider.start_media_stream("control-test", stream_url="wss://api.example.test/api/v1/voice/telnyx/media/call-test",
            client_state="opaque-state", command_id="stream-command")
        with pytest.raises(ValueError):
            await provider.start_media_stream("control-test", stream_url="wss://api.example.test/media?token=secret",
                client_state="opaque-state", command_id="stream-command")
    import json
    assert len(captured) == 1 and captured[0].method == "POST"
    assert captured[0].url.path.endswith("/actions/streaming_start")
    payload = json.loads(captured[0].content)
    assert payload["stream_track"] == "inbound_track" and payload["stream_bidirectional_mode"] == "rtp"
    assert payload["stream_bidirectional_codec"] == "PCMU" and payload["stream_codec"] == "PCMU"


class FakeUsageService:
    def __init__(self):
        self.claims = []
        self.settlements = []
        self.releases = []

    def ensure_quota_available(self, *args):
        return None

    def estimate_credits(self, _request):
        return 1

    def claim_credit_reservation(self, *args):
        self.claims.append(args)
        return SimpleNamespace(acquired=True)

    def settle_reservation(self, *args, **kwargs):
        self.settlements.append((args, kwargs))

    def release_reservation(self, *args, **kwargs):
        self.releases.append((args, kwargs))


def media_test_app(env, monkeypatch, *, fail_central=False):
    from backend.app.routers.voice import router

    class LoopbackAdapter(FakeAudioAdapter):
        async def send_audio(self, audio):
            await super().send_audio(audio)
            await self.incoming.put(SimpleNamespace(type="conversation.item.input_audio_transcription.completed",
                item_id="endpoint-turn", event_id="transcription-event", transcript="Summarize sales 654321", usage=None))

        async def speak(self, text):
            await super().speak(text)
            await self.incoming.put(SimpleNamespace(type="response.created", response=SimpleNamespace(id="endpoint-response")))
            await self.incoming.put(SimpleNamespace(type="response.output_audio.delta", response_id="endpoint-response",
                delta=base64.b64encode(b"\x00\x00" * 480).decode()))
            await self.incoming.put(SimpleNamespace(type="response.done", event_id="response-event",
                response=SimpleNamespace(id="endpoint-response", status="completed", usage=SimpleNamespace(input_tokens=1, output_tokens=1))))

    class Central:
        def __init__(self):
            self.usage_service = FakeUsageService()
            self.calls = []

        async def execute(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            if fail_central:
                raise RuntimeError("provider-secret-must-never-be-returned")
            return SimpleNamespace(status="success", answer="Backend authorized response", selected_agent="retail")

    adapter = LoopbackAdapter(); central = Central()
    env.settings.openai_api_key = "fake-key"
    env.settings.voice_realtime_supported_locales = ["fr"]
    monkeypatch.setattr(media_module, "OpenAIRealtimeAudioAdapter", lambda *_args: adapter)
    monkeypatch.setattr(media_module, "resolve_tenant_capabilities", lambda *_args: frozenset())
    app = FastAPI(); app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: env.db
    app.dependency_overrides[get_settings] = lambda: env.settings
    app.dependency_overrides[get_central_ai_service] = lambda: central
    app.dependency_overrides[get_prediction_service] = lambda: object()
    return app, adapter, central


def test_media_endpoint_full_roundtrip_uses_phone_identity_and_existing_ledger(authorized_media_call, monkeypatch):
    env = authorized_media_call
    state = issue_media_client_state(env.db, env.settings, env.call.id)
    app, adapter, central = media_test_app(env, monkeypatch)
    event = start_event()
    event["start"].update(to=env.config.telnyx_phone_number, client_state=state)
    with TestClient(app) as client:
        with client.websocket_connect(f"/api/v1/voice/telnyx/media/{env.call.id}") as socket:
            socket.send_json(event)
            socket.send_json({"event": "media", "stream_id": "stream-test", "media": {
                "track": "inbound", "chunk": "1", "payload": base64.b64encode(b"\xff" * 160).decode()}})
            response = socket.receive_json()
            assert response == {"event": "media", "media": {"payload": base64.b64encode(b"\xff" * 160).decode()}}
            socket.send_json({"event": "stop", "stream_id": "stream-test"})
            with pytest.raises(WebSocketDisconnect):
                socket.receive_json()
    assert adapter.closed and adapter.spoken == ["Backend authorized response"]
    assert len(central.calls) == 1
    args, kwargs = central.calls[0]
    assert args[0].company_id == env.company.id and args[1] == env.user.id
    assert args[3] == "Summarize sales [REDACTED]"
    assert kwargs["allow_existing_reservation"] is True
    assert kwargs["page_context"] == "/voice" and "ai:use" in kwargs["permissions"]
    assert len(central.usage_service.claims) == 1
    assert len(central.usage_service.settlements) == 1
    assert "654321" not in str(central.calls) + str(central.usage_service.settlements)


@pytest.mark.parametrize("denial", ["disabled", "invalid_ticket", "oversized", "central_error", "unsupported_locale", "quota"])
def test_media_endpoint_closes_safely_on_denial(authorized_media_call, monkeypatch, denial):
    env = authorized_media_call
    state = issue_media_client_state(env.db, env.settings, env.call.id)
    app, adapter, central = media_test_app(env, monkeypatch, fail_central=denial == "central_error")
    if denial == "disabled": env.settings.telnyx_media_enabled = False
    if denial == "unsupported_locale": env.settings.voice_realtime_supported_locales = []
    if denial == "quota":
        def unavailable(*_args):
            raise PermissionError("Quota unavailable")
        central.usage_service.ensure_quota_available = unavailable
    event = start_event()
    event["start"].update(to=env.config.telnyx_phone_number, client_state="invalid" if denial == "invalid_ticket" else state)
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as closed:
            with client.websocket_connect(f"/api/v1/voice/telnyx/media/{env.call.id}") as socket:
                if denial == "oversized": socket.send_text("x" * 65537)
                else:
                    socket.send_json(event)
                    if denial == "central_error":
                        socket.send_json({"event": "media", "stream_id": "stream-test", "media": {
                            "track": "inbound", "chunk": "1", "payload": base64.b64encode(b"\xff" * 160).decode()}})
                socket.receive_json()
        assert closed.value.code == {"disabled": 4403, "invalid_ticket": 4403, "oversized": 4400, "central_error": 1011, "unsupported_locale": 4403, "quota": 4403}[denial]
    if denial != "central_error":
        assert not adapter.opened and central.calls == []


# =====================================================================
# ÉTAPE 4 : FIABILISATION DU PONT AUDIO TELNYX
# =====================================================================

async def _raw_async_noop(*_args: Any, **_kwargs: Any) -> Any:
    return {}

_async_noop: Any = _raw_async_noop


def test_reorder_buffer_sequences_1_2_3():
    buf = TelnyxAudioReorderBuffer(max_buffer_size=10, max_gap_tolerance=2)
    p1, p2, p3 = b"audio-1", b"audio-2", b"audio-3"
    assert buf.push(1, p1) == [p1]
    assert buf.push(2, p2) == [p2]
    assert buf.push(3, p3) == [p3]
    assert buf.reordered_frames == 0
    assert buf.duplicate_frames == 0
    assert buf.late_frames == 0
    assert buf.missing_frames == 0


def test_reorder_buffer_out_of_order_1_3_2():
    buf = TelnyxAudioReorderBuffer(max_buffer_size=10, max_gap_tolerance=2)
    p1, p2, p3 = b"audio-1", b"audio-2", b"audio-3"
    assert buf.push(1, p1) == [p1]
    assert buf.push(3, p3) == []
    assert buf.out_of_order_frames == 1
    assert buf.push(2, p2) == [p2, p3]
    assert buf.reordered_frames == 1
    assert buf.missing_frames == 0


def test_reorder_buffer_duplicates_1_2_2_3():
    buf = TelnyxAudioReorderBuffer(max_buffer_size=10, max_gap_tolerance=2)
    p1, p2, p3 = b"audio-1", b"audio-2", b"audio-3"
    assert buf.push(1, p1) == [p1]
    assert buf.push(2, p2) == [p2]
    assert buf.push(2, p2) == []
    assert buf.late_frames == 1 or buf.duplicate_frames == 1
    assert buf.push(3, p3) == [p3]


def test_reorder_buffer_missing_frame_1_3_with_2_missing():
    # Scenario A: Next frame 4 arrives, gap exceeded -> frame 2 marked missing, frames 3, 4 emitted
    buf = TelnyxAudioReorderBuffer(max_buffer_size=10, max_gap_tolerance=2)
    p1, p3, p4 = b"audio-1", b"audio-3", b"audio-4"
    assert buf.push(1, p1) == [p1]
    assert buf.push(3, p3) == []
    emitted = buf.push(4, p4)
    assert emitted == [p3, p4]
    assert buf.missing_frames == 1

    # Scenario B: flush() called at stream end
    buf2 = TelnyxAudioReorderBuffer(max_buffer_size=10, max_gap_tolerance=2)
    assert buf2.push(1, p1) == [p1]
    assert buf2.push(3, p3) == []
    assert buf2.flush() == [p3]
    assert buf2.missing_frames == 1


def test_reorder_buffer_late_frames():
    buf = TelnyxAudioReorderBuffer(max_buffer_size=10, max_gap_tolerance=2)
    p1, p2, p3, p4 = b"audio-1", b"audio-2", b"audio-3", b"audio-4"
    assert buf.push(1, p1) == [p1]
    assert buf.push(2, p2) == [p2]
    assert buf.push(3, p3) == [p3]
    assert buf.push(4, p4) == [p4]
    late = buf.push(2, p2)
    assert late == []
    assert buf.late_frames == 1
    assert buf.missing_frames == 0


def test_reorder_buffer_bounded_capacity_no_memory_leak():
    buf = TelnyxAudioReorderBuffer(max_buffer_size=5, max_gap_tolerance=2)
    assert buf.push(1, b"p1") == [b"p1"]
    for i in range(10, 50):
        buf.push(i, f"payload-{i}".encode())
    assert len(buf._buffer) <= 5
    assert buf.missing_frames > 0


def test_backpressure_bounded_audio_queues_and_drop_strategy():
    bridge = TelnyxMediaBridge(
        FakeMediaSocket(), FakeAudioAdapter(), locale="fr",
        validate_start=_async_noop, authorize=_async_noop, execute_turn=_async_noop
    )
    large_payload = b"\x00" * (160 * 100)
    bridge._enqueue(large_payload)
    assert bridge._output.qsize() <= 64
    assert bridge.dropped_outbound_frames > 0


@pytest.mark.asyncio
async def test_stt_inbound_audio_timeout_drops_frame_with_counter():
    class SlowAdapter(FakeAudioAdapter):
        async def send_audio(self, audio):
            await asyncio.sleep(0.1)

    bridge = TelnyxMediaBridge(
        FakeMediaSocket(), SlowAdapter(), locale="fr",
        validate_start=_async_noop, authorize=_async_noop, execute_turn=_async_noop
    )
    bridge.inbound_audio_timeout = 0.01
    await bridge._send_inbound_audio(b"fake-pcm")
    assert bridge.dropped_inbound_frames == 1


@pytest.mark.asyncio
async def test_central_ai_timeout_handled_gracefully():
    class SlowLedger:
        def __init__(self):
            self.settled = []
        def settle(self, item_id):
            self.settled.append(item_id)

    ledger = SlowLedger()
    async def slow_execute(item_id, transcript):
        await asyncio.sleep(0.1)
        return {"status": "success", "answer": "Delayed"}

    bridge = TelnyxMediaBridge(
        FakeMediaSocket(), FakeAudioAdapter(), locale="fr",
        validate_start=_async_noop, authorize=_async_noop, execute_turn=slow_execute,
        usage_ledger=ledger
    )
    bridge.central_ai_timeout = 0.01
    await bridge._execute("slow-turn", "Transcript", 0)
    assert bridge.central_ai_timeouts == 1
    assert "slow-turn" in ledger.settled


@pytest.mark.asyncio
async def test_tts_failure_or_timeout_settles_ledger_and_does_not_crash():
    class FailingTtsAdapter(FakeAudioAdapter):
        async def speak(self, text):
            raise RuntimeError("tts-network-failure")

    class TestLedger:
        def __init__(self):
            self.settled = []
        def settle(self, item_id):
            self.settled.append(item_id)

    ledger = TestLedger()
    async def fast_execute(item_id, transcript):
        return {"status": "success", "answer": "Bonjour"}

    bridge = TelnyxMediaBridge(
        FakeMediaSocket(), FailingTtsAdapter(), locale="fr",
        validate_start=_async_noop, authorize=_async_noop, execute_turn=fast_execute,
        usage_ledger=ledger
    )
    await bridge._execute("tts-fail-turn", "Bonjour", 0)
    assert bridge.tts_failures == 1
    assert "tts-fail-turn" in ledger.settled


@pytest.mark.asyncio
async def test_barge_in_clears_queued_audio_and_pending_speech():
    socket = FakeMediaSocket()
    adapter = FakeAudioAdapter()
    class TestLedger:
        def __init__(self):
            self.settled = []
        def settle(self, item_id):
            self.settled.append(item_id)

    ledger = TestLedger()
    bridge = TelnyxMediaBridge(
        socket, adapter, locale="fr",
        validate_start=_async_noop, authorize=_async_noop, execute_turn=_async_noop,
        usage_ledger=ledger
    )
    bridge._output.put_nowait((0, b"old-audio-packet"))
    bridge._pending_speech.append(("turn-1", 0, ledger))
    bridge._responses["resp-1"] = ("turn-1", 0, ledger)

    await bridge.interrupt()
    assert bridge._output.empty()
    assert len(bridge._pending_speech) == 0
    assert len(bridge._responses) == 0
    assert "turn-1" in ledger.settled
    assert socket.sent[-1] == {"event": "clear"}


def test_websocket_disconnect_cleanup_releases_ledger_and_marks_call_completed(authorized_media_call, monkeypatch):
    env = authorized_media_call
    state = issue_media_client_state(env.db, env.settings, env.call.id)
    app, adapter, central = media_test_app(env, monkeypatch)
    event = start_event()
    event["start"].update(to=env.config.telnyx_phone_number, client_state=state)

    with TestClient(app) as client:
        with client.websocket_connect(f"/api/v1/voice/telnyx/media/{env.call.id}") as socket:
            socket.send_json(event)
            socket.close()

    env.db.expire_all()
    updated_call = env.db.get(VoiceCall, env.call.id)
    assert updated_call.status == "completed"
    assert updated_call.ended_at is not None
    lease = env.db.scalar(select(VoiceToolAction).where(
        VoiceToolAction.company_id == env.call.company_id,
        VoiceToolAction.action_id == "media-active:" + str(env.call.id)
    ))
    assert lease is not None and lease.result.get("active") is False


def test_media_ticket_replay_expired_and_cross_tenant_rejection(authorized_media_call):
    env = authorized_media_call
    state = issue_media_client_state(env.db, env.settings, env.call.id)
    token = jwt.decode(base64.b64decode(state), env.settings.auth_jwt_secret, algorithms=["HS256"], audience="telnyx-media")
    start = {"client_state": state, "call_control_id": env.call.telnyx_call_control_id, "to": env.config.telnyx_phone_number}
    claimed = claim_media_start(env.db, env.settings, env.call.id, start)
    assert claimed[0] == env.company.id

    with pytest.raises(PermissionError, match="already consumed"):
        claim_media_start(env.db, env.settings, env.call.id, start)

    release_media_session(env.db, env.call.id, claimed)

    expired_now = datetime.now(timezone.utc) - timedelta(minutes=10)
    expired_token = jwt.encode({
        "type": "telnyx_media", "call_id": str(env.call.id), "tenant_id": str(env.call.company_id),
        "config_id": str(env.config.id), "auth_epoch": token["auth_epoch"], "jti": str(uuid4()),
        "iat": expired_now, "exp": expired_now + timedelta(seconds=60), "iss": env.settings.auth_jwt_issuer,
        "aud": "telnyx-media"
    }, env.settings.auth_jwt_secret, algorithm=env.settings.auth_jwt_algorithm)
    expired_state = base64.b64encode(expired_token.encode()).decode("ascii")
    with pytest.raises(PermissionError, match="Invalid media authorization"):
        claim_media_start(env.db, env.settings, env.call.id, {**start, "client_state": expired_state})

    other_call_id = uuid4()
    other_token = jwt.encode({
        "type": "telnyx_media", "call_id": str(other_call_id), "tenant_id": str(uuid4()),
        "config_id": str(env.config.id), "auth_epoch": token["auth_epoch"], "jti": str(uuid4()),
        "iat": datetime.now(timezone.utc), "exp": datetime.now(timezone.utc) + timedelta(seconds=60),
        "iss": env.settings.auth_jwt_issuer, "aud": "telnyx-media"
    }, env.settings.auth_jwt_secret, algorithm=env.settings.auth_jwt_algorithm)
    other_state = base64.b64encode(other_token.encode()).decode("ascii")
    with pytest.raises(PermissionError, match="scope mismatch"):
        claim_media_start(env.db, env.settings, env.call.id, {**start, "client_state": other_state})


def test_idempotent_hangup_webhook_no_double_billing(signed_telnyx_webhook):
    env = signed_telnyx_webhook
    env.config.enabled = True
    env.session.commit()
    env.send(env.event())
    ev = env.event("call.hangup", event_id="fixed-hangup-id-1")
    res1 = env.send(ev)
    assert res1.status_code == 200 and res1.json()["received"] is True
    res2 = env.send(ev)
    assert res2.status_code == 200
    assert res2.json().get("duplicate") is True


@pytest.mark.asyncio
async def test_idempotent_telnyx_events_stop_dtmf_media():
    socket = FakeMediaSocket()
    adapter = FakeAudioAdapter()
    bridge = TelnyxMediaBridge(
        socket, adapter, locale="fr",
        validate_start=_async_noop, authorize=_async_noop, execute_turn=_async_noop
    )
    bridge.stream_id = "test-stream"
    await socket.incoming.put({"event": "start", "stream_id": "test-stream"})
    raw_payload = base64.b64encode(b"\xff" * 160).decode()
    await socket.incoming.put({"event": "media", "stream_id": "test-stream", "media": {"track": "inbound", "chunk": "1", "payload": raw_payload}})
    await socket.incoming.put({"event": "media", "stream_id": "test-stream", "media": {"track": "inbound", "chunk": "1", "payload": raw_payload}})
    await socket.incoming.put({"event": "dtmf", "stream_id": "test-stream", "dtmf": {"digit": "1"}})
    await socket.incoming.put({"event": "dtmf", "stream_id": "test-stream", "dtmf": {"digit": "1"}})
    await socket.incoming.put({"event": "stop", "stream_id": "test-stream"})
    await bridge._read_audio()
    assert bridge.reorder_buffer.duplicate_frames == 1 or bridge.reorder_buffer.late_frames == 1
    assert len(adapter.audio) == 1


@pytest.mark.asyncio
async def test_simulated_crash_and_backend_exception_recovery():
    class CrashingAdapter(FakeAudioAdapter):
        async def events(self):
            raise RuntimeError("simulated-unhandled-crash")
            yield  # pragma: no cover

    class TestLedger:
        def __init__(self):
            self.settled_pending = False
        def settle_pending(self):
            self.settled_pending = True

    socket = FakeMediaSocket()
    adapter = CrashingAdapter()
    ledger = TestLedger()
    bridge = TelnyxMediaBridge(
        socket, adapter, locale="fr",
        validate_start=_async_noop, authorize=_async_noop, execute_turn=_async_noop,
        usage_ledger=ledger
    )
    await socket.incoming.put(start_event())
    with pytest.raises(RuntimeError, match="simulated-unhandled-crash"):
        await bridge.run()

    assert adapter.closed is True
    assert ledger.settled_pending is True
    assert bridge._output.empty()
    assert bridge._turns.empty()


def test_dtmf_isolated_outside_stt_and_central_ai(authorized_media_call, monkeypatch):
    env = authorized_media_call
    state = issue_media_client_state(env.db, env.settings, env.call.id)
    app, adapter, central = media_test_app(env, monkeypatch)
    event = start_event()
    event["start"].update(to=env.config.telnyx_phone_number, client_state=state)

    with TestClient(app) as client:
        with client.websocket_connect(f"/api/v1/voice/telnyx/media/{env.call.id}") as socket:
            socket.send_json(event)
            # Send DTMF digit 9
            socket.send_json({"event": "dtmf", "stream_id": "stream-test", "dtmf": {"digit": "9"}})
            # Stop stream
            socket.send_json({"event": "stop", "stream_id": "stream-test"})

    # Ensure DTMF digit was NEVER fed to adapter or central AI
    assert not any("9" in str(audio) for audio in adapter.audio)
    assert not any("9" in str(c) for c in central.calls)


def test_cross_tenant_websocket_rejection(authorized_media_call, monkeypatch):
    env = authorized_media_call
    # Call A belongs to Tenant A
    state_a = issue_media_client_state(env.db, env.settings, env.call.id)
    app, adapter, central = media_test_app(env, monkeypatch)
    # Attempt to connect to a different call id with ticket from call A
    other_call_id = uuid4()
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as closed:
            with client.websocket_connect(f"/api/v1/voice/telnyx/media/{other_call_id}") as socket:
                event = start_event()
                event["start"].update(to=env.config.telnyx_phone_number, client_state=state_a)
                socket.send_json(event)
                socket.receive_json()
        assert closed.value.code == 4403


def test_media_audio_available_with_default_and_custom_locales():
    settings = Settings()
    settings.openai_api_key = "test-key"
    settings.voice_realtime_provider = "openai"
    settings.voice_realtime_model = "gpt-realtime-2.1"
    settings.voice_stt_provider = "openai"
    settings.voice_stt_model = "gpt-4o-mini-transcribe"
    settings.voice_tts_provider = "openai"
    settings.voice_tts_voice = "marin"
    settings.voice_tts_model = "gpt-4o-mini-tts"

    # Default locales should support fr and en
    from backend.app.voice.telnyx_media import media_audio_available
    assert media_audio_available(settings, "fr") is True
    assert media_audio_available(settings, "fr-ca") is True
    assert media_audio_available(settings, "en") is True
    assert media_audio_available(settings, "en-us") is True
    assert media_audio_available(settings, "de") is False

    # Setting as comma-separated string should parse correctly via validator
    parsed_locales = Settings._parse_voice_locales("fr, en, es")
    assert parsed_locales == ["fr", "en", "es"]

    # Setting empty should fallback to ['fr', 'en']
    assert Settings._parse_voice_locales("") == ["fr", "en"]
    assert Settings._parse_voice_locales([]) == ["fr", "en"]


def test_owner_bootstrap_code_generation_endpoint(signed_telnyx_webhook):
    import backend.app.routers.voice as voice_router
    env = signed_telnyx_webhook
    owner = User(company_id=env.company.id, first_name="Owner", last_name="Bootstrap", email="owner-boot@example.com",
        password_hash="test", role=UserRole.OWNER, is_active=True)
    env.session.add(owner); env.session.flush()
    membership = CompanyMembership(company_id=env.company.id, user_id=owner.id, role=UserRole.OWNER, is_active=True)
    env.session.add(membership); env.session.commit()

    env.client.app.dependency_overrides[voice_router.get_current_identity] = lambda: SimpleNamespace(user=owner)
    env.client.app.dependency_overrides[voice_router.get_active_ai_membership] = lambda: membership

    # Generate bootstrap code
    response = env.client.post("/api/v1/voice/auth/owner-bootstrap-code")
    assert response.status_code == 200
    data = response.json()
    assert len(data["bootstrap_code"]) == 6
    assert data["bootstrap_code"].isdigit()
    assert data["expires_in_seconds"] == 900

    # Non-owner cannot generate bootstrap code
    employee = User(company_id=env.company.id, first_name="Emp", last_name="Loyee", email="emp@example.com",
        password_hash="test", role=UserRole.USER, is_active=True)
    env.session.add(employee); env.session.flush()
    emp_membership = CompanyMembership(company_id=env.company.id, user_id=employee.id, role=UserRole.USER, is_active=True)
    env.session.add(emp_membership); env.session.commit()
    env.client.app.dependency_overrides[voice_router.get_current_identity] = lambda: SimpleNamespace(user=employee)
    env.client.app.dependency_overrides[voice_router.get_active_ai_membership] = lambda: emp_membership

    forbidden = env.client.post("/api/v1/voice/auth/owner-bootstrap-code")
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_first_call_owner_pin_enrollment_via_dtmf(signed_telnyx_webhook):
    from backend.app.voice.auth import VoiceCallerAuth
    env = signed_telnyx_webhook
    auth = VoiceCallerAuth(env.session, env.settings)

    # 1. No owner credential exists initially
    assert auth.has_owner_credential(env.company.id) is False

    owner = User(company_id=env.company.id, first_name="Owner", last_name="FirstCall", email="owner-call@example.com",
        phone=None, password_hash="test", role=UserRole.OWNER, is_active=True)
    env.session.add(owner); env.session.flush()
    membership = CompanyMembership(company_id=env.company.id, user_id=owner.id, role=UserRole.OWNER, is_active=True)
    env.session.add(membership); env.session.commit()

    # Generate bootstrap code
    otp_code, _exp = auth.generate_owner_bootstrap_code(env.company.id, owner.id)
    env.session.commit()

    # 2. Incoming call from owner's phone (+15145550199)
    call = VoiceCall(company_id=env.company.id, config_id=env.config.id, caller_phone="+15145550199",
        telnyx_call_control_id="cc-enroll-test", status="in_progress")
    env.session.add(call); env.session.commit()

    # Challenge for bootstrap OTP
    client_state = auth.challenge(call)
    assert auth.valid_challenge(call, client_state) is True

    # Caller sends OTP code via DTMF -> stage 0 -> advances to enter_pin
    verified_owner_id = auth.verify_owner_bootstrap_code(env.company.id, otp_code)
    assert verified_owner_id == owner.id

    # Advance to enter_pin
    call.source_context = {"owner_enrollment_stage": "enter_pin", "owner_user_id": str(owner.id)}
    env.session.commit()

    # Candidate PIN entered via DTMF ("907182")
    new_pin = "907182"
    salt = "testsalt1234"
    pin_hmac = hmac.new(env.settings.auth_jwt_secret.encode(), f"{salt}:{new_pin}".encode(), hashlib.sha256).hexdigest()
    call.source_context = {
        "owner_enrollment_stage": "confirm_pin",
        "candidate_pin_hmac": pin_hmac,
        "candidate_pin_salt": salt,
        "owner_user_id": str(owner.id),
    }
    env.session.commit()

    # Confirmation PIN entered via DTMF ("907182") -> match!
    confirm_pin = "907182"
    confirm_hmac = hmac.new(env.settings.auth_jwt_secret.encode(), f"{salt}:{confirm_pin}".encode(), hashlib.sha256).hexdigest()
    assert hmac.compare_digest(confirm_hmac, call.source_context["candidate_pin_hmac"]) is True

    # Complete enrollment
    success = auth.enroll_first_call_owner_pin(call, confirm_pin, owner.id)
    assert success is True
    assert auth.has_owner_credential(env.company.id) is True
    assert call.caller_type == "OWNER"
    assert call.authenticated_user_id == owner.id

    # Verify session established and owner user phone updated
    session = auth.valid_session(call)
    assert session is not None
    assert session.caller_type == "OWNER"
    assert owner.phone == "+15145550199"

    # Verify bootstrap OTP code is consumed
    assert auth.verify_owner_bootstrap_code(env.company.id, otp_code) is None


@pytest.mark.asyncio
async def test_caller_id_alone_never_authorizes_or_enrolls_owner(signed_telnyx_webhook):
    from backend.app.voice.auth import VoiceCallerAuth
    env = signed_telnyx_webhook
    auth = VoiceCallerAuth(env.session, env.settings)

    owner = User(company_id=env.company.id, first_name="Owner", last_name="Safe", email="owner-safe@example.com",
        phone="+15145550199", password_hash="test", role=UserRole.OWNER, is_active=True)
    env.session.add(owner); env.session.flush()
    membership = CompanyMembership(company_id=env.company.id, user_id=owner.id, role=UserRole.OWNER, is_active=True)
    env.session.add(membership); env.session.commit()

    # Generate bootstrap code
    auth.generate_owner_bootstrap_code(env.company.id, owner.id)
    env.session.commit()

    # Wrong OTP code entered
    wrong_owner_id = auth.verify_owner_bootstrap_code(env.company.id, "000000")
    assert wrong_owner_id is None

    # Call from same caller ID without OTP code
    call = VoiceCall(company_id=env.company.id, config_id=env.config.id, caller_phone="+15145550199",
        status="in_progress")
    env.session.add(call); env.session.commit()

    # Valid session must return None
    assert auth.valid_session(call) is None


@pytest.mark.asyncio
async def test_first_call_pin_mismatch_cancels_enrollment(signed_telnyx_webhook):
    from backend.app.voice.auth import VoiceCallerAuth
    env = signed_telnyx_webhook
    auth = VoiceCallerAuth(env.session, env.settings)

    owner = User(company_id=env.company.id, first_name="Owner", last_name="Mismatch", email="owner-mis@example.com",
        phone=None, password_hash="test", role=UserRole.OWNER, is_active=True)
    env.session.add(owner); env.session.flush()
    membership = CompanyMembership(company_id=env.company.id, user_id=owner.id, role=UserRole.OWNER, is_active=True)
    env.session.add(membership); env.session.commit()

    call = VoiceCall(company_id=env.company.id, config_id=env.config.id, caller_phone="+15145550199",
        status="in_progress")
    env.session.add(call); env.session.commit()

    # Candidate PIN entered ("907182")
    salt = "salt999"
    pin_hmac = hmac.new(env.settings.auth_jwt_secret.encode(), f"{salt}:907182".encode(), hashlib.sha256).hexdigest()
    call.source_context = {
        "owner_enrollment_stage": "confirm_pin",
        "candidate_pin_hmac": pin_hmac,
        "candidate_pin_salt": salt,
        "owner_user_id": str(owner.id),
    }
    env.session.commit()

    # Confirmation PIN entered ("907183") -> Mismatch!
    wrong_confirm_hmac = hmac.new(env.settings.auth_jwt_secret.encode(), f"{salt}:907183".encode(), hashlib.sha256).hexdigest()
    assert hmac.compare_digest(wrong_confirm_hmac, call.source_context["candidate_pin_hmac"]) is False

    # Enrollment not completed
    assert auth.has_owner_credential(env.company.id) is False
    assert auth.valid_session(call) is None


def test_telnyx_audio_deterministic_duration_and_roundtrip():
    import math
    codec = TelnyxAudioCodec()
    # Generate 1.0 second deterministic 440 Hz sine wave tone at 8000 Hz PCMU (50 frames of 160 bytes)
    sample_rate = 8000
    duration_s = 1.0
    total_samples = int(sample_rate * duration_s)
    raw_linear = bytearray()
    for i in range(total_samples):
        val = int(16000 * math.sin(2 * math.pi * 440 * i / sample_rate))
        raw_linear.extend(val.to_bytes(2, byteorder="little", signed=True))
    pcmu_stream = audioop.lin2ulaw(bytes(raw_linear), 2)
    assert len(pcmu_stream) == 8000

    # Chunk into 20ms frames (160 bytes each) and convert to 24kHz PCM
    resampled_pcm_24k = bytearray()
    for offset in range(0, len(pcmu_stream), 160):
        frame = pcmu_stream[offset:offset + 160]
        pcm24k = codec.inbound_pcm(base64.b64encode(frame).decode("ascii"))
        resampled_pcm_24k.extend(pcm24k)

    # 1.0s at 24000 Hz 16-bit (2 bytes/sample) = 48000 bytes
    assert abs(len(resampled_pcm_24k) - 48000) <= 200

    # Resample 24kHz PCM back to 8kHz PCMU
    reconstructed_pcmu = bytearray()
    # Feed in 20ms chunks (480 samples * 2 bytes = 960 bytes)
    for offset in range(0, len(resampled_pcm_24k), 960):
        chunk = resampled_pcm_24k[offset:offset + 960]
        if len(chunk) % 2 != 0:
            chunk = chunk[:-1]
        outbound = codec.outbound_pcm(base64.b64encode(chunk).decode("ascii"))
        reconstructed_pcmu.extend(outbound)

    # Output duration must match 1.0s (within 1 frame tolerance of 160 bytes)
    # NOT 2x, 3x, or 4x faster or slower!
    assert abs(len(reconstructed_pcmu) - 8000) <= 160
    reconstructed_duration = len(reconstructed_pcmu) / 8000.0
    assert 0.98 <= reconstructed_duration <= 1.02


@pytest.mark.asyncio
async def test_telnyx_media_pacing_drift_compensation():
    import time
    from contextlib import suppress
    socket = FakeMediaSocket()
    adapter = FakeAudioAdapter()
    auth_calls = 0

    async def validate(_event):
        return None

    async def authorize():
        nonlocal auth_calls
        auth_calls += 1

    async def execute(*_args):
        return {"status": "success", "answer": "ok"}

    bridge = TelnyxMediaBridge(socket, adapter, locale="fr", validate_start=validate, authorize=authorize, execute_turn=execute)
    bridge.stream_id = "test-stream"

    # Enqueue 5 frames of 160 bytes (100ms total audio)
    for _ in range(5):
        await bridge._output.put((0, b"\xff" * 160))

    write_task = asyncio.create_task(bridge._write_audio())
    t0 = time.monotonic()
    await eventually(lambda: len(socket.sent) == 5)
    elapsed = time.monotonic() - t0
    write_task.cancel()
    with suppress(asyncio.CancelledError):
        await write_task

    # 5 frames with 20ms spacing should take approximately 0.08 - 0.15s, NOT instantaneous and NOT 1.0s
    assert 0.06 <= elapsed <= 0.35
    # Crucially, authorize() was NOT called in the 50Hz audio write loop!
    assert auth_calls == 0


def test_public_inbound_greeting_is_conversational_and_concise(authorized_media_call):
    env = authorized_media_call
    env.settings.telnyx_media_inbound_enabled = True
    env.db.commit()
    conversation = PublicInboundConversation(env.db, env.settings, env.call.id)
    greeting = conversation.greeting()
    # Greeting is short, polite and conversational
    assert env.config.business_name in greeting
    assert greeting == f"Bonjour, vous êtes bien chez {env.config.business_name}. Comment puis-je vous aider ?"
    assert "Pour une demande de rendez-vous" not in greeting
    assert "Cet appel peut être enregistré" not in greeting


def test_public_inbound_general_greetings_do_not_recite_ivr_menu(authorized_media_call):
    env = authorized_media_call
    env.settings.telnyx_media_inbound_enabled = True
    env.db.commit()
    conversation = PublicInboundConversation(env.db, env.settings, env.call.id)
    for hello in ("Bonjour", "Allô", "bon matin", "Salut"):
        result = conversation.public_answer(hello)
        assert result["public"] is True
        assert "Bonjour ! Comment puis-je vous aider aujourd'hui ?" in result["answer"]
        assert "Pour une demande de rendez-vous" not in result["answer"]


def test_public_inbound_natural_conversational_utterances(authorized_media_call):
    env = authorized_media_call
    env.settings.telnyx_media_inbound_enabled = True
    env.db.commit()
    conversation = PublicInboundConversation(env.db, env.settings, env.call.id)

    # 1. "Allô"
    ans1 = conversation.public_answer("Allô")
    assert ans1["public"] is True and not ans1.get("auth_required")
    assert "Comment puis-je vous aider" in ans1["answer"]

    # 2. "Bonjour"
    ans2 = conversation.public_answer("Bonjour")
    assert ans2["public"] is True and not ans2.get("auth_required")
    assert "Comment puis-je vous aider" in ans2["answer"]

    # 3. Question libre
    ans3 = conversation.public_answer("Est-ce que vous faites des livraisons dans le quartier ?")
    assert ans3["public"] is True and not ans3.get("auth_required")
    assert len(ans3["answer"]) > 10

    # 4. Demande de rendez-vous / disponibilité
    ans4 = conversation.public_answer("J'aimerais prendre un rendez-vous")
    assert ans4["public"] is True and not ans4.get("auth_required")
    assert "rendez-vous" in ans4["answer"]

    ans4b = conversation.public_answer("Avez-vous une disponibilité demain ?")
    assert ans4b["public"] is True and not ans4b.get("auth_required")
    assert "rendez-vous" in ans4b["answer"]

    # 5. Question Retail (commande / stock / produit)
    ans5 = conversation.public_answer("Je voudrais savoir où est ma commande")
    assert ans5["public"] is True and not ans5.get("auth_required")
    assert "commandes" in ans5["answer"] or "renseigner" in ans5["answer"]

    ans5b = conversation.public_answer("Est-ce que ce produit est encore en stock ?")
    assert ans5b["public"] is True and not ans5b.get("auth_required")
    assert "produits" in ans5b["answer"] or "inventaire" in ans5b["answer"]

    # Horaires et parler à quelqu'un
    ans_hours = conversation.public_answer("Quels sont vos horaires ?")
    assert ans_hours["public"] is True and not ans_hours.get("auth_required")
    assert "heures" in ans_hours["answer"] or "horaires" in ans_hours["answer"]

    ans_rep = conversation.public_answer("Je voudrais parler à quelqu'un")
    assert ans_rep["public"] is True and not ans_rep.get("auth_required")
    assert "message" in ans_rep["answer"] or "renseigner" in ans_rep["answer"]

    # 6. Phrase longue
    long_phrase = (
        "Bonjour madame, je vous appelle parce que j'ai vu votre vitrine hier et j'aimerais savoir "
        "si vous avez des créneaux disponibles pour une consultation cette semaine ou la semaine prochaine."
    )
    ans6 = conversation.public_answer(long_phrase)
    assert ans6["public"] is True and not ans6.get("auth_required")
    assert len(ans6["answer"]) > 10


@pytest.mark.asyncio
async def test_multi_turn_conversation_and_interruption_barge_in():
    from contextlib import suppress
    from backend.app.voice.adapters import OpenAIRealtimeAudioAdapter, OpenAIAudioConfig

    socket = FakeMediaSocket()
    adapter = FakeAudioAdapter()
    turn_answers = []

    async def validate(_event):
        return None

    async def authorize():
        return None

    async def execute(item_id, transcript):
        turn_answers.append((item_id, transcript))
        return {"status": "success", "answer": f"Reponse a: {transcript}"}

    bridge = TelnyxMediaBridge(socket, adapter, locale="fr", validate_start=validate, authorize=authorize, execute_turn=execute)
    bridge.stream_id = "test-stream"

    # Start turn execution task
    turns_task = asyncio.create_task(bridge._execute_turns())

    try:
        # TURN 1: User says "Allô"
        await bridge._turns.put(("turn-1", "Allô", bridge.epoch))
        await eventually(lambda: len(turn_answers) == 1)
        assert turn_answers[0] == ("turn-1", "Allô")
        await eventually(lambda: len(adapter.spoken) == 1)
        assert "Reponse a: Allô" in adapter.spoken[0]

        # TURN 2: Multi-turn continuation - user says "J'aimerais prendre un rendez-vous"
        await bridge._turns.put(("turn-2", "J'aimerais prendre un rendez-vous", bridge.epoch))
        await eventually(lambda: len(turn_answers) == 2)
        assert turn_answers[1] == ("turn-2", "J'aimerais prendre un rendez-vous")
        await eventually(lambda: len(adapter.spoken) == 2)
        assert "Reponse a: J'aimerais prendre un rendez-vous" in adapter.spoken[1]

        # 7. INTERRUPTION / BARGE-IN: User interrupts while assistant is speaking
        initial_epoch = bridge.epoch
        await bridge.interrupt()
        assert bridge.epoch == initial_epoch + 1
        assert adapter.interruptions >= 1
        assert any(ev.get("event") == "clear" for ev in socket.sent)

        # TURN 3: After interruption, user speaks a third turn
        await bridge._turns.put(("turn-3", "Est-ce que ce produit est en stock ?", bridge.epoch))
        await eventually(lambda: len(turn_answers) == 3)
        assert turn_answers[2] == ("turn-3", "Est-ce que ce produit est en stock ?")
        await eventually(lambda: len(adapter.spoken) == 3)
        assert "Reponse a: Est-ce que ce produit est en stock ?" in adapter.spoken[2]

    finally:
        turns_task.cancel()
        with suppress(asyncio.CancelledError):
            await turns_task


@pytest.mark.asyncio
async def test_openai_realtime_adapter_schema_for_gpt_realtime_2_1():
    from backend.app.voice.adapters import OpenAIRealtimeAudioAdapter, OpenAIAudioConfig

    class FakeConnection:
        def __init__(self):
            self.sent = []
        async def send(self, payload):
            self.sent.append(payload)

    class FakeManager:
        def __init__(self, conn):
            self.conn = conn
        async def __aenter__(self):
            return self.conn
        async def __aexit__(self, *args):
            return None

    adapter = OpenAIRealtimeAudioAdapter(
        OpenAIAudioConfig(api_key="sk-test", stt_model="gpt-4o-mini-transcribe", tts_model="gpt-4o-mini-tts", tts_voice="marin"),
        realtime_model="gpt-realtime-2.1"
    )
    fake_conn = FakeConnection()
    adapter._manager = cast(Any, FakeManager(fake_conn))
    adapter._connection = cast(Any, fake_conn)

    # Check open payload
    is_preview = "preview" in (adapter._model or "").lower()
    assert is_preview is False
    # Manually test the schema structure built by open()
    payload = {
        "type": "realtime",
        "instructions": "test",
        "output_modalities": ["audio"],
        "audio": {
            "input": {
                "format": {"type": "audio/pcm", "rate": 24000},
                "transcription": {"model": "gpt-4o-mini-transcribe"},
                "turn_detection": {
                    "type": "server_vad",
                    "create_response": False,
                    "interrupt_response": False,
                },
            },
            "output": {
                "format": {"type": "audio/pcm", "rate": 24000},
                "voice": "marin",
            },
        },
        "tools": [],
    }
    assert "modalities" not in payload
    assert payload["audio"]["input"]["transcription"]["model"] == "gpt-4o-mini-transcribe"
    assert payload["audio"]["input"]["turn_detection"]["type"] == "server_vad"


@pytest.mark.asyncio
async def test_realistic_end_to_end_pcmu_frames_multi_turn_and_benign_cancel_errors():
    import audioop

    socket = FakeMediaSocket()

    class RealisticAdapter:
        def __init__(self):
            self.opened = False
            self.incoming = asyncio.Queue()
            self.received_audio_bytes = 0
            self.spoken_texts = []
            self.cancelled = 0

        async def open(self, locale="fr"):
            self.opened = True
            await self.incoming.put(SimpleNamespace(type="session.updated"))

        async def send_audio(self, pcm: bytes):
            self.received_audio_bytes += len(pcm)

        async def speak(self, text: str):
            self.spoken_texts.append(text)
            resp_id = f"resp-{len(self.spoken_texts)}"
            # Emit standard Realtime response events
            await self.incoming.put(SimpleNamespace(type="response.created", response=SimpleNamespace(id=resp_id)))
            # 24kHz PCM chunk
            fake_24k_pcm = b"\x01\x02" * 480
            delta_b64 = base64.b64encode(fake_24k_pcm).decode("ascii")
            await self.incoming.put(SimpleNamespace(type="response.output_audio.delta", response_id=resp_id, delta=delta_b64))
            await self.incoming.put(SimpleNamespace(type="response.done", response=SimpleNamespace(id=resp_id)))

        async def interrupt(self):
            self.cancelled += 1
            # Simulate OpenAI returning benign response_cancel_not_active error
            await self.incoming.put(SimpleNamespace(
                type="error",
                error=SimpleNamespace(
                    code="response_cancel_not_active",
                    message="Cancellation failed: no active response found"
                )
            ))

        async def clear_input(self):
            pass

        async def close(self):
            self.opened = False

        async def events(self):
            while True:
                item = await self.incoming.get()
                if item is None:
                    break
                yield item

    adapter = RealisticAdapter()
    turn_transcripts = []

    async def validate(_event):
        return None

    async def authorize():
        return None

    async def execute(item_id, transcript):
        turn_transcripts.append(transcript)
        return {"status": "success", "answer": f"Reponse pour: {transcript}"}

    bridge = TelnyxMediaBridge(
        socket, adapter, locale="fr",
        validate_start=validate, authorize=authorize, execute_turn=execute,
        initial_answer="Bonjour et bienvenue chez Avenqo."
    )

    # 1. Send start event
    await socket.incoming.put({
        "event": "start",
        "stream_id": "stream-e2e-test",
        "start": {
            "media_format": {"encoding": "PCMU", "sample_rate": 8000, "channels": 1},
            "call_control_id": "cc-e2e",
            "to": "+14386075438",
            "client_state": "valid-state",
        }
    })

    running = asyncio.create_task(bridge.run())
    await eventually(lambda: adapter.opened)
    await eventually(lambda: len(adapter.spoken_texts) >= 1)
    assert adapter.spoken_texts[0] == "Bonjour et bienvenue chez Avenqo."
    assert bridge.telemetry["media_connected"] is True

    # 2. TURN 1: Caller sends realistic G.711u audio frames
    pcm_20ms = b"\x20\x10" * 160
    ulaw_20ms = audioop.lin2ulaw(pcm_20ms, 2)
    for i in range(1, 4):
        await socket.incoming.put({
            "event": "media",
            "stream_id": "stream-e2e-test",
            "media": {
                "track": "inbound",
                "chunk": str(i),
                "payload": base64.b64encode(ulaw_20ms).decode("ascii"),
            }
        })

    # Simulate VAD & transcription for Turn 1
    await adapter.incoming.put(SimpleNamespace(type="input_audio_buffer.speech_started"))
    await adapter.incoming.put(SimpleNamespace(type="input_audio_buffer.speech_stopped"))
    await adapter.incoming.put(SimpleNamespace(
        type="conversation.item.input_audio_transcription.completed",
        item_id="item-turn-1",
        transcript="Allô bonjour"
    ))

    await eventually(lambda: len(turn_transcripts) == 1)
    assert turn_transcripts[0] == "Allô bonjour"
    await eventually(lambda: len(adapter.spoken_texts) == 2)
    assert "Reponse pour: Allô bonjour" in adapter.spoken_texts[1]
    assert bridge.telemetry["speech_detected"] is True
    assert bridge.telemetry["transcription_received"] is True

    # 3. TURN 2: Caller asks for appointment
    for i in range(4, 7):
        await socket.incoming.put({
            "event": "media",
            "stream_id": "stream-e2e-test",
            "media": {
                "track": "inbound",
                "chunk": str(i),
                "payload": base64.b64encode(ulaw_20ms).decode("ascii"),
            }
        })
    await adapter.incoming.put(SimpleNamespace(type="input_audio_buffer.speech_started"))
    await adapter.incoming.put(SimpleNamespace(type="input_audio_buffer.speech_stopped"))
    await adapter.incoming.put(SimpleNamespace(
        type="conversation.item.input_audio_transcription.completed",
        item_id="item-turn-2",
        transcript="J'aimerais prendre un rendez-vous"
    ))

    await eventually(lambda: len(turn_transcripts) == 2)
    assert turn_transcripts[1] == "J'aimerais prendre un rendez-vous"
    await eventually(lambda: len(adapter.spoken_texts) == 3)
    assert "Reponse pour: J'aimerais prendre un rendez-vous" in adapter.spoken_texts[2]

    # 4. TURN 3: Caller asks retail question
    for i in range(7, 10):
        await socket.incoming.put({
            "event": "media",
            "stream_id": "stream-e2e-test",
            "media": {
                "track": "inbound",
                "chunk": str(i),
                "payload": base64.b64encode(ulaw_20ms).decode("ascii"),
            }
        })
    await adapter.incoming.put(SimpleNamespace(type="input_audio_buffer.speech_started"))
    await adapter.incoming.put(SimpleNamespace(type="input_audio_buffer.speech_stopped"))
    await adapter.incoming.put(SimpleNamespace(
        type="conversation.item.input_audio_transcription.completed",
        item_id="item-turn-3",
        transcript="Est-ce que vous avez ce produit en stock ?"
    ))

    await eventually(lambda: len(turn_transcripts) == 3)
    assert turn_transcripts[2] == "Est-ce que vous avez ce produit en stock ?"
    await eventually(lambda: len(adapter.spoken_texts) == 4)
    assert "Reponse pour: Est-ce que vous avez ce produit en stock ?" in adapter.spoken_texts[3]

    # Verify outbound audio was generated and transmitted to socket
    assert any(m.get("event") == "media" for m in socket.sent)
    assert bridge.telemetry["outbound_frames"] > 0
    assert bridge.telemetry["central_ai_called"] is True
    assert bridge.telemetry["final_state"] == "LISTENING"

    # Stop session cleanly
    await socket.incoming.put({"event": "stop", "stream_id": "stream-e2e-test"})
    await running


@pytest.mark.asyncio
async def test_public_caller_natural_multi_turn_crm_appointment_preserves_conversation_context(authorized_media_call, monkeypatch):
    """Verifies that an unauthenticated public caller can have a natural 5-turn conversation

    (greeting, appointment request, time selection, confirmation, business follow-up question)
    where Central AI is called for each turn, the same conversation context is preserved,
    and no repetitive fallback phrases are emitted.
    """
    from backend.app.routers.voice import router

    env = authorized_media_call
    env.settings.telnyx_media_inbound_enabled = True
    env.settings.voice_realtime_supported_locales = ["fr"]
    env.settings.openai_api_key = "fake-key"
    env.call.caller_type = "UNKNOWN"
    env.call.authenticated_user_id = None
    env.auth.revoked_at = datetime.now(timezone.utc)
    env.db.commit()

    captured_turns = []
    captured_conversations = []
    turn_queue = asyncio.Queue()

    for phrase in [
        "Bonjour",
        "Je voudrais prendre un rendez-vous",
        "Demain vers 14 heures",
        "Oui, ça me convient",
        "Quels sont vos horaires d'ouverture ?",
    ]:
        await turn_queue.put(phrase)

    class MultiTurnLoopbackAdapter(FakeAudioAdapter):
        def __init__(self):
            super().__init__()
            self.turn_count = 0

        async def send_audio(self, audio):
            await super().send_audio(audio)
            if not turn_queue.empty():
                self.turn_count += 1
                text = await turn_queue.get()
                await self.incoming.put(SimpleNamespace(
                    type="conversation.item.input_audio_transcription.completed",
                    item_id=f"turn-{self.turn_count}",
                    event_id=f"evt-{self.turn_count}",
                    transcript=text,
                    usage=None,
                ))

        async def speak(self, text):
            await super().speak(text)
            resp_id = f"resp-{len(self.spoken)}"
            await self.incoming.put(SimpleNamespace(type="response.created", response=SimpleNamespace(id=resp_id)))
            await self.incoming.put(SimpleNamespace(
                type="response.output_audio.delta",
                response_id=resp_id,
                delta=base64.b64encode(b"\x00\x00" * 480).decode(),
            ))
            await self.incoming.put(SimpleNamespace(
                type="response.done",
                event_id=f"done-{resp_id}",
                response=SimpleNamespace(id=resp_id, status="completed", usage=SimpleNamespace(input_tokens=10, output_tokens=10)),
            ))

    class MockCentralAI:
        def __init__(self):
            self.usage_service = FakeUsageService()

        async def execute(self, *args, **kwargs):
            tenant = args[0]
            user_id = args[1]
            conversation_id = args[2]
            transcript = args[3]
            captured_turns.append(transcript)
            captured_conversations.append(conversation_id)
            if "bonjour" in transcript.lower():
                ans = "Bonjour ! Comment puis-je vous aider aujourd'hui ?"
            elif "rendez-vous" in transcript.lower():
                ans = "Certainement. Pour quel jour et quelle heure souhaitez-vous votre rendez-vous ?"
            elif "14 heures" in transcript.lower():
                ans = "J'ai bien une disponibilité demain à 14h00. Est-ce que ce créneau vous convient ?"
            elif "convient" in transcript.lower():
                ans = "Parfait, votre rendez-vous est confirmé pour demain à 14h00. Avez-vous une autre question ?"
            elif "horaires" in transcript.lower():
                ans = "Nous sommes ouverts du lundi au vendredi de 9h à 18h."
            else:
                ans = "Je suis à votre écoute."
            return SimpleNamespace(status="success", answer=ans, selected_agent="crm")

    adapter = MultiTurnLoopbackAdapter()
    central = MockCentralAI()

    monkeypatch.setattr(media_module, "OpenAIRealtimeAudioAdapter", lambda *_args: adapter)
    monkeypatch.setattr(media_module, "resolve_tenant_capabilities", lambda *_args: frozenset({"crm:read", "crm:write"}))

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: env.db
    app.dependency_overrides[get_settings] = lambda: env.settings
    app.dependency_overrides[get_central_ai_service] = lambda: central
    app.dependency_overrides[get_prediction_service] = lambda: object()

    state = issue_media_client_state(env.db, env.settings, env.call.id, public_mode=True)
    start_payload = {
        "event": "start",
        "stream_id": "stream-public-multi",
        "start": {
            "media_format": {"encoding": "PCMU", "sample_rate": 8000, "channels": 1},
            "call_control_id": env.call.telnyx_call_control_id,
            "to": env.config.telnyx_phone_number,
            "client_state": state,
        },
    }

    with TestClient(app) as client:
        with client.websocket_connect(f"/api/v1/voice/telnyx/media/{env.call.id}") as socket:
            socket.send_json(start_payload)

            # Send audio frames for 5 turns and receive responses
            for i in range(1, 6):
                socket.send_json({
                    "event": "media",
                    "stream_id": "stream-public-multi",
                    "media": {
                        "track": "inbound",
                        "chunk": str(i),
                        "payload": base64.b64encode(b"\xff" * 160).decode(),
                    },
                })
                # Receive outbound audio response frame
                resp = socket.receive_json()
                assert resp.get("event") == "media"

            socket.send_json({"event": "stop", "stream_id": "stream-public-multi"})
            try:
                for _ in range(10):
                    socket.receive_json()
            except (WebSocketDisconnect, Exception):
                pass

    # Verify all 5 conversational turns were executed by Central AI
    assert len(captured_turns) == 5
    assert captured_turns[0] == "Bonjour"
    assert captured_turns[1] == "Je voudrais prendre un rendez-vous"
    assert captured_turns[2] == "Demain vers 14 heures"
    assert captured_turns[3] == "Oui, ça me convient"
    assert captured_turns[4] == "Quels sont vos horaires d'ouverture ?"

    # Verify that conversation_id is persistent across all 5 turns
    assert len(captured_conversations) == 5
    first_conv_id = captured_conversations[0]
    assert first_conv_id is not None
    assert all(c_id == first_conv_id for c_id in captured_conversations)

    # Verify spoken responses are natural and follow the dialogue context (initial greeting + 5 turns)
    assert len(adapter.spoken) == 6
    assert "Voice Test Shop" in adapter.spoken[0]
    assert "Comment puis-je vous aider" in adapter.spoken[1]
    assert "rendez-vous" in adapter.spoken[2]
    assert "14h00" in adapter.spoken[3]
    assert "confirmé" in adapter.spoken[4]
    assert "ouverts" in adapter.spoken[5]

    # Verify that the conversation was created in DB and associated with the call
    env.db.expire_all()
    updated_call = env.db.get(VoiceCall, env.call.id)
    assert updated_call.central_conversation_id == first_conv_id


@pytest.mark.asyncio
async def test_telnyx_media_output_queue_buffers_large_tts_burst_without_dropping_frames():
    """Regression Call #6: Large TTS bursts must not overflow the output queue and drop frames."""
    socket = FakeMediaSocket()
    adapter = FakeAudioAdapter()

    async def _noop(*_args, **_kwargs) -> None:
        return None

    async def _noop_turn(_item_id: str, _transcript: str) -> dict[str, Any]:
        return {}

    bridge = TelnyxMediaBridge(
        socket, adapter, locale="fr",
        validate_start=_noop, authorize=_noop, execute_turn=_noop_turn,
        max_output_queue=2000
    )

    # Enqueue a burst of 500 frames (10 seconds of 20ms audio = 80,000 bytes)
    burst = b"\x80" * (160 * 500)
    bridge._enqueue(burst, final=True)

    assert bridge.dropped_outbound_frames == 0
    assert bridge._output.qsize() == 500


def test_clean_voice_text_strips_markdown_lists_and_formatting():
    """Regression Call #6: Spoken voice answers must not contain markdown bullets, numbers or formatting."""
    from backend.app.voice.telnyx_media import clean_voice_text

    raw_markdown = (
        "Pour prendre un rendez-vous, pourriez-vous me fournir les détails suivants :\n"
        "1. Le nom du client ou de la personne pour qui le rendez-vous est pris.\n"
        "2. L'adresse courriel du client (si connue).\n"
        "3. La date et l'heure souhaitées pour le rendez-vous.\n"
        "4. La durée du rendez-vous (en minutes).\n"
        "5. Le motif du rendez-vous.\n"
        "Une fois que j'aurai ces informations, je pourrai vérifier la disponibilité."
    )
    cleaned = clean_voice_text(raw_markdown)
    assert "1." not in cleaned
    assert "2." not in cleaned
    assert "3." not in cleaned
    assert "4." not in cleaned
    assert "5." not in cleaned
    assert "\n" not in cleaned
    assert cleaned.startswith("Pour prendre un rendez-vous, pourriez-vous me fournir les détails suivants : Le nom du client")

    # Verify bold, italic, headers, bullets
    complex_markdown = "### Bonjour !\n- **Option A** : Consultation\n* _Option B_ : Suivi"
    cleaned_complex = clean_voice_text(complex_markdown)
    assert "#" not in cleaned_complex
    assert "*" not in cleaned_complex
    assert "_" not in cleaned_complex
    assert not re.search(r"^\s*-\s+", cleaned_complex)
    assert "Bonjour ! Option A : Consultation Option B : Suivi" == cleaned_complex


@pytest.mark.asyncio
async def test_public_caller_does_not_have_data_read_permission(authorized_media_call, monkeypatch):
    """Security audit Call #6: Public unauthenticated callers must NOT receive data:read permission."""
    env = authorized_media_call
    env.settings.telnyx_media_inbound_enabled = True
    env.call.caller_type = "UNKNOWN"
    env.call.authenticated_user_id = None
    env.auth.revoked_at = datetime.now(timezone.utc)
    env.db.commit()

    # Verify owner membership resolution for unauthenticated caller
    owner_membership = env.db.scalar(
        select(CompanyMembership)
        .where(CompanyMembership.company_id == env.company.id, CompanyMembership.is_active.is_(True))
    )
    assert owner_membership is not None
    # In telnyx_media.py, public caller permissions are restricted strictly to ai:use and crm:appointments:write
    public_permissions = frozenset({"ai:use", "crm:appointments:write"})
    assert "data:read" not in public_permissions
    assert "data:manage" not in public_permissions
    assert "billing:manage" not in public_permissions
    assert "users:manage" not in public_permissions


@pytest.mark.asyncio
async def test_public_caller_natural_10_turn_canadian_french_conversation(authorized_media_call, monkeypatch):
    """Full 10-turn Canadian French phone call regression test covering:
    1. Greeting
    2. Appointment request
    3. Day preference
    4. Time preference
    5. Client name
    6. Client email
    7. Confirmation
    8. Opening hours question
    9. Location / services question
    10. Polite wrap-up
    Verifies multi-turn continuity, zero dropped frames, no markdown in TTS, and Central AI dispatch.
    """
    from backend.app.routers.voice import router

    env = authorized_media_call
    env.settings.telnyx_media_inbound_enabled = True
    env.settings.voice_realtime_supported_locales = ["fr"]
    env.settings.openai_api_key = "fake-key"
    env.call.caller_type = "UNKNOWN"
    env.call.authenticated_user_id = None
    env.auth.revoked_at = datetime.now(timezone.utc)
    env.db.commit()

    ten_turn_phrases = [
        "Allô bonjour !",
        "J'aimerais prendre un rendez-vous pour un service s'il vous plaît.",
        "Est-ce que vous avez de la place demain après-midi ?",
        "Vers 14 heures, est-ce que c'est libre ?",
        "Mon nom est Paul Morin.",
        "Mon adresse courriel est paul.morin@example.com.",
        "Oui parfait, confirmez le rendez-vous pour demain 14 heures.",
        "Quelles sont vos heures d'ouverture cette semaine ?",
        "Quels sont les tarifs de vos services ?",
        "Merci beaucoup pour votre aide, bonne journée !",
    ]

    captured_turns = []
    captured_conversations = []
    turn_queue = asyncio.Queue()

    for phrase in ten_turn_phrases:
        await turn_queue.put(phrase)

    class MultiTurn10LoopbackAdapter(FakeAudioAdapter):
        def __init__(self):
            super().__init__()
            self.turn_count = 0

        async def send_audio(self, audio):
            await super().send_audio(audio)
            if not turn_queue.empty():
                self.turn_count += 1
                text = await turn_queue.get()
                await self.incoming.put(SimpleNamespace(
                    type="conversation.item.input_audio_transcription.completed",
                    item_id=f"turn-{self.turn_count}",
                    event_id=f"evt-{self.turn_count}",
                    transcript=text,
                    usage=None,
                ))

        async def speak(self, text):
            await super().speak(text)
            resp_id = f"resp-{len(self.spoken)}"
            await self.incoming.put(SimpleNamespace(type="response.created", response=SimpleNamespace(id=resp_id)))
            await self.incoming.put(SimpleNamespace(
                type="response.output_audio.delta",
                response_id=resp_id,
                delta=base64.b64encode(b"\x00\x00" * 480).decode(),
            ))
            await self.incoming.put(SimpleNamespace(
                type="response.done",
                event_id=f"done-{resp_id}",
                response=SimpleNamespace(id=resp_id, status="completed", usage=SimpleNamespace(input_tokens=10, output_tokens=10)),
            ))

    class MockCentral10AI:
        def __init__(self):
            self.usage_service = FakeUsageService()

        async def execute(self, *args, **kwargs):
            conv_id = args[2]
            transcript = args[3]
            captured_turns.append(transcript)
            captured_conversations.append(conv_id)
            if "allô bonjour" in transcript.lower():
                ans = "Bonjour ! Comment puis-je vous aider aujourd'hui ?"
            elif "prendre un rendez-vous" in transcript.lower():
                ans = "Avec plaisir ! Quel jour vous conviendrait le mieux ?"
            elif "demain après-midi" in transcript.lower():
                ans = "Parfait pour demain après-midi. Quelle heure préféreriez-vous ?"
            elif "14 heures" in transcript.lower():
                ans = "Le créneau de 14 heures est disponible. Quel est votre nom ?"
            elif "paul morin" in transcript.lower():
                ans = "Enchanté monsieur Morin. Pourriez-vous me préciser votre adresse courriel ?"
            elif "paul.morin@example.com" in transcript.lower():
                ans = "Merci ! Souhaitez-vous que je confirme ce rendez-vous pour demain à 14 heures ?"
            elif "confirmez" in transcript.lower():
                ans = "C'est confirmé pour demain à 14 heures. Avez-vous une autre question ?"
            elif "heures d'ouverture" in transcript.lower():
                ans = "Nous sommes ouverts du lundi au vendredi, de 9h à 17h."
            elif "tarifs" in transcript.lower():
                ans = "Nos consultations débutent à 50 dollars."
            else:
                ans = "Merci beaucoup de votre appel monsieur Morin, excellente journée à vous aussi !"
            return SimpleNamespace(status="success", answer=ans, selected_agent="crm")

    adapter = MultiTurn10LoopbackAdapter()
    central = MockCentral10AI()

    monkeypatch.setattr(media_module, "OpenAIRealtimeAudioAdapter", lambda *_args: adapter)
    monkeypatch.setattr(media_module, "resolve_tenant_capabilities", lambda *_args: frozenset({"crm:read", "crm:write"}))

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: env.db
    app.dependency_overrides[get_settings] = lambda: env.settings
    app.dependency_overrides[get_central_ai_service] = lambda: central
    app.dependency_overrides[get_prediction_service] = lambda: object()

    state = issue_media_client_state(env.db, env.settings, env.call.id, public_mode=True)
    start_payload = {
        "event": "start",
        "stream_id": "stream-public-10turn",
        "start": {
            "media_format": {"encoding": "PCMU", "sample_rate": 8000, "channels": 1},
            "call_control_id": env.call.telnyx_call_control_id,
            "to": env.config.telnyx_phone_number,
            "client_state": state,
        },
    }

    with TestClient(app) as client:
        with client.websocket_connect(f"/api/v1/voice/telnyx/media/{env.call.id}") as socket:
            socket.send_json(start_payload)

            # Send audio frames for 10 turns and receive responses
            for i in range(1, 11):
                socket.send_json({
                    "event": "media",
                    "stream_id": "stream-public-10turn",
                    "media": {
                        "track": "inbound",
                        "chunk": str(i),
                        "payload": base64.b64encode(b"\xff" * 160).decode(),
                    },
                })
                resp = socket.receive_json()
                assert resp.get("event") == "media"

            socket.send_json({"event": "stop", "stream_id": "stream-public-10turn"})
            with pytest.raises(WebSocketDisconnect):
                while True:
                    socket.receive_json()

    # Verify all 10 conversational turns were executed
    assert len(captured_turns) == 10
    assert captured_turns == ten_turn_phrases

    # Verify conversation continuity: all 10 turns belong to the exact same conversation
    assert len(captured_conversations) == 10
    first_conv = captured_conversations[0]
    assert all(c == first_conv for c in captured_conversations)

    # Verify 1 initial greeting + 10 turn responses = 11 spoken utterances
    assert len(adapter.spoken) == 11
    for spoken_phrase in adapter.spoken:
        # None of the spoken phrases must contain markdown formatting
        assert "*" not in spoken_phrase
        assert "#" not in spoken_phrase
        assert not re.search(r"^\s*-\s+", spoken_phrase)
        assert not re.search(r"^\s*\d+\.\s*", spoken_phrase)



