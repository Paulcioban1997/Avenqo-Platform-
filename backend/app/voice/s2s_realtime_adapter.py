"""Architecture A: Native Speech-to-Speech (`gpt-realtime-2.1`) with Avenqo Tool Calling.

Provides true speech-to-speech bidirectional audio over OpenAI `/v1/realtime` while
enforcing Avenqo's deterministic security invariants:
- Strict OpenAI Realtime GA contract: `output_modalities: ["audio"]` (audio includes transcript)
- Pre-response authorization barrier: `turn_detection.create_response = False` so NO model speech
  or tool execution can start before input transcription completes and `_security_hook` validates
  PIN challenges, private-data gates, RBAC, and handover revocations
- Defense-in-depth audio & function-call output gate dropping any unsolicited/pre-auth audio or tool calls
- Dynamic `session.update` tools built exclusively from authorized Avenqo tool scopes (`reserve_product` blocked)
- Full `VoiceUsageLedger` metering of audio/cached/text tokens at `gpt-realtime-2.1` pricing
"""

from __future__ import annotations

import asyncio
import audioop
import base64
from contextlib import suppress
import json
import logging
from types import SimpleNamespace
from typing import Any, Awaitable, Callable
from uuid import uuid4

from openai import AsyncOpenAI

from backend.app.config.settings import Settings
from backend.app.core.locale_catalog import locale_info
from backend.app.models.voice import VoiceBusinessConfig
from backend.app.voice.adapters import ExternalVoiceConfigurationRequired, OpenAIAudioConfig
from backend.app.voice.messages import strip_markdown_for_speech
from backend.app.voice.realtime_provider import (
    NaturalInterruptionManager,
    build_personality_system_prompt,
)

logger = logging.getLogger("avenqo.voice.s2s")

_QUEUE_EOF = object()

ToolListProvider = Callable[[], list[dict[str, Any]]]
ToolCallExecutor = Callable[[str, str, str, dict[str, Any]], Awaitable[dict[str, Any]]]
TranscriptHook = Callable[[str, str], Awaitable[dict[str, Any] | None]]
AssistantTranscriptHook = Callable[[str, str], Awaitable[None]]


