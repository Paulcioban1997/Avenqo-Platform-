"""Issue #132 P0 Regression, Premium Models & A/B Voice Architectures Test Suite.

Covers:
1. Priority 1 incident reproduction: slow (>2.8s) THINKING turns + unconfirmed Gemini
   `server_content.interrupted` (`barge_in=0`) -> 0 cancelled Central AI turns, 0 Telnyx clears,
   auto-recovery when TTS aborts before chunks finish, and 8/8 audible answers.
2. Zero ignored transcripts during THINKING: split continuations (`<=3.5s`) coalesce into the active
   turn; late follow-up questions queue sequentially without dropping words.
3. All 75 Avenqo business tools sanitize cleanly for `gemini-flash-latest` `generate_with_tools`
   (including Pydantic v2 `Optional` `anyOf` + `$defs`/`$ref` + unsupported `format` stripping), AND
   multi-provider gateway falls back safely if one provider rejects tool schemas.
4. `SmartModelRouter` selects `gpt-6.2-sol` (never `gpt-4o-mini`) for `business_reasoning/high`
   and `tool_orchestration` on `professional` plans; `gpt-6.2-astra` is cost-gated and `OpenAIProvider`
   uses `max_completion_tokens` + valid `reasoning_effort` (never `'none'` or legacy `max_tokens`).
5. Architecture A (`gpt-realtime-2.1` S2S + secure Avenqo tools + RBAC + `reserve_product` block)
   and Architecture B (Independent STT + `gpt-6.2-sol` + Independent PCM TTS) + per-tenant routing.
6. Single-call 20-question + 10-interruption stress protocol across A, B, and Repaired Hybrid.
7. Optional live API integration tests skipped cleanly when API keys are absent in local env.
"""

from __future__ import annotations

import asyncio
import audioop
import base64
from decimal import Decimal
import json
import os
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from backend.app.ai.llm.circuit_breaker import ProviderCircuitBreaker
from backend.app.ai.llm.exceptions import LLMProviderError
from backend.app.ai.llm.gateway import AvenqoAIGateway
from backend.app.ai.llm.gemini_provider import GeminiProvider, _sanitize_schema_for_gemini
from backend.app.ai.llm.health import ProviderHealthRegistry
from backend.app.ai.llm.model_registry import LLMRateCard
from backend.app.ai.llm.openai_provider import OpenAIProvider, _build_completion_params
from backend.app.ai.llm.router import (
    LLMRoutingContext,
    LLMTaskComplexity,
    LLMTaskType,
    SmartModelRouter,
    routing_context_for_chat,
)
from backend.app.ai.llm.schemas import LLMGeneration, LLMMessage, ToolDefinition
from backend.app.ai.tools.business.registry_factory import build_business_tool_registry
from backend.app.config.settings import Settings
from backend.app.voice.adapters import OpenAIAudioConfig, OpenAITextToSpeechAdapter
from backend.app.models.voice import VoiceBusinessConfig
from backend.app.voice.modular_pipeline_adapter import ModularVoicePipelineAdapter
from backend.app.voice.realtime_provider import (
    GeminiLiveRealtimeAudioAdapter,
    NaturalInterruptionManager,
    VoiceArchitectureMode,
    VoiceRealtimeRouter,
    resolve_voice_architecture_mode,
)
from backend.app.voice.s2s_realtime_adapter import OpenAISpeechToSpeechRealtimeAdapter
from backend.app.voice.telnyx_media import TelnyxMediaBridge
from backend.app.voice.turn_control import adjudicate_transcript
from backend.app.voice.usage import voice_pricing_catalog


class _MemTelnyxSocket:
    def __init__(self) -> None:
        self.inbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.outbound: list[dict[str, Any]] = []
        self.stream_id: str | None = None

    async def receive_json(self) -> dict[str, Any]:
        msg = await self.inbound.get()
        if isinstance(msg, dict) and msg.get("event") == "start":
            self.stream_id = msg.get("stream_id")
        return msg

    async def send_json(self, payload: dict[str, Any]) -> None:
        self.outbound.append(payload)
        if isinstance(payload, dict) and payload.get("event") == "mark" and self.stream_id:
            await self.inbound.put({"event": "mark", "stream_id": self.stream_id, "mark": payload.get("mark")})


