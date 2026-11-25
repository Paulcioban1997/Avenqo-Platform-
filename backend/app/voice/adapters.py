"""Configured STT/TTS/realtime adapter contracts for Voice Central."""

from __future__ import annotations

from dataclasses import dataclass
import base64
import logging
from typing import Any, AsyncIterator, Protocol, cast

from openai import AsyncOpenAI

from backend.app.core.locale_catalog import locale_info
from backend.app.voice.messages import strip_markdown_for_speech

logger = logging.getLogger("avenqo.voice.adapters")


class SpeechToTextAdapter(Protocol):
    provider_id: str

    async def transcribe(self, audio: bytes, *, locale: str, content_type: str) -> str: ...


class TextToSpeechAdapter(Protocol):
    provider_id: str

    async def synthesize(self, text: str, *, locale: str) -> bytes: ...


class RealtimeAudioAdapter(Protocol):
    @property
    def provider_id(self) -> str: ...

    async def open(self, *, locale: str = "fr-CA") -> None: ...

    async def send_audio(self, audio: bytes) -> None: ...

    async def speak(self, text: str) -> None: ...

    async def interrupt(self) -> None: ...

    async def clear_input(self) -> None: ...

    async def close(self) -> None: ...

    def update_staff_identity(self, is_authenticated: bool, staff_name: str | None = None, staff_role: str | None = None) -> None: ...

    def events(self) -> AsyncIterator[Any]: ...


