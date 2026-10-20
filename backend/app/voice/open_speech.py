"""Experimental, bounded ASR -> existing Avenqo Central -> TTS audio adapter.

This module never generates a business answer or executes a tool. The existing
Telnyx bridge remains responsible for caller authentication, tenant context,
authorization, quotas, Central execution and telephone playback cancellation.
"""
from __future__ import annotations

import asyncio
import audioop
import base64
import math
from collections import deque
from dataclasses import dataclass, field
from types import SimpleNamespace as Event
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from backend.app.voice.open_speech_catalog import CHATTERBOX, KOKORO, PARAKEET, SpeechArtifact, language_code, pcm_wav


class SpeechUnavailable(RuntimeError):
    """Safe diagnostics: never include upstream bodies, audio, text or keys."""


def validate_worker_url(value: str) -> str:
    parsed = urlsplit(value)
    loopback = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"} or (parsed.scheme != "https" and not loopback)):
        raise ValueError("Worker requires HTTPS or explicit loopback HTTP without userinfo or path")
    return value.rstrip("/")


@dataclass(frozen=True)
class OpenSpeechConfig:
    asr_url: str
    tts_url: str
    api_key: str = field(repr=False)
    timeout_seconds: float = 30
    tts_artifact: SpeechArtifact = CHATTERBOX

    def __post_init__(self):
        validate_worker_url(self.asr_url)
        validate_worker_url(self.tts_url)
        if len(self.api_key) < 32 or not 1 <= self.timeout_seconds <= 60:
            raise ValueError("Independent speech credential and bounded timeout required")
        if self.tts_artifact not in {CHATTERBOX, KOKORO}:
            raise ValueError("Unreviewed TTS artifact")


class OpenSpeechClient:
    def __init__(self, config: OpenSpeechConfig, *, client=None):
        self.config = config
        self.client = client or httpx.AsyncClient(
            headers={"Authorization": "Bearer " + config.api_key},
            timeout=config.timeout_seconds, follow_redirects=False, trust_env=False,
        )
        self._owns_client = client is None

    async def ready(self, locale: str):
        code = language_code(locale)
        for url, artifact, role in ((self.config.asr_url, PARAKEET, "asr"),
                                    (self.config.tts_url, self.config.tts_artifact, "tts")):
            try:
                response = await self.client.get(url + "/health")
                response.raise_for_status()
                data = response.json()
                if (data.get("model") != artifact.model_id or data.get("revision") != artifact.revision
                        or data.get("status") != "ready" or data.get("role") != role
                        or code not in data.get("languages", [])):
                    raise SpeechUnavailable("Worker artifact or language mismatch")
            except (httpx.HTTPError, ValueError):
                raise SpeechUnavailable("Speech readiness failed") from None

    async def transcribe(self, pcm: bytes) -> dict:
        try:
            response = await self.client.post(self.config.asr_url + "/v1/audio/transcriptions",
                                             content=pcm_wav(pcm, 24000),
                                             headers={"Content-Type": "audio/wav"})
            response.raise_for_status()
            data = response.json()
            if (data.get("model") != PARAKEET.model_id or data.get("revision") != PARAKEET.revision
                    or not isinstance(data.get("text"), str) or len(data["text"]) > 12000):
                raise SpeechUnavailable("Invalid ASR response")
            seconds = float(data["audio_seconds"])
            if not math.isfinite(seconds) or abs(seconds - len(pcm) / 48000) > .05:
                raise SpeechUnavailable("Invalid ASR duration")
            return data
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise SpeechUnavailable("Speech recognition failed") from None

    async def synthesize(self, text: str, locale: str) -> tuple[bytes, str]:
        if language_code(locale) not in self.config.tts_artifact.locales:
            raise SpeechUnavailable("TTS language unsupported; explicit provider fallback required")
        try:
            # Stream and bound the response even if a worker sends no Content-Length.
            async with self.client.stream("POST", self.config.tts_url + "/v1/audio/speech",
                                          json={"input": text, "language": locale}) as response:
                response.raise_for_status()
                if (response.headers.get("X-Audio-Sample-Rate") != "24000"
                        or response.headers.get("X-Audio-Encoding") != "pcm_s16le"):
                    raise SpeechUnavailable("Unexpected PCM output contract")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > 40 * 48000:
                        raise SpeechUnavailable("Speech output exceeds bounded duration")
                if not body or len(body) % 2:
                    raise SpeechUnavailable("Invalid PCM output")
                return bytes(body), response.headers.get("X-Speech-Request-Id", uuid4().hex)
        except (httpx.HTTPError, ValueError):
            raise SpeechUnavailable("Speech synthesis failed") from None

    async def close(self):
        if self._owns_client:
            await self.client.aclose()


