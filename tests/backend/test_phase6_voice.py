from backend.app.core.locale_catalog import LOCALES
from backend.app.voice.central import default_voice_registry
from backend.app.voice.adapters import (
    ExternalVoiceConfigurationRequired,
    OpenAIAudioConfig,
    OpenAIRealtimeAudioAdapter,
    OpenAISpeechToTextAdapter,
    OpenAITextToSpeechAdapter,
)
from backend.app.routers import ai_voice
from backend.app.voice.usage import (
    VoiceUsageLedger,
    realtime_response_attempt,
    transcription_attempt,
    voice_pricing_catalog,
)
from backend.app.ai.usage.policy import AIQuotaPolicy
from backend.app.ai.usage.service import AIUsageService
from backend.app.ai.llm.schemas import LLMProviderAttempt, LLMUsage
from backend.app.config.settings import Settings
from backend.app.models import (
    AuthSession,
    Base,
    Company,
    CompanyMembership,
    TenantAICreditLedgerEntry,
    TenantAICreditReservation,
    TenantAIProviderAttempt,
    User,
    VoiceCentralSession,
)
from fastapi import WebSocketDisconnect
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from types import SimpleNamespace
from uuid import uuid4
from datetime import datetime, timedelta, timezone
import asyncio
import base64
import pytest
from decimal import Decimal


def test_voice_provider_capabilities_use_the_canonical_44_locales() -> None:
    codes = {locale.locale for locale in LOCALES}
    registry = default_voice_registry(codes)
    assert len(codes) == 44
    assert registry.compatible("fr", "speech_to_text")
    assert registry.compatible("ar", "text_to_speech") == ()
    assert registry.compatible("fr", "realtime_audio") == ()


def test_unconfigured_realtime_provider_is_not_claimed_as_available() -> None:
    registry = default_voice_registry({locale.locale for locale in LOCALES})
    assert all(provider.configured is False for provider in registry.list() if provider.provider_id == "retell")
    assert registry.compatible("fr", "realtime_audio") == ()


def test_voice_usage_normalizes_sdk_stt_and_cancelled_realtime_dimensions() -> None:
    catalog = voice_pricing_catalog()
    identity = {
        "attempt_number": 1,
        "request_id": "voice-turn-1",
        "tenant_id": "tenant-1",
        "user_id": "user-1",
        "conversation_id": "conversation-1",
        "agent_id": "retail",
        "module_id": "retail",
    }
    duration_stt = transcription_attempt(
        SimpleNamespace(
            event_id="evt-duration",
            usage=SimpleNamespace(type="duration", seconds=30.0),
        ),
        catalog=catalog,
        model="gpt-4o-mini-transcribe",
        **identity,
    )
    token_stt = transcription_attempt(
        SimpleNamespace(
            event_id="evt-tokens",
            usage=SimpleNamespace(
                type="tokens",
                input_tokens=100,
                output_tokens=10,
                input_token_details=SimpleNamespace(audio_tokens=80, text_tokens=20),
            ),
        ),
        catalog=catalog,
        model="gpt-4o-mini-transcribe",
        **{**identity, "attempt_number": 2},
    )
    cancelled_response = realtime_response_attempt(
        SimpleNamespace(
            event_id="evt-response-done",
            response=SimpleNamespace(
                id="resp-1",
                status="cancelled",
                usage=SimpleNamespace(
                    input_tokens=1000,
                    output_tokens=300,
                    input_token_details=SimpleNamespace(
                        audio_tokens=600,
                        text_tokens=400,
                        cached_tokens=200,
                        cached_tokens_details=SimpleNamespace(audio_tokens=100, text_tokens=100),
                    ),
                    output_token_details=SimpleNamespace(audio_tokens=200, text_tokens=100),
                ),
            ),
        ),
        catalog=catalog,
        model="gpt-realtime-2.1",
        **{**identity, "attempt_number": 3},
    )

    assert duration_stt.provider_cost_usd == Decimal("0.0015")
    assert token_stt.usage.audio_input_units == Decimal("80")
    assert token_stt.usage.text_input_tokens == 20
    assert token_stt.provider_cost_usd == Decimal("0.000175")
    assert cancelled_response is not None
    assert cancelled_response.request_status == "cancelled"
    assert cancelled_response.provider_cost_usd == Decimal("0.03248")
    assert cancelled_response.usage.audio_input_units == Decimal("600")
    assert cancelled_response.usage.cached_audio_input_units == Decimal("100")
    assert cancelled_response.usage.audio_output_units == Decimal("200")
    assert cancelled_response.usage.tenant_id == "tenant-1"
    assert cancelled_response.usage.user_id == "user-1"
    assert cancelled_response.usage.conversation_id == "conversation-1"
    assert cancelled_response.pricing_version == "2026-10-01"