def _pcm_24k(amplitude: int = 1200, frames: int = 1) -> bytes:
    """Return 20ms (or multiple of 20ms) 24kHz PCM16 bytes."""
    import struct
    samples = 480 * frames
    return struct.pack("<" + "h" * samples, *([amplitude, -amplitude] * (samples // 2)))


# ==============================================================================
# 1. PRIORITY 1: UNCONFIRMED GEMINI INTERRUPTS & >2.8s FILLER SELF-ABORT FIX
# ==============================================================================


@pytest.mark.asyncio
async def test_priority1_unconfirmed_interrupts_never_cancel_thinking_or_clear_audio() -> None:
    """Reproduces the Nov 24 2026 Railway incident:
    - Slow Central AI turns (>0.1s simulated / >2.8s real) MUST NOT be killed by thinking filler.
    - 6 unconfirmed Gemini Live `server_content.interrupted` events (`barge_in=0`) MUST NOT
      cancel `_current_turn_task`, bump `epoch`, or send `{"event": "clear"}` to Telnyx.
    - Aborted TTS responses auto-recover so all 8 turns produce audible Telnyx frames.
    """
    pcm_reply = _pcm_24k(1500, frames=4)

    class _UnstableGeminiSession:
        def __init__(self) -> None:
            self.q: asyncio.Queue[Any] = asyncio.Queue()
            self.client_contents: list[Any] = []
            self._attempts_by_prompt: dict[str, int] = {}
            self._turn_num = 0

        async def send_realtime_input(self, **_kw: Any) -> None:
            return None

        async def send_client_content(self, **kwargs: Any) -> None:
            turns = kwargs.get("turns")
            prompt_key = str(turns)
            attempt = self._attempts_by_prompt.get(prompt_key, 0) + 1
            self._attempts_by_prompt[prompt_key] = attempt
            if attempt == 1 and len(self._attempts_by_prompt) <= 6:
                # First attempt of first 6 answers aborts spontaneously with barge_in=0;
                # TelnyxMediaBridge auto-recovery re-speaks and succeeds on attempt 2!
                await self.q.put(
                    SimpleNamespace(
                        server_content=SimpleNamespace(
                            interrupted=True,
                            input_transcription=None,
                            output_transcription=None,
                            model_turn=None,
                            turn_complete=False,
                        )
                    )
                )
            else:
                await self.q.put(
                    SimpleNamespace(
                        server_content=SimpleNamespace(
                            interrupted=False,
                            input_transcription=None,
                            output_transcription=None,
                            model_turn=SimpleNamespace(
                                parts=[
                                    SimpleNamespace(
                                        inline_data=SimpleNamespace(
                                            data=pcm_reply,
                                            mime_type="audio/pcm;rate=24000",
                                        )
                                    )
                                ]
                            ),
                            turn_complete=True,
                        )
                    )
                )

        async def receive(self):
            while True:
                msg = await self.q.get()
                if msg is None:
                    return
                yield msg

    fake_sess = _UnstableGeminiSession()

    class _Ctx:
        async def __aenter__(self):
            return fake_sess

        async def __aexit__(self, *_a):
            await fake_sess.q.put(None)

    adapter = GeminiLiveRealtimeAudioAdapter(
        OpenAIAudioConfig(api_key="test", stt_model="gpt-4o-mini-transcribe", tts_voice="Aoede"),
        api_key="gem-test",
        company_name="Produits Ero",
        client_factory=lambda _k: SimpleNamespace(aio=SimpleNamespace(live=SimpleNamespace(connect=lambda **_kw: _Ctx()))),
    )

    sock = _MemTelnyxSocket()
    completed_central_turns: list[str] = []

    async def _slow_central(item_id: str, transcript: str) -> dict[str, Any]:
        await asyncio.sleep(0.03)
        completed_central_turns.append(item_id)
        return {"status": "success", "answer": f"Réponse complète pour {transcript[:40]}"}

    bridge = TelnyxMediaBridge(
        sock,
        adapter,
        locale="fr-CA",
        validate_start=AsyncMock(),
        authorize=AsyncMock(),
        execute_turn=_slow_central,
        realtime_model="gemini-3.8-live",
        stt_model="gpt-4o-mini-transcribe",
        max_output_queue=2000,
    )
    await sock.inbound.put({"event": "start", "stream_id": "inc-132", "start": {"stream_id": "inc-132", "media_format": {"encoding": "PCMU", "sample_rate": 8000, "channels": 1}}})
    bridge_task = asyncio.create_task(bridge.run())
    await asyncio.sleep(0.04)

    async def _wait_settled(expected_done: int) -> None:
        for _ in range(300):
            if (
                bridge.telemetry["voice_response_completed"] >= expected_done
                and not bridge._executing_turn
                and bridge.response_id is None
                and bridge.pending_epoch is None
                and not bridge._playback_active
                and bridge._output.empty()
                and bridge.phase == "LISTENING"
                and bridge._turns.empty()
            ):
                return
            await asyncio.sleep(0.01)

    for i in range(6):
        await fake_sess.q.put(
            SimpleNamespace(
                server_content=SimpleNamespace(
                    interrupted=False,
                    input_transcription=SimpleNamespace(text=f"Question entreprise numéro {i + 1}", finished=True),
                    output_transcription=None,
                    model_turn=None,
                    turn_complete=True,
                )
            )
        )
        # Inject an extra unconfirmed server_content.interrupted while THINKING
        await asyncio.sleep(0.01)
        if adapter._tts_active is False:
            adapter._tts_response_id = f"spurious-thinking-{i}"
            adapter._current_response_id = f"spurious-thinking-{i}"
            await fake_sess.q.put(
                SimpleNamespace(
                    server_content=SimpleNamespace(
                        interrupted=True,
                        input_transcription=None,
                        output_transcription=None,
                        model_turn=None,
                        turn_complete=False,
                    )
                )
            )
        await _wait_settled(i + 1)

    for i in range(6, 8):
        await fake_sess.q.put(
            SimpleNamespace(
                server_content=SimpleNamespace(
                    interrupted=False,
                    input_transcription=SimpleNamespace(text=f"Question entreprise numéro {i + 1}", finished=True),
                    output_transcription=None,
                    model_turn=None,
                    turn_complete=True,
                )
            )
        )
        await _wait_settled(i + 1)

    await sock.inbound.put({"event": "stop", "stream_id": "inc-132"})
    await asyncio.wait_for(bridge_task, timeout=5.0)

    clear_events = [m for m in sock.outbound if m.get("event") == "clear"]
    media_events = [m for m in sock.outbound if m.get("event") == "media"]
    assert len(completed_central_turns) == 8
    assert bridge.telemetry["tts_auto_recoveries"] == 6
    assert bridge.telemetry["voice_response_completed"] == 8
    assert bridge.telemetry["telnyx_clear_sent_count"] == 0
    assert len(clear_events) == 0
    assert bridge.telemetry["unconfirmed_provider_interrupts_suppressed"] >= 6
    assert bridge.central_ai_missing_answers == 0
    assert len(media_events) >= 8


# ==============================================================================
# 2. ZERO IGNORED TRANSCRIPTS DURING THINKING (COALESCE + QUEUE)
# ==============================================================================


@pytest.mark.asyncio
async def test_thinking_phase_coalesces_split_continuation_and_queues_followup() -> None:
    # 1) Split clause within 3.5s -> coalesce (NOT ignore!)
    assert adjudicate_transcript(
        "pour 2028",
        phase="THINKING",
        in_flight_transcript="Donne-moi trois stratégies",
        in_flight_age_seconds=1.2,
    ) == "coalesce"

    # 2) Follow-up arriving later (>3.5s) -> queue sequentially
    assert adjudicate_transcript(
        "et nos casques ?",
        phase="THINKING",
        in_flight_transcript="Donne-moi trois stratégies",
        in_flight_age_seconds=4.5,
    ) == "queue"

    # 2b) Distinct substantive follow-up with active turn -> queue; 1-word non-continuation noise -> ignore
    assert adjudicate_transcript(
        "Quel est notre chiffre d'affaires ce mois-ci ?",
        phase="THINKING",
        in_flight_transcript="Donne-moi trois stratégies",
        in_flight_age_seconds=1.2,
    ) == "queue"
    assert adjudicate_transcript(
        "voyons",
        phase="THINKING",
        in_flight_transcript="Donne-moi trois stratégies",
        in_flight_age_seconds=1.2,
    ) == "ignore"

    # 3) Bridge integration: split question merges and later follow-up queues -> 0 dropped!
    pcm_reply = _pcm_24k(1200, frames=2)

    class _QueueAdapter:
        provider_id = "mock"
        supports_concurrent_filler = False

        def __init__(self) -> None:
            self.q: asyncio.Queue[Any] = asyncio.Queue()
            self.spoken: list[str] = []

        async def open(self, *, locale: str = "fr-CA") -> None:
            await self.q.put(SimpleNamespace(type="session.updated"))

        async def send_audio(self, _audio: bytes) -> None:
            return None

        async def speak(self, text: str) -> None:
            self.spoken.append(text)
            rid = f"r-{len(self.spoken)}"
            await self.q.put(SimpleNamespace(type="response.created", response=SimpleNamespace(id=rid)))
            await self.q.put(SimpleNamespace(type="response.output_audio.delta", response_id=rid, delta=base64.b64encode(pcm_reply).decode("ascii")))
            await self.q.put(SimpleNamespace(type="response.done", response=SimpleNamespace(id=rid, status="completed")))

        async def interrupt(self) -> None:
            return None

        async def clear_input(self) -> None:
            return None

        async def close(self) -> None:
            await self.q.put(None)

        async def events(self):
            while True:
                ev = await self.q.get()
                if ev is None:
                    break
                yield ev

    adapter = _QueueAdapter()
    sock = _MemTelnyxSocket()
    received_queries: list[str] = []

    async def _exec(item_id: str, transcript: str) -> dict[str, Any]:
        if item_id == "t-first":
            await asyncio.sleep(0.15)
        else:
            await asyncio.sleep(0.02)
        received_queries.append(transcript)
        return {"status": "success", "answer": f"OK: {transcript}"}

    bridge = TelnyxMediaBridge(
        sock, adapter, locale="fr-CA",
        validate_start=AsyncMock(), authorize=AsyncMock(), execute_turn=_exec,
    )
    await sock.inbound.put({"event": "start", "stream_id": "s-coal", "start": {"stream_id": "s-coal", "media_format": {"encoding": "PCMU", "sample_rate": 8000, "channels": 1}}})
    task = asyncio.create_task(bridge.run())
    await asyncio.sleep(0.03)

    await adapter.q.put(SimpleNamespace(type="conversation.item.input_audio_transcription.completed", item_id="t-first", transcript="Donne-moi trois stratégies"))
    await asyncio.sleep(0.03)  # Bridge is now in THINKING (<3.5s)
    await adapter.q.put(SimpleNamespace(type="conversation.item.input_audio_transcription.completed", item_id="t-cont", transcript="pour 2028"))
    await asyncio.sleep(0.15)

    await sock.inbound.put({"event": "stop", "stream_id": "s-coal"})
    await asyncio.wait_for(task, timeout=5.0)

    assert bridge.telemetry["turns_coalesced"] == 1
    assert any("Donne-moi trois stratégies pour 2028" in q for q in received_queries)


# ==============================================================================
# 3. GEMINI TOOL SCHEMA SANITIZATION (ALL 75 TOOLS) + GATEWAY FALLBACK
# ==============================================================================


def test_gemini_sanitizes_all_75_business_tools_without_anyof_or_invalid_request() -> None:
    from google.genai import types

    reg = build_business_tool_registry(MagicMock(), MagicMock(), MagicMock())
    tools = list(getattr(reg, "_tools", {}).values())
    assert len(tools) >= 70

    for tool in tools:
        defn = tool.definition()
        sanitized = _sanitize_schema_for_gemini(defn.parameters_schema)
        decl = types.FunctionDeclaration(
            name=defn.name,
            description=defn.description,
            parameters=sanitized,
        )
        dumped = decl.model_dump(exclude_none=True)
        assert "anyOf" not in str(dumped), f"anyOf leaked into Gemini schema for {defn.name}"
        assert "$defs" not in str(dumped), f"$defs leaked into Gemini schema for {defn.name}"


@pytest.mark.asyncio
async def test_gateway_falls_back_from_gemini_tool_invalid_request_to_sol() -> None:
    from backend.app.ai.llm.base import LLMProvider

    class _FailingGemini(LLMProvider):
        name = "gemini"
        _model = "gemini-flash-latest"
        supports_tool_calling = True

        async def generate(self, *, system_instruction: str, prompt: str):
            raise NotImplementedError

        async def stream(self, *, system_instruction: str, prompt: str):
            if False:
                yield ""

        async def generate_with_tools(self, *, system_instruction, messages, tools):
            err = LLMProviderError("bad tool schema")
            err.__cause__ = RuntimeError("400 INVALID_ARGUMENT")
            raise err

    class _HealthySol(LLMProvider):
        name = "openai"
        _model = "gpt-6.2-sol"
        supports_tool_calling = True

        async def generate(self, *, system_instruction: str, prompt: str):
            return LLMGeneration("ok", "openai", "gpt-6.2-sol", {})

        async def stream(self, *, system_instruction: str, prompt: str):
            yield "ok"

        async def generate_with_tools(self, *, system_instruction, messages, tools):
            from backend.app.ai.llm.schemas import LLMToolResponse, LLMUsage
            usage = LLMUsage(provider="openai", model="gpt-6.2-sol", input_tokens=50, output_tokens=20)
            return LLMToolResponse(
                content="Réponse sécurisée Sol",
                tool_calls=(),
                provider="openai",
                model="gpt-6.2-sol",
                token_usage=usage.as_token_usage(),
                usage=usage,
            )

    gateway = AvenqoAIGateway(
        [_FailingGemini(), _HealthySol()],
        circuit_breaker=ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=60),
        health_registry=ProviderHealthRegistry(),
        max_retries_per_provider=0,
        base_delay_seconds=0.0,
        max_delay_seconds=0.0,
    )
    res = await gateway.generate_with_tools(
        system_instruction="sys",
        messages=[LLMMessage(role="user", content="test")],
        tools=[ToolDefinition(name="search_products", description="search", parameters_schema={"type": "object", "properties": {}})],
    )
    assert res.provider == "openai"
    assert res.model == "gpt-6.2-sol"


# ==============================================================================
# 4. SMART MODEL ROUTER & GPT-6.2 SOL / ASTRA PARAMETERS
# ==============================================================================


def test_smart_router_prefers_gpt62_sol_over_gpt4o_mini_on_professional_high_reasoning() -> None:
    rate_card = LLMRateCard.from_models({"openai": ("gpt-4o-mini", "gpt-6.2-sol", "gpt-6.2-astra")})
    health = ProviderHealthRegistry()
    specs: dict[str | tuple[str, str], Any] = {
        ("openai", m): rate_card.spec_for("openai", m)
        for m in ("gpt-4o-mini", "gpt-6.2-sol", "gpt-6.2-astra")
    }
    router = SmartModelRouter(specs, health)
    providers = [
        OpenAIProvider("k", "gpt-4o-mini", 0.2, 800),
        OpenAIProvider("k", "gpt-6.2-sol", 0.2, 800),
        OpenAIProvider("k", "gpt-6.2-astra", 0.2, 800),
    ]

    # Voice & high business reasoning on professional plan -> MUST pick gpt-6.2-sol (NOT gpt-4o-mini, NOT costly Astra)
    ctx_voice = routing_context_for_chat(
        query="Analyse pourquoi nos ventes de casques ont chuté et recommande trois actions.",
        prompt="x" * 2000,
        has_tools=True,
        plan_code="professional",
        remaining_credits=5000,
        avenqo_request_id="req-sol-1",
        latency_sensitive=True,
    )
    decision = router.decide(providers, ctx_voice)
    assert decision.selected_model == "gpt-6.2-sol"

    # Explicit deep non-latency REASONING with healthy credits -> cost-gated escalation to gpt-6.2-astra
    ctx_deep = LLMRoutingContext(
        task_type=LLMTaskType.BUSINESS_REASONING,
        complexity=LLMTaskComplexity.REASONING,
        context_tokens=4000,
        expected_output_tokens=1000,
        requires_tool_calling=True,
        requires_reasoning=True,
        latency_sensitive=False,
        plan_code="professional",
        remaining_credits=5000,
    )
    assert router.decide(providers, ctx_deep).selected_model == "gpt-6.2-astra"


def test_openai_provider_uses_valid_gpt62_parameters_never_none_reasoning_effort() -> None:
    sol_params = _build_completion_params("gpt-6.2-sol", temperature=0.2, max_tokens=800, reasoning_effort="none")
    assert "max_completion_tokens" in sol_params and sol_params["max_completion_tokens"] == 800
    assert "max_tokens" not in sol_params
    assert "temperature" not in sol_params
    assert sol_params["reasoning_effort"] == "low"

    astra_params = _build_completion_params("gpt-6.2-astra", temperature=0.2, max_tokens=1200)
    assert astra_params == {"max_completion_tokens": 1200, "reasoning_effort": "medium"}

    legacy_params = _build_completion_params("gpt-4o-mini", temperature=0.2, max_tokens=800)
    assert legacy_params == {"temperature": 0.2, "max_tokens": 800}


# ==============================================================================
# 5. ARCHITECTURE A (S2S gpt-realtime-2.1) & ARCHITECTURE B (MODULAR STT+SOL+TTS)
# ==============================================================================


@pytest.mark.asyncio
async def test_architecture_a_s2s_gpt_realtime_2_1_tools_and_security() -> None:
    cfg = SimpleNamespace(
        company_id=uuid4(),
        call_policy={"voice_architecture": "architecture_a_s2s"},
        voice_id="marin",
        personality_preset="professional_premium_warm",
        professionalism_level=100,
        warmth_level=85,
        humor_level=40,
        formality_level=65,
        allow_natural_interruptions=True,
        business_name="Produits Ero",
    )
    settings = Settings(**cast(dict[str, Any], {
        "_env_file": None,
        "ENVIRONMENT": "sandbox",
        "AUTH_JWT_SECRET": "sandbox-test-only-jwt-secret-key-minimum-32-chars",
    }))
    assert resolve_voice_architecture_mode(cast(VoiceBusinessConfig, cfg), settings) == VoiceArchitectureMode.ARCHITECTURE_A_S2S

    sent_ws: list[dict[str, Any]] = []
    tool_calls_executed: list[tuple[str, dict[str, Any]]] = []
    ws_queue: asyncio.Queue[Any] = asyncio.Queue()

    class _FakeConn:
        async def send(self, payload: dict[str, Any]) -> None:
            sent_ws.append(payload)

        def __aiter__(self):
            return self

        async def __anext__(self):
            item = await ws_queue.get()
            if item is None:
                raise StopAsyncIteration
            return item

    class _FakeMgr:
        async def __aenter__(self):
            return _FakeConn()

        async def __aexit__(self, *_a):
            await ws_queue.put(None)

    async def _exec_tool(turn_id: str, call_id: str, name: str, args: dict[str, Any]) -> dict[str, Any]:
        tool_calls_executed.append((name, args))
        return {"success": True, "products": [{"name": "Casque Alpin", "price": 129.99, "stock": 14}]}

    mgr = NaturalInterruptionManager()
    adapter = OpenAISpeechToSpeechRealtimeAdapter(
        OpenAIAudioConfig(api_key="test", stt_model="gpt-4o-mini-transcribe", tts_voice="marin"),
        settings=settings,
        config=cast(VoiceBusinessConfig, cfg),
        model="gpt-realtime-2.1",
        company_name="Produits Ero",
        tool_provider=lambda: [
            {"name": "search_products", "description": "Search catalog", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}}},
            {"name": "reserve_product", "description": "Should always be filtered out", "parameters": {"type": "object", "properties": {}}},
        ],
        tool_executor=_exec_tool,
        interruption_manager=mgr,
        connection_factory=lambda _m: _FakeMgr(),
    )
    await adapter.open(locale="fr-CA")
    session_upd = next(p for p in sent_ws if p.get("type") == "session.update")
    exposed_tool_names = [t["name"] for t in session_upd["session"]["tools"]]
    assert "search_products" in exposed_tool_names
    assert "reserve_product" not in exposed_tool_names

    # Trigger allowed tool + hard-blocked reserve_product attempt from model
    await ws_queue.put({"type": "response.function_call_arguments.done", "call_id": "c1", "name": "search_products", "arguments": '{"query":"casque"}'})
    await ws_queue.put({"type": "response.function_call_arguments.done", "call_id": "c2", "name": "reserve_product", "arguments": '{"product":"casque"}'})
    await asyncio.sleep(0.05)

    assert tool_calls_executed == [("search_products", {"query": "casque"})]
    outputs = [p for p in sent_ws if p.get("type") == "conversation.item.create" and p.get("item", {}).get("type") == "function_call_output"]
    assert len(outputs) == 2
    assert "tool_blocked_or_turn_cancelled" in outputs[1]["item"]["output"]
    await adapter.close()

    # Verify Architecture A security hook arms TelnyxMediaBridge PIN gate on private query
    sock_sec = _MemTelnyxSocket()
    conn_sec_q: asyncio.Queue[Any] = asyncio.Queue()

    class _SecConn:
        async def send(self, _p): return None
        def __aiter__(self): return self
        async def __anext__(self):
            it = await conn_sec_q.get()
            if it is None: raise StopAsyncIteration
            return it

    class _SecMgr:
        async def __aenter__(self): return _SecConn()
        async def __aexit__(self, *_a): await conn_sec_q.put(None)

    async def _sec_hook(_item_id: str, _transcript: str) -> dict[str, Any] | None:
        return {"handled": True, "auth_required": True, "answer": "Veuillez entrer votre NIP sur le clavier."}

    adapter_sec = OpenAISpeechToSpeechRealtimeAdapter(
        OpenAIAudioConfig(api_key="test", stt_model="gpt-4o-mini-transcribe", tts_voice="marin"),
        settings=settings,
        config=cast(VoiceBusinessConfig, cfg),
        model="gpt-realtime-2.1",
        company_name="Produits Ero",
        security_transcript_hook=_sec_hook,
        connection_factory=lambda _m: _SecMgr(),
    )
    bridge_sec = TelnyxMediaBridge(
        sock_sec, adapter_sec, locale="fr-CA",
        validate_start=AsyncMock(), authorize=AsyncMock(), execute_turn=AsyncMock(),
        begin_pin=AsyncMock(return_value={"success": True}),
        poll_pin=AsyncMock(return_value="pending"),
    )
    await sock_sec.inbound.put({"event": "start", "stream_id": "s2s-sec", "start": {"stream_id": "s2s-sec", "media_format": {"encoding": "PCMU", "sample_rate": 8000, "channels": 1}}})
    t_sec = asyncio.create_task(bridge_sec.run())
    await asyncio.sleep(0.03)
    await conn_sec_q.put({"type": "conversation.item.input_audio_transcription.completed", "item_id": "sec-pin-1", "transcript": "Quel est mon chiffre d'affaires ?"})
    await asyncio.sleep(0.05)
    assert bridge_sec._pin_turn == "sec-pin-1"
    await sock_sec.inbound.put({"event": "stop", "stream_id": "s2s-sec"})
    await asyncio.wait_for(t_sec, timeout=5.0)


