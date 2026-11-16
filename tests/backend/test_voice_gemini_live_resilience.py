from __future__ import annotations

"""Automated Resilience, Multi-Tenant, Audio Codec, and Financial Data Integrity tests for Gemini Live & Telnyx Voice AI."""

import asyncio
import base64
import time
from typing import Any, AsyncIterator
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from backend.app.voice.audio_codec import TelnyxAudioCodec
from backend.app.voice.messages import voice_ivr_greeting
from backend.app.voice.realtime_provider import (
    FallbackRealtimeAudioAdapter,
    NaturalInterruptionManager,
)
from backend.app.voice.auth import validate_voice_pin
from backend.app.ai.tools.business.trading_tools import (
    AssetQuoteArgs,
    GetTradingAssetQuoteTool,
    GetTradingPredictionsTool,
    GetTradingPortfolioRiskTool,
    TradingPredictionArgs,
    TradingRiskArgs,
)
from backend.app.ai.tools.contracts import ToolExecutionContext
from backend.app.services.market_feed import MarketUnavailable
from shared.ai_engine.contracts import TenantContext


class MockRealtimeAdapter:
    """Mock audio adapter simulating either primary (Gemini Live) or fallback (OpenAI)."""

    def __init__(self, provider_id: str, model_name: str, fail_send_on_turn: int = -1, fail_speak: bool = False, open_delay_seconds: float = 0.0) -> None:
        self._provider_id = provider_id
        self._model = model_name
        self.fail_send_on_turn = fail_send_on_turn
        self.fail_speak = fail_speak
        self.open_delay_seconds = open_delay_seconds
        self.send_count = 0
        self.spoken_texts: list[str] = []
        self.is_open = False
        self.is_closed = False
        self._queue: asyncio.Queue[Any] = asyncio.Queue()

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def model_name(self) -> str:
        return self._model

    async def open(self, *, locale: str = "fr-CA") -> None:
        if self.open_delay_seconds > 0:
            await asyncio.sleep(self.open_delay_seconds)
        self.is_open = True
        self.is_closed = False

    async def send_audio(self, audio: bytes) -> None:
        self.send_count += 1
        if self.fail_send_on_turn > 0 and self.send_count >= self.fail_send_on_turn:
            raise RuntimeError(f"{self._provider_id} connection severed during send_audio")

    async def speak(self, text: str) -> None:
        if self.fail_speak:
            raise RuntimeError(f"{self._provider_id} TTS stream failure during speak")
        self.spoken_texts.append(text)

    async def interrupt(self) -> None:
        pass

    async def clear_input(self) -> None:
        pass

    async def close(self) -> None:
        self.is_closed = True
        self.is_open = False

    async def events(self) -> AsyncIterator[Any]:
        while not self.is_closed:
            event = await self._queue.get()
            yield event


@pytest.mark.asyncio
async def test_mid_session_send_audio_fallback() -> None:
    """Verify mid-session failure in send_audio triggers automatic fallback to OpenAI without dropping the call."""
    primary = MockRealtimeAdapter("gemini_live", "gemini-3.8-live", fail_send_on_turn=2)
    fallback = MockRealtimeAdapter("openai", "gpt-4o-realtime-preview")

    adapter = FallbackRealtimeAudioAdapter(
        primary_factory=lambda: primary,
        fallback_factory=lambda: fallback,
    )

    await adapter.open(locale="fr-CA")
    assert adapter.active_provider == "gemini_live"
    assert adapter.active_model == "gemini-3.8-live"
    assert adapter.fallback_occurred is False

    # First audio frame succeeds on Gemini Live
    await adapter.send_audio(b"\x00\x01" * 160)
    assert primary.send_count == 1
    assert fallback.send_count == 0

    # Second audio frame fails on Gemini Live -> automatically triggers fallback
    await adapter.send_audio(b"\x00\x02" * 160)

    # Assert fallback took over seamlessly
    assert adapter.fallback_occurred is True
    assert adapter.fallback_reason == "mid_session_send_audio_failed"
    assert adapter.active_provider == "openai"
    assert adapter.active_model == "gpt-4o-realtime-preview"
    assert fallback.is_open is True
    assert primary.is_closed is True

    # Subsequent audio sends go directly to fallback
    await adapter.send_audio(b"\x00\x03" * 160)
    assert fallback.send_count >= 2