@pytest.mark.asyncio
async def test_configured_adapter_contract_fails_closed_without_provider_credentials() -> None:
    config = OpenAIAudioConfig(None, None, None, None)
    with pytest.raises(ExternalVoiceConfigurationRequired):
        await OpenAISpeechToTextAdapter(config).transcribe(b"audio", locale="fr", content_type="audio/webm")
    with pytest.raises(ExternalVoiceConfigurationRequired):
        await OpenAITextToSpeechAdapter(config).synthesize("hello", locale="fr")


@pytest.mark.asyncio
async def test_realtime_adapter_never_creates_autonomous_agent_response(monkeypatch) -> None:
    sent = []
    connection = SimpleNamespace(send=sent.append)

    class Manager:
        async def __aenter__(self):
            return connection

        async def __aexit__(self, *_args):
            return None

    client = SimpleNamespace(realtime=SimpleNamespace(connect=lambda **_kwargs: Manager()))
    monkeypatch.setattr("backend.app.voice.adapters.AsyncOpenAI", lambda **_kwargs: client)
    adapter = OpenAIRealtimeAudioAdapter(OpenAIAudioConfig("test", "gpt-4o-mini-transcribe", None, "marin"), "gpt-realtime-2.1")
    await adapter.open(locale="fr")
    await adapter.send_audio(b"\x01\x02")
    await adapter.speak("Authorized answer")
    await adapter.interrupt()
    await adapter.close()
    assert sent[0]["session"]["audio"]["input"]["turn_detection"]["create_response"] is False
    assert sent[0]["session"]["tools"] == []
    assert sent[1] == {"type": "input_audio_buffer.append", "audio": "AQI="}
    assert sent[2]["type"] == "response.create"
    assert sent[2]["response"]["input"][0]["content"][0]["text"] == "Authorized answer"
    assert [event["type"] for event in sent[-2:]] == ["response.cancel", "output_audio_buffer.clear"]


class FakeSocket:
    def __init__(self, token="test"):
        self.headers = {"authorization": f"Bearer {token}"}
        self.query_params = {}
        self.incoming = asyncio.Queue()
        self.sent = []
        self.closed = None

    async def accept(self, subprotocol=None):
        self.subprotocol = subprotocol

    async def send_json(self, event):
        self.sent.append(event)

    async def close(self, code=1000):
        self.closed = code

    async def receive_json(self):
        event = await self.incoming.get()
        if event is None:
            raise WebSocketDisconnect()
        return event


class FakeRealtime:
    def __init__(self):
        self.incoming = asyncio.Queue()
        self.audio = []
        self.spoken = []
        self.interruptions = 0
        self.opened = False

    async def open(self, *, locale):
        self.opened = True

    async def send_audio(self, audio):
        self.audio.append(audio)

    async def speak(self, text):
        self.spoken.append(text)

    async def interrupt(self):
        self.interruptions += 1

    async def close(self):
        pass

    async def events(self):
        while True:
            yield await self.incoming.get()


async def until(predicate):
    async def wait():
        while not predicate():
            await asyncio.sleep(0)
    await asyncio.wait_for(wait(), timeout=2)