@pytest.mark.asyncio
async def test_architecture_b_modular_pipeline_streams_pcm_and_handles_barge_in() -> None:
    cfg = SimpleNamespace(company_id=uuid4(), call_policy={"voice_architecture": "architecture_b_modular"})
    settings = Settings(**cast(dict[str, Any], {
        "_env_file": None,
        "ENVIRONMENT": "sandbox",
        "AUTH_JWT_SECRET": "sandbox-test-only-jwt-secret-key-minimum-32-chars",
    }))
    router = VoiceRealtimeRouter(settings)
    built = router.build_realtime_adapter(
        cast(VoiceBusinessConfig, cfg),
        OpenAIAudioConfig(api_key="test", stt_model="gpt-4o-mini-transcribe", tts_model="gpt-4o-mini-tts", tts_voice="marin"),
        fallback_factory=lambda: None,  # type: ignore[arg-type]
    )
    assert isinstance(built, ModularVoicePipelineAdapter)

    # Exercise end-to-end STT -> TelnyxMediaBridge -> Sol Central AI -> PCM TTS
    class _StubSTT:
        provider_id = "openai"

        async def transcribe(self, audio: bytes, *, locale: str, content_type: str) -> str:
            _ = audio
            return "Quels sont nos modules actifs ?"

    class _StubTTS:
        async def synthesize_pcm_chunks(self, _text: str, *, locale: str):
            for _ in range(3):
                yield _pcm_24k(900, frames=2)
                await asyncio.sleep(0.01)

    mod = ModularVoicePipelineAdapter(
        OpenAIAudioConfig(api_key="test", stt_model="gpt-4o-mini-transcribe", tts_model="gpt-4o-mini-tts", tts_voice="marin"),
        stt_adapter=_StubSTT(),
        tts_adapter=_StubTTS(),
    )
    sock = _MemTelnyxSocket()
    bridge = TelnyxMediaBridge(
        sock,
        mod,
        locale="fr-CA",
        validate_start=AsyncMock(),
        authorize=AsyncMock(),
        execute_turn=AsyncMock(return_value={"status": "success", "answer": "Vos modules sont Retail AI et Voice AI."}),
        realtime_model="gpt-4o-mini-tts",
        stt_model="gpt-4o-mini-transcribe",
    )
    await sock.inbound.put({"event": "start", "stream_id": "mod-call", "start": {"stream_id": "mod-call", "media_format": {"encoding": "PCMU", "sample_rate": 8000, "channels": 1}}})
    run_task = asyncio.create_task(bridge.run())
    await asyncio.sleep(0.03)

    speech_ulaw = base64.b64encode(audioop.lin2ulaw(_pcm_24k(1500)[:320], 2)).decode("ascii")
    silence_ulaw = base64.b64encode(audioop.lin2ulaw(b"\x00" * 320, 2)).decode("ascii")
    for ch in range(1, 5):
        await sock.inbound.put({"event": "media", "stream_id": "mod-call", "media": {"chunk": str(ch), "payload": speech_ulaw}})
    for ch in range(5, 19):
        await sock.inbound.put({"event": "media", "stream_id": "mod-call", "media": {"chunk": str(ch), "payload": silence_ulaw}})
    await asyncio.sleep(0.15)
    await sock.inbound.put({"event": "stop", "stream_id": "mod-call"})
    await asyncio.wait_for(run_task, timeout=5.0)

    assert bridge.telemetry["stt_final_count"] == 1
    assert bridge.telemetry["voice_response_completed"] == 1
    assert bridge.telemetry["unconfirmed_provider_interrupts_suppressed"] == 0
    assert len([m for m in sock.outbound if m.get("event") == "media"]) >= 3


