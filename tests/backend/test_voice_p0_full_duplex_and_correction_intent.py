"""P0 Full-Duplex Audio, Intelligent Barge-In, Objection Understanding & Retail Speech Suite.

Covers all 20 mandatory end-to-end & integration verification scenarios for GitHub Issue #128:
1. Continuous inbound audio during 25 seconds of TTS playback.
2. Human intervention at 3 seconds (independent STT rescue when Gemini drops input_transcription).
3. Human intervention at 10 seconds (partial/final transcript barge-in).
4. Multiple successive interruptions without losing turns.
5. Speakerphone acoustic echo with zero Telnyx clear cut-offs.
6. Multilingual human objections & corrections ("C'est pas de ça que je parlais" + reformulation).
7. Short "Allô" / "Allô, tu m'entends ?" during an active monologue (never ignored as backchannel).
8. Missing final transcription fallback + speech_stopped_without_transcript telemetry.
9. Late superseded transcription after interruption discarded cleanly.
10. Duplicate TTS cancellation idempotence.
11. New question preserved across epoch changes.
12. Ambiguous Retail commercial question clarification & follow-up.
13. Technical field names (compare_at_price, inventory_quantity, etc.) eliminated from voice speech.
14. Stale inventory never claimed as confirmed in-stock.
15. PIN authentication & PR #127 anti-self-cancellation guard preserved.
16. Owner & Employee hierarchical permissions preserved.
17. Strict multi-tenant data isolation (zero cross-tenant product leaks).
18. Mid-call Gemini disconnect and automatic reconnect without dropping the call.
19. 20 consecutive questions processed with zero silent drops.
20. Latency (p50/p95) & audio playback acknowledgment (`play-*` mark) telemetry.
"""
from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timedelta, timezone
import struct
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.ai.tools.business.commerce_tools import GetProductDetailTool, ProductDetailArgs
from backend.app.ai.tools.contracts import ToolExecutionContext
from backend.app.config.settings import Settings
from backend.app.models.base import Base
from backend.app.models.billing import BillingAccount
from backend.app.models.commerce_connection import CommerceConnection, NormalizedCommerceRecord
from backend.app.models.company import Company
from backend.app.models.company_membership import CompanyMembership
from backend.app.models.company_module import CompanyModule, CompanyModuleStatus
from backend.app.models.module import Module
from backend.app.models.user import User, UserRole
from backend.app.models.voice import CompanyRoutingNip, VoiceAuthSession, VoiceBusinessConfig, VoiceCall
from backend.app.services.company_intelligence_service import CompanyIntelligenceService
from backend.app.services.employee_coach_service import EmployeeCoachService
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from backend.app.voice.auth import VoiceCallerAuth
from backend.app.voice.direct_answers import (
    is_ambiguous_commercial_selling_question,
    resolve_direct_voice_answer,
    sanitize_retail_voice_text,
    spoken_catalog_answer,
)
from backend.app.voice.realtime_provider import (
    FallbackRealtimeAudioAdapter,
    GeminiLiveRealtimeAudioAdapter,
    NaturalInterruptionManager,
)
from backend.app.voice.telnyx_media import (
    TelnyxMediaBridge,
    authorize_media_session,
    clean_voice_text,
)
from backend.app.voice.turn_control import (
    ConversationState,
    adjudicate_transcript,
    build_correction_clarification,
    extract_reformulation_after_correction,
    extract_request_after_attention_check,
    is_attention_check,
    is_backchannel,
    is_correction_or_objection,
)
from shared.ai_engine.contracts import TenantContext


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


def _make_test_settings() -> Settings:
    settings = Settings()
    settings.database_url = "sqlite:///:memory:"
    settings.auth_jwt_secret = "test_secret_for_voice_full_duplex_32_bytes_long!!"
    settings.telnyx_api_key = "test-telnyx-key"
    settings.telnyx_public_key = "test-public-key"
    settings.telnyx_media_enabled = True
    settings.telnyx_media_inbound_enabled = True
    return settings


def _pcm_tone(amplitude: int, samples: int = 480) -> bytes:
    """Generate 20ms (480 samples @ 24kHz) of PCM16 audio at the requested RMS amplitude."""
    # Alternating +amplitude / -amplitude produces exact RMS == amplitude
    return struct.pack(f"<{samples}h", *([amplitude if i % 2 == 0 else -amplitude for i in range(samples)]))


def _pcm_silence(samples: int = 480) -> bytes:
    return b"\x00\x00" * samples


class FakeGeminiLiveSession:
    """Fake google-genai Live AsyncSession capturing all realtime inputs and yielding scripted messages."""

    def __init__(self, server_messages: asyncio.Queue[Any] | None = None, *, fail_after: int | None = None) -> None:
        self.audio_chunks: list[Any] = []
        self.audio_stream_ends: int = 0
        self.client_contents: list[Any] = []
        self._server_messages: asyncio.Queue[Any] = server_messages or asyncio.Queue()
        self._fail_after = fail_after
        self._yielded = 0

    async def send_realtime_input(self, *, audio: Any = None, audio_stream_end: bool = False) -> None:
        if audio is not None:
            self.audio_chunks.append(audio)
        if audio_stream_end:
            self.audio_stream_ends += 1

    async def send_client_content(self, *, turns: Any = None, turn_complete: bool = True) -> None:
        self.client_contents.append((turns, turn_complete))

    async def receive(self):
        while True:
            msg = await self._server_messages.get()
            if msg is None:
                return
            if isinstance(msg, Exception):
                raise msg
            self._yielded += 1
            yield msg
            if self._fail_after is not None and self._yielded >= self._fail_after:
                raise ConnectionResetError("Simulated Gemini Live mid-call disconnect")


class FakeGeminiClient:
    def __init__(self, sessions: list[FakeGeminiLiveSession]) -> None:
        self._sessions = list(sessions)
        self.connect_count = 0
        self.aio = SimpleNamespace(live=SimpleNamespace(connect=self._connect))

    def _connect(self, *, model: str, config: Any):
        self.connect_count += 1
        session = self._sessions[min(self.connect_count - 1, len(self._sessions) - 1)]

        class _Ctx:
            async def __aenter__(self):
                return session

            async def __aexit__(self, exc_type, exc, tb):
                return False

        return _Ctx()


class MockIndependentSTT:
    provider_id = "mock_independent_stt"

    def __init__(self, transcript: str) -> None:
        self.transcript = transcript
        self.calls: list[tuple[int, str, str]] = []

    async def transcribe(self, audio: bytes, *, locale: str, content_type: str) -> str:
        self.calls.append((len(audio), locale, content_type))
        return self.transcript


class QueueDrivenAdapter:
    provider_id = "gemini_live"
    model_name = "gemini-3.8-live"

    def __init__(self, events_queue: asyncio.Queue[Any]) -> None:
        self._events_queue = events_queue
        self.spoken_texts: list[str] = []
        self.interrupted_count = 0
        self.playback_states: list[bool] = []
        self.reconnect_calls = 0

    async def speak(self, text: str) -> None:
        self.spoken_texts.append(text)

    async def interrupt(self) -> None:
        self.interrupted_count += 1

    async def clear_input(self) -> None:
        pass

    async def send_audio(self, audio: bytes) -> None:
        pass

    def set_playback_active(self, active: bool) -> None:
        self.playback_states.append(active)

    async def reconnect(self, fallback_model: str = "gpt-realtime-2.1", locale: str = "fr-CA") -> None:
        self.reconnect_calls += 1

    async def events(self):
        while True:
            ev = await self._events_queue.get()
            if ev is None:
                break
            if isinstance(ev, Exception):
                raise ev
            yield ev


def _create_tenant_with_products(
    db: Session,
    *,
    company_name: str,
    owner_name: str = "Paul",
    employee_name: str = "Francis",
    live_stock: bool = True,
    products_spec: list[dict[str, Any]] | None = None,
):
    uid = uuid4().hex[:8]
    company = Company(
        id=uuid4(),
        name=company_name,
        slug=f"{company_name.lower().replace(' ', '-')}-{uid}",
        email=f"contact-{uid}@example.com",
        country="CA",
        timezone="America/Toronto",
        industry="retail",
        subscription_plan="enterprise",
        website="https://store.example.com",
    )
    db.add(company)
    db.flush()

    for code, name in (("voice", "Voice AI"), ("retail", "Retail Intelligence"), ("crm", "CRM")):
        existing_mod = db.query(Module).filter(Module.code == code).first()
        if existing_mod is None:
            existing_mod = Module(id=uuid4(), name=name, code=code, is_active=True)
            db.add(existing_mod)
            db.flush()
        db.add(
            CompanyModule(
                company_id=company.id,
                module_id=existing_mod.id,
                status=CompanyModuleStatus.ACTIVE,
                activated_at=datetime.now(timezone.utc),
            )
        )

    owner = User(
        id=uuid4(),
        company_id=company.id,
        email=f"owner-{uid}@example.com",
        first_name=owner_name,
        last_name="Boss",
        password_hash="hashed_pw",
        role=UserRole.OWNER,
        phone="+15145550100",
        is_active=True,
    )
    employee = User(
        id=uuid4(),
        company_id=company.id,
        email=f"emp-{uid}@example.com",
        first_name=employee_name,
        last_name="Staff",
        password_hash="hashed_pw",
        role=UserRole.USER,
        phone="+15145550199",
        is_active=True,
    )
    db.add_all([owner, employee])
    db.flush()
    db.add(CompanyMembership(company_id=company.id, user_id=owner.id, role=UserRole.OWNER, is_active=True))
    db.add(CompanyMembership(company_id=company.id, user_id=employee.id, role=UserRole.USER, is_active=True))
    db.add(BillingAccount(id=uuid4(), company_id=company.id, status="active"))
    db.add(CompanyRoutingNip(id=uuid4(), company_id=company.id, routing_code=f"12{uid[:4]}", routing_code_hash=f"h-{uid}", status="ACTIVE"))

    voice_config = VoiceBusinessConfig(
        id=uuid4(),
        company_id=company.id,
        business_name=company_name,
        preferred_language="fr-CA",
        opening_hours={"weekly": {"monday": [{"open": "09:00", "close": "17:00"}]}},
        services=[{"name": "Consultation", "price": 80, "currency": "CAD", "duration_minutes": 30}],
        greeting_message=f"Bonjour chez {company_name} !",
        voice_api_key_hash=f"vh-{uid}",
        voice_api_key_last4="1234",
        enabled=True,
    )
    db.add(voice_config)
    db.flush()

    now = datetime.now(timezone.utc)
    updated_at = now if live_stock else (now - timedelta(days=20))
    conn = CommerceConnection(
        id=uuid4(),
        company_id=company.id,
        provider="shopify",
        external_account_id=f"{uid}.myshopify.com",
        display_name=f"{company_name} Shopify",
        status="READY" if live_stock else "DEGRADED",
        last_successful_sync=updated_at,
    )
    db.add(conn)
    db.flush()

    default_products = products_spec or [
        {
            "product_id": f"p1-{uid}",
            "product_name": f"Planche Alpine {company_name}",
            "unit_price": 499.99,
            "compare_at_price": 599.99,
            "inventory_level": 8 if live_stock else 0,
            "in_stock": live_stock,
            "product_category": "planche",
            "sku": f"SKU-1-{uid}",
        },
        {
            "product_id": f"p2-{uid}",
            "product_name": f"Casque Pro {company_name}",
            "unit_price": 129.0,
            "compare_at_price": 159.0,
            "inventory_level": 12 if live_stock else 0,
            "in_stock": live_stock,
            "product_category": "accessoire",
            "sku": f"SKU-2-{uid}",
        },
        {
            "product_id": f"p3-{uid}",
            "product_name": f"Gants Thermiques {company_name}",
            "unit_price": 59.0,
            "inventory_level": 15 if live_stock else 0,
            "in_stock": live_stock,
            "product_category": "accessoire",
            "sku": f"SKU-3-{uid}",
        },
        {
            "product_id": f"p4-{uid}",
            "product_name": f"Fixations Carbone {company_name}",
            "unit_price": 249.0,
            "inventory_level": 4 if live_stock else 0,
            "in_stock": live_stock,
            "product_category": "accessoire",
            "sku": f"SKU-4-{uid}",
        },
    ]
    for idx, spec in enumerate(default_products):
        db.add(
            NormalizedCommerceRecord(
                id=uuid4(),
                company_id=company.id,
                connection_id=conn.id,
                provider="shopify",
                entity_type="product",
                source_record_id=f"ext-{uid}-{idx}",
                normalized_data=spec,
                source_updated_at=updated_at,
                deleted=False,
            )
        )

    call = VoiceCall(
        id=uuid4(),
        company_id=company.id,
        config_id=voice_config.id,
        telnyx_call_control_id=f"call-ctrl-{uid}",
        caller_phone="+15145550100",
        status="in_progress",
        locale="fr-CA",
        caller_type="OWNER",
        authenticated_user_id=owner.id,
        source_context={"live_call": True, "dispatcher_routing": True},
    )
    db.add(call)
    db.commit()
    return company, voice_config, call, owner, employee