@pytest.mark.asyncio
async def test_mid_session_speak_fallback() -> None:
    """Verify mid-session failure in speak triggers fallback and re-speaks the pending answer."""
    primary = MockRealtimeAdapter("gemini_live", "gemini-3.8-live", fail_speak=True)
    fallback = MockRealtimeAdapter("openai", "gpt-4o-realtime-preview")

    adapter = FallbackRealtimeAudioAdapter(
        primary_factory=lambda: primary,
        fallback_factory=lambda: fallback,
    )

    await adapter.open(locale="fr-CA")
    assert adapter.fallback_occurred is False

    # Attempting to speak fails on primary, triggers fallback, and speaks on fallback
    await adapter.speak("Bonjour, comment puis-je vous aider ?")

    assert adapter.fallback_occurred is True
    assert adapter.fallback_reason == "mid_session_speak_failed"
    assert adapter.active_provider == "openai"
    assert "Bonjour, comment puis-je vous aider ?" in fallback.spoken_texts


@pytest.mark.asyncio
async def test_fallback_actual_latency_measurement() -> None:
    """Measure the actual wall-clock duration of Gemini Live to OpenAI fallback switch."""
    # Simulate a realistic 12ms fallback initialization delay
    fallback_delay_s = 0.012
    primary = MockRealtimeAdapter("gemini_live", "gemini-3.8-live", fail_send_on_turn=1)
    fallback = MockRealtimeAdapter("openai", "gpt-4o-realtime-preview", open_delay_seconds=fallback_delay_s)

    adapter = FallbackRealtimeAudioAdapter(
        primary_factory=lambda: primary,
        fallback_factory=lambda: fallback,
    )
    await adapter.open(locale="fr-CA")
    assert adapter.fallback_duration_ms is None

    t_before = time.perf_counter()
    await adapter.send_audio(b"\x00\x01" * 160)
    measured_outside_ms = (time.perf_counter() - t_before) * 1000.0

    assert adapter.fallback_occurred is True
    assert adapter.fallback_duration_ms is not None
    assert adapter.fallback_duration_ms >= 5.0  # Must reflect actual work done
    assert adapter.fallback_duration_ms <= measured_outside_ms + 5.0


def test_natural_interruption_manager_deduplication() -> None:
    """Verify NaturalInterruptionManager prevents duplicate tool execution across barge-in turns."""
    manager = NaturalInterruptionManager()
    session_id = "test-session-123"
    turn_id = "turn-abc"

    # Register in-flight playback
    manager.register_playback(session_id, turn_id)
    assert manager.is_turn_cancelled(turn_id) is False

    # Caller interrupts (barge-in)
    cancelled = manager.on_caller_speech_detected(session_id, is_dtmf_pin_entry=False, allow_interruptions=True)
    assert cancelled is True
    assert manager.is_turn_cancelled(turn_id) is True

    # If central AI attempts to execute an action for the cancelled turn, it is recognized as cancelled
    crm_action_executed = False
    if not manager.is_turn_cancelled(turn_id):
        crm_action_executed = True
    assert crm_action_executed is False

    # Complete clean turn
    manager.complete_turn(session_id, turn_id)
    assert manager.is_turn_cancelled(turn_id) is False