# ==============================================================================
# 6. SINGLE-CALL STRESS PROTOCOL: 20 QUESTIONS + 10 INTERRUPTIONS
# ==============================================================================


@pytest.mark.asyncio
async def test_single_call_20_questions_and_10_interruptions_zero_lost_turns() -> None:
    from scripts.voice_sandbox_ab_protocol import run_deterministic_ab_benchmark

    results = await run_deterministic_ab_benchmark(seed=132)
    assert len(results) == 3
    for res in results:
        assert res.questions_asked == 20
        assert res.lost_turns == 0, f"{res.architecture} lost {res.lost_turns} turns"
        assert res.audible_answers >= 20, f"{res.architecture} had {res.audible_answers} < 20"
        if res.interruptions_sent > 0:
            assert res.interruptions_handled == 10


# ==============================================================================
# 7. PRICING CATALOG FOR GPT-REALTIME-2.1, GPT-6.2-SOL, GPT-6.2-ASTRA
# ==============================================================================


def test_pricing_catalog_covers_all_issue_132_models() -> None:
    cat = voice_pricing_catalog()
    rt = cat.lookup("openai", "gpt-realtime-2.1")
    assert rt.audio_input_cost_per_million_usd == Decimal("32")
    assert rt.audio_output_cost_per_million_usd == Decimal("64")
    rt_mini = cat.lookup("openai", "gpt-realtime-2.1-mini")
    assert rt_mini.audio_input_cost_per_million_usd == Decimal("10")
    sol = cat.lookup("openai", "gpt-6.2-sol")
    assert sol.input_cost_per_million_usd == Decimal("2.00")
    astra = cat.lookup("openai", "gpt-6.2-astra")
    assert astra.output_cost_per_million_usd == Decimal("40.00")