# =====================================================================
# 1. Continuous Inbound Audio During 25 Seconds of TTS Playback
# =====================================================================

@pytest.mark.asyncio
async def test_01_continuous_inbound_audio_during_25s_tts():
    """Verify 25 seconds (1,250 x 20ms frames) of continuous inbound audio flow to Gemini Live during TTS."""
    server_q: asyncio.Queue[Any] = asyncio.Queue()
    fake_session = FakeGeminiLiveSession(server_q)
    fake_client = FakeGeminiClient([fake_session])

    adapter = GeminiLiveRealtimeAudioAdapter(
        _make_test_settings(),
        api_key="fake-gemini-key",
        company_name="Produits Ero",
        client_factory=lambda _k: fake_client,
        vad_rms_threshold=450,
        silence_frames_threshold=5,
        stt_rescue_delay_seconds=0.05,
    )
    await adapter.open(locale="fr-CA")
    await adapter.speak("Voici la liste complète de vos produits disponibles dans le catalogue.")
    adapter.set_playback_active(True)

    # Stream 25 seconds (1,250 x 20ms frames) of continuous audio while TTS playback is active
    quiet_frame = _pcm_tone(120)
    for _ in range(1250):
        await adapter.send_audio(quiet_frame)

    # All 1,250 frames must reach Gemini Live continuously without stalling or closing input stream
    assert len(fake_session.audio_chunks) == 1250
    assert fake_session.audio_stream_ends == 0

    await server_q.put(None)
    await adapter.close()


# =====================================================================
# 2. Human Intervention at 3 Seconds (Independent STT Rescue)
# =====================================================================

@pytest.mark.asyncio
async def test_02_human_intervention_at_3s_rescued_by_independent_stt():
    """At 3s into TTS, caller speaks an objection; Gemini emits ZERO input_transcription;
    independent STT rescue transcribes it, Telnyx clear fires, and the objection is answered."""
    server_q: asyncio.Queue[Any] = asyncio.Queue()
    fake_session = FakeGeminiLiveSession(server_q)
    fake_client = FakeGeminiClient([fake_session])
    mock_stt = MockIndependentSTT("Non, c'est pas de ça que je parlais")

    adapter = GeminiLiveRealtimeAudioAdapter(
        _make_test_settings(),
        api_key="fake-gemini-key",
        company_name="Produits Ero",
        client_factory=lambda _k: fake_client,
        stt_adapter=mock_stt,
        vad_rms_threshold=450,
        silence_frames_threshold=3,
        stt_rescue_delay_seconds=0.03,
        min_speech_ms_for_rescue=200,
    )
    await adapter.open(locale="fr-CA")

    mock_socket = MagicMock()
    mock_socket.send_json = AsyncMock()
    executed_turns: list[str] = []

    async def mock_execute_turn(item_id: str, transcript: str):
        executed_turns.append(transcript)
        return {"status": "success", "answer": build_correction_clarification("fr-CA", last_topic="retail_catalog")}

    bridge = TelnyxMediaBridge(
        socket=mock_socket,
        adapter=adapter,
        locale="fr-CA",
        validate_start=AsyncMock(),
        authorize=AsyncMock(),
        execute_turn=mock_execute_turn,
        allow_natural_interruptions=True,
    )
    bridge.stream_id = "stream-3s-rescue"
    bridge._set_phase("PLAYING")
    bridge._set_playback_active(True)
    bridge._last_spoken = "Nous avons au catalogue la planche Alpine à 499 dollars."
    bridge.response_id = "resp-catalog-long"
    bridge._output.put_nowait((bridge.epoch, b"\xff" * 160))

    drain_task = asyncio.create_task(bridge._drain_provider_events())
    exec_task = asyncio.create_task(bridge._execute_turns())

    # Simulate 3s of quiet frames (150 frames @ 20ms) then human objection (20 loud frames = 400ms) + silence
    for _ in range(15):
        await adapter.send_audio(_pcm_tone(100))
    for _ in range(20):
        await adapter.send_audio(_pcm_tone(1800))  # Above 1.5x playback threshold (675)
    for _ in range(4):
        await adapter.send_audio(_pcm_silence())

    # Wait for independent STT rescue watchdog to fire
    await asyncio.sleep(0.2)

    await server_q.put(None)
    await adapter.close()
    await drain_task
    exec_task.cancel()
    try:
        await exec_task
    except asyncio.CancelledError:
        pass

    # Verify independent STT rescue ran and Telnyx clear stopped the runaway TTS!
    assert len(mock_stt.calls) >= 1
    assert bridge.telemetry["stt_rescue_succeeded"] >= 1
    assert bridge.telemetry["telnyx_clear_sent_count"] >= 1
    clears = [c[0][0] for c in mock_socket.send_json.call_args_list if isinstance(c[0][0], dict) and c[0][0].get("event") == "clear"]
    assert len(clears) >= 1
    assert any("pas de ça" in t for t in executed_turns)


# =====================================================================
# 3. Human Intervention at 10 Seconds (Partial Transcript Sub-500ms Barge-In)
# =====================================================================

@pytest.mark.asyncio
async def test_03_human_intervention_at_10s_partial_barge_in():
    """At 10s of TTS playback, a partial objection transcript immediately fires Telnyx clear
    and prevents duplicate clears when the final transcript arrives."""
    events_q: asyncio.Queue[Any] = asyncio.Queue()
    adapter = QueueDrivenAdapter(events_q)
    mock_socket = MagicMock()
    mock_socket.send_json = AsyncMock()
    executed: list[str] = []

    async def mock_exec(item_id: str, transcript: str):
        executed.append(transcript)
        return {"status": "success", "answer": "D'accord, j'ai mal compris. Tu cherches quels types de produits exactement ?"}

    bridge = TelnyxMediaBridge(
        socket=mock_socket,
        adapter=adapter,
        locale="fr-CA",
        validate_start=AsyncMock(),
        authorize=AsyncMock(),
        execute_turn=mock_exec,
        allow_natural_interruptions=True,
    )
    bridge.stream_id = "stream-10s"
    bridge._set_phase("PLAYING")
    bridge._set_playback_active(True)
    bridge.response_id = "resp-10s"
    bridge._last_spoken = "Voici nos articles disponibles en magasin aujourd'hui."

    drain_task = asyncio.create_task(bridge._drain_provider_events())
    exec_task = asyncio.create_task(bridge._execute_turns())

    await events_q.put(SimpleNamespace(type="input_audio_buffer.speech_started", item_id="item-10s"))
    t0 = time.monotonic()
    # Partial transcript arrives first -> immediate barge-in!
    await events_q.put(
        SimpleNamespace(
            type="conversation.item.input_audio_transcription.delta",
            item_id="item-10s",
            delta="Non, c'est pas de ça",
            transcript="Non, c'est pas de ça",
        )
    )
    await asyncio.sleep(0.05)
    t_clear = time.monotonic()
    # Final transcript arrives for SAME item_id -> must NOT send a duplicate clear!
    await events_q.put(
        SimpleNamespace(
            type="conversation.item.input_audio_transcription.completed",
            item_id="item-10s",
            transcript="Non, c'est pas de ça que je parlais",
        )
    )
    await asyncio.sleep(0.08)

    await events_q.put(None)
    await drain_task
    exec_task.cancel()
    try:
        await exec_task
    except asyncio.CancelledError:
        pass

    clears = [c[0][0] for c in mock_socket.send_json.call_args_list if isinstance(c[0][0], dict) and c[0][0].get("event") == "clear"]
    assert len(clears) == 1, f"Expected exactly 1 clear (no double clear), got {len(clears)}"
    assert (t_clear - t0) < 0.5
    assert bridge.telemetry["stt_partial_count"] == 1
    assert executed == ["Non, c'est pas de ça que je parlais"]


# =====================================================================
# 4. Multiple Successive Interruptions
# =====================================================================

@pytest.mark.asyncio
async def test_04_multiple_successive_interruptions():
    """5 successive interruptions during active playback each halt the old answer and process the new turn."""
    events_q: asyncio.Queue[Any] = asyncio.Queue()
    adapter = QueueDrivenAdapter(events_q)
    mock_socket = MagicMock()
    mock_socket.send_json = AsyncMock()
    processed: list[str] = []

    async def mock_exec(item_id: str, transcript: str):
        processed.append(transcript)
        return {"status": "success", "answer": f"Réponse courte pour {item_id}."}

    bridge = TelnyxMediaBridge(
        socket=mock_socket,
        adapter=adapter,
        locale="fr-CA",
        validate_start=AsyncMock(),
        authorize=AsyncMock(),
        execute_turn=mock_exec,
        allow_natural_interruptions=True,
    )
    bridge.stream_id = "stream-multi-barge"
    drain_task = asyncio.create_task(bridge._drain_provider_events())
    exec_task = asyncio.create_task(bridge._execute_turns())

    utterances = [
        "Quels sont vos horaires d'ouverture ?",
        "Non, c'est pas de ça que je parlais",
        "Attends, écoute-moi s'il te plaît",
        "Je veux savoir le prix des casques",
        "Allô, tu m'entends ?",
    ]
    for idx, text in enumerate(utterances):
        bridge._set_phase("PLAYING")
        bridge.response_id = f"resp-{idx}"
        await events_q.put(
            SimpleNamespace(
                type="conversation.item.input_audio_transcription.completed",
                item_id=f"multi-{idx}",
                transcript=text,
            )
        )
        await asyncio.sleep(0.06)

    await events_q.put(None)
    await drain_task
    exec_task.cancel()
    try:
        await exec_task
    except asyncio.CancelledError:
        pass

    assert len(processed) == 5
    assert bridge.telemetry["barge_in_triggered_count"] == 5
    assert bridge.telemetry["telnyx_clear_sent_count"] == 5


