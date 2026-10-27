"""Contract/security fixtures, not model quality or real telephone certification."""
import asyncio
import secrets
import struct
import threading

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.voice.open_speech import (
    OpenSpeechClient, OpenSpeechConfig, OpenSpeechRealtimeAdapter, SpeechUnavailable,
    validate_worker_url,
)
from backend.app.voice.open_speech_catalog import CHATTERBOX, PARAKEET, pcm_wav
from services.voice_speech.app import create_app
from services.voice_speech.models import decode_wav


class FixtureEngine:
    """Explicit fake engine; neural inference is measured separately in the GPU lab."""
    def transcribe(self, audio, locale):
        pcm, rate = decode_wav(audio)
        return {"text": "fixture transcription", "audio_seconds": len(pcm) / (rate * 2)}

    def synthesize(self, text, locale):
        return b"\0\0" * 2400


@pytest.mark.parametrize("url", [
    "http://untrusted.example", "https://user:pass@example.org", "https://example.org?key=x",
    "https://example.org/#fragment", "file:///tmp/audio", "https://example.org/tenant-url",
])
def test_worker_destination_is_server_configured_and_not_a_caller_url(url):
    with pytest.raises(ValueError):
        validate_worker_url(url)


@pytest.mark.parametrize("url", ["http://127.0.0.1:9001", "http://localhost:9001", "https://speech.example.org"])
def test_explicit_worker_destinations(url):
    assert validate_worker_url(url) == url