# ==============================================================================
# 8. ENV-GATED LIVE PROVIDER INTEGRATION CHECKS (HONEST LOCAL SKIP IF NO KEYS)
# ==============================================================================


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not present locally")
async def test_live_openai_gpt62_sol_and_tool_calling() -> None:
    provider = OpenAIProvider(os.getenv("OPENAI_API_KEY"), "gpt-6.2-sol", 0.2, 250)
    res = await provider.generate_with_tools(
        system_instruction="Answer briefly in French.",
        messages=[LLMMessage(role="user", content="Quel est l'avantage d'un casque certifié ?")],
        tools=[ToolDefinition(name="search_products", description="Search catalog", parameters_schema={"type": "object", "properties": {"query": {"type": "string"}}})],
    )
    assert res.content or res.tool_calls


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("GOOGLE_AI_API_KEY"), reason="GOOGLE_AI_API_KEY not present locally")
async def test_live_gemini_flash_latest_generate_with_tools() -> None:
    provider = GeminiProvider(os.getenv("GOOGLE_AI_API_KEY"), "gemini-flash-latest", 0.2, 250)
    res = await provider.generate_with_tools(
        system_instruction="Answer briefly in French.",
        messages=[LLMMessage(role="user", content="Cherche un casque de snowboard")],
        tools=[ToolDefinition(name="search_products", description="Search catalog", parameters_schema={"type": "object", "properties": {"query": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None}}})],
    )
    assert res.content or res.tool_calls


# ==============================================================================
# 9. PR #133 AUDIT FIXES: STRICT REALTIME CONTRACT, PRE-PIN BARRIER, *** SPEECH
# ==============================================================================


def test_s2s_session_update_conforms_strictly_to_openai_realtime_sdk_schema() -> None:
    """Audit Blocker #1: Validate session.update against official OpenAI Realtime SDK schema."""
    from openai.types.realtime.realtime_session_create_request import RealtimeSessionCreateRequest
    from openai.types.realtime.session_update_event import SessionUpdateEvent

    adapter = OpenAISpeechToSpeechRealtimeAdapter(
        OpenAIAudioConfig(api_key="test", stt_model="gpt-4o-mini-transcribe", tts_voice="marin"),
        model="gpt-realtime-2.1",
        company_name="Produits Ero",
        tool_provider=lambda: [
            {
                "name": "search_products",
                "description": "Search catalog",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
            }
        ],
    )
    payload = adapter._session_update_payload("fr-CA")
    session_dict = payload["session"]

    # Must strictly be ["audio"], NEVER ["audio", "text"]
    assert session_dict["output_modalities"] == ["audio"]
    # Must NEVER auto-create a response before server PIN / RBAC / handover gate runs
    assert session_dict["audio"]["input"]["turn_detection"]["create_response"] is False

    validated_session = RealtimeSessionCreateRequest.model_validate(session_dict)
    assert validated_session.output_modalities == ["audio"]
    validated_event = SessionUpdateEvent.model_validate(payload)
    assert validated_event.type == "session.update"