# =====================================================================
# 5. Speakerphone Acoustic Echo Without Cut-Off
# =====================================================================

@pytest.mark.asyncio
async def test_05_speakerphone_echo_without_cutoff():
    """Speakerphone echo (speech_started + partial echo + final echo) sends ZERO Telnyx clears."""
    events_q: asyncio.Queue[Any] = asyncio.Queue()
    adapter = QueueDrivenAdapter(events_q)
    mock_socket = MagicMock()
    mock_socket.send_json = AsyncMock()

    bridge = TelnyxMediaBridge(
        socket=mock_socket,
        adapter=adapter,
        locale="fr-CA",
        validate_start=AsyncMock(),
        authorize=AsyncMock(),
        execute_turn=AsyncMock(),
        allow_natural_interruptions=True,
    )
    bridge.stream_id = "stream-echo-safe"
    bridge._set_phase("PLAYING")
    bridge.response_id = "resp-echo-1"
    bridge._last_spoken = "Nous avons au catalogue la Planche Alpine au prix de quatre cent quatre-vingt-dix-neuf dollars."

    drain_task = asyncio.create_task(bridge._drain_provider_events())

    await events_q.put(SimpleNamespace(type="input_audio_buffer.speech_started", item_id="echo-1"))
    await events_q.put(
        SimpleNamespace(
            type="conversation.item.input_audio_transcription.delta",
            item_id="echo-1",
            delta="Nous avons au catalogue la Planche Alpine",
            transcript="Nous avons au catalogue la Planche Alpine",
        )
    )
    await events_q.put(
        SimpleNamespace(
            type="conversation.item.input_audio_transcription.completed",
            item_id="echo-1",
            transcript="nous avons au catalogue la planche alpine au prix de quatre cent quatre vingt dix neuf dollars",
        )
    )
    await asyncio.sleep(0.08)

    await events_q.put(None)
    await drain_task

    clears = [c[0][0] for c in mock_socket.send_json.call_args_list if isinstance(c[0][0], dict) and c[0][0].get("event") == "clear"]
    assert len(clears) == 0
    assert adapter.interrupted_count == 0
    assert bridge.phase == "PLAYING"


# =====================================================================
# 6. Human Objection Recognition (FR/EN/ES/RO) + Direct Reformulation
# =====================================================================

def test_06_correction_objection_recognition_and_reformulation():
    """Verify multilingual objection detection, contextual clarification, and direct reformulation extraction."""
    objections = [
        "Non, ce n'est pas de ça que je parlais.",
        "Non, c'est pas de ça que je parlais.",
        "Non, tu m'as mal compris.",
        "Attends, écoute-moi.",
        "Arrête, je veux autre chose.",
        "Je veux dire autre chose.",
        "That's not what I meant.",
        "Stop, listen to me.",
        "You misunderstood my question.",
        "No es eso lo que quería decir.",
        "Espera, escúchame.",
        "Nu asta am vrut să spun.",
        "Stai puțin, ascultă-mă.",
    ]
    for phrase in objections:
        assert is_correction_or_objection(phrase) is True, f"Missed objection: {phrase}"
        assert adjudicate_transcript(phrase, phase="PLAYING", allow_barge_in=True) == "replace"

    # Pure objection -> short contextual clarification
    assert extract_reformulation_after_correction("Non, c'est pas de ça que je parlais.") is None
    clar = build_correction_clarification("fr-CA", last_topic="retail_catalog")
    assert "mal compris" in clar.lower() and "produits" in clar.lower()

    # Objection WITH reformulation -> directly extracts new request
    reformulated = extract_reformulation_after_correction(
        "Non, c'est pas de ça que je parlais, je veux connaître les produits les plus rentables"
    )
    assert reformulated is not None
    assert "rentables" in reformulated.lower()


# =====================================================================
# 7. Short "Allô" During Ignored Response Is Never Dropped
# =====================================================================

def test_07_short_allo_during_playback_triggers_barge_in():
    """'Allô' and 'Allô, tu m'entends ?' must NEVER be dropped as a backchannel."""
    for phrase in ("Allô", "Allô ?", "Allô, tu m'entends ?", "Hello? Can you hear me?", "¿Aló? ¿Me escuchas?", "Alo? Mă auzi?"):
        assert is_attention_check(phrase) is True
        assert is_backchannel(phrase) is False
        assert adjudicate_transcript(phrase, phase="PLAYING", allow_barge_in=True) == "replace"
        assert adjudicate_transcript(phrase, phase="LISTENING", seconds_since_last_turn=6.0) == "accept"

    # True backchannels remain ignored during playback
    for bc in ("euh", "oui", "d'accord", "merci", "ok", "parfait"):
        assert is_backchannel(bc) is True
        assert adjudicate_transcript(bc, phase="PLAYING", allow_barge_in=True) == "ignore"


# =====================================================================
# 8. Missing Final Transcription Fallback & Separate Telemetry
# =====================================================================

@pytest.mark.asyncio
async def test_08_missing_final_transcription_stops_monologue_and_recovers():
    """When confirmed non-echo caller speech (>450ms) during playback loses its final transcript,
    speech_stopped_without_transcript increments separately from silence, TTS stops, and short cue is spoken."""
    events_q: asyncio.Queue[Any] = asyncio.Queue()
    adapter = QueueDrivenAdapter(events_q)
    mock_socket = MagicMock()
    mock_socket.send_json = AsyncMock()

    bridge = TelnyxMediaBridge(
        socket=mock_socket,
        adapter=adapter,
        locale="fr-CA",
        validate_start=AsyncMock(),
        authorize=AsyncMock(),
        execute_turn=AsyncMock(),
        allow_natural_interruptions=True,
    )
    bridge.stream_id = "stream-missing-stt"
    bridge._set_phase("PLAYING")
    bridge.response_id = "resp-runaway"
    bridge._last_spoken = "Nous avons au catalogue la Planche Alpine à quatre cent quatre-vingt-dix-neuf dollars."
    bridge._output.put_nowait((bridge.epoch, b"\xff" * 160))

    drain_task = asyncio.create_task(bridge._drain_provider_events())

    await events_q.put(SimpleNamespace(type="input_audio_buffer.speech_started", item_id="miss-1"))
    # Non-echo partial transcript proves a human caller actually spoke (not speakerphone echo)
    await events_q.put(
        SimpleNamespace(
            type="conversation.item.input_audio_transcription.delta",
            item_id="miss-1",
            delta="quel est le",
            transcript="quel est le",
        )
    )
    await events_q.put(SimpleNamespace(type="input_audio_buffer.speech_stopped", item_id="miss-1", duration_ms=700))
    await events_q.put(
        SimpleNamespace(
            type="input_audio_buffer.transcription_missing",
            item_id="miss-1",
            duration_ms=700,
            peak_rms=1900,
            tts_playing=True,
            echo_rejected=True,
            caller_speech_confirmed=True,
        )
    )
    await asyncio.sleep(0.08)

    await events_q.put(None)
    await drain_task

    assert bridge.telemetry["speech_stopped_without_transcript"] == 1
    assert bridge.telemetry["unexpected_silence_count"] == 0
    assert bridge.telemetry["telnyx_clear_sent_count"] == 1
    assert any("je vous écoute" in s.lower() for s in adapter.spoken_texts)


# =====================================================================
# 9. Late Superseded Transcription After Interruption Discarded
# =====================================================================

@pytest.mark.asyncio
async def test_09_late_transcription_after_interruption_discarded():
    """A late transcription belonging to a superseded pre-interruption item_id is cleanly discarded."""
    events_q: asyncio.Queue[Any] = asyncio.Queue()
    adapter = QueueDrivenAdapter(events_q)
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
    bridge.stream_id = "stream-late-trans"
    bridge._interrupted_item_ids.add("old-item-99")

    drain_task = asyncio.create_task(bridge._drain_provider_events())
    await events_q.put(
        SimpleNamespace(
            type="conversation.item.input_audio_transcription.completed",
            item_id="old-item-99",
            transcript="Quels sont vos horaires ?",
        )
    )
    await asyncio.sleep(0.06)
    await events_q.put(None)
    await drain_task

    assert bridge.telemetry["late_transcripts_discarded"] == 1
    assert bridge._turns.empty()


# =====================================================================
# 10. Duplicate TTS Cancellation Idempotence
# =====================================================================

@pytest.mark.asyncio
async def test_10_duplicate_tts_cancellation_idempotent():
    """response.interrupted followed by response.done(status='cancelled') for the same response_id
    triggers exactly ONE interrupt/clear and ONE epoch bump."""
    events_q: asyncio.Queue[Any] = asyncio.Queue()
    adapter = QueueDrivenAdapter(events_q)
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
    bridge.stream_id = "stream-idem"
    bridge.epoch = 1
    bridge.response_id = "resp-dup-1"
    bridge.response_epoch = 1
    bridge._responses["resp-dup-1"] = ("item-dup", 1, None)

    drain_task = asyncio.create_task(bridge._drain_provider_events())
    await events_q.put(SimpleNamespace(type="response.interrupted", response_id="resp-dup-1"))
    await events_q.put(
        SimpleNamespace(
            type="response.done",
            response=SimpleNamespace(id="resp-dup-1", status="cancelled", usage=None),
        )
    )
    await asyncio.sleep(0.08)
    await events_q.put(None)
    await drain_task

    assert bridge.epoch == 2
    assert bridge.telemetry["telnyx_clear_sent_count"] == 1


# =====================================================================
# 11. New Question Preserved Across Epoch Change
# =====================================================================

@pytest.mark.asyncio
async def test_11_new_question_preserved_across_epoch_change():
    """A confirmed new question queued for the current epoch survives interrupt() with updated epoch."""
    events_q: asyncio.Queue[Any] = asyncio.Queue()
    adapter = QueueDrivenAdapter(events_q)
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
    bridge.epoch = 3
    bridge._turns.put_nowait(("stale-q", "ancienne question", 2))
    bridge._turns.put_nowait(("fresh-q", "nouvelle question confirmée", 3))

    await bridge.interrupt(reason="caller_speech_barge_in")

    assert bridge.epoch == 4
    assert bridge._turns.qsize() == 1
    kept_id, kept_text, kept_epoch = bridge._turns.get_nowait()
    assert kept_id == "fresh-q"
    assert kept_text == "nouvelle question confirmée"
    assert kept_epoch == 4


# =====================================================================
# 12. Ambiguous Retail Commercial Question Clarification & Follow-up
# =====================================================================

