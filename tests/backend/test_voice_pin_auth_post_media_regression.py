"""P0 regression: PIN auth must succeed and reach employee mode even when realtime models fail.

Incident 2026-11-27 (~17:37 UTC):
- PIN validate succeeded server-side
- Gemini Live primary failed
- OpenAI fallback opened with gpt-live-1 then died on session.update (invalid_model)
- No audible auth confirmation; media websocket 1011; caller perceived a loop
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, call as mock_call
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config.settings import Settings
from datetime import datetime, timezone
from pathlib import Path

from backend.app.models import (
    Base,
    BillingAccount,
    Company,
    CompanyMembership,
    Dataset,
    DatasetStatus,
    Mapping,
    User,
    UserRole,
)
from backend.app.voice.adapters import OpenAIAudioConfig, OpenAIRealtimeAudioAdapter
from backend.app.voice.auth import validate_voice_pin
from backend.app.voice.messages import voice_auth_message
from backend.app.voice.realtime_provider import (
    FallbackRealtimeAudioAdapter,
    RealtimeProviderType,
    VoiceRealtimeRouter,
)
from backend.app.voice.selected_source_intelligence import (
    assert_tool_allowed_for_selected_sources,
    classify_voice_data_intent,
    resolve_authorized_selected_sources,
)
from backend.app.voice.telnyx_media import media_session_opening_line
from backend.app.voice.tool_guard import VoiceToolDenied
from shared.ai_engine.contracts import TenantContext


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'voice-pin-auth-reg.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session


@pytest.mark.asyncio
async def test_openai_realtime_remaps_gpt_live_after_session_update_invalid_model(monkeypatch):
    """gpt-live-1 can accept the websocket then fail on session.update — remap must cover that."""
    config = OpenAIAudioConfig("sk-test", "gpt-4o-mini-transcribe", None, "marin")
    adapter = OpenAIRealtimeAudioAdapter(config, realtime_model="gpt-live-1")

    sent: list[dict] = []
    connects: list[str] = []

    class FakeConnection:
        def __init__(self, model: str) -> None:
            self.model = model

        async def send(self, payload):
            if payload.get("type") == "session.update" and self.model == "gpt-live-1":
                raise ConnectionError("invalid_request_error.invalid_model")
            sent.append(payload)

    class FakeManager:
        def __init__(self, model: str) -> None:
            self.model = model
            self.connection = FakeConnection(model)

        async def __aenter__(self):
            return self.connection

        async def __aexit__(self, *_args):
            return None

    class FakeClient:
        class realtime:
            @staticmethod
            def connect(*, model: str):
                connects.append(model)
                return FakeManager(model)

        def __init__(self, **_kwargs) -> None:
            pass

    monkeypatch.setattr("backend.app.voice.adapters.AsyncOpenAI", FakeClient)

    await adapter.open(locale="fr-CA")

    assert connects == ["gpt-live-1", "gpt-realtime-2.1"]
    assert adapter._model == "gpt-realtime-2.1"
    assert sent and sent[0]["type"] == "session.update"
    assert sent[0]["session"]["type"] == "realtime"


@pytest.mark.asyncio
async def test_gemini_live_fallback_uses_certified_openai_realtime_model(monkeypatch):
    settings = Settings(
        AUTH_JWT_SECRET="test-secret-key-32-chars-minimum--",
        GOOGLE_AI_API_KEY="test-google-key",
        OPENAI_API_KEY="sk-test",
        VOICE_REALTIME_MODEL="gpt-live-1",
        VOICE_REALTIME_FALLBACK_MODEL="gpt-realtime-2.1",
        GEMINI_LIVE_MODEL="gemini-3.8-live",
    )
    router = VoiceRealtimeRouter(settings)
    monkeypatch.setattr(router._gemini, "is_available", lambda: True)

    class FailingGemini:
        provider_id = "gemini_live"
        _model = "gemini-3.8-live"
        model_name = "gemini-3.8-live"

        async def open(self, *, locale: str = "fr-CA") -> None:
            raise RuntimeError("gemini_primary_down")

        async def close(self) -> None:
            return None

    monkeypatch.setattr(
        router._gemini,
        "create_audio_adapter",
        lambda *_a, **_k: FailingGemini(),
    )

    captured: dict[str, str | None] = {"model": None}

    class CapturingAdapter:
        provider_id = "openai"

        def __init__(self, _cfg, model=None) -> None:
            captured["model"] = model
            self._model = model
            self.model_name = str(model or "")

        async def open(self, *, locale: str = "fr-CA") -> None:
            return None

        async def close(self) -> None:
            return None

    audio = OpenAIAudioConfig("sk-test", "gpt-4o-mini-transcribe", None, "marin")
    config = SimpleNamespace(
        company_id=uuid4(),
        realtime_provider=RealtimeProviderType.GEMINI_LIVE,
        gemini_live_enabled=True,
        call_policy={},
        architecture_mode=None,
    )
    adapter = router.build_realtime_adapter(
        config,
        audio,
        fallback_factory=lambda model=None: CapturingAdapter(audio, model),
    )
    assert isinstance(adapter, FallbackRealtimeAudioAdapter)
    await adapter.open(locale="fr-CA")
    assert adapter.used_fallback is True
    assert captured["model"] == "gpt-realtime-2.1"
    assert adapter.active_model == "gpt-realtime-2.1"


def test_auth_confirmation_opening_line_and_no_duplicate_after_call_control():
    success = media_session_opening_line(
        public_mode=False,
        public_greeting=None,
        locale="fr",
        confirm_authentication=True,
    )
    assert success == "Authentification réussie."
    assert media_session_opening_line(
        public_mode=False,
        public_greeting=None,
        locale="fr",
        confirm_authentication=True,
        auth_confirmation_already_spoken=True,
    ) is None
    # Public welcome must not replay after staff auth.
    assert media_session_opening_line(
        public_mode=False,
        public_greeting="Bienvenue chez Produits Véro.",
        locale="fr",
        confirm_authentication=True,
        auth_confirmation_already_spoken=True,
    ) is None


def test_no_selection_denies_private_tools_but_auth_confirmation_still_available(db_session: Session):
    """Connected sources without selection deny private tools — PIN auth still proceeds."""
    company = Company(
        name="No Selection Co",
        slug=f"no-sel-{uuid4().hex[:8]}",
        email=f"owner-{uuid4().hex[:6]}@example.test",
        country="CA",
        timezone="America/Montreal",
        industry="Retail",
        subscription_plan="professional",
    )
    db_session.add(company)
    db_session.flush()
    db_session.add(BillingAccount(company_id=company.id, plan_code="professional", status="active"))
    user = User(
        company_id=company.id,
        first_name="Staff",
        last_name="Owner",
        email=f"staff-{uuid4().hex[:6]}@example.test",
        password_hash="x",
        role=UserRole.OWNER,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(
        CompanyMembership(
            company_id=company.id,
            user_id=user.id,
            role=UserRole.OWNER,
            is_active=True,
        )
    )
    dataset = Dataset(
        company_id=company.id,
        name="connected-unselected.xlsx",
        type="csv",
        source=str(Path("connected-unselected.xlsx")),
        status=DatasetStatus.READY,
        uploaded_at=datetime.now(timezone.utc),
        columns_count=3,
        rows_count=10,
    )
    dataset.mapping = Mapping(mapping_json={"accepted": {}}, confidence=1, approved=True)
    db_session.add(dataset)
    db_session.commit()

    tenant = TenantContext(company.id, user.id)
    resolution = resolve_authorized_selected_sources(db_session, tenant, require_data_read=True)
    assert resolution.state == "NO_SELECTION"
    assert resolution.excluded_source_ids  # connected but unselected

    with pytest.raises(VoiceToolDenied):
        assert_tool_allowed_for_selected_sources(
            tool_name="get_sales_summary",
            resolution=resolution,
            intent=classify_voice_data_intent("ventes du fichier", has_selected_dataset=False),
        )

    # Auth confirmation path is independent of dataset selection.
    assert media_session_opening_line(
        public_mode=False,
        public_greeting=None,
        locale="fr",
        confirm_authentication=True,
    ) == "Authentification réussie."


@pytest.mark.asyncio
async def test_staff_auth_confirmation_speaks_before_media_stream(monkeypatch):
    """Valid PIN success path must speak confirmation before streaming_start."""
    speak = AsyncMock()
    stream = AsyncMock()
    sleep = AsyncMock()
    order: list[str] = []

    async def _speak(*_a, **_k):
        order.append("speak")

    async def _stream(*_a, **_k):
        order.append("stream")

    async def _sleep(*_a, **_k):
        order.append("sleep")

    speak.side_effect = _speak
    stream.side_effect = _stream
    sleep.side_effect = _sleep
    monkeypatch.setattr(asyncio, "sleep", sleep)

    call_id = uuid4()
    active_control_id = "v3:test-control"
    confirm_text = voice_auth_message("fr-CA", 1)
    await speak(
        active_control_id,
        text_prompt=confirm_text,
        language="fr-CA",
        command_id="auth-confirm-test",
    )
    await asyncio.sleep(1.6)
    source_context = {
        "ivr_stage": "staff_authenticated",
        "pin_gather_status": "authenticated",
        "auth_confirmation_spoken": True,
    }
    await stream(
        active_control_id,
        stream_url=f"wss://example/media/{call_id}",
        client_state="ticket",
        command_id="media-staff-test",
    )

    assert order == ["speak", "sleep", "stream"]
    assert "Authentification réussie" in confirm_text
    assert source_context["ivr_stage"] == "staff_authenticated"
    assert source_context["auth_confirmation_spoken"] is True
    assert speak.await_count == 1
    assert stream.await_count == 1
    assert speak.await_args == mock_call(
        active_control_id,
        text_prompt=confirm_text,
        language="fr-CA",
        command_id="auth-confirm-test",
    )


@pytest.mark.parametrize(
    ("raw", "ok"),
    [
        ("682491", True),
        ("948205183", True),
        ("12345", False),  # incomplete
        ("", False),
        ("111111", False),  # trivial repeated
    ],
)
def test_pin_digit_validation_incomplete_invalid_and_valid(raw: str, ok: bool):
    if ok:
        assert validate_voice_pin(raw) == raw
    else:
        with pytest.raises(ValueError):
            validate_voice_pin(raw)


def test_gather_digits_strip_terminating_pound_before_validate():
    """IVR gather strips trailing # before PIN validation (Telnyx terminating digit)."""
    digits = "682491#"
    normalized = digits.strip().rstrip("#")
    assert validate_voice_pin(normalized) == "682491"