@pytest.mark.asyncio
async def test_s2s_zero_audio_or_tool_leakage_before_pin_and_during_delayed_stt_or_handover() -> None:
    """Audit Blocker #2: Zero private audio or tool execution before PIN auth, on delayed STT, or during handover."""
    sock = _MemTelnyxSocket()
    ws_in: asyncio.Queue[Any] = asyncio.Queue()
    ws_sent: list[dict[str, Any]] = []
    executed_tools: list[str] = []

    class _GateConn:
        async def send(self, payload: dict[str, Any]) -> None:
            ws_sent.append(payload)
            # Only respond with audio when authorized system PIN/handover prompt (conversation='none') is requested
            if payload.get("type") == "response.create" and payload.get("response", {}).get("conversation") == "none":
                rid = f"sys-{len(ws_sent)}"
                await ws_in.put({"type": "response.created", "response": {"id": rid}})
                await ws_in.put({
                    "type": "response.audio.delta",
                    "response_id": rid,
                    "delta": base64.b64encode(_pcm_24k(900, frames=2)).decode("ascii"),
                })
                await ws_in.put({"type": "response.done", "response": {"id": rid, "status": "completed"}})

        def __aiter__(self):
            return self

        async def __anext__(self):
            it = await ws_in.get()
            if it is None:
                raise StopAsyncIteration
            return it

    class _GateMgr:
        async def __aenter__(self):
            return _GateConn()

        async def __aexit__(self, *_a):
            await ws_in.put(None)

    is_staff = {"auth": False}

    async def _sec_hook(_item_id: str, transcript: str) -> dict[str, Any] | None:
        low = transcript.lower()
        if not is_staff["auth"] and ("chiffre" in low or "marge" in low or "revenu" in low):
            return {
                "handled": True,
                "auth_required": True,
                "answer": "Veuillez composer votre NIP sur le clavier.",
            }
        if is_staff["auth"] and "collègue" in low:
            is_staff["auth"] = False
            adapter.update_staff_identity(False, None, None)
            return {
                "handled": True,
                "auth_required": True,
                "answer": "Session clôturée. Le nouveau collaborateur doit saisir son NIP.",
            }
        return None

    async def _tool_exec(_turn_id: str, _cid: str, name: str, _args: dict[str, Any]) -> dict[str, Any]:
        executed_tools.append(name)
        return {"success": True, "secret_revenue": "999999 CAD"}

    adapter = OpenAISpeechToSpeechRealtimeAdapter(
        OpenAIAudioConfig(api_key="test", stt_model="gpt-4o-mini-transcribe", tts_voice="marin"),
        model="gpt-realtime-2.1",
        company_name="Produits Ero",
        tool_provider=lambda: [
            {"name": "get_sales_summary", "description": "Private KPI", "parameters": {"type": "object", "properties": {}}}
        ],
        tool_executor=_tool_exec,
        security_transcript_hook=_sec_hook,
        connection_factory=lambda _m: _GateMgr(),
    )
    bridge = TelnyxMediaBridge(
        sock,
        adapter,
        locale="fr-CA",
        validate_start=AsyncMock(),
        authorize=AsyncMock(),
        execute_turn=AsyncMock(),
        begin_pin=AsyncMock(return_value={"success": True}),
        poll_pin=AsyncMock(return_value="pending"),
    )
    await sock.inbound.put({
        "event": "start",
        "stream_id": "s2s-strict-gate",
        "start": {"stream_id": "s2s-strict-gate", "media_format": {"encoding": "PCMU", "sample_rate": 8000, "channels": 1}},
    })
    run_task = asyncio.create_task(bridge.run())
    await asyncio.sleep(0.04)

    # 1) Simulate delayed STT: rogue/speculative response.created + audio.delta + tool call BEFORE transcript completes!
    await ws_in.put({"type": "input_audio_buffer.speech_started", "item_id": "pre-auth-1"})
    await ws_in.put({"type": "response.created", "response": {"id": "rogue-pre-auth"}})
    await ws_in.put({
        "type": "response.audio.delta",
        "response_id": "rogue-pre-auth",
        "delta": base64.b64encode(_pcm_24k(1800, frames=3)).decode("ascii"),
    })
    await ws_in.put({
        "type": "response.function_call_arguments.done",
        "call_id": "rogue-fc-1",
        "name": "get_sales_summary",
        "arguments": "{}",
    })
    await asyncio.sleep(0.05)

    # ZERO outbound media frames and ZERO executed tools before transcription + security hook!
    assert [m for m in sock.outbound if m.get("event") == "media"] == []
    assert executed_tools == []
    assert adapter.dropped_unauthorized_audio_chunks >= 1
    assert adapter.blocked_unauthorized_tool_calls >= 1

    # 2) Delayed STT arrives asking confidential revenue -> security hook intercepts & arms PIN, ZERO conversational response.create!
    await ws_in.put({
        "type": "conversation.item.input_audio_transcription.completed",
        "item_id": "pre-auth-1",
        "transcript": "Quel est notre chiffre d'affaires confidentiel ?",
    })
    await asyncio.sleep(0.08)
    assert bridge._pin_turn == "pre-auth-1"
    assert adapter._auth_gate_locked is True
    conversational_creates = [
        p for p in ws_sent
        if p.get("type") == "response.create" and p.get("response", {}).get("conversation") != "none"
    ]
    assert conversational_creates == []
    assert executed_tools == []

    # 3) Authenticate staff, clear PIN state, verify authorized turn works, then trigger handover revocation!
    bridge._pin_turn = None
    is_staff["auth"] = True
    adapter.update_staff_identity(True, "Francis", "owner")
    await asyncio.sleep(0.02)

    await ws_in.put({
        "type": "conversation.item.input_audio_transcription.completed",
        "item_id": "handover-1",
        "transcript": "Je passe le téléphone à mon collègue.",
    })
    # Racing function call arriving during handover must be hard-blocked!
    await ws_in.put({
        "type": "response.function_call_arguments.done",
        "call_id": "handover-fc-race",
        "name": "get_sales_summary",
        "arguments": "{}",
    })
    await asyncio.sleep(0.08)
    assert adapter._auth_gate_locked is True
    assert executed_tools == []
    assert adapter.blocked_unauthorized_tool_calls >= 2

    await sock.inbound.put({"event": "stop", "stream_id": "s2s-strict-gate"})
    await asyncio.wait_for(run_task, timeout=5.0)


def test_railway_sandbox_legacy_openai_model_env_upgrades_to_gpt62_sol() -> None:
    """Audit Finding #4: Legacy OPENAI_MODEL=gpt-4o-mini on Sandbox upgrades to gpt-6.2-sol unless explicitly pinned in AI_PROVIDER_MODELS."""
    from backend.app.ai.llm.factory import LLMProviderFactory

    sandbox_legacy = Settings(**cast(dict[str, Any], {
        "_env_file": None,
        "ENVIRONMENT": "sandbox",
        "AUTH_JWT_SECRET": "sandbox-test-only-jwt-secret-key-minimum-32-chars",
        "AI_PRIMARY_PROVIDER": "openai",
        "OPENAI_API_KEY": "test-key",
        "OPENAI_MODEL": "gpt-4o-mini",
        "GOOGLE_AI_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
    }))
    gw = LLMProviderFactory.create_gateway(sandbox_legacy)
    assert isinstance(gw, AvenqoAIGateway)
    assert [(p.name, getattr(p, "_model", None)) for p in gw._providers] == [("openai", "gpt-6.2-sol")]

    # Explicit AI_PROVIDER_MODELS remains authoritative if operator intentionally specifies models
    explicit_override = Settings(**cast(dict[str, Any], {
        "_env_file": None,
        "ENVIRONMENT": "sandbox",
        "AUTH_JWT_SECRET": "sandbox-test-only-jwt-secret-key-minimum-32-chars",
        "AI_PRIMARY_PROVIDER": "openai",
        "OPENAI_API_KEY": "test-key",
        "OPENAI_MODEL": "gpt-4o-mini",
        "AI_PROVIDER_MODELS": {"openai": ["gpt-4o-mini", "gpt-6.2-sol"]},
        "GOOGLE_AI_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
    }))
    gw_explicit = LLMProviderFactory.create_gateway(explicit_override)
    assert isinstance(gw_explicit, AvenqoAIGateway)
    assert [(p.name, getattr(p, "_model", None)) for p in gw_explicit._providers] == [
        ("openai", "gpt-4o-mini"),
        ("openai", "gpt-6.2-sol"),
    ]