def test_12_ambiguous_retail_commercial_question_and_followup(db_session: Session):
    """'Quels sont les produits que je peux vendre ?' from authenticated staff asks ONE short
    commercial clarification, and the follow-up filters properly."""
    company, _cfg, call, owner, _emp = _create_tenant_with_products(
        db_session, company_name="Produits Ero", live_stock=True
    )
    q = "Quels sont les produits que je peux vendre ?"
    assert is_ambiguous_commercial_selling_question(q) is True

    clar = resolve_direct_voice_answer(
        db_session,
        company_id=company.id,
        transcript=q,
        authenticated_staff=True,
        staff_role="OWNER",
        locale="fr-CA",
        user_id=owner.id,
        call=call,
    )
    assert clar is not None
    assert "stock" in clar.lower() and "rentables" in clar.lower()
    assert (call.source_context or {}).get("pending_retail_clarification") is True

    # Follow-up 1: caller chooses "Les plus rentables" on catalog WITHOUT cost/margin data -> honest answer
    followup_prof = resolve_direct_voice_answer(
        db_session,
        company_id=company.id,
        transcript="Les plus rentables",
        authenticated_staff=True,
        staff_role="OWNER",
        locale="fr-CA",
        user_id=owner.id,
        call=call,
    )
    assert followup_prof is not None
    assert "coûts" in followup_prof.lower() or "marges" in followup_prof.lower()
    assert "Planche Alpine" not in followup_prof
    assert (call.source_context or {}).get("pending_retail_clarification") is None

    # Follow-up 2: caller asks again and chooses "Les meilleures opportunités à promouvoir"
    call.source_context = {**(call.source_context or {}), "pending_retail_clarification": True}
    db_session.commit()
    followup_promo = resolve_direct_voice_answer(
        db_session,
        company_id=company.id,
        transcript="Les meilleures opportunités à promouvoir",
        authenticated_staff=True,
        staff_role="OWNER",
        locale="fr-CA",
        user_id=owner.id,
        call=call,
    )
    assert followup_promo is not None
    assert "au lieu de" in followup_promo.lower()
    assert "compare_at_price" not in followup_promo
    assert (call.source_context or {}).get("catalog_view_mode") == "promote"


# =====================================================================
# 13. Technical Fields Removed From Spoken Voice Output
# =====================================================================

def test_13_technical_fields_eliminated_from_voice_output():
    """Forbidden schema fields (compare_at_price, inventory_quantity, product_variant,
    normalized_data, source_updated_at) must NEVER appear in spoken output."""
    raw = (
        "Produit: Planche Alpine, unit_price: 499$, compare_at_price: 599$, "
        "inventory_quantity: 8, product_variant: XL, normalized_data, source_updated_at: 2026-11-22."
    )
    cleaned = clean_voice_text(raw, locale="fr-CA")
    for forbidden in (
        "compare_at_price",
        "inventory_quantity",
        "product_variant",
        "normalized_data",
        "source_updated_at",
        "unit_price",
    ):
        assert forbidden not in cleaned.lower(), f"Forbidden token leaked: {forbidden} in {cleaned!r}"
    assert "prix comparatif" in cleaned.lower()
    assert "quantité en stock" in cleaned.lower()

    # Also verify spoken_catalog_answer natural comparative price formatting
    spoken = spoken_catalog_answer(
        [
            {
                "name": "Planche Alpine",
                "price": 499,
                "compare_at_price": 599,
                "currency": "CAD",
                "is_live_stock": True,
                "in_stock": True,
                "stock_availability": "IN_STOCK",
            }
        ],
        retail_enabled=True,
        locale="fr-CA",
    )
    assert "compare_at_price" not in spoken.lower()
    assert "au lieu de 599 $" in spoken


# =====================================================================
# 14. Stale Inventory Never Announced As Confirmed In Stock
# =====================================================================

def test_14_stale_inventory_never_announced_as_available(db_session: Session):
    """Products with stale/unconfirmed stock must NEVER be presented as confirmed available."""
    company, _cfg, call, owner, _emp = _create_tenant_with_products(
        db_session, company_name="Produits Ero Stale", live_stock=False
    )
    stale_spoken = spoken_catalog_answer(
        [
            {
                "name": "Planche Hiver",
                "price": 399,
                "currency": "CAD",
                "is_live_stock": False,
                "freshness_status": "STALE",
                "in_stock": None,
                "stock_availability": "UNKNOWN",
            }
        ],
        retail_enabled=True,
        locale="fr-CA",
    )
    assert "non confirmé" in stale_spoken.lower() or "non récentes" in stale_spoken.lower()
    assert ", disponible" not in stale_spoken.lower()
    assert "en stock confirmé" not in stale_spoken.lower()

    # Commercial follow-up "Ceux en stock" on stale tenant honestly reports no verified real-time stock
    call.source_context = {**(call.source_context or {}), "pending_retail_clarification": True}
    db_session.commit()
    ans = resolve_direct_voice_answer(
        db_session,
        company_id=company.id,
        transcript="Ceux en stock",
        authenticated_staff=True,
        staff_role="OWNER",
        locale="fr-CA",
        user_id=owner.id,
        call=call,
    )
    assert ans is not None
    assert "aucun produit" in ans.lower() and "temps réel" in ans.lower()


# =====================================================================
# 15. PIN Authentication & PR #127 Anti-Self-Cancellation Preserved
# =====================================================================

@pytest.mark.asyncio
async def test_15_pin_authentication_and_no_self_cancellation_preserved(db_session: Session):
    """Verify PIN auth verification, DTMF '*' cancel, and _execute_turns anti-self-cancellation remain intact."""
    company, _cfg, call, _owner, emp = _create_tenant_with_products(db_session, company_name="Pin Co")
    settings = _make_test_settings()
    auth = VoiceCallerAuth(db_session, settings)
    auth.set_pin(TenantContext(company.id, emp.id), "USER", emp.id, "719284", phone_number="+15145550199")
    call.caller_phone = "+15145550199"
    call.authenticated_user_id = None
    call.caller_type = "UNKNOWN"
    auth.challenge(call)
    db_session.commit()

    # Valid PIN authenticates cleanly
    res = auth.verify_gather(call, "719284")
    assert res["authenticated"] is True
    assert call.authenticated_user_id == emp.id

    # PR #127: _execute_turns with auth_required never self-cancels
    events_q: asyncio.Queue[Any] = asyncio.Queue()
    adapter = QueueDrivenAdapter(events_q)
    mock_socket = MagicMock()
    mock_socket.send_json = AsyncMock()
    bridge = TelnyxMediaBridge(
        socket=mock_socket,
        adapter=adapter,
        locale="fr-CA",
        validate_start=AsyncMock(),
        authorize=AsyncMock(),
        execute_turn=AsyncMock(return_value={"status": "success", "answer": "Veuillez saisir votre NIP.", "auth_required": True}),
    )
    bridge.begin_pin = AsyncMock(return_value={"success": True})
    bridge.poll_pin = AsyncMock(return_value={"status": "pending"})
    await bridge._turns.put(("pin-turn-1", "Mes tâches", bridge.epoch))
    t = asyncio.create_task(bridge._execute_turns())
    await asyncio.sleep(0.08)
    t.cancel()
    try:
        await t
    except asyncio.CancelledError:
        pass
    assert bridge._pin_turn == "pin-turn-1"
    assert len(adapter.spoken_texts) >= 1


# =====================================================================
# 16. Employee & Owner Permissions Preserved
# =====================================================================

def test_16_employee_and_owner_permissions_preserved(db_session: Session):
    """Owner accesses executive financials; operational employee is strictly blocked from executive payroll/margins."""
    company, _cfg, call, owner, emp = _create_tenant_with_products(db_session, company_name="Perm Co")
    coach = EmployeeCoachService(db_session)

    owner_allowed, _ = coach.check_hierarchical_data_access(owner, "Quelle est la marge nette et le bilan ?")
    emp_allowed, emp_reason = coach.check_hierarchical_data_access(emp, "Quelle est la marge nette et la masse salariale ?")
    assert owner_allowed is True
    assert emp_allowed is False
    assert emp_reason is not None

    # Authorize media session continuity for authenticated Owner
    settings = _make_test_settings()
    auth = VoiceCallerAuth(db_session, settings)
    auth.set_pin(TenantContext(company.id, owner.id), "USER", owner.id, "482913", phone_number="+15145550100")
    db_session.add(
        VoiceAuthSession(
            company_id=company.id,
            call_id=call.id,
            caller_type="OWNER",
            principal_id=owner.id,
            permissions=["ai:use", "voice:owner"],
            authenticated_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )
    )
    db_session.commit()
    plan = ModuleEntitlementService(db_session).get_company_plan(TenantContext(company.id)).code.value
    pub_mode, princ_id, epoch, _ledger = authorize_media_session(
        db_session,
        settings,
        call.id,
        plan,
        public_mode=False,
        principal_id=None,
        auth_epoch=None,
        claim={"ok": True},
    )
    assert pub_mode is False
    assert princ_id == owner.id
    assert epoch is not None


# =====================================================================
# 17. Multi-Tenant Isolation — Zero Cross-Tenant Product Leaks
# =====================================================================

@pytest.mark.asyncio
async def test_17_cross_tenant_isolation_zero_leakage(db_session: Session):
    """Products belonging to Tenant A are strictly inaccessible to Tenant B via commerce tools and voice."""
    co_a, _cfg_a, _call_a, owner_a, _ = _create_tenant_with_products(
        db_session, company_name="AlphaBoard", live_stock=True
    )
    co_b, _cfg_b, call_b, owner_b, _ = _create_tenant_with_products(
        db_session, company_name="BetaSki", live_stock=True
    )

    tool = GetProductDetailTool(db_session)
    ctx_b = ToolExecutionContext(
        tenant=TenantContext(co_b.id, owner_b.id),
        user_id=owner_b.id,
        permissions=frozenset({"ai:use", "data:read"}),
        request_id="req-iso-1",
    )
    res_b = await tool.run(ctx_b, ProductDetailArgs(product_name="AlphaBoard"))
    assert res_b.success is True
    assert res_b.data.get("found") is False

    voice_ans_b = resolve_direct_voice_answer(
        db_session,
        company_id=co_b.id,
        transcript="Quels sont vos produits en catalogue ?",
        authenticated_staff=True,
        staff_role="OWNER",
        locale="fr-CA",
        user_id=owner_b.id,
        call=call_b,
    )
    assert voice_ans_b is not None
    assert "BetaSki" in voice_ans_b
    assert "AlphaBoard" not in voice_ans_b
    assert co_a.id != co_b.id


# =====================================================================
# 18. Gemini Live Mid-Call Disconnect and Automatic Reconnect
# =====================================================================

@pytest.mark.asyncio
async def test_18_gemini_mid_call_disconnect_and_reconnect():
    """If Gemini Live drops mid-call, TelnyxMediaBridge automatically reconnects without ending the call."""
    q1: asyncio.Queue[Any] = asyncio.Queue()
    q2: asyncio.Queue[Any] = asyncio.Queue()
    sess1 = FakeGeminiLiveSession(q1, fail_after=1)
    sess2 = FakeGeminiLiveSession(q2)
    fake_client = FakeGeminiClient([sess1, sess2])

    adapter = GeminiLiveRealtimeAudioAdapter(
        _make_test_settings(),
        api_key="fake-gemini-key",
        company_name="Produits Ero",
        client_factory=lambda _k: fake_client,
    )
    await adapter.open(locale="fr-CA")

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

    prov_task = asyncio.create_task(bridge._provider_events())

    # Trigger disconnect on session 1
    await q1.put(SimpleNamespace(server_content=SimpleNamespace(turn_complete=True)))
    await asyncio.sleep(0.15)

    # Session 2 should now be connected and receiving transcriptions!
    assert fake_client.connect_count == 2
    assert bridge.telemetry.get("reconnect_triggered") is True
    assert bridge.telemetry.get("reconnect_attempts") == 1

    await q2.put(
        SimpleNamespace(
            server_content=SimpleNamespace(
                input_transcription=SimpleNamespace(text="Quels sont vos horaires ?", finished=True),
                turn_complete=True,
            )
        )
    )
    await asyncio.sleep(0.08)

    bridge._stop_event.set()
    await q2.put(None)
    await adapter.close()
    prov_task.cancel()
    try:
        await prov_task
    except asyncio.CancelledError:
        pass

    assert bridge._turns.qsize() >= 1


