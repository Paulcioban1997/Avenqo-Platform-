"""Configured STT/TTS/realtime adapter contracts for Voice Central."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx


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

    async def interrupt(self) -> None: ...

    async def close(self) -> None: ...


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

    def __init__(self, config: OpenAIAudioConfig, client: httpx.AsyncClient | None = None) -> None:
        self._config = config
        self._client = client

    async def transcribe(self, audio: bytes, *, locale: str, content_type: str) -> str:
        if not self._config.api_key or not self._config.stt_model:
            raise ExternalVoiceConfigurationRequired("OPENAI_API_KEY and VOICE_STT_MODEL are required")
        files = {"file": ("voice-input", audio, content_type)}
        data = {"model": self._config.stt_model, "language": locale.split("-")[0]}
        headers = {"Authorization": f"Bearer {self._config.api_key}"}
        if self._client is not None:
            response = await self._client.post(f"{self._config.base_url}/audio/transcriptions", headers=headers, data=data, files=files)
        else:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(f"{self._config.base_url}/audio/transcriptions", headers=headers, data=data, files=files)
        response.raise_for_status()
        return str(response.json().get("text") or "")


class OpenAITextToSpeechAdapter:
    provider_id = "openai"

    def __init__(self, config: OpenAIAudioConfig, client: httpx.AsyncClient | None = None) -> None:
        self._config = config
        self._client = client

    async def synthesize(self, text: str, *, locale: str) -> bytes:
        if not self._config.api_key or not self._config.tts_model or not self._config.tts_voice:
            raise ExternalVoiceConfigurationRequired(
                "OPENAI_API_KEY, VOICE_TTS_MODEL and VOICE_TTS_VOICE are required"
            )
        payload = {"model": self._config.tts_model, "voice": self._config.tts_voice, "input": text, "response_format": "opus"}
        headers = {"Authorization": f"Bearer {self._config.api_key}", "Content-Type": "application/json"}
        if self._client is not None:
            response = await self._client.post(f"{self._config.base_url}/audio/speech", headers=headers, json=payload)
        else:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(f"{self._config.base_url}/audio/speech", headers=headers, json=payload)
        response.raise_for_status()
        return response.content


class UnconfiguredRealtimeAudioAdapter:
    provider_id = "none"

    async def open(self, *, locale: str) -> None:
        raise ExternalVoiceConfigurationRequired("VOICE_REALTIME_PROVIDER is required")

    async def send_audio(self, audio: bytes) -> None:
        raise ExternalVoiceConfigurationRequired("VOICE_REALTIME_PROVIDER is required")

    async def interrupt(self) -> None:
        return None

    async def close(self) -> None:
        return None