@pytest.mark.asyncio
async def test_zero_spoken_asterisks_across_voice_and_central_tts() -> None:
    """Ensure '***' or '**' is NEVER pronounced as 'astérisque astérisque' in Voice or Central AI."""
    from backend.app.ai.chat.chat_service import _sanitize_assistant_content
    from backend.app.voice.messages import strip_markdown_for_speech
    from backend.app.voice.realtime_rotation import RotatingRealtimeAdapter
    from backend.app.voice.telnyx_media import clean_voice_text

    raw_llm_output = (
        "***\n"
        "### Plan de croissance 2027\n"
        "1. **Stratégie Alpha** : ***Expansion logistique*** avec `compare_at_price` optimisé.\n"
        "* Deuxième axe : fidélisation VIP.\n"
        "***\n"
        "Voici le résumé **important**."
    )
    spoken_voice = clean_voice_text(raw_llm_output, locale="fr-CA")
    spoken_generic = strip_markdown_for_speech(raw_llm_output)
    central_voice = _sanitize_assistant_content(raw_llm_output, is_voice=True)
    central_web = _sanitize_assistant_content(raw_llm_output, is_voice=False)

    assert "*" not in spoken_voice
    assert "#" not in spoken_voice
    assert "`" not in spoken_voice
    assert "compare_at_price" not in spoken_voice
    assert "*" not in spoken_generic
    assert "*" not in central_voice
    assert "***" not in central_web

    # Verify OpenAITextToSpeechAdapter strips markdown before sending input to OpenAI TTS
    captured_tts_inputs: list[str] = []

    class _FakeSpeechEndpoint:
        async def create(self, **kwargs: Any):
            captured_tts_inputs.append(str(kwargs.get("input") or ""))
            return b"\x00\x01" * 100

    fake_openai = SimpleNamespace(audio=SimpleNamespace(speech=_FakeSpeechEndpoint()))
    tts = OpenAITextToSpeechAdapter(
        OpenAIAudioConfig(api_key="test", tts_model="gpt-4o-mini-tts", tts_voice="marin"),
        client=cast(Any, fake_openai),
    )
    await tts.synthesize_pcm(raw_llm_output, locale="fr-CA")
    assert len(captured_tts_inputs) == 1
    assert "*" not in captured_tts_inputs[0]

    # Verify RotatingRealtimeAdapter delegates native_s2s_enabled & staff identity cleanly EVEN BEFORE open()
    s2s = OpenAISpeechToSpeechRealtimeAdapter(
        OpenAIAudioConfig(api_key="test", stt_model="gpt-4o-mini-transcribe", tts_voice="marin"),
    )
    rot = RotatingRealtimeAdapter(lambda: s2s, AsyncMock(), rotation_seconds=3000)
    assert rot.native_s2s_enabled is True
    assert rot.supports_concurrent_filler is False
    rot.update_staff_identity(True, "Francis", "owner")
    assert s2s._is_authenticated_staff is True


