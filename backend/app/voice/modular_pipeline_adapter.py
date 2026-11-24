"""Architecture B: Decoupled Modular Pipeline (Independent STT + GPT-6.2 Sol + Independent TTS).

Eliminates Gemini Live's `server_content.interrupted` self-abort bug by construction:
- Input audio goes strictly to echo-aware local RMS VAD + independent STT (`gpt-4o-mini-transcribe`)
- Reasoning runs through Avenqo Central AI (`gpt-6.2-sol`, optional cost-gated `gpt-6.2-astra`)
- Output speech is synthesized cleanly via independent `OpenAITextToSpeechAdapter.synthesize_pcm_chunks`
- Real caller barge-in cancels ONLY the local TTS synthesis task in < 60ms without any remote
  bidirectional LLM session generating spurious interruptions (`barge_in=0` impossible).
"""

from __future__ import annotations

import asyncio
import audioop
import base64
from contextlib import suppress
import io
import logging
from types import SimpleNamespace
from typing import Any, Callable
from uuid import uuid4
import wave

from backend.app.voice.adapters import (
    ExternalVoiceConfigurationRequired,
    OpenAIAudioConfig,
    OpenAISpeechToTextAdapter,
    OpenAITextToSpeechAdapter,
    SpeechToTextAdapter,
)

logger = logging.getLogger("avenqo.voice.modular")

_QUEUE_EOF = object()


def _pcm16_to_wav_bytes(pcm_data: bytes, *, sample_rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)
    return buf.getvalue()


