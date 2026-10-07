"""Configured STT/TTS/realtime adapter contracts for Voice Central."""

from __future__ import annotations

from dataclasses import dataclass
import base64
from typing import Any, Protocol, cast

from openai import AsyncOpenAI

from backend.app.core.locale_catalog import locale_info


class SpeechToTextAdapter(Protocol):
    provider_id: str

    async def transcribe(self, audio: bytes, *, locale: str, content_type: str) -> str: ...


class TextToSpeechAdapter(Protocol):
    provider_id: str

    async def synthesize(self, text: str, *, locale: str) -> bytes: ...


class RealtimeAudioAdapter(Protocol):
    provider_id: str

    async def open(self, *, locale: str) -> None: ...

    async def send_audio(self, audio: bytes) -> None: ...

    async def speak(self, text: str) -> None: ...

    async def interrupt(self) -> None: ...

    async def clear_input(self) -> None: ...

    async def close(self) -> None: ...

    async def events(self): ...


class ExternalVoiceConfigurationRequired(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OpenAIAudioConfig:
    api_key: str | None
    stt_model: str | None
    tts_model: str | None
    tts_voice: str | None
    base_url: str = "https://api.openai.com/v1"


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
            instructions=f"Speak naturally in {locale_info(locale).english_name}. Preserve the input language; do not translate.",
        )
        return response.read()


class UnconfiguredRealtimeAudioAdapter:
    provider_id = "none"

    async def open(self, *, locale: str) -> None:
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

    async def open(self, *, locale: str) -> None:
        if not self._config.api_key or not self._model:
            raise ExternalVoiceConfigurationRequired("OPENAI_API_KEY and VOICE_REALTIME_MODEL are required")
        client = AsyncOpenAI(api_key=self._config.api_key, base_url=self._config.base_url)
        self._manager = client.realtime.connect(model=self._model)
        self._connection = await self._manager.__aenter__()
        await self._connection.send(cast(Any, {
            "type": "session.update",
            "session": {
                "type": "realtime",
                "instructions": (
                    "Avenqo AI Central supplies the authorized response text. Speak it in its original language. "
                    "When a new user utterance uses a different language, follow that language. Never translate to French by default."
                ),
                "output_modalities": ["audio"],
                "tools": [],
                "audio": {
                    "input": {
                        "format": {"type": "audio/pcm", "rate": 24000},
                        "transcription": {"model": self._config.stt_model},
                        "turn_detection": {
                            "type": "server_vad", "create_response": False, "interrupt_response": False,
                        },
                    },
                    "output": {"format": {"type": "audio/pcm", "rate": 24000}, "voice": self._config.tts_voice},
                },
            },
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
                "instructions": "Speak the supplied text verbatim in its existing language. Do not translate, answer, or add information.",
                "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}],
            },
        })

    async def interrupt(self) -> None:
        if self._connection is not None:
            await self._connection.send({"type": "response.cancel"})
            await self._connection.send({"type": "output_audio_buffer.clear"})

    async def clear_input(self) -> None:
        if self._connection is not None:
            await self._connection.send({"type": "input_audio_buffer.clear"})

    async def close(self) -> None:
        if self._manager is not None:
            await self._manager.__aexit__(None, None, None)
        self._manager = None
        self._connection = None

    async def events(self):
        if self._connection is None:
            raise ExternalVoiceConfigurationRequired("Realtime session is not open")
        async for event in self._connection:
            yield event