@pytest.mark.asyncio
async def test_audit_pr133_all_copilot_threads_regression(tmp_path: Any) -> None:
    """Comprehensive verification for PR #133 review threads (Gemini nullable, Astra gate, S2S real ToolAuthorizationPolicy, handover reset, Modular streaming/duration/long-audio/barge-in, retry metering)."""
    from pydantic import Field
    from backend.app.ai.llm.gemini_provider import _sanitize_schema_for_gemini
    from backend.app.ai.tools.authorization import ToolAuthorizationPolicy
    from backend.app.ai.tools.base import AITool, ToolArguments
    from backend.app.ai.tools.contracts import ToolExecutionContext, ToolResult
    from backend.app.ai.tools.executor import ToolExecutor
    from backend.app.ai.tools.registry import ToolRegistry
    from backend.app.assistants.registry import AssistantRegistry
    from shared.ai_engine.contracts import TenantContext
    from tests.backend.test_voice_universal_architecture import _create_test_db

    # Thread 1: Gemini nullable union preserves integer/number/boolean types instead of turning them into string
    raw_union_schema = {
        "type": "object",
        "properties": {
            "limit": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
            "include_archived": {"oneOf": [{"type": "boolean"}, {"type": "null"}]},
            "min_price": {"anyOf": [{"type": "null"}, {"type": "number"}]},
        },
    }
    clean_schema = _sanitize_schema_for_gemini(raw_union_schema)
    assert clean_schema["properties"]["limit"] == {"type": "integer", "nullable": True}
    assert clean_schema["properties"]["include_archived"] == {"type": "boolean", "nullable": True}
    assert clean_schema["properties"]["min_price"] == {"type": "number", "nullable": True}

    # Thread 13: Astra eligibility gate excludes gpt-6.2-astra from rank() and fallbacks when latency_sensitive, low credits, or unknown credits
    rate_card = LLMRateCard.from_models({"openai": ("gpt-6.2-sol", "gpt-6.2-astra")})
    specs: dict[str | tuple[str, str], Any] = {
        ("openai", m): rate_card.spec_for("openai", m) for m in ("gpt-6.2-sol", "gpt-6.2-astra")
    }
    router = SmartModelRouter(specs, ProviderHealthRegistry())
    providers = [
        OpenAIProvider("k", "gpt-6.2-sol", 0.2, 800),
        OpenAIProvider("k", "gpt-6.2-astra", 0.2, 800),
    ]
    ctx_unknown_credits = LLMRoutingContext(
        task_type=LLMTaskType.BUSINESS_REASONING,
        complexity=LLMTaskComplexity.REASONING,
        context_tokens=1000,
        expected_output_tokens=400,
        requires_tool_calling=True,
        requires_reasoning=True,
        latency_sensitive=False,
        plan_code="professional",
        remaining_credits=None,
    )
    ranked_unknown = router.rank(providers, ctx_unknown_credits)
    assert [getattr(p, "_model", None) for p in ranked_unknown] == ["gpt-6.2-sol"]

    ctx_low_credits = LLMRoutingContext(
        task_type=LLMTaskType.BUSINESS_REASONING,
        complexity=LLMTaskComplexity.REASONING,
        context_tokens=1000,
        expected_output_tokens=400,
        requires_tool_calling=True,
        requires_reasoning=True,
        latency_sensitive=False,
        plan_code="professional",
        remaining_credits=150,
    )
    assert [getattr(p, "_model", None) for p in router.rank(providers, ctx_low_credits)] == ["gpt-6.2-sol"]

    # Threads 9 & 10: Real ToolAuthorizationPolicy + ToolExecutor with selected_agent_id, authorized_tool_agents, and user_message confirmation
    from backend.app.assistants.registry import build_default_assistant_registry
    from backend.app.models import BillingAccount, VoiceModulePermission

    session, company_a, user_a, *_ = _create_test_db(tmp_path)
    session.add(
        BillingAccount(
            id=uuid4(),
            company_id=company_a.id,
            plan_code="professional",
            status="active",
        )
    )
    session.add(
        VoiceModulePermission(
            id=uuid4(),
            company_id=company_a.id,
            module_code="crm",
            action_code="create_appointment",
            granted=True,
            revoked_at=None,
            permission_epoch=1,
        )
    )
    session.commit()

    class _BookingArgs(ToolArguments):
        client: str = Field(description="Client name")
        confirmed: bool = Field(default=False, description="Confirmation flag")

    class _RealBookingTool(AITool):
        name = "create_appointment"
        description = "Book VIP appointment"
        input_schema = _BookingArgs
        required_permissions = ("ai:use",)
        module_code = "crm"
        agent_ids = frozenset({"crm"})
        read_only = False
        mutates = True
        mutation_capabilities = frozenset({"appointment.create"})
        confirmation_policy = "explicit_user_confirmation"
        requires_confirmation = True

        async def run(self, context: ToolExecutionContext, arguments: _BookingArgs) -> ToolResult:
            return ToolResult(
                success=True,
                data={"booked": True, "client": arguments.client, "agent": context.selected_agent_id},
            )

    from backend.app.ai.tools.idempotency import AIToolExecutionIdempotencyStore

    reg = ToolRegistry()
    reg.register(_RealBookingTool())
    real_executor = ToolExecutor(
        reg,
        ToolAuthorizationPolicy(session, build_default_assistant_registry(reg)),
        AIToolExecutionIdempotencyStore(session),
    )
    cid = company_a.id
    uid = user_a.id
    conv_id = uuid4()
    authorized_map = {"create_appointment": "crm"}

    # Without confirmation in user_message -> confirmation_required challenge created
    unconfirmed_ctx = ToolExecutionContext(
        tenant=TenantContext(company_id=cid, user_id=uid),
        user_id=uid,
        permissions=frozenset({"ai:use", "data:read"}),
        request_id="req-s2s-unconf",
        conversation_id=conv_id,
        selected_agent_id="crm",
        authorized_tool_agents=authorized_map,
        user_message="Réserve un rendez-vous pour Martin",
        voice_path=True,
    )
    res_unconf = await real_executor.execute("create_appointment", unconfirmed_ctx, {"client": "Martin"})
    assert res_unconf.success is False
    assert res_unconf.data.get("confirmation_required") is True or res_unconf.metadata.get("confirmation_required") is True

    # With natural-language confirmation in user_message on same conversation_id -> consumes challenge & succeeds
    confirmed_ctx = ToolExecutionContext(
        tenant=TenantContext(company_id=cid, user_id=uid),
        user_id=uid,
        permissions=frozenset({"ai:use", "data:read"}),
        request_id="req-s2s-conf",
        conversation_id=conv_id,
        selected_agent_id="crm",
        authorized_tool_agents=authorized_map,
        user_message="Oui je confirme",
        voice_path=True,
    )
    res_conf = await real_executor.execute("create_appointment", confirmed_ctx, {"client": "Martin"})
    assert res_conf.success is True
    assert res_conf.data == {"booked": True, "client": "Martin", "agent": "crm"}

    # Thread 7 & 11: S2S reconnect drains stale EOF and handover reset purges provider conversation items
    ws_events: asyncio.Queue[Any] = asyncio.Queue()
    sent_payloads: list[dict[str, Any]] = []

    class _HandoverConn:
        async def send(self, payload: dict[str, Any]) -> None:
            sent_payloads.append(payload)

        def __aiter__(self):
            return self

        async def __anext__(self):
            ev = await ws_events.get()
            if ev is None:
                raise StopAsyncIteration
            return ev

    class _HandoverMgr:
        async def __aenter__(self):
            return _HandoverConn()

        async def __aexit__(self, *_a):
            await ws_events.put(None)

    s2s_handover = OpenAISpeechToSpeechRealtimeAdapter(
        OpenAIAudioConfig(api_key="test", stt_model="gpt-4o-mini-transcribe", tts_voice="marin"),
        connection_factory=lambda _m: _HandoverMgr(),
    )
    await s2s_handover.open(locale="fr-CA")
    await ws_events.put({"type": "conversation.item.created", "item": {"id": "secret-item-1"}})
    await asyncio.sleep(0.03)
    assert "secret-item-1" in s2s_handover._conversation_item_ids
    s2s_handover.update_staff_identity(True, "Francis", "owner")
    await asyncio.sleep(0.02)
    # Trigger handover revocation -> must delete secret-item-1 from provider session
    s2s_handover.update_staff_identity(False, None, None)
    await asyncio.sleep(0.04)
    deleted_ids = [p.get("item_id") for p in sent_payloads if p.get("type") == "conversation.item.delete"]
    assert "secret-item-1" in deleted_ids

    # Reconnect must drain stale EOF so next events() consumer receives session.updated
    await s2s_handover.reconnect(fallback_model="gpt-realtime-2.1", locale="fr-CA")
    first_ev = await asyncio.wait_for(s2s_handover.events().__anext__(), timeout=1.0)
    assert getattr(first_ev, "type", None) == "session.updated"
    await s2s_handover.close()

    # Threads 2, 4, 14, 15, 16: Modular streaming TTS, duration-based STT/TTS usage, >15s utterance segmentation, and immediate barge-in
    stream_Yields: list[int] = []

    class _FakeStreamingResp:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return None

        async def iter_bytes(self, chunk_size: int = 1920):
            for _ in range(3):
                stream_Yields.append(chunk_size)
                yield b"\x10\x00" * (chunk_size // 2)

    class _FakeStreamingSpeech:
        with_streaming_response = SimpleNamespace(create=lambda **_kw: _FakeStreamingResp())

    streaming_tts = OpenAITextToSpeechAdapter(
        OpenAIAudioConfig(api_key="test", tts_model="gpt-4o-mini-tts", tts_voice="marin"),
        client=cast(Any, SimpleNamespace(audio=SimpleNamespace(speech=_FakeStreamingSpeech()))),
    )
    chunks_out = [c async for c in streaming_tts.synthesize_pcm_chunks("Bonjour", locale="fr-CA", chunk_bytes=1920)]
    assert len(chunks_out) == 3
    assert all(len(c) == 1920 for c in chunks_out)

    # Long >15s utterance (2 segments) + duration-based STT usage
    stt_calls: list[int] = []

    class _SegSTT:
        provider_id = "openai"

        async def transcribe(self, audio: bytes, *, locale: str, content_type: str) -> str:
            stt_calls.append(len(audio))
            return f"segment-{len(stt_calls)}"

    mod = ModularVoicePipelineAdapter(
        OpenAIAudioConfig(api_key="test", stt_model="gpt-4o-mini-transcribe", tts_model="gpt-4o-mini-tts", tts_voice="marin"),
        stt_adapter=_SegSTT(),
        tts_adapter=streaming_tts,
        silence_frames_threshold=2,
    )
    await mod.open(locale="fr-CA")
    _ = await mod._event_queue.get()  # session.updated

    # Send >720,000 bytes (16 seconds at 24kHz PCM16 = 768,000 bytes) in loud 48,000-byte (1s) chunks
    loud_1s = _pcm_24k(1200, frames=50)
    for _ in range(16):
        await mod.send_audio(loud_1s)
    await mod.flush_speech()
    ev_started = await asyncio.wait_for(mod._event_queue.get(), timeout=1.0)
    assert ev_started.type == "input_audio_buffer.speech_started"
    ev_stopped = await asyncio.wait_for(mod._event_queue.get(), timeout=1.0)
    assert ev_stopped.type == "input_audio_buffer.speech_stopped"
    ev_trans = await asyncio.wait_for(mod._event_queue.get(), timeout=2.0)
    assert ev_trans.type == "conversation.item.input_audio_transcription.completed"
    # Both segments must be coalesced without dropping the tail > 15s!
    assert ev_trans.transcript == "segment-1 segment-2"
    assert ev_trans.usage["type"] == "duration"
    assert ev_trans.usage["seconds"] == 16.0

    # Thread 4: Modular TTS usage is duration-based and invariant to chunk size
    await mod.speak("Réponse complète.")
    _ = await asyncio.wait_for(mod._event_queue.get(), timeout=1.0)  # response.created
    for _ in range(3):
        _ = await asyncio.wait_for(mod._event_queue.get(), timeout=1.0)  # deltas
    ev_done = await asyncio.wait_for(mod._event_queue.get(), timeout=1.0)
    assert ev_done.type == "response.done"
    assert ev_done.response.usage == {"type": "duration", "seconds": round((1920 * 3) / 48000.0, 3)}
    await mod.close()