@pytest.fixture
def voice_route(monkeypatch):
    company_id, user_id, conversation_id, session_id, auth_id = (uuid4() for _ in range(5))
    voice = SimpleNamespace(id=session_id, company_id=company_id, user_id=user_id, conversation_id=conversation_id,
                            locale="fr", status="active", interruption_count=0, ended_at=None)
    company = SimpleNamespace(country="CA", currency_code="CAD", timezone="America/Toronto")
    user = SimpleNamespace(id=user_id, company_id=company_id, is_active=True, company=company)
    membership = SimpleNamespace(role="owner", is_active=True)
    auth = SimpleNamespace(id=auth_id, revoked_at=None, expires_at=datetime.now(timezone.utc) + timedelta(hours=1))

    class DB:
        def scalar(self, query):
            entity = query.column_descriptions[0]["entity"]
            if entity is CompanyMembership:
                return membership if membership.is_active else None
            return voice

        def get(self, entity, key):
            return user if entity is User else auth

        def refresh(self, _item):
            pass

        def commit(self):
            pass

    calls = []

    class Service:
        async def execute(self, tenant, caller, conversation, transcript, **kwargs):
            calls.append((tenant.company_id, caller, conversation, transcript, kwargs))
            attempt_sink = kwargs.get("attempt_sink")
            if attempt_sink is not None:
                request_id = kwargs["request_id"]
                usage = LLMUsage(
                    provider="openai",
                    model="gpt-4o-mini",
                    input_tokens=1_000,
                    output_tokens=100,
                    avenqo_request_id=request_id,
                    tenant_id=str(tenant.company_id),
                    user_id=str(caller),
                    conversation_id=str(conversation),
                    agent_id="retail",
                    module_id="retail",
                    idempotency_key=request_id,
                )
                attempt_sink.append(LLMProviderAttempt(
                    provider="openai",
                    model="gpt-4o-mini",
                    operation="generate",
                    attempt_number=1,
                    success=True,
                    latency_ms=5,
                    usage=usage,
                    provider_cost_usd=Decimal("0.00021"),
                    input_cost_per_million_usd=Decimal("0.15"),
                    output_cost_per_million_usd=Decimal("0.60"),
                    pricing_version="2026-10-01",
                    pricing_source="openai-api-pricing",
                    pricing_effective_from="2026-10-01",
                ))
            return SimpleNamespace(
                answer="Central authorized answer", status="success",
                remaining_ai_credits=9, selected_agent="retail",
            )

    monkeypatch.setattr(ai_voice, "decode_access_token", lambda _token: {
        "sub": str(user_id), "tenant_id": str(company_id), "session_id": str(auth_id),
    })
    adapter = FakeRealtime()
    monkeypatch.setattr(ai_voice, "_realtime_available", lambda _locale: True)
    monkeypatch.setattr(ai_voice, "_realtime_adapter", lambda: adapter)
    return SimpleNamespace(voice=voice, membership=membership, db=DB(), service=Service(), adapter=adapter, calls=calls)