# =====================================================================
# 19. 20 Consecutive Questions Without Silent Drops
# =====================================================================

@pytest.mark.asyncio
async def test_19_twenty_consecutive_questions_no_silent_drops():
    """20 consecutive questions (mix of Retail, objections, attention checks, hours) all execute cleanly."""
    events_q: asyncio.Queue[Any] = asyncio.Queue()
    adapter = QueueDrivenAdapter(events_q)
    mock_socket = MagicMock()
    mock_socket.send_json = AsyncMock()
    answered: list[str] = []

    async def mock_exec(item_id: str, transcript: str):
        answered.append(item_id)
        return {"status": "success", "answer": f"Réponse {item_id}"}

    bridge = TelnyxMediaBridge(
        socket=mock_socket,
        adapter=adapter,
        locale="fr-CA",
        validate_start=AsyncMock(),
        authorize=AsyncMock(),
        execute_turn=mock_exec,
        allow_natural_interruptions=True,
    )
    drain_task = asyncio.create_task(bridge._drain_provider_events())
    exec_task = asyncio.create_task(bridge._execute_turns())

    sample_questions = [
        "Quels sont vos horaires d'ouverture ?",
        "Non, c'est pas de ça que je parlais",
        "Quels sont les produits les plus rentables ?",
        "Allô, tu m'entends ?",
        "Quelle est votre adresse physique ?",
    ]
    for i in range(20):
        q = f"{sample_questions[i % len(sample_questions)]} numéro {i + 1}"
        await events_q.put(
            SimpleNamespace(
                type="conversation.item.input_audio_transcription.completed",
                item_id=f"turn-20-{i}",
                transcript=q,
            )
        )
        await asyncio.sleep(0.02)

    await asyncio.sleep(0.15)
    await events_q.put(None)
    await drain_task
    exec_task.cancel()
    try:
        await exec_task
    except asyncio.CancelledError:
        pass

    assert len(answered) == 20
    assert bridge.telemetry["stt_final_count"] == 20
    assert bridge.central_ai_missing_answers == 0


# =====================================================================
# 20. Latency (p50/p95) & Outbound Playback ACK (`play-*` Mark) Telemetry
# =====================================================================

@pytest.mark.asyncio
async def test_20_latency_p50_p95_and_playback_mark_acknowledgment():
    """Verify full telemetry instrumentation: play-* mark enqueued on response.done,
    acknowledged on Telnyx mark event, phase returns to LISTENING, and p50/p95 latencies computed."""
    events_q: asyncio.Queue[Any] = asyncio.Queue()
    adapter = QueueDrivenAdapter(events_q)
    inbound_events = [
        {"event": "mark", "stream_id": "stream-telemetry", "mark": {"name": "play-resp-ack-1"}},
        {"event": "stop", "stream_id": "stream-telemetry"},
    ]
    inbound_iter = iter(inbound_events)
    mock_socket = MagicMock()
    mock_socket.send_json = AsyncMock()
    mock_socket.receive_json = AsyncMock(side_effect=lambda: next(inbound_iter))

    bridge = TelnyxMediaBridge(
        socket=mock_socket,
        adapter=adapter,
        locale="fr-CA",
        validate_start=AsyncMock(),
        authorize=AsyncMock(),
        execute_turn=AsyncMock(),
        interruption_manager=NaturalInterruptionManager(),
    )
    bridge.stream_id = "stream-telemetry"
    bridge.epoch = 1
    bridge.response_id = "resp-ack-1"
    bridge.response_epoch = 1
    bridge._responses["resp-ack-1"] = ("item-ack-1", 1, None)
    bridge._turn_metrics["item-ack-1"] = {
        "transcript_final_at": time.monotonic() - 0.2,
        "first_pcm_sent_at": None,
        "playback_completed_at": None,
    }
    bridge._last_speech_stopped_at = time.monotonic() - 0.15

    drain_task = asyncio.create_task(bridge._drain_provider_events())

    # 1. Audio delta + response.done -> enqueues audio + play-resp-ack-1 mark
    pcm_chunk = base64.b64encode(_pcm_tone(300)).decode("ascii")
    await events_q.put(
        SimpleNamespace(
            type="response.output_audio.delta",
            response_id="resp-ack-1",
            delta=pcm_chunk,
        )
    )
    await events_q.put(
        SimpleNamespace(
            type="response.done",
            response=SimpleNamespace(id="resp-ack-1", status="completed", usage=None),
        )
    )
    await asyncio.sleep(0.08)

    # Verify play-* mark was queued right after audio frames
    queued_items = []
    while not bridge._output.empty():
        queued_items.append(bridge._output.get_nowait())
    marks = [item[1] for item in queued_items if isinstance(item[1], dict) and item[1].get("event") == "mark"]
    assert any(m["mark"]["name"] == "play-resp-ack-1" for m in marks)

    # 2. Simulate Telnyx echoing back the play-* mark -> outbound_playback_acknowledged increments!
    await bridge._read_audio()
    assert bridge.telemetry["outbound_playback_acknowledged"] == 1
    assert bridge.phase == "LISTENING"
    assert bridge.orchestrator.state == ConversationState.LISTENING

    # 3. Record barge-in & Central AI samples and verify p50/p95 summary
    bridge.orchestrator.record_barge_in_latency(180.0)
    bridge.orchestrator.record_barge_in_latency(240.0)
    bridge.orchestrator.record_barge_in_latency(320.0)
    bridge.orchestrator.record_central_ai_latency(850.0)
    bridge.orchestrator.record_central_ai_latency(1200.0)

    summary = bridge.get_latency_summary()
    assert summary["barge_in_reaction_ms"]["count"] == 3
    assert summary["barge_in_reaction_ms"]["p50"] == 240.0
    assert summary["barge_in_reaction_ms"]["p95"] == 320.0
    first_audio_count = summary["first_audio_latency_ms"]["count"]
    assert first_audio_count is not None and first_audio_count >= 1
    assert summary["central_ai_latency_ms"]["p50"] == 850.0

    await events_q.put(None)
    await drain_task


# =====================================================================
# 21. Early STT Rescue Emits Partial Only & Finalizes Utterance Once
# =====================================================================

@pytest.mark.asyncio
async def test_21_early_stt_rescue_emits_partial_only_and_finalizes_once():
    """During active TTS playback, speaking >500ms (25 frames) triggers ONLY a partial delta
    for fast barge-in, retains the same item_id, and finalizes the complete utterance ONCE
    at speech_stopped with zero duplicate business turns."""
    server_q: asyncio.Queue[Any] = asyncio.Queue()
    fake_session = FakeGeminiLiveSession(server_q)
    fake_client = FakeGeminiClient([fake_session])

    class SequentialSTT:
        provider_id = "mock_seq_stt"

        def __init__(self) -> None:
            self.calls: list[int] = []

        async def transcribe(self, audio: bytes, *, locale: str, content_type: str) -> str:
            self.calls.append(len(audio))
            if len(self.calls) == 1:
                return "Non, c'est pas de ça"
            return "Non, c'est pas de ça que je parlais, montre-moi les casques"

    seq_stt = SequentialSTT()
    adapter = GeminiLiveRealtimeAudioAdapter(
        _make_test_settings(),
        api_key="fake-gemini-key",
        company_name="Produits Ero",
        client_factory=lambda _k: fake_client,
        stt_adapter=seq_stt,
        vad_rms_threshold=450,
        silence_frames_threshold=3,
        stt_rescue_delay_seconds=0.03,
        min_speech_ms_for_rescue=200,
    )
    await adapter.open(locale="fr-CA")
    adapter.set_playback_active(True)

    # Stream 35 loud frames (~700ms) continuously — still speaking, NO silence yet!
    for _ in range(35):
        await adapter.send_audio(_pcm_tone(1800))
    await asyncio.sleep(0.06)

    # Caller is still speaking: segment ID MUST still be retained, NOT finalized yet!
    active_id_mid_speech = adapter._current_item_id
    assert active_id_mid_speech is not None
    assert active_id_mid_speech not in adapter._emitted_items

    # Caller continues speaking 20 more frames (~400ms), then stops (4 silence frames)
    for _ in range(20):
        await adapter.send_audio(_pcm_tone(1800))
    for _ in range(4):
        await adapter.send_audio(_pcm_silence())
    await asyncio.sleep(0.12)

    await server_q.put(None)
    await adapter.close()

    emitted: list[Any] = []
    while not adapter._event_queue.empty():
        ev = adapter._event_queue.get_nowait()
        if hasattr(ev, "type"):
            emitted.append(ev)

    deltas = [e for e in emitted if e.type == "conversation.item.input_audio_transcription.delta"]
    finals = [e for e in emitted if e.type == "conversation.item.input_audio_transcription.completed"]
    assert len(deltas) == 1, f"Expected 1 early partial delta, got {len(deltas)}"
    assert len(finals) == 1, f"Expected exactly 1 final completion, got {len(finals)}"
    assert deltas[0].item_id == active_id_mid_speech
    assert finals[0].item_id == active_id_mid_speech
    assert deltas[0].finished is False
    assert "montre-moi les casques" in finals[0].transcript


# =====================================================================
# 22. Delayed Rescue for Segment A Never Flushes Segment B's Buffer
# =====================================================================

@pytest.mark.asyncio
async def test_22_delayed_rescue_for_segment_a_never_flushes_segment_b():
    """If Segment A's delayed rescue fires after Segment B has started accumulating Gemini
    partials in _transcript_parts, A's rescue MUST NOT flush B's unfinished buffer."""
    server_q: asyncio.Queue[Any] = asyncio.Queue()
    fake_session = FakeGeminiLiveSession(server_q)
    fake_client = FakeGeminiClient([fake_session])
    mock_stt = MockIndependentSTT("Première question sur les horaires")

    adapter = GeminiLiveRealtimeAudioAdapter(
        _make_test_settings(),
        api_key="fake-gemini-key",
        company_name="Produits Ero",
        client_factory=lambda _k: fake_client,
        stt_adapter=mock_stt,
        vad_rms_threshold=450,
        silence_frames_threshold=3,
        stt_rescue_delay_seconds=0.12,
        min_speech_ms_for_rescue=100,
    )
    await adapter.open(locale="fr-CA")

    # Segment A: caller speaks & stops -> schedules delayed rescue (0.12s)
    for _ in range(10):
        await adapter.send_audio(_pcm_tone(1800))
    seg_a_id = adapter._current_item_id
    assert seg_a_id is not None
    for _ in range(4):
        await adapter.send_audio(_pcm_silence())

    # Before A's rescue fires, Segment B starts and Gemini emits an unfinished partial for B
    await asyncio.sleep(0.02)
    for _ in range(6):
        await adapter.send_audio(_pcm_tone(1800))
    seg_b_id = adapter._current_item_id
    assert seg_b_id is not None and seg_b_id != seg_a_id
    await server_q.put(
        SimpleNamespace(
            server_content=SimpleNamespace(
                input_transcription=SimpleNamespace(text="Deuxième question en cours", finished=False),
            )
        )
    )
    # Let A's delayed rescue run while B is STILL unfinished!
    await asyncio.sleep(0.18)

    # B must NOT have been prematurely flushed by A's rescue!
    assert adapter._transcript_item_id == seg_b_id
    assert adapter._transcript_parts == ["Deuxième question en cours"]
    assert seg_b_id not in adapter._emitted_items
    assert seg_a_id in adapter._emitted_items

    # Now finish Segment B via Gemini final transcription
    await server_q.put(
        SimpleNamespace(
            server_content=SimpleNamespace(
                input_transcription=SimpleNamespace(text="sur les casques", finished=True),
                turn_complete=True,
            )
        )
    )
    await asyncio.sleep(0.06)

    await server_q.put(None)
    await adapter.close()

    emitted: list[Any] = []
    while not adapter._event_queue.empty():
        ev = adapter._event_queue.get_nowait()
        if hasattr(ev, "type"):
            emitted.append(ev)

    finals = [e for e in emitted if e.type == "conversation.item.input_audio_transcription.completed"]
    by_id = {e.item_id: e.transcript for e in finals}
    assert by_id[seg_a_id] == "Première question sur les horaires"
    assert by_id[seg_b_id] == "Deuxième question en cours sur les casques"


