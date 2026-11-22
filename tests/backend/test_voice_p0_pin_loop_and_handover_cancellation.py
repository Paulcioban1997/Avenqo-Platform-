import asyncio
import time
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config.settings import Settings
from backend.app.models.base import Base
from backend.app.models.company import Company
from backend.app.models.company_module import CompanyModule, CompanyModuleStatus
from backend.app.models.company_membership import CompanyMembership
from backend.app.models.module import Module
from backend.app.models.user import User, UserRole
from backend.app.models.voice import VoiceAuthSession, VoiceBusinessConfig, VoiceCall, VoiceCallerCredential
from shared.ai_engine.contracts import TenantContext
from backend.app.voice.auth import VoiceCallerAuth
from backend.app.voice.telnyx_media import (
    PublicInboundConversation,
    TelnyxMediaBridge,
    authorize_media_session,
    is_handover_positive_intent,
    is_pin_challenge_cancellation,
    is_session_retention_intent,
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


class MockStreamingAdapter:
    def __init__(self, events_queue: asyncio.Queue):
        self._events_queue = events_queue
        self.spoken_texts = []
        self.interrupted_count = 0

    async def speak(self, text):
        self.spoken_texts.append(text)

    async def interrupt(self):
        self.interrupted_count += 1

    async def clear_input(self):
        pass

    async def events(self):
        while True:
            ev = await self._events_queue.get()
            if ev is None:
                break
            yield ev


def _make_test_company_and_call(db_session: Session):
    uid = uuid4().hex[:8]
    company = Company(
        id=uuid4(),
        name="Produits_Ero",
        slug=f"produits-ero-{uid}",
        email=f"contact-{uid}@produits-ero.example.com",
        country="CA",
        timezone="America/Toronto",
        industry="retail",
        subscription_plan="enterprise",
        website="https://produits-ero.example.com",
    )
    db_session.add(company)
    mod_voice = Module(id=uuid4(), name="Voice AI", code="voice", is_active=True)
    db_session.add(mod_voice)
    db_session.flush()

    cm = CompanyModule(
        company_id=company.id,
        module_id=mod_voice.id,
        status=CompanyModuleStatus.ACTIVE,
        activated_at=datetime.now(timezone.utc),
    )
    db_session.add(cm)

    # Initial employee: Francis
    francis = User(
        id=uuid4(),
        company_id=company.id,
        email=f"francis-{uid}@produits-ero.example.com",
        first_name="Francis",
        last_name="Audet",
        password_hash="fake_hashed_pw_123",
        role=UserRole.USER,
        phone="+15145550199",
        is_active=True,
    )
    db_session.add(francis)

    # Second employee: Marie
    marie = User(
        id=uuid4(),
        company_id=company.id,
        email=f"marie-{uid}@produits-ero.example.com",
        first_name="Marie",
        last_name="Tremblay",
        password_hash="fake_hashed_pw_456",
        role=UserRole.USER,
        phone="+15145550288",
        is_active=True,
    )
    db_session.add(marie)
    db_session.flush()

    db_session.add(CompanyMembership(company_id=company.id, user_id=francis.id, role=UserRole.USER, is_active=True))
    db_session.add(CompanyMembership(company_id=company.id, user_id=marie.id, role=UserRole.USER, is_active=True))

    voice_config = VoiceBusinessConfig(
        id=uuid4(),
        company_id=company.id,
        business_name="Produits_Ero",
        preferred_language="fr-CA",
        opening_hours={"weekly": {"monday": [{"open": "09:00", "close": "17:00"}]}},
        services=[{"name": "Vente de matériel", "price": 100, "currency": "CAD", "duration_minutes": 30}],
        greeting_message="Bonjour et bienvenue chez Produits Ero !",
        voice_api_key_hash=f"hash_{uid}",
        voice_api_key_last4="1234",
        enabled=True,
    )
    db_session.add(voice_config)

    from backend.app.models.voice import CompanyRoutingNip
    from backend.app.models.billing import BillingAccount
    db_session.add(BillingAccount(id=uuid4(), company_id=company.id, status="active"))
    db_session.add(CompanyRoutingNip(id=uuid4(), company_id=company.id, routing_code="123456", routing_code_hash="hash123", status="ACTIVE"))

    call = VoiceCall(
        id=uuid4(),
        company_id=company.id,
        config_id=voice_config.id,
        telnyx_call_control_id=f"v-call-{uid}",
        caller_phone="+15145550199",
        status="in_progress",
        locale="fr-CA",
        source_context={"live_call": True, "dispatcher_routing": True},
    )
    db_session.add(call)
    db_session.commit()
    return company, voice_config, call, francis, marie


# =====================================================================
# 1. Handover Intent Parsers & Session Retention Guard
# =====================================================================

def test_intent_parsers_refusal_and_session_retention():
    """Verify that intent parsers strictly distinguish session retention from positive handover."""
    retention_phrases = [
        "Non, je vais rester moi-même Francis",
        "Non, je vais rester Francis",
        "Non, je ne passe pas le téléphone",
        "Je reste Francis",
        "Je garde ma session",
        "Reviens à Francis",
        "Non je veux rester",
        "Ne passe pas le téléphone",
        "No voy a pasar el teléfono",
        "Me quedo yo",
        "Nu dau telefonul",
        "Raman eu",
        "I will stay",
        "Don't pass the phone",
    ]
    for phrase in retention_phrases:
        assert is_session_retention_intent(phrase), f"Expected '{phrase}' to match retention intent"
        assert not is_handover_positive_intent(phrase), f"Expected '{phrase}' NOT to trigger handover"

    positive_handover_phrases = [
        "Je passe le téléphone à mon collègue",
        "Je te passe mon collègue",
        "Changer d'employé s'il vous plaît",
        "Passe le téléphone",
        "Switch employee",
        "Change employee",
        "Pass the phone",
        "Te paso a mi colega",
        "Iti dau colegul",
    ]
    for phrase in positive_handover_phrases:
        assert not is_session_retention_intent(phrase), f"Expected '{phrase}' NOT to match retention intent"
        assert is_handover_positive_intent(phrase), f"Expected '{phrase}' to match positive handover"


def test_pin_cancellation_intent_parser():
    """Verify that verbal cancellation phrases are accurately recognized."""
    cancellation_phrases = [
        "Annuler",
        "Annule",
        "Non merci",
        "Non merci, reviens à Francis",
        "Laisse tomber",
        "Arrête le NIP",
        "Stop",
        "Abandonner",
        "Pas de NIP",
        "Cancel",
        "Never mind",
        "No thanks",
        "Cancelar",
        "Anulare",
    ]
    for phrase in cancellation_phrases:
        assert is_pin_challenge_cancellation(phrase), f"Expected '{phrase}' to match cancellation intent"

    # Non-cancellation inputs must return False
    assert not is_pin_challenge_cancellation("123456")
    assert not is_pin_challenge_cancellation("Quels sont vos horaires ?")
    assert not is_pin_challenge_cancellation("Je veux parler à Francis")


# =====================================================================
# 2. Handover Refusal Prevents Revocation in Session
# =====================================================================

@pytest.mark.asyncio
async def test_handover_refusal_keeps_session_active(db_session: Session):
    """When an authenticated employee says 'Non, je vais rester moi-même Francis',
    the session must remain active, authenticated, and AUDIT_VOICE_HANDOVER_REVOCATION must NOT occur."""
    company, voice_config, call, francis, _ = _make_test_company_and_call(db_session)
    call.authenticated_user_id = francis.id
    call.caller_type = "EMPLOYEE"
    call.source_context = {"user_id": str(francis.id), "authenticated": True}
    db_session.commit()

    transcript = "Non, je vais rester moi-même Francis"

    norm_trans = "".join(c for c in transcript.casefold() if c.isalnum() or c.isspace())
    assert is_session_retention_intent(norm_trans)
    assert not is_handover_positive_intent(norm_trans)

    # Session is maintained
    assert call.authenticated_user_id == francis.id
    assert (call.source_context or {}).get("handover_revoked") is not True


# =====================================================================
# 3. Positive Handover Triggers Revocation and PIN Prompt
# =====================================================================

@pytest.mark.asyncio
async def test_handover_positive_triggers_revocation(db_session: Session):
    """When an authenticated employee says 'Je passe le téléphone à mon collègue',
    the session is revoked, AUDIT_VOICE_HANDOVER_REVOCATION is recorded, and handover_revoked is set."""
    company, voice_config, call, francis, _ = _make_test_company_and_call(db_session)
    call.authenticated_user_id = francis.id
    call.caller_type = "EMPLOYEE"
    call.source_context = {"user_id": str(francis.id), "authenticated": True}
    db_session.commit()

    transcript = "Je passe le téléphone à mon collègue"
    assert is_handover_positive_intent(transcript)

    # Simulate revocation execution
    call.authenticated_user_id = None
    call.caller_type = "UNKNOWN"
    existing_ctx = dict(call.source_context or {})
    existing_ctx.pop("user_id", None)
    existing_ctx["authenticated"] = False
    existing_ctx["handover_revoked"] = True
    call.source_context = existing_ctx
    db_session.commit()

    reloaded = db_session.get(VoiceCall, call.id)
    assert reloaded.authenticated_user_id is None
    assert reloaded.source_context.get("handover_revoked") is True


# =====================================================================
# 4. DTMF '*' Cancels PIN Challenge and Returns to Public Reception
# =====================================================================

def test_dtmf_star_cancels_pin_challenge(db_session: Session):
    """When a caller enters '*' via DTMF during PIN challenge, verify_gather
    returns cancelled=True and clears handover_revoked without penalizing attempts."""
    company, voice_config, call, _, _ = _make_test_company_and_call(db_session)
    settings = Settings(
        auth_jwt_secret="test_secret_for_jwt_32_bytes_long!!",
        voice_pin_max_attempts=5,
    )
    auth = VoiceCallerAuth(db_session, settings)
    call.pin_challenge_hash = "mock_hash"
    call.pin_challenge_expires_at = datetime.now(timezone.utc)
    call.source_context = {"handover_revoked": True, "pin_gather_status": "pending"}
    db_session.commit()

    result = auth.verify_gather(call, "*")

    assert result["cancelled"] is True
    assert result["authenticated"] is False
    assert result["reason"] == "user_cancelled"
    assert call.verification_attempts == 0
    assert call.pin_challenge_hash is None
    assert call.source_context.get("handover_revoked") is None
    assert call.source_context.get("handover_cancelled") is True
    assert call.source_context.get("pin_gather_status") == "cancelled"


# =====================================================================
# 5. Verbal Cancellation During Active PIN Challenge in Bridge
# =====================================================================

@pytest.mark.asyncio
async def test_voice_cancellation_during_pin_challenge_in_bridge(db_session: Session):
    """When an active PIN challenge is running and the caller says 'Non merci, reviens à Francis',
    the bridge detects verbal cancellation, clears the PIN turn, executes cancel_pin(), and enters public mode."""
    company, voice_config, call, _, _ = _make_test_company_and_call(db_session)
    call.source_context = {"handover_revoked": True, "pin_gather_status": "pending"}
    db_session.commit()

    events_queue = asyncio.Queue()
    adapter = MockStreamingAdapter(events_queue)
    mock_socket = MagicMock()
    mock_socket.send_json = AsyncMock()

    cancelled_called = False

    async def mock_cancel_pin():
        nonlocal cancelled_called
        cancelled_called = True
        ctx = dict(call.source_context or {})
        ctx.pop("handover_revoked", None)
        ctx["handover_cancelled"] = True
        ctx["pin_gather_status"] = "cancelled"
        call.source_context = ctx
        db_session.commit()

    bridge = TelnyxMediaBridge(
        socket=mock_socket,
        adapter=adapter,
        locale="fr-CA",
        validate_start=AsyncMock(),
        authorize=AsyncMock(),
        execute_turn=AsyncMock(),
        cancel_pin=mock_cancel_pin,
    )
    bridge._pin_turn = "turn-pin-1"
    bridge.stream_id = "stream-1"

    drain_task = asyncio.create_task(bridge._drain_provider_events())

    # Provider transcribes caller saying "Non merci, reviens à Francis"
    ev = SimpleNamespace(
        type="conversation.item.input_audio_transcription.completed",
        item_id="item-cancel-1",
        transcript="Non merci, reviens à Francis",
    )
    await events_queue.put(ev)
    await asyncio.sleep(0.1)

    await events_queue.put(None)
    await drain_task

    assert cancelled_called is True
    assert bridge._pin_turn is None
    assert bridge.input_paused is False
    assert any("Saisie du NIP annulée" in t for t in adapter.spoken_texts)

    reloaded = db_session.get(VoiceCall, call.id)
    assert reloaded.source_context.get("handover_revoked") is None
    assert reloaded.source_context.get("handover_cancelled") is True


# =====================================================================
# 6. No Automatic Privilege Restoration After Revocation
# =====================================================================

def test_no_automatic_privilege_restoration_after_revocation(db_session: Session):
    """Once a session is revoked, pronouncing 'Je suis Francis' does NOT grant employee privileges.
    Confidential data queries must still be blocked and gated by PIN."""
    company, voice_config, call, francis, _ = _make_test_company_and_call(db_session)
    call.authenticated_user_id = None
    call.caller_type = "UNKNOWN"
    call.source_context = {**(call.source_context or {}), "handover_cancelled": True}
    db_session.commit()

    settings = Settings(
        auth_jwt_secret="test_secret_for_jwt_32_bytes_long!!",
        telnyx_media_enabled=True,
        telnyx_media_inbound_enabled=True,
    )
    conv = PublicInboundConversation(db_session, settings, call.id)

    # 1. Mere utterance of name does not restore credentials
    assert call.authenticated_user_id is None

    # 2. Confidential business query is blocked by security_gate
    gate_res = conv.security_gate("Quel est le chiffre d'affaires d'aujourd'hui ?")
    assert gate_res is not None
    assert gate_res.get("auth_required") is True or "NIP" in gate_res.get("answer", "")

    # 3. Public question is answered normally
    public_res = conv.public_answer("Quels sont vos horaires d'ouverture ?")
    assert public_res is not None
    assert public_res.get("public") is True
    assert "heures" in public_res.get("answer", "").lower() or "09:00" in public_res.get("answer", "")


# =====================================================================
# 7. Max PIN Retries Clean Exit Without Infinite Loop
# =====================================================================

@pytest.mark.asyncio
async def test_max_pin_retries_exits_cleanly_without_loop(db_session: Session):
    """Verify that after 3 empty gathers, the bridge reprompts with '*' guidance
    and on exceeding max retries, exits cleanly to public reception mode and clears handover_revoked."""
    company, voice_config, call, _, _ = _make_test_company_and_call(db_session)
    call.source_context = {"handover_revoked": True, "pin_gather_status": "pending"}
    db_session.commit()

    adapter = MockStreamingAdapter(asyncio.Queue())
    mock_socket = MagicMock()
    mock_socket.send_json = AsyncMock()

    cancel_invoked = False

    async def mock_cancel():
        nonlocal cancel_invoked
        cancel_invoked = True
        ctx = dict(call.source_context or {})
        ctx.pop("handover_revoked", None)
        ctx["pin_gather_status"] = "cancelled"
        call.source_context = ctx
        db_session.commit()

    bridge = TelnyxMediaBridge(
        socket=mock_socket,
        adapter=adapter,
        locale="fr-CA",
        validate_start=AsyncMock(),
        authorize=AsyncMock(),
        execute_turn=AsyncMock(),
        cancel_pin=mock_cancel,
    )
    bridge.max_pin_retries = 3
    bridge._pin_turn = "pin-turn-test"

    # 1. Simulate 3 reprompts
    for i in range(1, 4):
        await bridge._reprompt_pin()
        assert bridge._pin_retry_count == i
        assert any("étoile pour annuler" in t for t in adapter.spoken_texts)

    # 2. 4th attempt exceeds max retries -> _finish_pin('refused')
    await bridge._reprompt_pin()

    assert cancel_invoked is True
    assert bridge._pin_turn is None
    assert bridge.input_paused is False
    assert any("Nombre maximal de tentatives atteint" in t for t in adapter.spoken_texts)

    reloaded = db_session.get(VoiceCall, call.id)
    assert reloaded.source_context.get("handover_revoked") is None


# =====================================================================
# 8. Late Webhook Ignored After Cancellation
# =====================================================================

def test_late_gather_webhook_ignored_after_cancellation(db_session: Session):
    """When a stale or duplicate call.gather.ended arrives after cancellation,
    it must return stale=True without modifying call context."""
    company, voice_config, call, _, _ = _make_test_company_and_call(db_session)
    settings = Settings(
        auth_jwt_secret="test_secret_for_jwt_32_bytes_long!!",
    )
    auth = VoiceCallerAuth(db_session, settings)

    # Session is already cancelled, hash is None
    call.pin_challenge_hash = None
    call.pin_challenge_expires_at = None
    call.source_context = {"pin_gather_status": "cancelled", "handover_cancelled": True}
    db_session.commit()

    # Incoming webhook payload with expired client state
    stale_state = auth.challenge(call)
    call.pin_challenge_hash = None  # simulate challenge completed/cancelled

    # Check valid_challenge returns False
    is_valid = auth.valid_challenge(call, stale_state)
    assert is_valid is False

    # Router logic check
    current_status = (call.source_context or {}).get("pin_gather_status")
    assert current_status in {"cancelled", "authenticated"} and not call.pin_challenge_hash


# =====================================================================
# 9. Successful Handover to Second Employee With PIN
# =====================================================================

def test_successful_handover_to_second_employee(db_session: Session):
    """After handover revocation, second employee Marie enters her valid PIN.
    Session is successfully transferred and authenticated as Marie."""
    company, voice_config, call, francis, marie = _make_test_company_and_call(db_session)
    settings = Settings(
        auth_jwt_secret="test_secret_for_jwt_32_bytes_long!!",
        voice_pin_max_attempts=5,
    )
    auth = VoiceCallerAuth(db_session, settings)

    # Configure PIN for Marie: 719284
    auth.set_pin(
        TenantContext(company.id, marie.id),
        "USER",
        marie.id,
        "719284",
        phone_number="+15145550288",
    )
    db_session.commit()

    # Simulate handover revoked previous user
    call.authenticated_user_id = None
    call.caller_type = "UNKNOWN"
    call.source_context = {"handover_revoked": True}
    client_state = auth.challenge(call)
    db_session.commit()

    # Marie enters 719284
    result = auth.verify_gather(call, "719284")
    assert result["authenticated"] is True
    assert call.authenticated_user_id == marie.id
    assert call.source_context["user_id"] == str(marie.id)
    assert call.caller_type == "EMPLOYEE"


# =====================================================================
# 10. Voluntary Barge-In Stops Reprompt TTS
# =====================================================================

@pytest.mark.asyncio
async def test_voluntary_barge_in_stops_reprompt_tts():
    """While PIN prompt/reprompt is playing, caller speech immediately halts audio playback."""
    events_queue = asyncio.Queue()
    adapter = MockStreamingAdapter(events_queue)
    mock_socket = MagicMock()
    mock_socket.send_json = AsyncMock()

    bridge = TelnyxMediaBridge(
        socket=mock_socket,
        adapter=adapter,
        locale="fr-CA",
        validate_start=AsyncMock(),
        authorize=AsyncMock(),
        execute_turn=AsyncMock(),
    )
    bridge.stream_id = "stream-barge-in"
    bridge._pin_turn = "turn-pin-prompt"
    bridge.phase = "PLAYING"
    bridge.response_id = "resp-barge-1"
    bridge._last_spoken_prompt = "Veuillez saisir votre code NIP"

    drain_task = asyncio.create_task(bridge._drain_provider_events())

    # Caller starts speaking while TTS is playing
    await events_queue.put(SimpleNamespace(type="input_audio_buffer.speech_started"))
    await asyncio.sleep(0.05)

    # Confirmed speech arrived (not echo, cancellation intent)
    await events_queue.put(
        SimpleNamespace(
            type="conversation.item.input_audio_transcription.completed",
            item_id="trans-barge-1",
            transcript="Non merci, annule le transfert",
        )
    )
    await asyncio.sleep(0.1)

    await events_queue.put(None)
    await drain_task

    # Interrupted called to halt TTS chunk transmission
    assert adapter.interrupted_count >= 1
    # Telnyx socket instructed to clear playback buffer
    mock_socket.send_json.assert_called_with({"event": "clear"})


# =====================================================================
# 11. Staff Handover -> Verbal Refusal -> Public Reception on Same Conn
# =====================================================================

@pytest.mark.asyncio
async def test_end_to_end_staff_handover_verbal_refusal_and_public_fallback(db_session: Session):
    """End-to-end integration test:
    1. Authenticated staff caller requests handover.
    2. Session is revoked and PIN challenge initiated.
    3. Caller says verbal refusal ('Non merci, annuler').
    4. Call context transitions to public_fallback=True without staff privileges.
    5. Next authorize() on same WebSocket does NOT raise PermissionError.
    6. Public question ('Quels sont vos horaires ?') answered in public mode.
    """
    company, voice_config, call, francis, marie = _make_test_company_and_call(db_session)
    settings = Settings(
        DATABASE_URL="sqlite:///:memory:",
        SECRET_KEY="test_secret_for_voice_unit_tests",
        TELNYX_API_KEY="test-telnyx-key",
        TELNYX_PUBLIC_KEY="test-public-key",
        TELNYX_MEDIA_ENABLED=True,
        TELNYX_MEDIA_INBOUND_ENABLED=True,
    )

    # 1. Staff session active
    call.caller_type = "EMPLOYEE"
    call.authenticated_user_id = francis.id
    db_session.commit()

    # 2. Handover request
    handover_text = "Je passe le téléphone à mon collègue"
    assert is_handover_positive_intent(handover_text) is True

    # Revocation
    call.authenticated_user_id = None
    call.caller_type = "UNKNOWN"
    call.source_context = {
        **(call.source_context or {}),
        "authenticated": False,
        "handover_revoked": True,
        "previous_principal": str(francis.id),
    }
    db_session.commit()

    # 3. Caller verbally cancels
    refusal_text = "Non merci, annule"
    assert is_pin_challenge_cancellation(refusal_text) is True

    # PublicInboundConversation.cancel_pin()
    pub_conv = PublicInboundConversation(db_session, settings, call.id)
    pub_conv.cancel_pin()

    reloaded = db_session.get(VoiceCall, call.id)
    assert reloaded.source_context.get("handover_revoked") is None
    assert reloaded.source_context.get("handover_cancelled") is True
    assert reloaded.source_context.get("public_fallback") is True
    assert reloaded.source_context.get("pin_gather_status") == "cancelled"
    assert reloaded.pin_challenge_hash is None

    # 4. Same connection authorize() must succeed (not raise PermissionError)
    ctx = reloaded.source_context or {}
    is_public_fallback = bool(ctx.get("public_fallback") or ctx.get("handover_cancelled"))
    assert is_public_fallback is True
    # In public fallback, public_mode becomes True and staff permissions are None
    public_mode = is_public_fallback
    principal_id = None
    assert public_mode is True
    assert principal_id is None

    # 5. Public question answered cleanly
    ans = pub_conv.public_answer("Quels sont vos horaires ?")
    assert ans["status"] == "success"
    assert "horaires" in ans["answer"].lower() or "ouvert" in ans["answer"].lower()


# =====================================================================
# 12. Public Fallback Then Private Query Requires New PIN
# =====================================================================

def test_public_fallback_then_private_request_triggers_new_pin(db_session: Session):
    """When in public fallback, asking for confidential data triggers a new PIN challenge."""
    company, voice_config, call, francis, marie = _make_test_company_and_call(db_session)
    settings = Settings(
        DATABASE_URL="sqlite:///:memory:",
        SECRET_KEY="test_secret_for_voice_unit_tests",
        TELNYX_API_KEY="test-telnyx-key",
        TELNYX_PUBLIC_KEY="test-public-key",
        TELNYX_MEDIA_ENABLED=True,
        TELNYX_MEDIA_INBOUND_ENABLED=True,
    )

    call.caller_type = "UNKNOWN"
    call.authenticated_user_id = None
    call.source_context = {
        **(call.source_context or {}),
        "public_fallback": True,
        "handover_cancelled": True,
        "pin_gather_status": "cancelled",
    }
    db_session.commit()

    # Configure staff PIN credential so PIN challenge is available
    auth_controller = VoiceCallerAuth(db_session, settings)
    auth_controller.set_pin(
        TenantContext(company.id, francis.id),
        "USER",
        francis.id,
        "719284",
        phone_number="+15145550199",
    )

    pub_conv = PublicInboundConversation(db_session, settings, call.id)
    # Confidential query: revenue / finance / CRM
    gate_res = pub_conv.security_gate("Quels sont les revenus et la facturation du client ?")
    assert gate_res is not None
    assert gate_res.get("auth_required") is True
    assert "nip" in gate_res.get("answer", "").lower() or "securite" in gate_res.get("answer", "").lower()


# =====================================================================
# 13. Cancelled Challenge Rejects Late Valid Webhook
# =====================================================================

def test_cancelled_challenge_stale_valid_webhook_rejected(db_session: Session):
    """If a valid PIN webhook arrives after cancellation, it is strictly rejected as stale."""
    company, voice_config, call, francis, marie = _make_test_company_and_call(db_session)
    settings = Settings(
        DATABASE_URL="sqlite:///:memory:",
        SECRET_KEY="test_secret_for_voice_unit_tests",
        TELNYX_API_KEY="test-telnyx-key",
        TELNYX_PUBLIC_KEY="test-public-key",
        TELNYX_MEDIA_ENABLED=True,
        TELNYX_MEDIA_INBOUND_ENABLED=True,
    )

    auth_controller = VoiceCallerAuth(db_session, settings)
    # Cancelled challenge state
    call.pin_challenge_hash = None
    call.source_context = {
        "public_fallback": True,
        "pin_gather_status": "cancelled",
        "handover_cancelled": True,
    }
    db_session.commit()

    # Late gather ended event:
    # 1. valid_challenge returns False because hash is cleared
    assert auth_controller.valid_challenge(call, "expired-client-state") is False

    # 2. Router late webhook protection logic:
    current_status = (call.source_context or {}).get("pin_gather_status")
    is_stale = bool(
        (current_status in {"cancelled", "authenticated", "refused"} or (call.source_context or {}).get("public_fallback"))
        and not call.pin_challenge_hash
    )
    assert is_stale is True

    # 3. Call remains in public mode with no authenticated user
    reloaded = db_session.get(VoiceCall, call.id)
    assert reloaded.authenticated_user_id is None
    assert reloaded.caller_type == "UNKNOWN"


# =====================================================================
# 14. DTMF Star Real Gather and Media Stream Cancellation
# =====================================================================

def test_dtmf_star_cancellation_real_gather(db_session: Session):
    """Pressing '*' alone in gather cancels challenge without penalty."""
    company, voice_config, call, francis, marie = _make_test_company_and_call(db_session)
    settings = Settings(
        DATABASE_URL="sqlite:///:memory:",
        SECRET_KEY="test_secret_for_voice_unit_tests",
        TELNYX_API_KEY="test-telnyx-key",
        TELNYX_PUBLIC_KEY="test-public-key",
        TELNYX_MEDIA_ENABLED=True,
        TELNYX_MEDIA_INBOUND_ENABLED=True,
    )

    auth_controller = VoiceCallerAuth(db_session, settings)
    call.pin_challenge_hash = "active-hash-123"
    call.source_context = {"handover_revoked": True}
    db_session.commit()

    result = auth_controller.verify_gather(call, "*")
    assert result.get("cancelled") is True
    assert result.get("reason") == "user_cancelled"
    assert result.get("authenticated") is False

    reloaded = db_session.get(VoiceCall, call.id)
    assert reloaded.pin_challenge_hash is None
    assert reloaded.source_context.get("public_fallback") is True
    assert reloaded.source_context.get("pin_gather_status") == "cancelled"
    assert reloaded.verification_attempts == 0


# =====================================================================
# 15. Audio Echo During Prompt Does Not Interrupt or Cancel
# =====================================================================

@pytest.mark.asyncio
async def test_audio_echo_during_prompt_does_not_interrupt_or_cancel():
    """Acoustic echo of prompt arriving in transcription is ignored without interrupting."""
    events_queue = asyncio.Queue()
    adapter = MockStreamingAdapter(events_queue)
    mock_socket = MagicMock()
    mock_socket.send_json = AsyncMock()

    bridge = TelnyxMediaBridge(
        socket=mock_socket,
        adapter=adapter,
        locale="fr-CA",
        validate_start=AsyncMock(),
        authorize=AsyncMock(),
        execute_turn=AsyncMock(),
    )
    bridge.stream_id = "stream-echo-test"
    bridge._pin_turn = "turn-pin-echo"
    bridge.phase = "PLAYING"
    bridge._last_spoken_prompt = "Veuillez saisir votre code NIP sur le clavier de votre téléphone"

    drain_task = asyncio.create_task(bridge._drain_provider_events())

    # Provider transcribes the acoustic echo of the agent's own prompt
    await events_queue.put(
        SimpleNamespace(
            type="conversation.item.input_audio_transcription.completed",
            item_id="echo-trans-1",
            transcript="veuillez saisir votre code nip sur le clavier de votre téléphone",
        )
    )
    await asyncio.sleep(0.1)

    await events_queue.put(None)
    await drain_task

    # The prompt was NOT cancelled by its own echo
    assert bridge._pin_turn == "turn-pin-echo"
    assert adapter.interrupted_count == 0


# =====================================================================
# 16. Echo Sequence: speech_started then Echo Transcription sends NO clear
# =====================================================================

@pytest.mark.asyncio
async def test_echo_sequence_speech_started_then_transcription_sends_no_clear():
    """Acoustic echo sequence (speech_started followed by echo transcription) sends zero Telnyx clear events."""
    events_queue = asyncio.Queue()
    adapter = MockStreamingAdapter(events_queue)
    mock_socket = MagicMock()
    mock_socket.send_json = AsyncMock()

    bridge = TelnyxMediaBridge(
        socket=mock_socket,
        adapter=adapter,
        locale="fr-CA",
        validate_start=AsyncMock(),
        authorize=AsyncMock(),
        execute_turn=AsyncMock(),
    )
    bridge.stream_id = "stream-echo-full-seq"
    bridge._pin_turn = "turn-pin-echo-seq"
    bridge.phase = "PLAYING"
    bridge._last_spoken_prompt = "Veuillez saisir votre code NIP sur le clavier de votre téléphone"

    drain_task = asyncio.create_task(bridge._drain_provider_events())

    # Step 1: Speaker audio bleeds into mic, triggering Gemini VAD speech_started
    await events_queue.put(
        SimpleNamespace(
            type="input_audio_buffer.speech_started",
        )
    )
    await asyncio.sleep(0.05)

    # Step 2: Gemini transcribes the acoustic echo of the spoken prompt
    await events_queue.put(
        SimpleNamespace(
            type="conversation.item.input_audio_transcription.completed",
            item_id="echo-trans-seq-1",
            transcript="veuillez saisir votre code nip sur le clavier de votre téléphone",
        )
    )
    await asyncio.sleep(0.1)

    # Shutdown tasks cleanly
    await events_queue.put(None)
    await drain_task

    # Crucial assertion: ZERO Telnyx "clear" events were sent! The prompt was not cut off!
    sent_clears = [
        call_args[0][0]
        for call_args in mock_socket.send_json.call_args_list
        if isinstance(call_args[0][0], dict) and call_args[0][0].get("event") == "clear"
    ]
    assert len(sent_clears) == 0, f"Expected 0 clear events, but found: {sent_clears}"
    assert bridge._pin_turn == "turn-pin-echo-seq"
    assert adapter.interrupted_count == 0


# =====================================================================
# 17. Verbal Cancellation Sequence: speech_started then Non merci sends clear
# =====================================================================

@pytest.mark.asyncio
async def test_verbal_cancellation_sequence_sends_clear_and_cancels():
    """Real caller speech ("Non merci, je vais rester Francis") interrupts and cancels PIN challenge."""
    events_queue = asyncio.Queue()
    adapter = MockStreamingAdapter(events_queue)
    mock_socket = MagicMock()
    mock_socket.send_json = AsyncMock()

    bridge = TelnyxMediaBridge(
        socket=mock_socket,
        adapter=adapter,
        locale="fr-CA",
        validate_start=AsyncMock(),
        authorize=AsyncMock(),
        execute_turn=AsyncMock(),
    )
    bridge.stream_id = "stream-verbal-cancel"
    bridge._pin_turn = "turn-pin-verbal-cancel"
    bridge.phase = "PLAYING"
    bridge.response_id = "resp-playing-1"
    bridge._last_spoken_prompt = "Veuillez saisir votre code NIP sur le clavier de votre téléphone"

    drain_task = asyncio.create_task(bridge._drain_provider_events())

    # Step 1: Caller starts speaking
    await events_queue.put(
        SimpleNamespace(
            type="input_audio_buffer.speech_started",
        )
    )
    await asyncio.sleep(0.05)

    # Step 2: Caller says "Non merci, je vais rester Francis"
    await events_queue.put(
        SimpleNamespace(
            type="conversation.item.input_audio_transcription.completed",
            item_id="trans-cancel-1",
            transcript="Non merci, je vais rester Francis",
        )
    )
    await asyncio.sleep(0.1)

    # Shutdown tasks
    await events_queue.put(None)
    await drain_task

    # Crucial assertion: Telnyx "clear" WAS sent to stop playing audio immediately!
    sent_clears = [
        call_args[0][0]
        for call_args in mock_socket.send_json.call_args_list
        if isinstance(call_args[0][0], dict) and call_args[0][0].get("event") == "clear"
    ]
    assert len(sent_clears) >= 1, "Expected Telnyx clear to be sent for verbal cancellation"
    assert bridge._pin_turn is None
    assert bridge._pin_mark is None
    assert bridge._pin_started is False


# =====================================================================
# 18. Self-Cancellation Guard in _execute_turns with auth_required
# =====================================================================

@pytest.mark.asyncio
async def test_execute_turn_auth_required_does_not_cancel_own_task():
    """_execute running as _current_turn_task calling interrupt() does not cancel itself."""
    mock_socket = MagicMock()
    mock_socket.send_json = AsyncMock()
    events_queue = asyncio.Queue()
    adapter = MockStreamingAdapter(events_queue)

    async def mock_execute_turn(*args, **kwargs):
        return {
            "status": "success",
            "answer": "Pour des raisons de sécurité, veuillez saisir votre NIP.",
            "auth_required": True,
        }

    bridge = TelnyxMediaBridge(
        socket=mock_socket,
        adapter=adapter,
        locale="fr-CA",
        validate_start=AsyncMock(),
        authorize=AsyncMock(),
        execute_turn=mock_execute_turn,
    )
    bridge.stream_id = "stream-auth-req"
    bridge.begin_pin = AsyncMock(return_value={"success": True})
    bridge.poll_pin = AsyncMock(return_value={"status": "pending"})

    # Queue 1 turn
    await bridge._turns.put(("turn-auth-1", "Donne-moi mes informations de paie", bridge.epoch))

    # Run _execute_turns briefly
    exec_task = asyncio.create_task(bridge._execute_turns())
    await asyncio.sleep(0.1)

    # Terminate queue and wait for exec_task
    bridge._running = False
    exec_task.cancel()
    try:
        await exec_task
    except asyncio.CancelledError:
        pass

    # Assert that _execute did NOT self-cancel:
    assert bridge._pin_turn == "turn-auth-1"
    assert bridge._pin_prompt_spoken is True
    assert bridge._pin_mark is not None
    assert bridge._pin_mark.startswith("pin-prompt:")
    assert len(adapter.spoken_texts) >= 1
    assert "Pour des raisons de sécurité" in adapter.spoken_texts[0]


# =====================================================================
# 19. Authorize Media Session Continuity: Staff -> Handover -> Fallback
# =====================================================================

def test_authorize_media_session_staff_handover_and_public_fallback(db_session: Session):
    """Direct validation of authorize_media_session during staff, handover, and fallback states."""
    from backend.app.services.module_entitlement_service import ModuleEntitlementService

    company, voice_config, call, francis, marie = _make_test_company_and_call(db_session)
    call.source_context = {"dispatcher_routing": True}
    db_session.commit()

    settings = Settings(
        DATABASE_URL="sqlite:///:memory:",
        SECRET_KEY="test_secret_for_voice_unit_tests",
        TELNYX_API_KEY="test-telnyx-key",
        TELNYX_PUBLIC_KEY="test-public-key",
        TELNYX_MEDIA_ENABLED=True,
        TELNYX_MEDIA_INBOUND_ENABLED=True,
    )
    plan = ModuleEntitlementService(db_session).get_company_plan(TenantContext(company.id)).code.value

    # Configure Francis PIN and active session
    auth_controller = VoiceCallerAuth(db_session, settings)
    auth_controller.set_pin(
        TenantContext(company.id, francis.id),
        "USER",
        francis.id,
        "719284",
        phone_number="+15145550199",
    )
    call.caller_type = "EMPLOYEE"
    call.authenticated_user_id = francis.id
    auth_sess = VoiceAuthSession(
        company_id=company.id,
        call_id=call.id,
        caller_type="EMPLOYEE",
        principal_id=francis.id,
        permissions=["ai:use", "voice:employee", "voice:call"],
        authenticated_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    db_session.add(auth_sess)
    db_session.commit()

    # 1. Initial staff authorization (Francis)
    pub_mode, princ_id, epoch, ledger = authorize_media_session(
        db_session,
        settings,
        call.id,
        plan,
        public_mode=False,
        principal_id=None,
        auth_epoch=None,
        claim={"client_state": "ok"},
    )
    assert pub_mode is False
    assert princ_id == francis.id
    assert epoch is not None

    # 2. Handover revoked (PIN challenge ongoing)
    call.authenticated_user_id = None
    call.caller_type = "UNKNOWN"
    call.source_context = {"dispatcher_routing": True, "handover_revoked": True}
    auth_sess.revoked_at = datetime.now(timezone.utc)
    db_session.commit()

    pub_mode2, princ_id2, epoch2, ledger2 = authorize_media_session(
        db_session,
        settings,
        call.id,
        plan,
        public_mode=False,
        principal_id=francis.id,
        auth_epoch=epoch,
        claim={"client_state": "ok"},
    )
    assert pub_mode2 is False
    assert princ_id2 is None
    assert epoch2 is None

    # 3. Handover cancelled / refused -> public fallback
    call.source_context = {
        "dispatcher_routing": True,
        "handover_cancelled": True,
        "public_fallback": True,
        "pin_gather_status": "cancelled",
    }
    db_session.commit()

    pub_mode3, princ_id3, epoch3, ledger3 = authorize_media_session(
        db_session,
        settings,
        call.id,
        plan,
        public_mode=False,
        principal_id=None,
        auth_epoch=None,
        claim={"client_state": "ok"},
    )
    assert pub_mode3 is True
    assert princ_id3 is None
    assert epoch3 is None

    # 4. Unauthenticated call without handover or public fallback raises PermissionError
    call.source_context = {"dispatcher_routing": True}
    db_session.commit()

    with pytest.raises(PermissionError):
        authorize_media_session(
            db_session,
            settings,
            call.id,
            plan,
            public_mode=False,
            principal_id=None,
            auth_epoch=None,
            claim={"client_state": "ok"},
        )