class OpenAISpeechToSpeechRealtimeAdapter:
    """Architecture A adapter: OpenAI `gpt-realtime-2.1` speech-to-speech + pre-response security gate."""

    provider_id = "openai_s2s"
    native_s2s_enabled = True
    supports_concurrent_filler = False

    def __init__(
        self,
        audio_config: OpenAIAudioConfig,
        *,
        settings: Settings | None = None,
        config: VoiceBusinessConfig | None = None,
        model: str = "gpt-realtime-2.1",
        company_name: str = "Avenqo",
        tool_provider: ToolListProvider | None = None,
        tool_executor: ToolCallExecutor | None = None,
        security_transcript_hook: TranscriptHook | None = None,
        assistant_transcript_hook: AssistantTranscriptHook | None = None,
        interruption_manager: NaturalInterruptionManager | None = None,
        connection_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self._config = audio_config
        self._settings = settings or Settings()
        self._voice_config = config
        self._model = (model or "gpt-realtime-2.1").strip()
        self.model_name = self._model
        self.fallback_model = getattr(self._settings, "voice_realtime_fallback_model", "gpt-realtime-2.1")
        self._company_name = str(company_name or "Avenqo").replace("_", " ").strip()
        self._tool_provider = tool_provider
        self._tool_executor = tool_executor
        self._security_hook = security_transcript_hook
        self._assistant_transcript_hook = assistant_transcript_hook
        self._interruptions = interruption_manager or NaturalInterruptionManager()
        self._connection_factory = connection_factory

        self._manager: Any = None
        self._connection: Any = None
        self._receive_task: asyncio.Task[None] | None = None
        self._event_queue: asyncio.Queue[Any] = asyncio.Queue()
        self._closed: bool = False
        self._locale: str = "fr-CA"
        self._playback_active: bool = False
        self._current_response_id: str | None = None
        self._active_turn_id: str = f"s2s-turn-{uuid4().hex[:8]}"
        self._handled_function_calls: set[str] = set()
        self._speech_active: bool = False
        self._speech_frames_during_playback: int = 0
        self._verified_caller_speech: bool = False

        # Pre-response authorization & PIN/handover barrier state
        self._authorized_turn_ids: set[str] = set()
        self._authorized_response_turn_id: str | None = None
        self._system_speech_pending: int = 0
        self._current_response_authorized: bool = False
        self._current_response_is_system: bool = False
        self._current_response_audio_chunks: int = 0
        self._current_response_tool_calls: int = 0
        self._auth_gate_locked: bool = False
        self._conversation_item_ids: list[str] = []
        self._conversation_reset_epoch: int = 0
        self.dropped_unauthorized_audio_chunks: int = 0
        self.blocked_unauthorized_tool_calls: int = 0

        self._is_authenticated_staff: bool = False
        self._staff_name: str | None = None
        self._staff_role: str | None = None

    def set_playback_active(self, active: bool) -> None:
        self._playback_active = bool(active)
        if not self._playback_active:
            self._speech_frames_during_playback = 0

    def update_staff_identity(
        self,
        is_authenticated: bool,
        staff_name: str | None = None,
        staff_role: str | None = None,
    ) -> None:
        was_authenticated = self._is_authenticated_staff
        old_identity = (self._is_authenticated_staff, self._staff_name, self._staff_role)
        self._is_authenticated_staff = bool(is_authenticated)
        self._staff_name = staff_name if is_authenticated else None
        self._staff_role = staff_role if is_authenticated else None
        new_identity = (self._is_authenticated_staff, self._staff_name, self._staff_role)
        identity_changed = old_identity != new_identity
        if is_authenticated:
            self._auth_gate_locked = False
        elif was_authenticated and not is_authenticated:
            # Staff handover / session revocation immediately locks conversational generation
            self._auth_gate_locked = True
            self._authorized_turn_ids.clear()
            self._authorized_response_turn_id = None
        if self._connection is not None and not self._closed:
            try:
                loop = asyncio.get_running_loop()
                if identity_changed and was_authenticated:
                    loop.create_task(self.reset_conversation_session())
                else:
                    loop.create_task(self.refresh_session())
            except RuntimeError:
                pass

    async def reset_conversation_session(self) -> None:
        """Purge prior principal conversation context and tool outputs on staff handover or PIN revocation."""
        self._conversation_reset_epoch += 1
        self._authorized_turn_ids.clear()
        self._authorized_response_turn_id = None
        self._current_response_authorized = False
        self._handled_function_calls.clear()
        if self._connection is None or self._closed:
            self._conversation_item_ids.clear()
            return
        with suppress(Exception):
            await self._connection.send({"type": "response.cancel"})
        with suppress(Exception):
            await self._connection.send({"type": "input_audio_buffer.clear"})
        items_to_delete = list(self._conversation_item_ids)
        self._conversation_item_ids.clear()
        for item_id in items_to_delete:
            if item_id:
                with suppress(Exception):
                    await self._connection.send({"type": "conversation.item.delete", "item_id": item_id})
        if hasattr(self._connection, "clear_conversation_history") and callable(self._connection.clear_conversation_history):
            with suppress(Exception):
                self._connection.clear_conversation_history()
        await self.refresh_session()

    def _build_instructions(self, locale: str) -> str:
        cfg = self._voice_config
        base = build_personality_system_prompt(
            company_name=self._company_name,
            locale=locale,
            personality_preset=getattr(cfg, "personality_preset", "professional_premium_warm") if cfg else "professional_premium_warm",
            professionalism_level=int(getattr(cfg, "professionalism_level", 100) if cfg else 100),
            warmth_level=int(getattr(cfg, "warmth_level", 85) if cfg else 85),
            humor_level=int(getattr(cfg, "humor_level", 40) if cfg else 40),
            formality_level=int(getattr(cfg, "formality_level", 65) if cfg else 65),
            allow_natural_interruptions=bool(getattr(cfg, "allow_natural_interruptions", True) if cfg else True),
            custom_pronunciation=(
                getattr(cfg, "custom_pronunciation", None) or getattr(cfg, "voice_pronunciation", None)
                if cfg else None
            ),
            is_authenticated_staff=self._is_authenticated_staff,
            staff_name=self._staff_name,
            staff_role=self._staff_role,
        )
        return (
            f"{base}\n\n"
            "REALTIME PHONE EXECUTION RULES:\n"
            f"- Primary language: {locale_info(locale).english_name}. Match the caller's spoken language accurately.\n"
            "- Keep spoken answers clear, concise (1-3 spoken sentences per point unless asked for detail), and natural with ZERO markdown (never emit *, **, ***, #, or bullet symbols).\n"
            "- ALWAYS use your authorized Avenqo function tools before quoting catalog prices, stock quantities, modules, identity, KPIs, or CRM bookings.\n"
            "- NEVER disclose confidential company financials, sales, margins, or internal records unless returned by an authorized tool in this active session.\n"
            "- NEVER invent stock quantities, prices, margins, or company metrics. If a tool is unauthorized or unavailable, state it transparently."
        )

    def _safe_tools_payload(self) -> list[dict[str, Any]]:
        if self._auth_gate_locked or self._tool_provider is None:
            return []
        raw_tools = self._tool_provider() or []
        tools: list[dict[str, Any]] = []
        for tool in raw_tools:
            name = str(tool.get("name") or "")
            if not name or name == "reserve_product":
                continue
            tools.append({
                "type": "function",
                "name": name,
                "description": str(tool.get("description") or ""),
                "parameters": tool.get("parameters") or {"type": "object", "properties": {}},
            })
        return tools

    def _session_update_payload(self, locale: str) -> dict[str, Any]:
        noise = (
            None
            if self._config.input_noise_reduction == "off"
            else {"type": self._config.input_noise_reduction}
        )
        allow_interrupt = bool(
            getattr(self._voice_config, "allow_natural_interruptions", True)
            if self._voice_config is not None
            else True
        )
        return {
            "type": "session.update",
            "session": {
                "type": "realtime",
                "instructions": self._build_instructions(locale),
                # OpenAI Realtime GA contract: MUST be ["audio"] OR ["text"], never both;
                # ["audio"] automatically includes output audio transcription events.
                "output_modalities": ["audio"],
                "audio": {
                    "input": {
                        "noise_reduction": noise or {"type": "near_field"},
                        "format": {"type": "audio/pcm", "rate": 24000},
                        "transcription": {"model": self._config.stt_model or "gpt-4o-mini-transcribe"},
                        "turn_detection": {
                            "type": "server_vad",
                            # SECURITY BARRIER: Never auto-generate before server PIN/RBAC/handover validation!
                            "create_response": False,
                            "interrupt_response": allow_interrupt,
                            "prefix_padding_ms": 300,
                            "silence_duration_ms": 550,
                            "threshold": 0.55,
                        },
                    },
                    "output": {
                        "speed": self._config.speech_speed,
                        "format": {"type": "audio/pcm", "rate": 24000},
                        "voice": self._config.tts_voice or "marin",
                    },
                },
                "tools": self._safe_tools_payload(),
                "tool_choice": "auto",
            },
        }

    async def refresh_session(self) -> None:
        if self._connection is not None and not self._closed:
            with suppress(Exception):
                await self._connection.send(self._session_update_payload(self._locale))

    async def open(self, *, locale: str = "fr-CA") -> None:
        if not self._config.api_key and self._connection_factory is None:
            raise ExternalVoiceConfigurationRequired("OPENAI_API_KEY is required for gpt-realtime-2.1 S2S")
        self._locale = locale
        self._closed = False
        while not self._event_queue.empty():
            with suppress(asyncio.QueueEmpty):
                self._event_queue.get_nowait()
        if self._connection_factory is not None:
            self._manager = self._connection_factory(self._model)
        else:
            client = AsyncOpenAI(api_key=self._config.api_key, base_url=self._config.base_url)
            self._manager = client.realtime.connect(model=self._model)
        self._connection = await self._manager.__aenter__()
        await self._connection.send(self._session_update_payload(locale))
        self._receive_task = asyncio.create_task(self._receive_loop())
        await self._event_queue.put(SimpleNamespace(type="session.updated"))
        logger.info(
            "s2s_realtime_adapter_opened model=%s voice=%s locale=%s tools=%d",
            self._model,
            self._config.tts_voice,
            locale,
            len(self._safe_tools_payload()),
        )

    async def send_audio(self, audio: bytes) -> None:
        if self._connection is None or self._closed:
            raise ExternalVoiceConfigurationRequired("S2S realtime session is not open")
        if not audio:
            return
        sample = audio[:-1] if len(audio) % 2 else audio
        if sample:
            rms = audioop.rms(sample, 2)
            if self._playback_active and rms >= 675:
                self._speech_frames_during_playback += 1
                if self._speech_frames_during_playback >= 3:
                    self._verified_caller_speech = True
            elif self._playback_active:
                self._speech_frames_during_playback = 0
        await self._connection.send({
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(audio).decode("ascii"),
        })

    async def speak(self, text: str) -> None:
        """Speak an explicitly server-authorized message (greeting, PIN challenge, handover, error)."""
        if self._connection is None or self._closed:
            raise ExternalVoiceConfigurationRequired("S2S realtime session is not open")
        cleaned = strip_markdown_for_speech(text)
        if not cleaned:
            return
        self._system_speech_pending += 1
        await self._connection.send({
            "type": "response.create",
            "response": {
                "conversation": "none",
                "output_modalities": ["audio"],
                "instructions": (
                    "Speak the supplied authorized message verbatim with a warm, natural human tone. "
                    "Do not translate, do not use markdown symbols, and do not add extra claims."
                ),
                "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": cleaned}]}],
            },
        })

    async def _request_authorized_turn_response(self, turn_id: str) -> None:
        """Trigger native S2S generation ONLY after server security/PIN/RBAC validation passed."""
        if self._connection is None or self._closed or self._auth_gate_locked:
            return
        self._authorized_response_turn_id = turn_id
        await self._connection.send({
            "type": "response.create",
            "response": {
                "output_modalities": ["audio"],
            },
        })

    async def interrupt(self) -> None:
        self._authorized_response_turn_id = None
        self._current_response_authorized = False
        if self._connection is not None and not self._closed:
            with suppress(Exception):
                await self._connection.send({"type": "response.cancel"})
        if self._current_response_id:
            self._interruptions.cancel_turn("s2s", self._active_turn_id)

    async def clear_input(self) -> None:
        self._verified_caller_speech = False
        self._speech_frames_during_playback = 0
        if self._connection is not None and not self._closed:
            with suppress(Exception):
                await self._connection.send({"type": "input_audio_buffer.clear"})

    async def close(self) -> None:
        self._closed = True
        if self._receive_task is not None:
            self._receive_task.cancel()
            with suppress(Exception, asyncio.CancelledError):
                await self._receive_task
            self._receive_task = None
        if self._manager is not None:
            with suppress(Exception):
                await self._manager.__aexit__(None, None, None)
            self._manager = None
        self._connection = None
        await self._event_queue.put(_QUEUE_EOF)

    async def reconnect(self, fallback_model: str = "gpt-realtime-2.1", locale: str = "fr-CA") -> None:
        await self.close()
        while not self._event_queue.empty():
            with suppress(asyncio.QueueEmpty):
                self._event_queue.get_nowait()
        self._model = fallback_model or self._model
        self.model_name = self._model
        await self.open(locale=locale)

    async def _handle_function_call(self, call_id: str, tool_name: str, raw_args: Any) -> None:
        if not call_id or call_id in self._handled_function_calls:
            return
        self._handled_function_calls.add(call_id)
        if len(self._handled_function_calls) > 500:
            self._handled_function_calls.clear()

        if isinstance(raw_args, dict):
            parsed_args = raw_args
        else:
            try:
                parsed_args = json.loads(str(raw_args or "{}"))
            except Exception:
                parsed_args = {}

        turn_id = self._active_turn_id
        # Hard server-side authorization barrier on function calls
        turn_authorized = (
            not self._auth_gate_locked
            and (self._security_hook is None or turn_id in self._authorized_turn_ids)
        )
        if (
            not turn_authorized
            or tool_name == "reserve_product"
            or not self._interruptions.can_execute_tool(turn_id, tool_name, parsed_args)
        ):
            if not turn_authorized:
                self.blocked_unauthorized_tool_calls += 1
            output_payload: dict[str, Any] = {
                "status": "blocked",
                "error": "tool_blocked_or_turn_cancelled" if turn_authorized else "turn_not_authorized_or_pin_required",
            }
        elif self._tool_executor is not None:
            self._interruptions.record_tool_execution(turn_id, tool_name, parsed_args)
            try:
                output_payload = await self._tool_executor(turn_id, call_id, tool_name, parsed_args)
            except Exception as exc:
                logger.warning("s2s_tool_execution_error tool=%s error=%s", tool_name, type(exc).__name__)
                output_payload = {"status": "error", "error": "tool_execution_failed"}
        else:
            output_payload = {"status": "error", "error": "no_tool_executor_configured"}

        if self._connection is not None and not self._closed:
            await self._connection.send({
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(output_payload, default=str),
                },
            })
            if turn_authorized and not self._auth_gate_locked:
                self._authorized_response_turn_id = turn_id
                await self._connection.send({
                    "type": "response.create",
                    "response": {"output_modalities": ["audio"]},
                })

    async def _receive_loop(self) -> None:
        try:
            async for raw_event in self._connection:
                if self._closed:
                    break
                ev_type = str(getattr(raw_event, "type", None) or (raw_event.get("type") if isinstance(raw_event, dict) else "") or "")
                get_f = (lambda k, d=None: raw_event.get(k, d)) if isinstance(raw_event, dict) else (lambda k, d=None: getattr(raw_event, k, d))

                if ev_type == "input_audio_buffer.speech_started":
                    self._speech_active = True
                    # Invalidate previous conversational turn approval until the new utterance is transcribed & verified
                    self._authorized_response_turn_id = None
                    await self._event_queue.put(
                        SimpleNamespace(
                            type="input_audio_buffer.speech_started",
                            item_id=get_f("item_id") or f"s2s-item-{uuid4().hex[:10]}",
                            verified_caller_barge_in=self._verified_caller_speech or not self._playback_active,
                        )
                    )
                elif ev_type == "input_audio_buffer.speech_stopped":
                    self._speech_active = False
                    await self._event_queue.put(
                        SimpleNamespace(
                            type="input_audio_buffer.speech_stopped",
                            item_id=get_f("item_id") or f"s2s-item-{uuid4().hex[:10]}",
                        )
                    )
                elif ev_type == "conversation.item.created":
                    item = get_f("item")
                    c_item_id = (
                        item.get("id")
                        if isinstance(item, dict)
                        else getattr(item, "id", None)
                    ) or get_f("item_id")
                    if c_item_id:
                        self._conversation_item_ids.append(str(c_item_id))
                        if len(self._conversation_item_ids) > 500:
                            del self._conversation_item_ids[:-500]
                elif ev_type == "conversation.item.input_audio_transcription.completed":
                    item_id = str(get_f("item_id") or f"s2s-item-{uuid4().hex[:10]}")
                    self._conversation_item_ids.append(item_id)
                    if len(self._conversation_item_ids) > 500:
                        del self._conversation_item_ids[:-500]
                    transcript = str(get_f("transcript") or "").strip()
                    self._active_turn_id = item_id
                    if not transcript:
                        continue
                    normalized_transcript_event = SimpleNamespace(
                        type="conversation.item.input_audio_transcription.completed",
                        item_id=item_id,
                        transcript=transcript,
                        event_id=get_f("event_id") or f"evt-{item_id}",
                        usage=get_f("usage"),
                        security_intercept=None,
                    )
                    if self._security_hook is not None:
                        sec = await self._security_hook(item_id, transcript)
                        if isinstance(sec, dict) and sec.get("handled"):
                            if sec.get("auth_required"):
                                self._auth_gate_locked = True
                                self._authorized_turn_ids.clear()
                                await self.reset_conversation_session()
                            elif sec.get("public"):
                                self._auth_gate_locked = False
                                await self.reset_conversation_session()
                            await self.interrupt()
                            normalized_transcript_event.security_intercept = sec
                            await self._event_queue.put(normalized_transcript_event)
                            continue
                    if self._auth_gate_locked:
                        # Caller is inside an active PIN/handover gate; forward to bridge for verbal-cancel check ONLY,
                        # NEVER trigger S2S response generation!
                        await self._event_queue.put(normalized_transcript_event)
                        continue
                    if len(self._authorized_turn_ids) >= 500:
                        self._authorized_turn_ids.clear()
                    self._authorized_turn_ids.add(item_id)
                    await self._event_queue.put(normalized_transcript_event)
                    await self._request_authorized_turn_response(item_id)
                elif ev_type == "response.created":
                    resp = get_f("response")
                    resp_id = getattr(resp, "id", None) if resp is not None and not isinstance(resp, dict) else (resp.get("id") if isinstance(resp, dict) else None)
                    self._current_response_id = str(resp_id) if resp_id else f"s2s-resp-{uuid4().hex[:10]}"
                    self._current_response_audio_chunks = 0
                    self._current_response_tool_calls = 0
                    if self._system_speech_pending > 0:
                        self._system_speech_pending -= 1
                        self._current_response_authorized = True
                        self._current_response_is_system = True
                    elif self._authorized_response_turn_id is not None and not self._auth_gate_locked:
                        self._current_response_authorized = True
                        self._current_response_is_system = False
                    else:
                        # Unsolicited / pre-authorization speculative response -> block & cancel immediately!
                        self._current_response_authorized = False
                        self._current_response_is_system = False
                        if self._connection is not None and not self._closed:
                            with suppress(Exception):
                                await self._connection.send({"type": "response.cancel"})
                        continue
                    self._interruptions.register_playback("s2s", self._active_turn_id)
                    await self._event_queue.put(SimpleNamespace(type="response.created", response=SimpleNamespace(id=self._current_response_id)))
                elif ev_type in {"response.audio.delta", "response.output_audio.delta"}:
                    if not self._current_response_authorized or (self._auth_gate_locked and not self._current_response_is_system):
                        self.dropped_unauthorized_audio_chunks += 1
                        if self._connection is not None and not self._closed:
                            with suppress(Exception):
                                await self._connection.send({"type": "response.cancel"})
                        continue
                    self._current_response_audio_chunks += 1
                    await self._event_queue.put(
                        SimpleNamespace(
                            type="response.output_audio.delta",
                            response_id=get_f("response_id") or self._current_response_id,
                            delta=get_f("delta"),
                        )
                    )
                elif ev_type in {"response.audio_transcript.done", "response.output_audio_transcript.done"}:
                    if not self._current_response_authorized:
                        continue
                    out_text = strip_markdown_for_speech(str(get_f("transcript") or ""))
                    if out_text and self._assistant_transcript_hook is not None:
                        with suppress(Exception):
                            await self._assistant_transcript_hook(self._active_turn_id, out_text)
                elif ev_type == "response.function_call_arguments.done":
                    self._current_response_tool_calls += 1
                    await self._handle_function_call(
                        str(get_f("call_id") or ""),
                        str(get_f("name") or ""),
                        get_f("arguments"),
                    )
                elif ev_type == "response.output_item.done":
                    item = get_f("item")
                    if item is not None:
                        if isinstance(item, dict):
                            item_id_done = item.get("id")
                            item_type = item.get("type")
                            call_id = item.get("call_id")
                            fn_name = item.get("name")
                            fn_args = item.get("arguments")
                        else:
                            item_id_done = getattr(item, "id", None)
                            item_type = getattr(item, "type", None)
                            call_id = getattr(item, "call_id", None)
                            fn_name = getattr(item, "name", None)
                            fn_args = getattr(item, "arguments", None)
                        if item_id_done:
                            self._conversation_item_ids.append(str(item_id_done))
                            if len(self._conversation_item_ids) > 500:
                                del self._conversation_item_ids[:-500]
                        if item_type == "function_call":
                            self._current_response_tool_calls += 1
                            await self._handle_function_call(
                                str(call_id or ""),
                                str(fn_name or ""),
                                fn_args,
                            )
                elif ev_type == "response.done":
                    was_authorized = self._current_response_authorized
                    audio_chunks = self._current_response_audio_chunks
                    tool_calls = self._current_response_tool_calls
                    resp = get_f("response")
                    if isinstance(resp, dict):
                        resp_ns = SimpleNamespace(
                            id=resp.get("id") or self._current_response_id,
                            status=resp.get("status") or "completed",
                            usage=resp.get("usage"),
                        )
                    else:
                        resp_ns = resp
                    status = getattr(resp_ns, "status", "completed") if resp_ns is not None else "completed"
                    verified = self._verified_caller_speech or (self._speech_active and self._speech_frames_during_playback >= 3)
                    self._current_response_id = None
                    self._current_response_authorized = False
                    self._current_response_is_system = False
                    self._current_response_audio_chunks = 0
                    self._current_response_tool_calls = 0
                    self._verified_caller_speech = False
                    self._speech_frames_during_playback = 0
                    if not was_authorized:
                        continue
                    await self._event_queue.put(
                        SimpleNamespace(
                            type="response.done",
                            response=resp_ns,
                            audio_chunks_emitted=audio_chunks,
                            function_call_only=(audio_chunks == 0 and tool_calls > 0),
                            turn_id=self._active_turn_id,
                            verified_caller_barge_in=verified if status == "cancelled" else None,
                            interruption_source=(
                                "verified_caller_speech"
                                if (status == "cancelled" and verified)
                                else ("provider_unconfirmed" if status == "cancelled" else None)
                            ),
                        )
                    )
                elif ev_type == "error":
                    err_raw = get_f("error")
                    if isinstance(err_raw, dict):
                        err_ns = SimpleNamespace(
                            code=err_raw.get("code") or "realtime_error",
                            message=err_raw.get("message") or str(err_raw),
                        )
                    else:
                        err_ns = err_raw or SimpleNamespace(code="realtime_error", message=str(raw_event))
                    await self._event_queue.put(SimpleNamespace(type="error", error=err_ns))
                else:
                    await self._event_queue.put(raw_event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("s2s_realtime_receive_error: %s", exc, exc_info=True)
            await self._event_queue.put(
                SimpleNamespace(
                    type="error",
                    error=SimpleNamespace(code="s2s_stream_error", message=str(exc)),
                )
            )
        finally:
            await self._event_queue.put(_QUEUE_EOF)

    async def events(self):
        while True:
            ev = await self._event_queue.get()
            if ev is _QUEUE_EOF:
                break
            yield ev