def test_worker_denies_missing_auth_and_exposes_no_transcript_or_secret(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    key = secrets.token_urlsafe(32)
    with TestClient(create_app(role="asr", api_key=key, engine=FixtureEngine())) as client:
        assert client.get("/health").status_code == 401
        response = client.get("/health", headers={"Authorization": "Bearer " + key})
        assert response.status_code == 200
        assert response.json()["revision"] == PARAKEET.revision
        assert response.json()["retains_audio"] is False
        assert key not in response.text


def test_worker_refuses_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(RuntimeError, match="Sandbox"):
        create_app(role="asr", api_key=secrets.token_urlsafe(32), engine=FixtureEngine())


def test_worker_reads_bounded_audio_and_returns_measured_duration(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    key = secrets.token_urlsafe(32)
    with TestClient(create_app(role="asr", api_key=key, engine=FixtureEngine())) as client:
        headers = {"Authorization": "Bearer " + key}
        response = client.post("/v1/audio/transcriptions", headers=headers, content=pcm_wav(b"\0\0" * 2400, 24000))
        assert response.status_code == 200
        assert response.json()["audio_seconds"] == .1
        assert response.json()["text"] == "fixture transcription"
        assert client.post("/v1/audio/transcriptions", headers=headers, content=b"broken wav").status_code == 422
        assert client.post("/v1/audio/transcriptions", headers=headers, content=b"0" * 3_000_001).status_code == 413


def test_speech_worker_forbids_business_identity_tools_and_unlisted_language(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    key = secrets.token_urlsafe(32)
    with TestClient(create_app(role="tts", api_key=key, engine=FixtureEngine())) as client:
        headers = {"Authorization": "Bearer " + key}
        base = {"input": "Bonjour", "language": "fr-CA"}
        assert client.post("/v1/audio/speech", headers=headers, json=base).status_code == 200
        for extra in ({"company_id": "foreign-tenant"}, {"tools": ["read_sales"]}, {"voice_reference": "/tmp/voice.wav"}):
            assert client.post("/v1/audio/speech", headers=headers, json={**base, **extra}).status_code == 422
        assert client.post("/v1/audio/speech", headers=headers, json={**base, "language": "ro"}).status_code == 422


def test_worker_refuses_concurrent_gpu_work_without_overlap(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    entered, release = threading.Event(), threading.Event()

    class SlowFixture(FixtureEngine):
        def synthesize(self, text, locale):
            entered.set()
            assert release.wait(5)
            return super().synthesize(text, locale)

    key = secrets.token_urlsafe(32)
    with TestClient(create_app(role="tts", api_key=key, engine=SlowFixture())) as client:
        headers = {"Authorization": "Bearer " + key}
        results = []
        first = threading.Thread(target=lambda: results.append(client.post("/v1/audio/speech", headers=headers, json={"input": "fixture", "language": "fr"})))
        first.start()
        try:
            assert entered.wait(5)
            second = client.post("/v1/audio/speech", headers=headers, json={"input": "second fixture", "language": "en"})
            assert second.status_code == 429
        finally:
            release.set()
            first.join(timeout=5)
        assert results[0].status_code == 200


@pytest.mark.parametrize("pcm,rate", [(b"", 24000), (b"\0\0" * 24001 * 30, 24000), (b"\0\0", 11025)], ids=["empty", "too-long", "unsupported-rate"])
def test_invalid_audio_never_reaches_model(pcm, rate):
    with pytest.raises(ValueError):
        decode_wav(pcm_wav(pcm, rate))


def test_independent_secret_is_not_represented():
    key = secrets.token_urlsafe(32)
    config = OpenSpeechConfig("http://127.0.0.1:9001", "http://127.0.0.1:9002", key)
    assert key not in repr(config)


@pytest.mark.asyncio
async def test_artifact_revision_mismatch_is_fail_closed():
    async def handler(request):
        return httpx.Response(200, json={"status": "ready", "model": PARAKEET.model_id, "revision": "wrong", "role": "asr", "languages": ["fr"]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = OpenSpeechClient(OpenSpeechConfig("http://localhost:1", "http://localhost:2", secrets.token_urlsafe(32)), client=http)
        with pytest.raises(SpeechUnavailable):
            await client.ready("fr-CA")


@pytest.mark.asyncio
async def test_wrong_provider_body_never_exposes_secrets():
    key = secrets.token_urlsafe(32)
    async def handler(request):
        return httpx.Response(401, text=key)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = OpenSpeechClient(OpenSpeechConfig("http://localhost:1", "http://localhost:2", key), client=http)
        with pytest.raises(SpeechUnavailable) as exc:
            await client.transcribe(b"\0\0" * 240)
        assert key not in str(exc.value)


class FixtureSpeechClient:
    def __init__(self):
        self.called = []
        self.block = asyncio.Event()

    async def ready(self, locale):
        self.called.append(locale)

    async def transcribe(self, pcm):
        return {"text": "Quels produits vendez-vous ?", "audio_seconds": len(pcm) / 48000, "request_id": "fixture-request"}

    async def synthesize(self, text, locale):
        self.called.append((text, locale))
        return b"\0\0" * 2400, "fixture-speech"

    async def close(self):
        pass


async def next_event(adapter):
    return await asyncio.wait_for(adapter.queue.get(), 2)


@pytest.mark.asyncio
async def test_vad_emits_transcript_but_never_generates_a_business_answer():
    client = FixtureSpeechClient()
    adapter = OpenSpeechRealtimeAdapter(client)
    await adapter.open(locale="fr-CA")
    assert (await next_event(adapter)).type == "session.updated"
    for _ in range(10):
        await adapter.send_audio(struct.pack("<h", 1000) * 480)
    for _ in range(25):
        await adapter.send_audio(b"\0\0" * 480)
    assert (await next_event(adapter)).type == "input_audio_buffer.speech_started"
    assert (await next_event(adapter)).type == "input_audio_buffer.speech_stopped"
    event = await next_event(adapter)
    assert event.type == "conversation.item.input_audio_transcription.completed"
    assert event.model == PARAKEET.model_id
    assert client.called == ["fr-CA"]  # No autonomous TTS or LLM call.
    await adapter.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("locale", ["fr-CA", "en", "es"])
async def test_speaks_only_authorized_central_text_and_preserves_language(locale):
    client = FixtureSpeechClient()
    adapter = OpenSpeechRealtimeAdapter(client)
    await adapter.open(locale=locale)
    await next_event(adapter)
    await adapter.speak("Stock inconnu.")
    assert (await next_event(adapter)).type == "response.created"
    assert (await next_event(adapter)).type == "response.output_audio.delta"
    assert (await next_event(adapter)).type == "response.done"
    assert client.called[-1] == ("Stock inconnu.", locale)
    await adapter.close()


@pytest.mark.asyncio
async def test_barge_in_cancels_stale_audio_without_replaying_business_tools():
    class SlowClient(FixtureSpeechClient):
        async def synthesize(self, text, locale):
            await self.block.wait()
            return await super().synthesize(text, locale)

    client = SlowClient()
    adapter = OpenSpeechRealtimeAdapter(client)
    await adapter.open(locale="fr")
    await next_event(adapter)
    await adapter.speak("Ancienne réponse.")
    await next_event(adapter)
    await adapter.interrupt()
    client.block.set()
    await asyncio.sleep(0)
    assert adapter.queue.empty()
    await adapter.speak("Nouvelle question.")
    assert (await next_event(adapter)).type == "response.created"
    assert (await next_event(adapter)).type == "response.output_audio.delta"
    assert (await next_event(adapter)).type == "response.done"
    await adapter.close()


@pytest.mark.asyncio
async def test_caller_sessions_keep_language_and_audio_queues_isolated():
    a, b = OpenSpeechRealtimeAdapter(FixtureSpeechClient()), OpenSpeechRealtimeAdapter(FixtureSpeechClient())
    await a.open(locale="fr")
    await b.open(locale="en")
    await next_event(a)
    await next_event(b)
    await a.speak("Réponse privée du tenant A.")
    assert b.queue.empty()
    assert a.locale == "fr" and b.locale == "en"
    await asyncio.gather(a.close(), b.close())


@pytest.mark.asyncio
async def test_interrupt_discards_audio_already_queued_before_barge_in():
    adapter = OpenSpeechRealtimeAdapter(FixtureSpeechClient())
    await adapter.open(locale="fr")
    await next_event(adapter)
    await adapter.speak("Réponse interrompue.")
    await adapter._tts_task
    assert not adapter.queue.empty()
    await adapter.interrupt()
    assert adapter.queue.empty()
    await adapter.close()


@pytest.mark.asyncio
async def test_pin_input_clear_discards_completed_transcript_still_in_queue():
    adapter = OpenSpeechRealtimeAdapter(FixtureSpeechClient())
    await adapter._emit("conversation.item.input_audio_transcription.completed", transcript="private fixture")
    await adapter._emit("session.updated")
    await adapter.clear_input()
    assert (await next_event(adapter)).type == "session.updated"
    assert adapter.queue.empty()
    await adapter.close()


def test_lab_flag_never_selects_unmetered_phone_provider():
    from backend.app.config.settings import Settings
    from backend.app.voice.open_speech_runtime import build_phone_adapter, phone_readiness
    settings = Settings(_env_file=None, ENVIRONMENT="sandbox", AUTH_JWT_SECRET=secrets.token_urlsafe(48), VOICE_OPEN_SPEECH_LAB_ENABLED=True)
    marker = object()
    assert build_phone_adapter(settings, lambda: marker) is marker
    assert phone_readiness(settings)["telephone_ready"] is False
    assert "cancelled_inference_cost_settlement_pending" in phone_readiness(settings)["blockers"]


@pytest.mark.parametrize("environment,enabled,authorized", [
    ("production", True, True), ("sandbox", False, True), ("sandbox", True, False),
])
def test_lab_factory_denies_production_disabled_flag_and_other_tenants(environment, enabled, authorized):
    from uuid import uuid4
    from backend.app.config.settings import Settings
    from backend.app.voice.open_speech_runtime import build_lab_adapter
    company = uuid4()
    settings = Settings(_env_file=None, ENVIRONMENT="test", AUTH_JWT_SECRET=secrets.token_urlsafe(48), VOICE_OPEN_SPEECH_LAB_ENABLED=enabled,
                        VOICE_OPEN_SPEECH_COMPANY_IDS=[company] if authorized else [])
    # Only the speech factory is under test; do not manufacture production credentials.
    settings.environment = environment
    with pytest.raises(SpeechUnavailable):
        build_lab_adapter(settings, company_id=company)


@pytest.mark.asyncio
async def test_lab_factory_requires_independent_worker_configuration_and_selects_pinned_kokoro():
    from uuid import uuid4
    from backend.app.config.settings import Settings
    from backend.app.voice.open_speech_runtime import build_lab_adapter
    from backend.app.voice.open_speech_catalog import KOKORO
    company = uuid4()
    settings = Settings(_env_file=None, ENVIRONMENT="sandbox", AUTH_JWT_SECRET=secrets.token_urlsafe(48), VOICE_OPEN_SPEECH_LAB_ENABLED=True,
                        VOICE_OPEN_SPEECH_COMPANY_IDS=[company])
    with pytest.raises(SpeechUnavailable, match="incomplete"):
        build_lab_adapter(settings, company_id=company)
    settings.voice_open_speech_asr_url = "http://localhost:9001"
    settings.voice_open_speech_tts_url = "http://localhost:9002"
    settings.voice_open_speech_api_key = secrets.token_urlsafe(32)
    adapter = build_lab_adapter(settings, company_id=company)
    assert adapter.client.config.tts_artifact == KOKORO
    assert settings.voice_open_speech_api_key not in repr(settings)
    await adapter.close()


def test_kokoro_worker_has_distinct_pinned_artifact_and_rejects_unsupported_romanian(monkeypatch):
    from backend.app.voice.open_speech_catalog import KOKORO
    monkeypatch.setenv("ENVIRONMENT", "test")
    key = secrets.token_urlsafe(32)
    with TestClient(create_app(role="tts", api_key=key, engine=FixtureEngine(), tts_backend="kokoro")) as client:
        headers = {"Authorization": "Bearer " + key}
        assert client.get("/health", headers=headers).json()["revision"] == KOKORO.revision
        assert client.post("/v1/audio/speech", headers=headers,
                           json={"input": "Fixture", "language": "ro"}).status_code == 422