@pytest.mark.asyncio
async def test_voice_stream_routes_final_audio_through_central_and_handles_barge_in(voice_route):
    socket = FakeSocket()
    run = asyncio.create_task(ai_voice.stream_session(socket, voice_route.voice.id, voice_route.db, voice_route.service))
    await until(lambda: voice_route.adapter.opened)
    frame = {"type": "audio", "sequence": 1, "audio": base64.b64encode(b"\x00\x01").decode()}
    await socket.incoming.put(frame)
    await socket.incoming.put(frame)
    await until(lambda: bool(voice_route.adapter.audio))
    assert voice_route.adapter.audio == [b"\x00\x01"]
    await voice_route.adapter.incoming.put(SimpleNamespace(type="conversation.item.input_audio_transcription.delta", transcript="Delete everything"))
    await asyncio.sleep(0)
    assert voice_route.calls == []
    final = SimpleNamespace(type="conversation.item.input_audio_transcription.completed", item_id="item-1", transcript="Summarize sales")
    await voice_route.adapter.incoming.put(final)
    await until(lambda: bool(voice_route.adapter.spoken))
    await voice_route.adapter.incoming.put(final)
    await voice_route.adapter.incoming.put(SimpleNamespace(type="response.created", response=SimpleNamespace(id="resp-1")))
    await voice_route.adapter.incoming.put(SimpleNamespace(type="response.output_audio.delta", response_id="resp-1", delta="AQI="))
    await until(lambda: any(event["type"] == "audio" for event in socket.sent))
    assert socket.sent[0]["text_fallback"] is False
    assert voice_route.calls[0][:4] == (voice_route.voice.company_id, voice_route.voice.user_id,
                                      voice_route.voice.conversation_id, "Summarize sales")
    assert len(voice_route.calls) == 1
    assert voice_route.calls[0][-1]["request_id"]
    assert voice_route.adapter.spoken == ["Central authorized answer"]
    assert any(event.get("conversation_id") == str(voice_route.voice.conversation_id) for event in socket.sent)
    assert any(event["type"] == "audio" and event["audio"] == "AQI=" for event in socket.sent)
    await socket.incoming.put({"type": "interrupt"})
    await until(lambda: voice_route.adapter.interruptions == 1)
    await voice_route.adapter.incoming.put(SimpleNamespace(type="response.output_audio.delta", response_id="resp-1", delta="AAAA"))
    await asyncio.sleep(0)
    assert len([event for event in socket.sent if event["type"] == "audio"]) == 1
    await socket.incoming.put(None)
    await run
    assert voice_route.voice.status == "active"


@pytest.mark.asyncio
async def test_voice_stream_fallback_reconnect_and_revoked_membership(voice_route, monkeypatch):
    monkeypatch.setattr(ai_voice, "_realtime_available", lambda _locale: False)
    socket = FakeSocket()
    run = asyncio.create_task(ai_voice.stream_session(socket, voice_route.voice.id, voice_route.db, voice_route.service))
    await until(lambda: bool(socket.sent))
    assert socket.sent[0]["text_fallback"] is True
    await socket.incoming.put({"type": "audio", "audio": "AQI="})
    await until(lambda: len(socket.sent) > 1)
    assert socket.sent[1]["status"] == "text_fallback"
    await socket.incoming.put(None)
    await run
    assert voice_route.voice.status == "active"
    voice_route.membership.is_active = False
    reconnect = FakeSocket()
    await ai_voice.stream_session(reconnect, voice_route.voice.id, voice_route.db, voice_route.service)
    assert reconnect.closed == 4403
    assert voice_route.calls == []


@pytest.mark.asyncio
async def test_voice_stream_rejects_cross_tenant_token_and_unsupported_locale(voice_route, monkeypatch):
    other_company = uuid4()
    monkeypatch.setattr(ai_voice, "decode_access_token", lambda _token: {
        "sub": str(voice_route.voice.user_id), "tenant_id": str(other_company),
        "session_id": str(uuid4()),
    })
    socket = FakeSocket()
    await ai_voice.stream_session(socket, voice_route.voice.id, voice_route.db, voice_route.service)
    assert socket.closed == 4403
    assert voice_route.calls == []

    monkeypatch.setattr(ai_voice, "decode_access_token", lambda _token: {
        "sub": str(voice_route.voice.user_id), "tenant_id": str(voice_route.voice.company_id),
        "session_id": str(uuid4()),
    })
    monkeypatch.setattr(ai_voice, "_realtime_available", lambda locale: locale == "fr")
    voice_route.voice.locale = "unsupported-XX"
    fallback = FakeSocket()
    run = asyncio.create_task(ai_voice.stream_session(fallback, voice_route.voice.id, voice_route.db, voice_route.service))
    await until(lambda: bool(fallback.sent))
    assert fallback.sent[0]["text_fallback"] is True
    assert voice_route.adapter.opened is False
    await fallback.incoming.put(None)
    await run