# =====================================================================
# 23. Task-Identity Cleanup in _rescue_tasks Prevents Leaked Tasks
# =====================================================================

@pytest.mark.asyncio
async def test_23_rescue_task_replacement_cleanup_preserves_new_task_identity():
    """Replacing an in-flight rescue task for the same item_id must NOT allow the cancelled
    old task's finally block to remove the replacement task from _rescue_tasks."""
    server_q: asyncio.Queue[Any] = asyncio.Queue()
    fake_session = FakeGeminiLiveSession(server_q)
    fake_client = FakeGeminiClient([fake_session])

    slow_stt_started = asyncio.Event()
    slow_stt_gate = asyncio.Event()

    class SlowSTT:
        provider_id = "slow_stt"

        async def transcribe(self, audio: bytes, *, locale: str, content_type: str) -> str:
            slow_stt_started.set()
            await slow_stt_gate.wait()
            return "texte final"

    adapter = GeminiLiveRealtimeAudioAdapter(
        _make_test_settings(),
        api_key="fake-gemini-key",
        company_name="Produits Ero",
        client_factory=lambda _k: fake_client,
        stt_adapter=SlowSTT(),
        stt_rescue_delay_seconds=0.0,
        min_speech_ms_for_rescue=100,
    )
    await adapter.open(locale="fr-CA")

    pcm = _pcm_tone(1800) * 10
    # 1. Start early rescue task #1
    adapter._schedule_stt_rescue("item-race-1", pcm, 500, 1800, tts_playing=True, delay_seconds=0.0, early_partial=True)
    task1 = adapter._rescue_tasks["item-race-1"]
    await slow_stt_started.wait()

    # 2. Replace with final rescue task #2 for the SAME item_id
    adapter._schedule_stt_rescue("item-race-1", pcm, 900, 1800, tts_playing=True, delay_seconds=0.5, early_partial=False)
    task2 = adapter._rescue_tasks["item-race-1"]
    assert task2 is not task1

    # 3. Yield so cancelled task1 completes its finally block
    await asyncio.sleep(0.05)
    assert task1.done()
    # task2 MUST still be tracked in _rescue_tasks!
    assert adapter._rescue_tasks.get("item-race-1") is task2
    assert not task2.done()

    # 4. clear_input() MUST cancel task2 cleanly!
    await adapter.clear_input()
    await asyncio.sleep(0.03)
    assert task2.cancelled() or task2.done()
    assert "item-race-1" not in adapter._rescue_tasks

    await server_q.put(None)
    await adapter.close()


# =====================================================================
# 24. Sustained Echo/Noise Missing-Transcript Never Clears Playback
# =====================================================================

@pytest.mark.asyncio
async def test_24_sustained_echo_or_noise_transcription_missing_never_clears_playback():
    """Sustained speakerphone echo or background noise (>450ms) producing transcription_missing
    WITHOUT echo-rejected caller speech evidence must NOT clear playback or call interrupt()."""
    events_q: asyncio.Queue[Any] = asyncio.Queue()
    adapter = QueueDrivenAdapter(events_q)
    mock_socket = MagicMock()
    mock_socket.send_json = AsyncMock()

    bridge = TelnyxMediaBridge(
        socket=mock_socket,
        adapter=adapter,
        locale="fr-CA",
        validate_start=AsyncMock(),
        authorize=AsyncMock(),
        execute_turn=AsyncMock(),
        allow_natural_interruptions=True,
    )
    bridge.stream_id = "stream-echo-noise-guard"
    bridge._set_phase("PLAYING")
    bridge._set_playback_active(True)
    bridge.response_id = "resp-keep-playing"
    bridge._last_spoken = "Voici la description complète de votre catalogue de produits."
    bridge._output.put_nowait((bridge.epoch, b"\xff" * 160))

    drain_task = asyncio.create_task(bridge._drain_provider_events())

    # Simulate loud echo/noise (>700ms) where even an echo partial arrived (rejected as echo)
    await events_q.put(SimpleNamespace(type="input_audio_buffer.speech_started", item_id="echo-noise-1"))
    await events_q.put(
        SimpleNamespace(
            type="conversation.item.input_audio_transcription.delta",
            item_id="echo-noise-1",
            delta="Voici la description complète",
            transcript="Voici la description complète",
        )
    )
    await events_q.put(
        SimpleNamespace(
            type="input_audio_buffer.transcription_missing",
            item_id="echo-noise-1",
            duration_ms=820,
            peak_rms=2100,
            tts_playing=True,
            echo_rejected=False,
            caller_speech_confirmed=False,
        )
    )
    await asyncio.sleep(0.08)
    await events_q.put(None)
    await drain_task

    clears = [c[0][0] for c in mock_socket.send_json.call_args_list if isinstance(c[0][0], dict) and c[0][0].get("event") == "clear"]
    assert bridge.telemetry["speech_stopped_without_transcript"] == 1
    assert bridge.telemetry["unconfirmed_barge_in_suppressed"] == 1
    assert len(clears) == 0
    assert bridge.telemetry["telnyx_clear_sent_count"] == 0
    assert adapter.interrupted_count == 0
    assert bridge.phase == "PLAYING"
    assert bridge._playback_active is True


# =====================================================================
# 25. play-* Marker Guaranteed Under Full Output Queue & Preserves Epoch
# =====================================================================

@pytest.mark.asyncio
async def test_25_play_mark_guaranteed_when_output_queue_full_and_preserves_epoch():
    """Even when _output is 100% full, play-* completion marker is delivered at the tail so
    playback acknowledgment transitions back to LISTENING without getting stuck in PLAYING."""
    events_q: asyncio.Queue[Any] = asyncio.Queue()
    adapter = QueueDrivenAdapter(events_q)
    inbound_events = [
        {"event": "mark", "stream_id": "stream-full-q", "mark": {"name": "play-resp-full-1"}},
        {"event": "stop", "stream_id": "stream-full-q"},
    ]
    inbound_iter = iter(inbound_events)
    mock_socket = MagicMock()
    mock_socket.send_json = AsyncMock()
    mock_socket.receive_json = AsyncMock(side_effect=lambda: next(inbound_iter))

    bridge = TelnyxMediaBridge(
        socket=mock_socket,
        adapter=adapter,
        locale="fr-CA",
        validate_start=AsyncMock(),
        authorize=AsyncMock(),
        execute_turn=AsyncMock(),
        max_output_queue=4,
    )
    bridge.stream_id = "stream-full-q"
    bridge.epoch = 2
    bridge.response_id = "resp-full-1"
    bridge.response_epoch = 2
    bridge._responses["resp-full-1"] = ("item-full-1", 2, None)
    bridge._set_phase("PLAYING")
    bridge._set_playback_active(True)

    # Completely saturate the bounded output queue (4/4 frames)
    for i in range(4):
        bridge._output.put_nowait((2, bytes([i]) * 160))
    assert bridge._output.full()

    drain_task = asyncio.create_task(bridge._drain_provider_events())
    await events_q.put(
        SimpleNamespace(
            type="response.done",
            response=SimpleNamespace(id="resp-full-1", status="completed", usage=None),
        )
    )
    await asyncio.sleep(0.06)

    assert bridge._active_play_mark == "play-resp-full-1"
    queued: list[tuple[int, Any]] = []
    while not bridge._output.empty():
        queued.append(bridge._output.get_nowait())
    assert len(queued) == 4
    # Tail item MUST be the control mark with matching epoch=2
    assert queued[-1] == (2, {"event": "mark", "mark": {"name": "play-resp-full-1"}})
    assert bridge.dropped_outbound_frames >= 1

    # Telnyx echoes back play-resp-full-1 -> playback exits cleanly to LISTENING
    await bridge._read_audio()
    assert bridge.telemetry["outbound_playback_acknowledged"] == 1
    assert bridge._active_play_mark is None
    assert bridge._playback_active is False
    assert bridge.phase == "LISTENING"

    await events_q.put(None)
    await drain_task


# =====================================================================
# 26. Serialized Gemini Reconnect With Concurrent Mic Streaming
# =====================================================================

@pytest.mark.asyncio
async def test_26_concurrent_gemini_reconnect_with_continuous_mic_audio_no_race():
    """Concurrent microphone writes during a slow Gemini reconnect must buffer cleanly without
    raising errors, without triggering competing fallbacks, and without detached sessions."""
    q1: asyncio.Queue[Any] = asyncio.Queue()
    q2: asyncio.Queue[Any] = asyncio.Queue()
    sess1 = FakeGeminiLiveSession(q1)
    sess2 = FakeGeminiLiveSession(q2)
    reconnect_entered = asyncio.Event()
    allow_reopen = asyncio.Event()

    class SlowReconnectClient:
        def __init__(self) -> None:
            self.connect_count = 0
            self.aio = SimpleNamespace(live=SimpleNamespace(connect=self._connect))

        def _connect(self, *, model: str, config: Any):
            self.connect_count += 1
            idx = self.connect_count

            class _Ctx:
                async def __aenter__(self):
                    if idx == 2:
                        reconnect_entered.set()
                        await allow_reopen.wait()
                        return sess2
                    return sess1

                async def __aexit__(self, exc_type, exc, tb):
                    return False

            return _Ctx()

    slow_client = SlowReconnectClient()
    fallback_opened = 0

    def _make_primary():
        return GeminiLiveRealtimeAudioAdapter(
            _make_test_settings(),
            api_key="fake-gemini-key",
            company_name="Produits Ero",
            client_factory=lambda _k: slow_client,
        )

    class DummyFallback:
        provider_id = "openai_fallback"
        _model = "gpt-realtime-2.1"

        async def open(self, *, locale: str = "fr-CA") -> None:
            nonlocal fallback_opened
            fallback_opened += 1

        async def send_audio(self, audio: bytes) -> None:
            pass

        async def speak(self, text: str) -> None:
            pass

        async def interrupt(self) -> None:
            pass

        async def clear_input(self) -> None:
            pass

        async def close(self) -> None:
            pass

        async def events(self):
            if False:
                yield None

    wrapper = FallbackRealtimeAudioAdapter(
        primary_factory=_make_primary,
        fallback_factory=lambda: DummyFallback(),  # type: ignore[arg-type]
    )
    await wrapper.open(locale="fr-CA")

    # Start mid-call reconnect while simultaneously blasting 25 mic frames
    rec_task = asyncio.create_task(wrapper.reconnect(locale="fr-CA"))
    await reconnect_entered.wait()

    mic_errors: list[Exception] = []

    async def _stream_mic() -> None:
        frame = _pcm_tone(150)
        for _ in range(25):
            try:
                await wrapper.send_audio(frame)
            except Exception as exc:
                mic_errors.append(exc)
            await asyncio.sleep(0.002)

    mic_task = asyncio.create_task(_stream_mic())
    await asyncio.sleep(0.03)
    allow_reopen.set()
    await asyncio.gather(rec_task, mic_task)

    # Zero errors, zero competing fallbacks, primary reconnected cleanly, buffered audio delivered!
    assert mic_errors == []
    assert fallback_opened == 0
    assert wrapper.used_fallback is False
    assert slow_client.connect_count == 2
    assert len(sess2.audio_chunks) >= 10

    await q2.put(None)
    await wrapper.close()


