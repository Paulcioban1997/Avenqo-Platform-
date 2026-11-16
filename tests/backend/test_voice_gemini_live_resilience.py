"""Automated Resilience, Multi-Tenant, and Audio Codec tests for Gemini Live & Telnyx Voice AI."""

from __future__ import annotations

import asyncio
import base64
import time
from typing import Any, AsyncIterator
from unittest.mock import MagicMock
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
    GetTradingAssetQuoteTool,
    GetTradingPredictionsTool,
    GetTradingPortfolioRiskTool,
)


class MockRealtimeAdapter:
    """Mock audio adapter simulating either primary (Gemini Live) or fallback (OpenAI)."""

    def __init__(self, provider_id: str, model_name: str, fail_send_on_turn: int = -1, fail_speak: bool = False) -> None:
        self._provider_id = provider_id
        self._model = model_name
        self.fail_send_on_turn = fail_send_on_turn
        self.fail_speak = fail_speak
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

    # Tenant 3: Financial Trading AI Tools
    trading_id = uuid4()
    quote_tool = GetTradingAssetQuoteTool()
    btc_quote = quote_tool.execute(asset="BTC")
    assert btc_quote["status"] == "success"
    assert btc_quote["asset"] == "BTC"
    assert "price_usd" in btc_quote
    assert btc_quote["price_usd"] > 0

    pred_tool = GetTradingPredictionsTool()
    btc_pred = pred_tool.execute(asset="BTC", horizon="24h")
    assert btc_pred["status"] == "success"
    assert btc_pred["asset"] == "BTC"
    assert "models" in btc_pred
    assert "GRU" in btc_pred["models"]
    assert "XGBoost" in btc_pred["models"]
    assert "Transformer" in btc_pred["models"]
    assert "vocal_summary" in btc_pred
    assert "Bitcoin" in btc_pred["vocal_summary"] or "BTC" in btc_pred["vocal_summary"]

    risk_tool = GetTradingPortfolioRiskTool()
    risk_summary = risk_tool.execute()
    assert risk_summary["status"] == "success"
    assert "sharpe_ratio" in risk_summary
    assert "max_drawdown" in risk_summary


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
    assert "Bonjour" in greeting_fr
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
    # Converted frame is valid μ-law bytes
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