class OpenSpeechRealtimeAdapter:
    """Realtime event facade over utterance-batch models, NOT native streaming TTS.

    Energy VAD is an experimental baseline, not a certified end-of-turn detector.
    It must be benchmarked with telephone noise before any commercial activation.
    """
    provider_id = "open_speech"
    FRAME_BYTES = 960  # 20ms PCM16 mono at 24kHz.

    def __init__(self, client: OpenSpeechClient):
        self.client = client
        self.queue = asyncio.Queue(maxsize=64)
        self.locale = "fr"
        self.closed = False
        self._pcm = bytearray()
        self._pre = deque(maxlen=12)
        self._utterance = bytearray()
        self._item = None
        self._silence = 0
        self._input_generation = 0
        self._response_generation = 0
        self._asr_tasks = set()
        self._tts_task = None
        self._response_id = None

    async def _emit(self, kind, **fields):
        if not self.closed:
            await self.queue.put(Event(type=kind, **fields))

    async def open(self, *, locale):
        await self.client.ready(locale)
        self.locale = locale
        await self._emit("session.updated")

    async def send_audio(self, audio: bytes):
        if self.closed or len(audio) % 2 or len(audio) > 48000:
            raise SpeechUnavailable("Invalid bounded PCM input")
        self._pcm.extend(audio)
        while len(self._pcm) >= self.FRAME_BYTES:
            frame = bytes(self._pcm[:self.FRAME_BYTES])
            del self._pcm[:self.FRAME_BYTES]
            voiced = audioop.rms(frame, 2) >= 350
            if self._item is None:
                self._pre.append(frame)
                if not voiced:
                    continue
                self._item = uuid4().hex
                self._utterance = bytearray(b"".join(self._pre))
                self._pre.clear()
                self._silence = 0
                await self._emit("input_audio_buffer.speech_started", item_id=self._item)
            else:
                self._utterance.extend(frame)
                self._silence = 0 if voiced else self._silence + 1
            if self._silence >= 25 or len(self._utterance) >= 30 * 48000:
                item, pcm = self._item, bytes(self._utterance[:30 * 48000])
                self._item = None
                self._utterance.clear()
                self._silence = 0
                await self._emit("input_audio_buffer.speech_stopped", item_id=item)
                if len(self._asr_tasks) >= 2:
                    raise SpeechUnavailable("Pending utterance limit reached")
                task = asyncio.create_task(self._transcribe(item, pcm, self._input_generation))
                self._asr_tasks.add(task)
                task.add_done_callback(self._asr_tasks.discard)

    async def _transcribe(self, item, pcm, generation):
        try:
            data = await self.client.transcribe(pcm)
            if generation == self._input_generation:
                await self._emit("conversation.item.input_audio_transcription.completed",
                                 item_id=item, event_id=data["request_id"], transcript=data["text"],
                                 model=PARAKEET.model_id,
                                 usage=Event(type="duration", provider="open_speech",
                                             seconds=data["audio_seconds"]))
        except asyncio.CancelledError:
            raise
        except Exception:
            await self._emit("error", error=Event(code="open_speech_asr_unavailable", message="Speech recognition unavailable"))

    async def speak(self, text):
        if self.closed or not text.strip() or len(text) > 12000:
            raise SpeechUnavailable("Invalid speech text")
        if self._tts_task and not self._tts_task.done():
            raise SpeechUnavailable("Speech response already active")
        response_id = self._response_id = uuid4().hex
        await self._emit("response.created", response=Event(id=response_id))
        self._tts_task = asyncio.create_task(self._speak(text, response_id, self._response_generation))

    async def _speak(self, text, response_id, generation):
        total_seconds = 0.0
        try:
            # Sentence chunks avoid unbounded GPU generation; no autonomous LLM is involved.
            import re
            sentences = re.split(r"(?<=[.!?])\s+", text)
            for sentence in sentences:
                for start in range(0, len(sentence), 500):
                    pcm, _request_id = await self.client.synthesize(sentence[start:start + 500], self.locale)
                    total_seconds += len(pcm) / 48000
                    for offset in range(0, len(pcm), 9600):
                        if generation != self._response_generation:
                            return
                        await self._emit("response.output_audio.delta", response_id=response_id,
                                         delta=base64.b64encode(pcm[offset:offset + 9600]).decode("ascii"))
            if generation == self._response_generation:
                await self._emit("response.done", event_id=response_id, response=Event(
                    id=response_id, model=getattr(getattr(self.client, "config", None), "tts_artifact", CHATTERBOX).model_id,
                    usage=Event(provider="open_speech", audio_output_seconds=total_seconds)))
        except asyncio.CancelledError:
            raise
        except Exception:
            await self._emit("error", error=Event(code="open_speech_tts_unavailable", message="Speech synthesis unavailable"))

    async def interrupt(self):
        self._response_generation += 1
        if self._tts_task:
            self._tts_task.cancel()
            await asyncio.gather(self._tts_task, return_exceptions=True)
        self._discard_events(lambda event: event.type.startswith("response."))
        self._response_id = None

    def _discard_events(self, predicate):
        retained = []
        while not self.queue.empty():
            event = self.queue.get_nowait()
            if not predicate(event):
                retained.append(event)
        for event in retained:
            self.queue.put_nowait(event)

    async def clear_input(self):
        self._input_generation += 1
        self._pcm.clear()
        self._pre.clear()
        self._utterance.clear()
        self._item = None
        for task in list(self._asr_tasks):
            task.cancel()
        await asyncio.gather(*self._asr_tasks, return_exceptions=True)
        self._discard_events(lambda event: event.type.startswith("input_audio_buffer.")
                             or event.type == "conversation.item.input_audio_transcription.completed")

    async def close(self):
        self.closed = True
        await self.interrupt()
        await self.clear_input()
        await self.client.close()

    async def events(self):
        while not self.closed:
            yield await self.queue.get()