class ExternalVoiceConfigurationRequired(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OpenAIAudioConfig:
    api_key: str | None = None
    stt_model: str | None = None
    tts_model: str | None = None
    tts_voice: str | None = None
    base_url: str = "https://api.openai.com/v1"
    speech_speed: float = 1.0
    input_noise_reduction: str = "off"
    delivery_style: str = "professional"


class OpenAISpeechToTextAdapter:
    provider_id = "openai"

    def __init__(self, config: OpenAIAudioConfig, client: AsyncOpenAI | None = None) -> None:
        self._config = config
        self._client = client
        self.last_usage: dict[str, Any] | None = None

    async def transcribe(self, audio: bytes, *, locale: str, content_type: str) -> str:
        if not self._config.api_key or not self._config.stt_model:
            raise ExternalVoiceConfigurationRequired("OPENAI_API_KEY and VOICE_STT_MODEL are required")
        client = self._client or AsyncOpenAI(api_key=self._config.api_key, base_url=self._config.base_url)
        response = await client.audio.transcriptions.create(
            file=("voice-input", audio, content_type),
            model=self._config.stt_model,
        )
        raw_usage = getattr(response, "usage", None)
        if isinstance(raw_usage, dict):
            self.last_usage = dict(raw_usage)
        elif raw_usage is not None and hasattr(raw_usage, "model_dump"):
            self.last_usage = raw_usage.model_dump()
        else:
            self.last_usage = None
        return str(getattr(response, "text", response) or "")


class OpenAITextToSpeechAdapter:
    provider_id = "openai"

    def __init__(self, config: OpenAIAudioConfig, client: AsyncOpenAI | None = None) -> None:
        self._config = config
        self._client = client
        self.last_usage: dict[str, Any] | None = None

    async def synthesize(self, text: str, *, locale: str) -> bytes:
        if not self._config.api_key or not self._config.tts_model or not self._config.tts_voice:
            raise ExternalVoiceConfigurationRequired(
                "OPENAI_API_KEY, VOICE_TTS_MODEL and VOICE_TTS_VOICE are required"
            )
        cleaned_input = strip_markdown_for_speech(text) or text
        client = self._client or AsyncOpenAI(api_key=self._config.api_key, base_url=self._config.base_url)
        response = await client.audio.speech.create(
            input=cleaned_input,
            model=self._config.tts_model,
            voice=self._config.tts_voice,
            response_format="opus",
            speed=self._config.speech_speed,
            instructions=f"Speak naturally in {locale_info(locale).english_name}. Preserve the input language; do not translate.",
        )
        return response.read()

    async def synthesize_pcm(self, text: str, *, locale: str) -> bytes:
        """Synthesize 24kHz 16-bit little-endian mono PCM audio for streaming telephony."""
        if not self._config.api_key or not self._config.tts_model or not self._config.tts_voice:
            raise ExternalVoiceConfigurationRequired(
                "OPENAI_API_KEY, VOICE_TTS_MODEL and VOICE_TTS_VOICE are required"
            )
        cleaned_input = strip_markdown_for_speech(text) or text
        client = self._client or AsyncOpenAI(api_key=self._config.api_key, base_url=self._config.base_url)
        response = await client.audio.speech.create(
            input=cleaned_input,
            model=self._config.tts_model,
            voice=self._config.tts_voice,
            response_format="pcm",
            speed=self._config.speech_speed,
            instructions=f"Speak naturally in {locale_info(locale).english_name}. Preserve the input language; do not translate.",
        )
        read_fn = getattr(response, "read", None)
        raw_val: Any = read_fn() if callable(read_fn) else response
        if hasattr(raw_val, "__await__"):
            raw_val = await cast(Any, raw_val)
        raw = bytes(raw_val)
        if len(raw) % 2 != 0:
            raw = raw[:-1]
        return raw

    async def synthesize_pcm_chunks(
        self,
        text: str,
        *,
        locale: str,
        chunk_bytes: int = 1920,
    ) -> AsyncIterator[bytes]:
        """Stream 24kHz PCM16 frames (default 40ms = 1920 bytes) as bytes arrive from OpenAI TTS."""
        if not self._config.api_key or not self._config.tts_model or not self._config.tts_voice:
            raise ExternalVoiceConfigurationRequired(
                "OPENAI_API_KEY, VOICE_TTS_MODEL and VOICE_TTS_VOICE are required"
            )
        cleaned_input = strip_markdown_for_speech(text) or text
        step = max(960, chunk_bytes - (chunk_bytes % 2))
        client = self._client or AsyncOpenAI(api_key=self._config.api_key, base_url=self._config.base_url)
        speech_api = getattr(getattr(client, "audio", None), "speech", None)
        streaming_factory = getattr(speech_api, "with_streaming_response", None)
        instructions = f"Speak naturally in {locale_info(locale).english_name}. Preserve the input language; do not translate."

        if streaming_factory is not None and hasattr(streaming_factory, "create"):
            async with streaming_factory.create(
                input=cleaned_input,
                model=self._config.tts_model,
                voice=self._config.tts_voice,
                response_format="pcm",
                speed=self._config.speech_speed,
                instructions=instructions,
            ) as stream_resp:
                buffer = bytearray()
                iter_bytes_fn: Any = getattr(stream_resp, "iter_bytes", None)
                if callable(iter_bytes_fn):
                    byte_stream: Any = iter_bytes_fn(chunk_size=step)
                    async for incoming in byte_stream:
                        if not incoming:
                            continue
                        buffer.extend(incoming)
                        while len(buffer) >= step:
                            frame = bytes(buffer[:step])
                            del buffer[:step]
                            yield frame
                else:
                    raw_body = await stream_resp.read()
                    buffer.extend(raw_body)
                if len(buffer) % 2 != 0:
                    del buffer[-1:]
                if buffer:
                    yield bytes(buffer)
            return

        pcm = await self.synthesize_pcm(text, locale=locale)
        for offset in range(0, len(pcm), step):
            chunk = pcm[offset:offset + step]
            if chunk:
                yield chunk


class UnconfiguredRealtimeAudioAdapter:
    provider_id = "none"

    async def open(self, *, locale: str = "fr-CA") -> None:
        raise ExternalVoiceConfigurationRequired("VOICE_REALTIME_PROVIDER is required")

    async def send_audio(self, audio: bytes) -> None:
        raise ExternalVoiceConfigurationRequired("VOICE_REALTIME_PROVIDER is required")

    async def speak(self, text: str) -> None:
        raise ExternalVoiceConfigurationRequired("VOICE_REALTIME_PROVIDER is required")

    async def interrupt(self) -> None:
        return None

    async def clear_input(self) -> None:
        return None

    async def close(self) -> None:
        return None

    def update_staff_identity(self, is_authenticated: bool, staff_name: str | None = None, staff_role: str | None = None) -> None:
        pass

    async def events(self):
        if False:
            yield None


class OpenAIRealtimeAudioAdapter:
    provider_id = "openai"

    def __init__(self, config: OpenAIAudioConfig, realtime_model: str | None) -> None:
        self._config = config
        self._model = realtime_model
        self._manager = None
        self._connection = None
        self._is_authenticated_staff: bool = False
        self._staff_name: str | None = None
        self._staff_role: str | None = None

    def update_staff_identity(self, is_authenticated: bool, staff_name: str | None = None, staff_role: str | None = None) -> None:
        self._is_authenticated_staff = is_authenticated
        self._staff_name = staff_name
        self._staff_role = staff_role

    async def open(self, *, locale: str = "fr-CA") -> None:
        if not self._config.api_key or not self._model:
            raise ExternalVoiceConfigurationRequired("OPENAI_API_KEY and VOICE_REALTIME_MODEL are required")
        client = AsyncOpenAI(api_key=self._config.api_key, base_url=self._config.base_url)
        try:
            self._manager = client.realtime.connect(model=self._model)
            self._connection = await self._manager.__aenter__()
        except Exception as exc:
            # Fallback transparent et vérifié : gpt-live-1 / gpt-live-1.1 -> gpt-realtime-2.1
            if self._model in ("gpt-live-1", "gpt-live-1.1"):
                logger.warning("Primary voice model %s unavailable (%s); falling back to gpt-realtime-2.1", self._model, exc)
                self._model = "gpt-realtime-2.1"
                self._manager = client.realtime.connect(model=self._model)
                self._connection = await self._manager.__aenter__()
            else:
                raise
        is_preview = "preview" in (self._model or "").lower()
        noise = None if self._config.input_noise_reduction == "off" else {"type": self._config.input_noise_reduction}
        if is_preview:
            session_payload: dict[str, Any] = {
                "instructions": (
                    f"You are a warm, highly natural, professional phone receptionist representing the business. "
                    f"Start in {locale_info(locale).english_name}. Speak with a {self._config.delivery_style} delivery, "
                    "natural conversational pacing, and friendly human intonation. Avoid mechanical, robotic, or monotonous reading. "
                    "Avenqo AI Central supplies the authorized response text. Speak it naturally in its original language. "
                    "When a new user utterance uses a different language, follow that language. Never translate to French by default."
                ),
                "modalities": ["audio", "text"],
                "voice": self._config.tts_voice,
                "speed": self._config.speech_speed,
                "input_audio_noise_reduction": noise,
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {"model": self._config.stt_model} if self._config.stt_model else None,
                "turn_detection": {
                    "type": "server_vad",
                    "create_response": False,
                    "interrupt_response": False,
                },
                "tools": [],
            }
        else:
            session_payload = {
                "type": "realtime",
                "instructions": (
                    f"You are a warm, highly natural, professional phone receptionist representing the business. "
                    f"Start in {locale_info(locale).english_name}. Speak with a {self._config.delivery_style} delivery, "
                    "natural conversational pacing, and friendly human intonation. Avoid mechanical, robotic, or monotonous reading. "
                    "Avenqo AI Central supplies the authorized response text. Speak it naturally in its original language. "
                    "When a new user utterance uses a different language, follow that language. Never translate to French by default."
                ),
                "output_modalities": ["audio"],
                "audio": {
                    "input": {
                        "noise_reduction": noise,
                        "format": {"type": "audio/pcm", "rate": 24000},
                        "transcription": {"model": self._config.stt_model or "gpt-4o-mini-transcribe"},
                        "turn_detection": {
                            "type": "server_vad",
                            "create_response": False,
                            "interrupt_response": False,
                            "prefix_padding_ms": 300,
                            "silence_duration_ms": 500,
                            "threshold": 0.5,
                        },
                    },
                    "output": {
                        "speed": self._config.speech_speed,
                        "format": {"type": "audio/pcm", "rate": 24000},
                        "voice": self._config.tts_voice or "marin",
                    },
                },
                "tools": [],
            }
        await self._connection.send(cast(Any, {
            "type": "session.update",
            "session": session_payload,
        }))

    async def send_audio(self, audio: bytes) -> None:
        if self._connection is None:
            raise ExternalVoiceConfigurationRequired("Realtime session is not open")
        await self._connection.send({
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(audio).decode("ascii"),
        })

    async def speak(self, text: str) -> None:
        if self._connection is None:
            raise ExternalVoiceConfigurationRequired("Realtime session is not open")
        cleaned_text = strip_markdown_for_speech(text) or text
        await self._connection.send({
            "type": "response.create",
            "response": {
                "conversation": "none",
                "output_modalities": ["audio"],
                "instructions": (
                    "Speak the supplied text verbatim with a natural, conversational, warm, and friendly human tone. "
                    f"Use a {self._config.delivery_style} delivery with smooth pacing and expressive warmth. "
                    "Avoid robotic, mechanical, or monotone reading. Do not translate or add information."
                ),
                "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": cleaned_text}]}],
            },
        })

    async def interrupt(self) -> None:
        if self._connection is not None:
            await self._connection.send(cast(Any, {"type": "response.cancel"}))

    async def clear_input(self) -> None:
        if self._connection is not None:
            await self._connection.send({"type": "input_audio_buffer.clear"})

    async def close(self) -> None:
        if self._manager is not None:
            await self._manager.__aexit__(None, None, None)
        self._manager = None
        self._connection = None

    async def reconnect(self, fallback_model: str = "gpt-realtime-2.1", locale: str = "fr-CA") -> None:
        """Mid-call failover and reconnection if primary session drops."""
        logger.warning("Reconnecting realtime audio adapter to fallback model=%s", fallback_model)
        await self.close()
        self._model = fallback_model
        await self.open(locale=locale)

    async def events(self):
        if self._connection is None:
            raise ExternalVoiceConfigurationRequired("Realtime session is not open")
        async for event in self._connection:
            yield event
