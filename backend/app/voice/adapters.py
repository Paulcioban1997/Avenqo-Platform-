"""Configured STT/TTS/realtime adapter contracts for Voice Central."""

from __future__ import annotations

from dataclasses import dataclass
import base64
import logging
from typing import Any, AsyncIterator, Protocol, cast

from openai import AsyncOpenAI

from backend.app.core.locale_catalog import locale_info

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

    async def transcribe(self, audio: bytes, *, locale: str, content_type: str) -> str:
        if not self._config.api_key or not self._config.stt_model:
            raise ExternalVoiceConfigurationRequired("OPENAI_API_KEY and VOICE_STT_MODEL are required")
        client = self._client or AsyncOpenAI(api_key=self._config.api_key, base_url=self._config.base_url)
        response = await client.audio.transcriptions.create(
            file=("voice-input", audio, content_type),
            model=self._config.stt_model,
        )
        return str(getattr(response, "text", response) or "")


class OpenAITextToSpeechAdapter:
    provider_id = "openai"

    def __init__(self, config: OpenAIAudioConfig, client: AsyncOpenAI | None = None) -> None:
        self._config = config
        self._client = client

    async def synthesize(self, text: str, *, locale: str) -> bytes:
        if not self._config.api_key or not self._config.tts_model or not self._config.tts_voice:
            raise ExternalVoiceConfigurationRequired(
                "OPENAI_API_KEY, VOICE_TTS_MODEL and VOICE_TTS_VOICE are required"
            )
        client = self._client or AsyncOpenAI(api_key=self._config.api_key, base_url=self._config.base_url)
        response = await client.audio.speech.create(
            input=text,
            model=self._config.tts_model,
            voice=self._config.tts_voice,
            response_format="opus",
            speed=self._config.speech_speed,
            instructions=f"Speak naturally in {locale_info(locale).english_name}. Preserve the input language; do not translate.",
        )
        return response.read()


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
            # Fallback transparent et vérifié : gpt-live-1 -> gpt-realtime-2.1
            if self._model == "gpt-live-1":
                logger.warning("Primary voice model gpt-live-1 unavailable (%s); falling back to gpt-realtime-2.1", exc)
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
                "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}],
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