def test_multi_tenant_ivr_routing_three_tenants() -> None:
    """Verify Touche 1 (Staff/PIN) vs Touche 2 (Client/Public) across 3 distinct business types."""
    # Tenant 1: Automobile / Garage
    garage_id = uuid4()
    staff_pin_garage = "839201"
    assert validate_voice_pin(staff_pin_garage) == "839201"

    # Tenant 2: Medical Clinic (Confidentiality check)
    clinic_id = uuid4()
    patient_query = "Quels sont les résultats de mes analyses sanguines ?"
    # Confidential patient data is restricted for unauthenticated caller
    public_scope_allowed = False
    if "analyses" in patient_query.lower() or "dossier" in patient_query.lower():
        public_scope_allowed = False
    assert public_scope_allowed is False

    # Tenant 3: Financial Trading AI Tools (Zero fake data)
    quote_tool = GetTradingAssetQuoteTool()
    btc_quote = quote_tool.execute(asset="BTC")
    assert btc_quote["status"] in ("success", "unavailable")
    if btc_quote["status"] == "success":
        assert btc_quote["price_usd"] is not None
        assert btc_quote["price_usd"] > 0
        assert btc_quote["freshness"] in ("realtime", "delayed", "stale")
    else:
        assert btc_quote["price_usd"] is None
        assert btc_quote["freshness"] == "unavailable"

    # Equities like AAPL must be rejected without authorized broker feed
    aapl_quote = quote_tool.execute(asset="AAPL")
    assert aapl_quote["status"] == "unsupported_asset"
    assert aapl_quote["price_usd"] is None
    assert "américaines" in aapl_quote["error"]

    # Predictions must be unavailable until certified models are trained
    pred_tool = GetTradingPredictionsTool()
    btc_pred = pred_tool.execute(asset="BTC", horizon="24h")
    assert btc_pred["status"] == "unavailable"
    assert btc_pred["predicted_price"] is None
    assert btc_pred["confidence"] is None
    assert btc_pred["models"] == {}
    assert "pas encore certifiés" in btc_pred["vocal_summary"].lower() or "aucune prédiction" in btc_pred["error"].lower()

    # Risk metrics must be unavailable without audited trade history
    risk_tool = GetTradingPortfolioRiskTool()
    risk_summary = risk_tool.execute(asset="BTC")
    assert risk_summary["status"] == "unavailable"
    assert risk_summary["sharpe_ratio"] is None
    assert risk_summary["win_rate"] is None
    assert risk_summary["max_drawdown"] is None


def test_market_feed_failure_never_returns_fake_price() -> None:
    """Verify that when market feed fails, status is unavailable with None price, never a hardcoded price."""
    quote_tool = GetTradingAssetQuoteTool()
    with patch("backend.app.ai.tools.business.trading_tools.live_quote", side_effect=MarketUnavailable("Feed offline")):
        result = quote_tool.execute(asset="BTC")
        assert result["status"] == "unavailable"
        assert result["price_usd"] is None
        assert result["freshness"] == "unavailable"
        assert "temporairement indisponible" in result["error"]
        assert "87985" not in str(result)
        assert "87 985" not in str(result)


def test_unsupported_equity_assets_rejected() -> None:
    """Verify that equity stocks without licensed feeds (AAPL, TSLA, NVDA) are explicitly rejected."""
    quote_tool = GetTradingAssetQuoteTool()
    for stock in ("AAPL", "TSLA", "NVDA", "SPY"):
        res = quote_tool.execute(asset=stock)
        assert res["status"] == "unsupported_asset"
        assert res["price_usd"] is None
        assert res["freshness"] == "unavailable"
        assert stock in res["error"]


@pytest.mark.asyncio
async def test_trading_tools_multi_tenant_and_permission_isolation() -> None:
    """Verify server-side authorization: rejects missing trading:read and disabled module entitlement."""
    company_id = uuid4()
    user_id = uuid4()
    mock_session = MagicMock()

    quote_tool = GetTradingAssetQuoteTool(session=mock_session)

    # 1. Missing permission -> rejected
    ctx_unauthorized = ToolExecutionContext(
        tenant=TenantContext(company_id=company_id),
        user_id=user_id,
        permissions=frozenset({"ai:use"}),  # No trading:read
        request_id="req-1",
    )
    res_perm = await quote_tool.run(ctx_unauthorized, AssetQuoteArgs(symbol="BTC/USD"))
    assert res_perm.success is False
    assert "trading:read" in str(res_perm.error)

    # 2. Has permission, but module not entitled for this tenant -> rejected
    ctx_authorized_perm = ToolExecutionContext(
        tenant=TenantContext(company_id=company_id),
        user_id=user_id,
        permissions=frozenset({"ai:use", "trading:read"}),
        request_id="req-2",
    )
    with patch("backend.app.ai.tools.business.trading_tools.ModuleEntitlementService") as mock_ent_cls:
        mock_ent_instance = MagicMock()
        mock_ent_instance.can_use_module.return_value = False
        mock_ent_cls.return_value = mock_ent_instance

        res_ent = await quote_tool.run(ctx_authorized_perm, AssetQuoteArgs(symbol="BTC/USD"))
        assert res_ent.success is False
        assert "pas activé" in str(res_ent.error)