@pytest.mark.asyncio
async def test_browser_ticket_is_bound_to_authenticated_voice_session(voice_route, monkeypatch):
    auth_id = uuid4()
    voice_route.db.get = lambda entity, key: (
        SimpleNamespace(id=auth_id, revoked_at=None, expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
        if entity is AuthSession else SimpleNamespace(
            id=voice_route.voice.user_id, company_id=voice_route.voice.company_id,
            is_active=True, company=SimpleNamespace(country="CA", currency_code="CAD", timezone="UTC"),
        )
    )
    identity = SimpleNamespace(user=SimpleNamespace(id=voice_route.voice.user_id),
                               auth_session=SimpleNamespace(id=auth_id))
    tenant = SimpleNamespace(company_id=voice_route.voice.company_id)
    ticket = ai_voice.stream_ticket(voice_route.voice.id, tenant, identity, voice_route.db, voice_route.membership)["ticket"]
    socket = FakeSocket(token="")
    socket.headers["sec-websocket-protocol"] = f"avenqo.voice, ticket.{ticket}"
    run = asyncio.create_task(ai_voice.stream_session(socket, voice_route.voice.id, voice_route.db, voice_route.service))
    await until(lambda: bool(socket.sent))
    assert socket.subprotocol == "avenqo.voice"
    assert socket.sent[0]["conversation_id"] == str(voice_route.voice.conversation_id)
    await socket.incoming.put(None)
    await run

    invalid = FakeSocket(token="")
    invalid.headers["sec-websocket-protocol"] = "avenqo.voice, ticket.invalid"
    await ai_voice.stream_session(invalid, voice_route.voice.id, voice_route.db, voice_route.service)
    assert invalid.closed == 4401


@pytest.mark.asyncio
async def test_voice_websocket_settles_sdk_usage_through_phase4_once(voice_route, monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'voice-route-usage.db'}")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        company = Company(
            id=voice_route.voice.company_id,
            name="Voice Route Usage",
            slug="voice-route-usage",
            email="voice-route-usage@example.com",
            country="CA",
            timezone="America/Toronto",
            industry="Retail",
            subscription_plan="professional",
        )
        db.add(company)
        db.commit()
        voice_route.service.usage_service = AIUsageService(
            db,
            AIQuotaPolicy(Settings(_env_file=None, AUTH_JWT_SECRET="c" * 32)),
        )
        monkeypatch.setattr(ai_voice, "_realtime_available", lambda _locale: True)
        monkeypatch.setattr(ai_voice, "_realtime_adapter", lambda: voice_route.adapter)
        monkeypatch.setattr(ai_voice, "get_settings", lambda: SimpleNamespace(
            ai_model_rate_card={},
            voice_stt_model="gpt-4o-mini-transcribe",
            voice_realtime_model="gpt-realtime-2.1",
        ))

        socket = FakeSocket()
        run = asyncio.create_task(
            ai_voice.stream_session(socket, voice_route.voice.id, voice_route.db, voice_route.service)
        )
        await until(lambda: bool(socket.sent))
        frame = {"type": "audio", "sequence": 0, "audio": base64.b64encode(b"\x00\x01").decode()}
        await socket.incoming.put(frame)
        await socket.incoming.put(frame)
        await until(lambda: len(voice_route.adapter.audio) == 1)
        await voice_route.adapter.incoming.put(SimpleNamespace(
            type="input_audio_buffer.speech_started", item_id="item-route-1"
        ))
        await voice_route.adapter.incoming.put(SimpleNamespace(
            type="conversation.item.input_audio_transcription.completed",
            event_id="transcription-route-1",
            item_id="item-route-1",
            transcript="Summarize sales",
            usage=SimpleNamespace(type="duration", seconds=30.0),
        ))
        await until(lambda: bool(voice_route.adapter.spoken))
        await voice_route.adapter.incoming.put(SimpleNamespace(
            type="response.created", response=SimpleNamespace(id="response-route-1")
        ))
        await voice_route.adapter.incoming.put(SimpleNamespace(
            type="response.done",
            event_id="response-done-route-1",
            response=SimpleNamespace(
                id="response-route-1",
                status="completed",
                usage=SimpleNamespace(
                    input_tokens=1000,
                    output_tokens=300,
                    input_token_details=SimpleNamespace(
                        audio_tokens=600,
                        text_tokens=400,
                        cached_tokens=200,
                        cached_tokens_details=SimpleNamespace(audio_tokens=100, text_tokens=100),
                    ),
                    output_token_details=SimpleNamespace(audio_tokens=200, text_tokens=100),
                ),
            ),
        ))
        request_id = VoiceUsageLedger(
            voice_route.service.usage_service,
            voice_pricing_catalog(),
            company_id=company.id,
            user_id=voice_route.voice.user_id,
            conversation_id=voice_route.voice.conversation_id,
            plan_code="professional",
        ).request_id_for("item-route-1")
        await until(lambda: db.scalar(select(TenantAICreditLedgerEntry.id).where(
            TenantAICreditLedgerEntry.company_id == company.id,
            TenantAICreditLedgerEntry.reference_id == request_id,
            TenantAICreditLedgerEntry.transaction_type == "ai_settlement",
        )) is not None)
        await socket.incoming.put(None)
        await run

        attempts = db.scalars(select(TenantAIProviderAttempt).where(
            TenantAIProviderAttempt.company_id == company.id,
            TenantAIProviderAttempt.avenqo_request_id == request_id,
        )).all()
        settlements = db.scalars(select(TenantAICreditLedgerEntry).where(
            TenantAICreditLedgerEntry.company_id == company.id,
            TenantAICreditLedgerEntry.reference_id == request_id,
            TenantAICreditLedgerEntry.transaction_type == "ai_settlement",
        )).all()
        reservation = db.scalar(select(TenantAICreditReservation).where(
            TenantAICreditReservation.company_id == company.id,
            TenantAICreditReservation.avenqo_request_id == request_id,
        ))
        assert len(attempts) == 3
        assert {attempt.operation for attempt in attempts} == {
            "voice_stt", "voice_realtime_tts", "generate",
        }
        assert sum(attempt.audio_input_units for attempt in attempts) == Decimal("600")
        assert sum(attempt.audio_output_units for attempt in attempts) == Decimal("200")
        assert len(settlements) == 1
        assert reservation.actual_credits == 114
        assert len(voice_route.calls) == 1
    engine.dispose()