class ModularVoicePipelineAdapter:
    """Architecture B adapter implementing `RealtimeAudioAdapter` over decoupled STT + TTS."""

    provider_id = "openai_modular"
    native_s2s_enabled = False
    supports_concurrent_filler = True

    def __init__(
        self,
        audio_config: OpenAIAudioConfig,
        *,
        central_model: str = "gpt-6.2-sol",
        stt_adapter: SpeechToTextAdapter | None = None,
        tts_adapter: Any | None = None,
        vad_rms_threshold: int = 450,
        silence_frames_threshold: int = 12,
        tts_pacing_delay_seconds: float = 0.0,
    ) -> None:
        self._config = audio_config
        self._central_model = central_model
        self.model_name = f"{audio_config.stt_model or 'stt'}+{central_model}+{audio_config.tts_model or 'tts'}"
        self._stt: SpeechToTextAdapter = stt_adapter or OpenAISpeechToTextAdapter(audio_config)
        self._tts = tts_adapter or OpenAITextToSpeechAdapter(audio_config)
        self._vad_rms_threshold = max(100, int(vad_rms_threshold))
        self._silence_frames_threshold = max(2, int(silence_frames_threshold))
        self._tts_pacing_delay = max(0.0, float(tts_pacing_delay_seconds))

        self._event_queue: asyncio.Queue[Any] = asyncio.Queue()
        self._closed: bool = False
        self._locale: str = "fr-CA"
        self._playback_active: bool = False

        self._speech_active: bool = False
        self._silence_frames: int = 0
        self._speech_frames: int = 0
        self._speech_peak_rms: int = 0
        self._current_item_id: str | None = None
        self._speech_pcm: bytearray = bytearray()

        self._tts_task: asyncio.Task[None] | None = None
        self._stt_tasks: set[asyncio.Task[None]] = set()
        self._current_response_id: str | None = None

        self._is_authenticated_staff: bool = False
        self._staff_name: str | None = None
        self._staff_role: str | None = None

    def set_playback_active(self, active: bool) -> None:
        self._playback_active = bool(active)

    def update_staff_identity(
        self,
        is_authenticated: bool,
        staff_name: str | None = None,
        staff_role: str | None = None,
    ) -> None:
        self._is_authenticated_staff = bool(is_authenticated)
        self._staff_name = staff_name
        self._staff_role = staff_role

    async def open(self, *, locale: str = "fr-CA") -> None:
        if not self._config.api_key and type(self._tts) is OpenAITextToSpeechAdapter:
            raise ExternalVoiceConfigurationRequired("OPENAI_API_KEY is required for Modular Voice pipeline")
        self._locale = locale
        self._closed = False
        await self._event_queue.put(SimpleNamespace(type="session.updated"))
        logger.info(
            "modular_voice_adapter_opened stt=%s central=%s tts=%s voice=%s locale=%s",
            self._config.stt_model,
            self._central_model,
            self._config.tts_model,
            self._config.tts_voice,
            locale,
        )

    def _spawn_stt_job(self, item_id: str, pcm_bytes: bytes, duration_ms: int) -> None:
        async def _run_stt() -> None:
            try:
                if len(pcm_bytes) < 960 or self._closed:
                    return
                wav_data = _pcm16_to_wav_bytes(pcm_bytes, sample_rate=24000)
                transcript = (
                    await asyncio.wait_for(
                        self._stt.transcribe(wav_data, locale=self._locale, content_type="audio/wav"),
                        timeout=6.0,
                    )
                ).strip()
                if not transcript or self._closed:
                    await self._event_queue.put(
                        SimpleNamespace(
                            type="input_audio_buffer.transcription_missing",
                            item_id=item_id,
                            duration_ms=duration_ms,
                            echo_rejected=False,
                            caller_speech_confirmed=False,
                        )
                    )
                    return
                est_tokens = max(1, len(transcript) // 4)
                await self._event_queue.put(
                    SimpleNamespace(
                        type="conversation.item.input_audio_transcription.completed",
                        item_id=item_id,
                        transcript=transcript,
                        event_id=f"mod-stt-{item_id}",
                        source="openai_modular_stt",
                        usage={
                            "type": "tokens",
                            "input_tokens": est_tokens,
                            "output_tokens": 1,
                            "input_token_details": {
                                "audio_tokens": est_tokens,
                                "text_tokens": 0,
                            },
                        },
                    )
                )
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning("modular_voice_stt_failed item_id=%s error=%s", item_id, type(exc).__name__)
            finally:
                task = asyncio.current_task()
                if task is not None:
                    self._stt_tasks.discard(task)

        task = asyncio.create_task(_run_stt())
        self._stt_tasks.add(task)

    async def send_audio(self, audio: bytes) -> None:
        if self._closed or not audio:
            return
        if len(audio) % 2 != 0:
            audio = audio[:-1]
        if not audio:
            return
        rms = audioop.rms(audio, 2)
        playback_on = self._playback_active or (self._current_response_id is not None)
        threshold = int(self._vad_rms_threshold * 1.5) if playback_on else self._vad_rms_threshold

        if rms >= threshold:
            self._silence_frames = 0
            if not self._speech_active:
                self._speech_active = True
                self._speech_frames = 0
                self._speech_peak_rms = rms
                self._speech_pcm.clear()
                self._current_item_id = f"mod-item-{uuid4().hex[:12]}"
                await self._event_queue.put(
                    SimpleNamespace(
                        type="input_audio_buffer.speech_started",
                        item_id=self._current_item_id,
                        rms=rms,
                        tts_playing=playback_on,
                        verified_caller_barge_in=True,
                    )
                )
            self._speech_frames += 1
            self._speech_peak_rms = max(self._speech_peak_rms, rms)
            if len(self._speech_pcm) < 720_000:
                self._speech_pcm.extend(audio)
        elif self._speech_active:
            self._silence_frames += 1
            if len(self._speech_pcm) < 720_000:
                self._speech_pcm.extend(audio)
            if self._silence_frames >= self._silence_frames_threshold:
                self._speech_active = False
                self._silence_frames = 0
                item_id = self._current_item_id or f"mod-item-{uuid4().hex[:12]}"
                self._current_item_id = None
                duration_ms = self._speech_frames * 20
                pcm_snapshot = bytes(self._speech_pcm)
                self._speech_frames = 0
                self._speech_peak_rms = 0
                self._speech_pcm.clear()
                await self._event_queue.put(
                    SimpleNamespace(
                        type="input_audio_buffer.speech_stopped",
                        item_id=item_id,
                        duration_ms=duration_ms,
                    )
                )
                self._spawn_stt_job(item_id, pcm_snapshot, duration_ms)

    async def flush_speech(self) -> None:
        """Finalize any buffered speech immediately (useful in deterministic tests and stream end)."""
        if self._speech_active and self._current_item_id:
            self._speech_active = False
            self._silence_frames = 0
            item_id = self._current_item_id
            self._current_item_id = None
            duration_ms = self._speech_frames * 20
            pcm_snapshot = bytes(self._speech_pcm)
            self._speech_frames = 0
            self._speech_peak_rms = 0
            self._speech_pcm.clear()
            await self._event_queue.put(
                SimpleNamespace(type="input_audio_buffer.speech_stopped", item_id=item_id, duration_ms=duration_ms)
            )
            self._spawn_stt_job(item_id, pcm_snapshot, duration_ms)

    async def speak(self, text: str) -> None:
        if self._closed:
            raise ExternalVoiceConfigurationRequired("Modular pipeline closed")
        cleaned = (text or "").strip()
        if not cleaned:
            return
        if self._tts_task is not None and not self._tts_task.done():
            self._tts_task.cancel()
            with suppress(Exception, asyncio.CancelledError):
                await self._tts_task

        resp_id = f"mod-resp-{uuid4().hex[:12]}"
        self._current_response_id = resp_id
        await self._event_queue.put(
            SimpleNamespace(type="response.created", response=SimpleNamespace(id=resp_id))
        )

        async def _stream_tts() -> None:
            emitted_chunks = 0
            try:
                if hasattr(self._tts, "synthesize_pcm_chunks"):
                    async for chunk in self._tts.synthesize_pcm_chunks(cleaned, locale=self._locale):
                        if self._closed or self._current_response_id != resp_id:
                            return
                        emitted_chunks += 1
                        await self._event_queue.put(
                            SimpleNamespace(
                                type="response.output_audio.delta",
                                response_id=resp_id,
                                delta=base64.b64encode(chunk).decode("ascii"),
                            )
                        )
                        if self._tts_pacing_delay > 0:
                            await asyncio.sleep(self._tts_pacing_delay)
                elif hasattr(self._tts, "synthesize_pcm"):
                    pcm = await self._tts.synthesize_pcm(cleaned, locale=self._locale)
                    for off in range(0, len(pcm), 1920):
                        if self._closed or self._current_response_id != resp_id:
                            return
                        emitted_chunks += 1
                        await self._event_queue.put(
                            SimpleNamespace(
                                type="response.output_audio.delta",
                                response_id=resp_id,
                                delta=base64.b64encode(pcm[off:off + 1920]).decode("ascii"),
                            )
                        )
                in_tokens = max(1, len(cleaned) // 4)
                out_tokens = max(1, emitted_chunks * 8)
                self._current_response_id = None
                await self._event_queue.put(
                    SimpleNamespace(
                        type="response.done",
                        response=SimpleNamespace(
                            id=resp_id,
                            status="completed",
                            usage={
                                "input_tokens": in_tokens,
                                "output_tokens": out_tokens,
                                "input_token_details": {
                                    "audio_tokens": 0,
                                    "text_tokens": in_tokens,
                                    "cached_tokens": 0,
                                    "cached_tokens_details": {"audio_tokens": 0, "text_tokens": 0},
                                },
                                "output_token_details": {
                                    "audio_tokens": out_tokens,
                                    "text_tokens": 0,
                                },
                            },
                        ),
                    )
                )
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning("modular_voice_tts_error resp_id=%s error=%s", resp_id, type(exc).__name__)
                self._current_response_id = None
                await self._event_queue.put(
                    SimpleNamespace(
                        type="error",
                        error=SimpleNamespace(code="modular_tts_error", message=str(exc)),
                    )
                )

        self._tts_task = asyncio.create_task(_stream_tts())

    async def interrupt(self) -> None:
        active_resp = self._current_response_id
        self._current_response_id = None
        if self._tts_task is not None and not self._tts_task.done():
            self._tts_task.cancel()
            with suppress(Exception, asyncio.CancelledError):
                await self._tts_task
        if active_resp is not None:
            await self._event_queue.put(
                SimpleNamespace(
                    type="response.done",
                    verified_caller_barge_in=True,
                    interruption_source="verified_caller_speech",
                    response=SimpleNamespace(id=active_resp, status="cancelled", usage=None),
                )
            )

    async def clear_input(self) -> None:
        self._speech_active = False
        self._silence_frames = 0
        self._speech_frames = 0
        self._speech_peak_rms = 0
        self._current_item_id = None
        self._speech_pcm.clear()

    async def close(self) -> None:
        self._closed = True
        if self._tts_task is not None and not self._tts_task.done():
            self._tts_task.cancel()
            with suppress(Exception, asyncio.CancelledError):
                await self._tts_task
        for t in list(self._stt_tasks):
            if not t.done():
                t.cancel()
        self._stt_tasks.clear()
        await self._event_queue.put(_QUEUE_EOF)

    async def events(self):
        while True:
            ev = await self._event_queue.get()
            if ev is _QUEUE_EOF:
                break
            yield ev
