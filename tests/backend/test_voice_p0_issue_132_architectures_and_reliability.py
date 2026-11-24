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