@pytest.mark.asyncio
async def test_voice_frame_sequence_is_rejected_after_reconnect(voice_route, monkeypatch):
    monkeypatch.setattr(ai_voice, "_realtime_available", lambda _locale: True)
    monkeypatch.setattr(ai_voice, "_realtime_adapter", lambda: voice_route.adapter)
    first = FakeSocket()
    first_run = asyncio.create_task(
        ai_voice.stream_session(first, voice_route.voice.id, voice_route.db, voice_route.service)
    )
    await until(lambda: bool(first.sent))
    frame = {"type": "audio", "sequence": 12, "audio": base64.b64encode(b"\x00\x01").decode()}
    await first.incoming.put(frame)
    await until(lambda: len(voice_route.adapter.audio) == 1)
    await first.incoming.put(None)
    await first_run

    second = FakeSocket()
    second_run = asyncio.create_task(
        ai_voice.stream_session(second, voice_route.voice.id, voice_route.db, voice_route.service)
    )
    await until(lambda: bool(second.sent))
    assert second.sent[0]["next_audio_sequence"] == 13
    await second.incoming.put(frame)
    await asyncio.sleep(0)
    assert len(voice_route.adapter.audio) == 1
    await second.incoming.put({**frame, "sequence": 13})
    await until(lambda: len(voice_route.adapter.audio) == 2)
    await second.incoming.put(None)
    await second_run