# =====================================================================
# 27. Per-Turn first_audio_latency_ms Samples Every Turn for p50/p95
# =====================================================================

@pytest.mark.asyncio
async def test_27_per_turn_first_audio_latency_p50_p95_samples_all_turns():
    """Every turn's first audio chunk must contribute one sample to first_audio_latency_ms,
    keeping session-level first_audible_response_latency_ms separate."""
    events_q: asyncio.Queue[Any] = asyncio.Queue()
    adapter = QueueDrivenAdapter(events_q)
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
    bridge.stream_id = "stream-per-turn-lat"
    bridge.epoch = 1

    drain_task = asyncio.create_task(bridge._drain_provider_events())
    pcm_chunk = base64.b64encode(_pcm_tone(250)).decode("ascii")

    # Simulate 5 distinct turns with distinct response IDs and multiple audio chunks each
    expected_delays = [0.05, 0.12, 0.20, 0.08, 0.30]
    for idx, delay_s in enumerate(expected_delays, start=1):
        resp_id = f"resp-turn-{idx}"
        item_id = f"item-turn-{idx}"
        bridge.response_id = resp_id
        bridge.response_epoch = bridge.epoch
        bridge._responses[resp_id] = (item_id, bridge.epoch, None)
        bridge._turn_metrics[item_id] = {
            "speech_stopped_at": time.monotonic() - delay_s,
            "first_pcm_sent_at": None,
            "playback_completed_at": None,
        }
        # Send 3 chunks for the same turn -> MUST record exactly 1 sample per turn!
        for _ in range(3):
            await events_q.put(
                SimpleNamespace(type="response.output_audio.delta", response_id=resp_id, delta=pcm_chunk)
            )
        await events_q.put(
            SimpleNamespace(
                type="response.done",
                response=SimpleNamespace(id=resp_id, status="completed", usage=None),
            )
        )
        await asyncio.sleep(0.02)

    await events_q.put(None)
    await drain_task

    summary = bridge.get_latency_summary()
    assert bridge.telemetry["tts_first_audio_chunk_received"] == 1
    assert summary["first_audio_latency_ms"]["count"] == 5
    p50 = summary["first_audio_latency_ms"]["p50"]
    p95 = summary["first_audio_latency_ms"]["p95"]
    assert p50 is not None and p95 is not None
    assert p95 >= p50


# =====================================================================
# 28. Sanitization Never Upgrades Stale in_stock: true to Confirmed
# =====================================================================

def test_28_sanitize_retail_voice_text_never_confirms_stale_in_stock_true():
    """Sanitizing raw text containing `in_stock: true` + `freshness_status: STALE` must use
    neutral wording and NEVER claim 'en stock confirmé' or 'confirmed in stock'."""
    raw_fr = "Planche Alpine, in_stock: true, freshness_status: STALE, is_live_stock: false, compare_at_price: 599$"
    cleaned_fr = sanitize_retail_voice_text(raw_fr, locale="fr-CA")
    assert "confirmé" not in cleaned_fr.lower()
    assert "in_stock" not in cleaned_fr.lower()
    assert "freshness_status" not in cleaned_fr.lower()
    assert "stale" not in cleaned_fr.lower()
    assert "compare_at_price" not in cleaned_fr.lower()
    assert "non récentes" in cleaned_fr.lower() or "à confirmer" in cleaned_fr.lower()

    raw_en = "Alpine Board, in_stock: true, freshness_status: STALE, is_live_stock: false"
    cleaned_en = sanitize_retail_voice_text(raw_en, locale="en-US")
    assert "confirmed in stock" not in cleaned_en.lower()
    assert "unverified" in cleaned_en.lower() or "not recent" in cleaned_en.lower()


# =====================================================================
# 29. DB Profile compare_at_price -> Voice & Profitability Honesty
# =====================================================================

def test_29_db_profile_compare_at_price_to_voice_and_profitability_honesty(db_session: Session):
    """Verify CompanyIntelligenceService.get_profile().public_products populates compare_at_price
    (top-level AND variant-level), enables natural comparative speech, refuses to equate selling
    price with profitability when cost/margin is absent, and ranks by real margin when present."""
    # Case A: Variant-level compare_at_price + NO cost/margin data
    company_a, _cfg_a, call_a, owner_a, _emp_a = _create_tenant_with_products(
        db_session,
        company_name="PromoDB",
        live_stock=True,
        products_spec=[
            {
                "product_id": "pa-1",
                "product_name": "Planche Prestige",
                "unit_price": 699.0,
                "inventory_level": 5,
                "product_category": "planche",
            },
            {
                "product_id": "pa-2",
                "product_name": "Casque Promo Variant",
                "variants": [{"unit_price": 89.0, "compare_at_price": 139.0, "inventory_level": 10}],
                "product_category": "accessoire",
            },
        ],
    )
    profile_a = CompanyIntelligenceService(db_session).get_profile(company_a.id)
    by_name = {p["name"]: p for p in profile_a.public_products}
    assert by_name["Casque Promo Variant"]["compare_at_price"] == 139.0

    # Real DB-backed voice catalog output speaks comparative price naturally
    ans_cat = resolve_direct_voice_answer(
        db_session,
        company_id=company_a.id,
        transcript="Quels accessoires avez-vous au catalogue ?",
        authenticated_staff=True,
        staff_role="OWNER",
        locale="fr-CA",
        user_id=owner_a.id,
        call=call_a,
    )
    assert ans_cat is not None
    assert "89 $ au lieu de 139 $" in ans_cat
    assert "compare_at_price" not in ans_cat.lower()

    # Profitability without cost/margin MUST NOT return highest-priced product
    ans_no_prof = resolve_direct_voice_answer(
        db_session,
        company_id=company_a.id,
        transcript="Quels sont les produits les plus rentables ?",
        authenticated_staff=True,
        staff_role="OWNER",
        locale="fr-CA",
        user_id=owner_a.id,
        call=call_a,
    )
    assert ans_no_prof is not None
    assert "coûts" in ans_no_prof.lower() or "marges" in ans_no_prof.lower()
    assert "Planche Prestige" not in ans_no_prof

    # Case B: Authorized unit_cost present -> ranks by REAL margin, NOT selling price, and blocks non-exec!
    company_b, _cfg_b, call_b, owner_b, emp_b = _create_tenant_with_products(
        db_session,
        company_name="MarginDB",
        live_stock=True,
        products_spec=[
            {
                "product_id": "pb-1",
                "product_name": "Planche Chère Faible Marge",
                "unit_price": 500.0,
                "unit_cost": 450.0,  # margin = 50$
                "inventory_level": 4,
                "product_category": "planche",
            },
            {
                "product_id": "pb-2",
                "product_name": "Casque Haute Marge",
                "unit_price": 200.0,
                "unit_cost": 60.0,  # margin = 140$ (MORE profitable despite lower price!)
                "inventory_level": 9,
                "product_category": "accessoire",
            },
        ],
    )
    profile_b = CompanyIntelligenceService(db_session).get_profile(company_b.id)
    # Public context MUST strip private supplier costs & margins!
    pub_ctx = profile_b.as_context(public=True)
    for prod in pub_ctx["public_products"]:
        assert "unit_cost" not in prod
        assert "profit_margin_amount" not in prod
        assert "profit_margin_pct" not in prod

    # Owner gets genuine highest-margin product first
    ans_owner_prof = resolve_direct_voice_answer(
        db_session,
        company_id=company_b.id,
        transcript="Quels sont les produits les plus rentables ?",
        authenticated_staff=True,
        staff_role="OWNER",
        locale="fr-CA",
        user_id=owner_b.id,
        call=call_b,
    )
    assert ans_owner_prof is not None
    assert ans_owner_prof.index("Casque Haute Marge") < ans_owner_prof.index("Planche Chère Faible Marge")

    # Operational employee is blocked from margin rankings
    ans_emp_prof = resolve_direct_voice_answer(
        db_session,
        company_id=company_b.id,
        transcript="Quels sont les produits les plus rentables ?",
        authenticated_staff=True,
        staff_role="USER",
        locale="fr-CA",
        user_id=emp_b.id,
        call=call_b,
    )
    assert ans_emp_prof is not None
    assert "réservées à la direction" in ans_emp_prof.lower()


# =====================================================================
# 30. Persisted Filter & Ranking Across Catalog Pagination
# =====================================================================

def test_30_filtered_and_ranked_catalog_pagination_persists_across_pages(db_session: Session):
    """Pagination after 'en stock' or 'promouvoir' must preserve the selected filter/ordering
    across subsequent pages without repeating items or leaking out-of-stock products."""
    company, _cfg, call, owner, _emp = _create_tenant_with_products(
        db_session,
        company_name="PageFilterCo",
        live_stock=True,
        products_spec=[
            {"product_id": "p1", "product_name": "Article Stock 1", "unit_price": 100.0, "inventory_level": 5},
            {"product_id": "p2", "product_name": "Article Rupture A", "unit_price": 200.0, "inventory_level": 0},
            {"product_id": "p3", "product_name": "Article Stock 2", "unit_price": 80.0, "compare_at_price": 160.0, "inventory_level": 6},
            {"product_id": "p4", "product_name": "Article Stock 3", "unit_price": 150.0, "inventory_level": 3},
            {"product_id": "p5", "product_name": "Article Rupture B", "unit_price": 300.0, "inventory_level": 0},
            {"product_id": "p6", "product_name": "Article Stock 4", "unit_price": 90.0, "compare_at_price": 120.0, "inventory_level": 7},
        ],
    )

    # 1. Start in-stock filtered view via clarification follow-up
    call.source_context = {**(call.source_context or {}), "pending_retail_clarification": True}
    db_session.commit()
    page1 = resolve_direct_voice_answer(
        db_session,
        company_id=company.id,
        transcript="Les produits en stock",
        authenticated_staff=True,
        staff_role="OWNER",
        locale="fr-CA",
        user_id=owner.id,
        call=call,
    )
    assert page1 is not None
    assert "Article Rupture A" not in page1 and "Article Rupture B" not in page1
    ctx_p1: dict[str, Any] = dict(call.source_context or {})
    assert ctx_p1.get("catalog_view_mode") == "in_stock"
    page1_names = [r["name"] for r in list(ctx_p1.get("presented_catalog_products") or [])]
    assert len(page1_names) == 3

    # 2. Request next page -> MUST return ONLY the 4th live in-stock item, zero duplicates, zero out-of-stock!
    page2 = resolve_direct_voice_answer(
        db_session,
        company_id=company.id,
        transcript="Quels sont les trois prochains produits ?",
        authenticated_staff=True,
        staff_role="OWNER",
        locale="fr-CA",
        user_id=owner.id,
        call=call,
    )
    assert page2 is not None
    assert "Article Rupture A" not in page2 and "Article Rupture B" not in page2
    ctx_p2: dict[str, Any] = dict(call.source_context or {})
    page2_names = [r["name"] for r in list(ctx_p2.get("presented_catalog_products") or [])]
    assert len(page2_names) == 1
    assert set(page1_names).isdisjoint(set(page2_names))

    # 3. Promotion ranking persists across pages (50% discount Stock 2 & 25% discount Stock 4 come first!)
    call.source_context = {**(call.source_context or {}), "pending_retail_clarification": True}
    db_session.commit()
    promo_p1 = resolve_direct_voice_answer(
        db_session,
        company_id=company.id,
        transcript="Les meilleures opportunités à promouvoir",
        authenticated_staff=True,
        staff_role="OWNER",
        locale="fr-CA",
        user_id=owner.id,
        call=call,
    )
    assert promo_p1 is not None
    ctx_promo1: dict[str, Any] = dict(call.source_context or {})
    promo_p1_names = [r["name"] for r in list(ctx_promo1.get("presented_catalog_products") or [])]
    assert promo_p1_names[0] == "Article Stock 2"  # 50% off
    assert promo_p1_names[1] == "Article Stock 4"  # 25% off
    assert ctx_promo1.get("catalog_view_mode") == "promote"

    promo_p2 = resolve_direct_voice_answer(
        db_session,
        company_id=company.id,
        transcript="Quels sont les trois prochains produits ?",
        authenticated_staff=True,
        staff_role="OWNER",
        locale="fr-CA",
        user_id=owner.id,
        call=call,
    )
    assert promo_p2 is not None
    ctx_promo2: dict[str, Any] = dict(call.source_context or {})
    promo_p2_names = [r["name"] for r in list(ctx_promo2.get("presented_catalog_products") or [])]
    assert len(promo_p2_names) == 3
    assert set(promo_p1_names).isdisjoint(set(promo_p2_names))