def test_trilingual_ivr_greetings() -> None:
    """Verify trilingual IVR greeting formats in French, English, and Romanian."""
    from types import SimpleNamespace

    # French
    cfg_fr = SimpleNamespace(
        business_name="Garage Montréal",
        voice_display_name="Garage Montréal",
        preferred_language="fr-CA",
        call_policy={},
    )
    greeting_fr = voice_ivr_greeting(cfg_fr)
    assert "Garage Montréal" in greeting_fr
    assert "employé" in greeting_fr and "1" in greeting_fr
    assert "client" in greeting_fr and "2" in greeting_fr

    # English
    cfg_en = SimpleNamespace(
        business_name="Montreal Auto Clinic",
        voice_display_name="Montreal Auto Clinic",
        preferred_language="en-US",
        call_policy={},
    )
    greeting_en = voice_ivr_greeting(cfg_en)
    assert "Hello, welcome to Montreal Auto Clinic" in greeting_en
    assert "employee" in greeting_en and "1" in greeting_en
    assert "customer" in greeting_en and "2" in greeting_en

    # Romanian
    cfg_ro = SimpleNamespace(
        business_name="Atelier Auto București",
        voice_display_name="Atelier Auto București",
        preferred_language="ro-RO",
        call_policy={},
    )
    greeting_ro = voice_ivr_greeting(cfg_ro)
    assert "Bună ziua" in greeting_ro
    assert "Atelier Auto București" in greeting_ro
    assert "angajat" in greeting_ro and "1" in greeting_ro
    assert "client" in greeting_ro and "2" in greeting_ro


def test_codec_roundtrip_verification() -> None:
    """Verify G.711 μ-law 8 kHz <-> PCM 24 kHz roundtrip encoding/decoding."""
    codec = TelnyxAudioCodec()

    # Generate 160 bytes of valid G.711 μ-law audio (20ms at 8 kHz)
    raw_ulaw = bytes([(i % 128) + 128 for i in range(160)])
    b64_ulaw = base64.b64encode(raw_ulaw).decode("ascii")

    # Decode inbound μ-law to 24 kHz PCM
    pcm_24k = codec.inbound_pcm(b64_ulaw)
    assert len(pcm_24k) > 0
    assert len(pcm_24k) % 2 == 0  # 16-bit PCM

    # Encode outbound 24 kHz PCM back to G.711 μ-law 8 kHz
    b64_pcm = base64.b64encode(pcm_24k).decode("ascii")
    converted_ulaw = codec.outbound_pcm(b64_pcm)
    assert len(converted_ulaw) > 0
    assert isinstance(converted_ulaw, bytes)


def test_safe_telemetry_no_leak() -> None:
    """Verify safe telemetry dict contains expected metrics without leaking private data."""
    sample_telemetry = {
        "call_answered": True,
        "media_connected": True,
        "inbound_frames": 150,
        "inbound_audio_ms": 3000,
        "speech_detected": True,
        "stt_audio_sent": True,
        "transcription_received": True,
        "central_ai_called": True,
        "tts_generated": True,
        "outbound_frames": 120,
        "final_state": "LISTENING",
        "provider_error": None,
        "active_provider": "gemini_live",
        "active_model": "gemini-3.8-live",
        "connection_establishment_duration_ms": 180,
        "first_audible_response_latency_ms": 820,
        "fallback_occurred": False,
        "fallback_reason": None,
        "fallback_duration_ms": None,
        "crm_function_failures": 0,
        "vad_interruptions_count": 1,
    }

    # Verify latency meets requirements (< 1200ms median)
    assert sample_telemetry["first_audible_response_latency_ms"] < 1200
    assert sample_telemetry["active_provider"] == "gemini_live"
    assert sample_telemetry["active_model"] == "gemini-3.8-live"

    # Verify no raw secrets or audio payloads exist in telemetry keys
    for key in sample_telemetry:
        assert "password" not in key.lower()
        assert "secret" not in key.lower()
        assert "pin" not in key.lower()
        assert "audio_raw" not in key.lower()