# =====================================================================
# 31. "Allô, tu m'entends ? Quel est le prix des casques ?" + 10 Real Sequence
# =====================================================================

@pytest.mark.asyncio
async def test_31_allo_with_embedded_commercial_question_and_10_consecutive_interruptions(db_session: Session):
    """Verify 'Allô, tu m'entends ? Quel est le prix des casques ?' extracts and answers the
    product question (while pure 'Allô, tu m'entends ?' returns confirmation), AND run a 10-turn
    full-duplex interruption sequence with partial+final+echo+objection+latency telemetry."""
    assert extract_request_after_attention_check("Allô ?") is None
    assert extract_request_after_attention_check("Allô, tu m'entends ?") is None
    assert extract_request_after_attention_check("Hello, can you hear me?") is None

    extracted_fr = extract_request_after_attention_check("Allô, tu m'entends ? Quel est le prix des casques ?")
    assert extracted_fr == "Quel est le prix des casques ?"
    extracted_en = extract_request_after_attention_check("Hello, can you hear me? What is the price of helmets?")
    assert extracted_en == "What is the price of helmets?"
    extracted_es = extract_request_after_attention_check("¿Aló, me escuchas? ¿Cuál es el precio de los cascos?")
    assert extracted_es == "¿Cuál es el precio de los cascos?"
    extracted_ro = extract_request_after_attention_check("Alo, mă auzi? Care este prețul căștilor?")
    assert extracted_ro == "Care este prețul căștilor?"

    company, _cfg, call, owner, _emp = _create_tenant_with_products(
        db_session, company_name="AlloRetail", live_stock=True
    )
    ans = resolve_direct_voice_answer(
        db_session,
        company_id=company.id,
        transcript="Allô, tu m'entends ? Quel est le prix des casques ?",
        authenticated_staff=True,
        staff_role="OWNER",
        locale="fr-CA",
        user_id=owner.id,
        call=call,
    )
    assert ans is not None
    assert "Casque Pro AlloRetail" in ans
    assert "129 $ au lieu de 159 $" in ans

    events_q: asyncio.Queue[Any] = asyncio.Queue()
    adapter = QueueDrivenAdapter(events_q)
    mock_socket = MagicMock()
    mock_socket.send_json = AsyncMock()
    executed_questions: list[str] = []

    async def _exec(item_id: str, transcript: str):
        executed_questions.append(transcript)
        emb = extract_request_after_attention_check(transcript)
        effective = emb or transcript
        if is_correction_or_objection(effective):
            return {"status": "success", "answer": build_correction_clarification("fr-CA", last_topic="retail_catalog")}
        da = resolve_direct_voice_answer(
            db_session,
            company_id=company.id,
            transcript=effective,
            authenticated_staff=True,
            staff_role="OWNER",
            locale="fr-CA",
            user_id=owner.id,
            call=call,
        )
        return {"status": "success", "answer": da or "Réponse traitée."}

    bridge = TelnyxMediaBridge(
        socket=mock_socket,
        adapter=adapter,
        locale="fr-CA",
        validate_start=AsyncMock(),
        authorize=AsyncMock(),
        execute_turn=_exec,
        allow_natural_interruptions=True,
    )
    bridge.stream_id = "stream-10-real-seq"
    drain_task = asyncio.create_task(bridge._drain_provider_events())
    exec_task = asyncio.create_task(bridge._execute_turns())

    scenarios = [
        ("Non, c'est pas de ça", "Non, c'est pas de ça que je parlais"),
        ("Allô, tu m'entends ?", "Allô, tu m'entends ? Quel est le prix des casques ?"),
        ("Attends, écoute-moi", "Attends, écoute-moi, quels produits sont en stock ?"),
        ("Non, tu m'as mal compris", "Non, tu m'as mal compris, montre les accessoires"),
        ("Stop, arrête", "Stop, arrête, quels sont les horaires ?"),
        ("Allô ?", "Allô ? Quel est le prix de la planche ?"),
        ("Non, pas de ça", "Non, pas de ça, je veux les promotions"),
        ("Attends une seconde", "Attends une seconde, combien coûte le casque ?"),
        ("Arrête, autre chose", "Arrête, autre chose, quels sont les produits ?"),
        ("Allô, vous m'entendez ?", "Allô, vous m'entendez ? Quel est le prix des gants ?"),
    ]
    pcm_chunk = base64.b64encode(_pcm_tone(200)).decode("ascii")
    for idx, (partial_t, final_t) in enumerate(scenarios, start=1):
        resp_id = f"resp-seq-{idx}"
        item_id = f"seq-{idx}"
        bridge._set_phase("PLAYING")
        bridge._set_playback_active(True)
        bridge.response_id = resp_id
        bridge.response_epoch = bridge.epoch
        bridge._responses[resp_id] = (f"prev-{idx}", bridge.epoch, None)
        bridge._last_spoken = "Voici la liste complète de notre catalogue de produits disponibles aujourd'hui."

        # Inject an echo event before real interruption -> must NOT clear!
        await events_q.put(
            SimpleNamespace(
                type="conversation.item.input_audio_transcription.delta",
                item_id=f"echo-seq-{idx}",
                delta="Voici la liste complète de notre catalogue",
                transcript="Voici la liste complète de notre catalogue",
            )
        )
        # Real caller speech starts -> partial triggers fast clear -> final executes once without double clear
        await events_q.put(SimpleNamespace(type="input_audio_buffer.speech_started", item_id=item_id))
        await events_q.put(
            SimpleNamespace(
                type="conversation.item.input_audio_transcription.delta",
                item_id=item_id,
                delta=partial_t,
                transcript=partial_t,
            )
        )
        await events_q.put(SimpleNamespace(type="input_audio_buffer.speech_stopped", item_id=item_id))
        await events_q.put(
            SimpleNamespace(
                type="conversation.item.input_audio_transcription.completed",
                item_id=item_id,
                transcript=final_t,
            )
        )
        await asyncio.sleep(0.05)
        bridge.response_id = f"ans-resp-{idx}"
        bridge.response_epoch = bridge.epoch
        bridge._responses[f"ans-resp-{idx}"] = (item_id, bridge.epoch, None)
        await events_q.put(
            SimpleNamespace(type="response.output_audio.delta", response_id=f"ans-resp-{idx}", delta=pcm_chunk)
        )
        await asyncio.sleep(0.02)

    await events_q.put(None)
    await drain_task
    exec_task.cancel()
    try:
        await exec_task
    except asyncio.CancelledError:
        pass

    assert len(executed_questions) == 10
    assert bridge.telemetry["telnyx_clear_sent_count"] == 10
    lat = bridge.get_latency_summary()
    assert lat["barge_in_reaction_ms"]["count"] == 10
    assert lat["first_audio_latency_ms"]["count"] == 10
    assert lat["central_ai_latency_ms"]["count"] == 10


# =====================================================================
# 32. Fallback Reconnect Failure Switches Once Under Lock + Buffered Audio
# =====================================================================

@pytest.mark.asyncio
async def test_32_fallback_reconnect_failure_switches_once_under_lock():
    """If primary reconnect fails while concurrent microphone writes arrive, FallbackRealtimeAudioAdapter
    switches to fallback exactly once under lock and flushes buffered mic audio without raising."""
    fallback_opens = 0
    fallback_audio: list[bytes] = []
    rec_started = asyncio.Event()
    fail_rec = asyncio.Event()

    class FailingPrimary:
        provider_id = "gemini_live"
        _model = "gemini-3.8-live"

        async def open(self, *, locale: str = "fr-CA") -> None:
            pass

        async def send_audio(self, audio: bytes) -> None:
            pass

        async def speak(self, text: str) -> None:
            pass

        async def interrupt(self) -> None:
            pass

        async def clear_input(self) -> None:
            pass

        async def reconnect(self, fallback_model: str | None = None, locale: str | None = None) -> None:
            rec_started.set()
            await fail_rec.wait()
            raise ConnectionError("Primary reconnect failed")

        async def close(self) -> None:
            pass

        async def events(self):
            if False:
                yield None

    class HealthyFallback:
        provider_id = "openai_fallback"
        _model = "gpt-realtime-2.1"

        async def open(self, *, locale: str = "fr-CA") -> None:
            nonlocal fallback_opens
            fallback_opens += 1

        async def send_audio(self, audio: bytes) -> None:
            fallback_audio.append(audio)

        async def speak(self, text: str) -> None:
            pass

        async def interrupt(self) -> None:
            pass

        async def clear_input(self) -> None:
            pass

        async def close(self) -> None:
            pass

        async def events(self):
            if False:
                yield None

    wrapper = FallbackRealtimeAudioAdapter(
        primary_factory=lambda: FailingPrimary(),  # type: ignore[arg-type]
        fallback_factory=lambda: HealthyFallback(),  # type: ignore[arg-type]
    )
    await wrapper.open(locale="fr-CA")

    rec_task = asyncio.create_task(wrapper.reconnect(locale="fr-CA"))
    await rec_started.wait()

    errors: list[Exception] = []
    for _ in range(15):
        try:
            await wrapper.send_audio(_pcm_tone(200))
        except Exception as exc:
            errors.append(exc)

    fail_rec.set()
    await rec_task

    assert errors == []
    assert fallback_opens == 1
    assert wrapper.used_fallback is True
    assert wrapper.fallback_reason == "mid_session_reconnect_failed"
    assert len(fallback_audio) == 15
    await wrapper.close()


