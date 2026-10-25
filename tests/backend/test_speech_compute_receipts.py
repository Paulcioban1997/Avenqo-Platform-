"""Unpaid lab receipts/authorization, no hosted inference or live phone calls."""
import asyncio
import secrets
import threading
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.voice.open_speech import OpenSpeechClient, OpenSpeechConfig, SpeechUnavailable
from backend.app.voice.open_speech_catalog import CHATTERBOX, PARAKEET
from backend.app.voice.speech_jobs import PilotUsageLedger, SpeechJobConflict, SpeechJobJournal
from services.voice_speech.app import create_app


class FixtureEngine:
    def synthesize(self, text, locale):
        return b"\0\0" * 2400


def test_receipt_survives_restart_duplicate_is_never_recomputed(tmp_path):
    path = tmp_path / "worker-usage.sqlite"
    journal = SpeechJobJournal(path)
    job = str(uuid4())
    journal.start(job, CHATTERBOX, "tts")
    journal.finish(job, 1.25, "completed")
    reopened = SpeechJobJournal(path)
    assert reopened.receipt(job)["inference_seconds"] == 1.25
    with pytest.raises(SpeechJobConflict):
        reopened.start(job, CHATTERBOX, "tts")
    unknown = str(uuid4())
    reopened.start(unknown, CHATTERBOX, "tts")
    assert SpeechJobJournal(path).receipt(unknown)["status"] == "unknown"


def test_journal_bound_refuses_more_jobs_without_deleting_receipts():
    journal = SpeechJobJournal(capacity=1)
    job = str(uuid4())
    journal.start(job, PARAKEET, "asr")
    with pytest.raises(SpeechJobConflict):
        journal.start(str(uuid4()), PARAKEET, "asr")
    assert journal.receipt(job)["status"] == "running"


def test_unpaid_lab_cost_is_explicit_unknown_cost_and_other_call_are_denied():
    company, call, job = uuid4(), uuid4(), str(uuid4())
    with pytest.raises(ValueError):
        PilotUsageLedger(company_id=company, call_id=call).register(job)
    with pytest.raises(ValueError):
        PilotUsageLedger(company_id=company, call_id=call, rate_usd_per_compute_second=0, source="unknown")
    ledger = PilotUsageLedger(company_id=company, call_id=call,
                              rate_usd_per_compute_second="0.01", source="fixture-allocation")
    receipt = {"id": job, "status": "completed", "inference_seconds": 2.5}
    with pytest.raises(PermissionError):
        ledger.reconcile(receipt)
    ledger.register(job)
    assert ledger.reconcile(receipt)["estimated_compute_cost_usd"] == "0.025"
    ledger.reconcile(receipt)
    assert len(ledger.settlements) == 1
    with pytest.raises(ValueError):
        ledger.reconcile({**receipt, "status": "unknown"})


@pytest.mark.asyncio
async def test_cancelled_http_inference_finishes_and_has_reconcilable_cost(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    entered, release = threading.Event(), threading.Event()
    class SlowFixture(FixtureEngine):
        def synthesize(self, text, locale):
            entered.set()
            assert release.wait(3)
            return super().synthesize(text, locale)
    key, job = secrets.token_urlsafe(32), str(uuid4())
    app = create_app(role="tts", api_key=key, engine=SlowFixture())
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://worker",
                                     headers={"Authorization": "Bearer " + key}) as client:
            task = asyncio.create_task(client.post("/v1/audio/speech", json={"input": "Fixture", "language": "fr"},
                                                   headers={"X-Speech-Job-Id": job}))
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                assert app.state.usage_journal.receipt(job)["status"] == "running"
                assert (await client.post("/v1/audio/speech", json={"input": "Fixture", "language": "fr"})).status_code == 429
            finally:
                release.set()
            for _ in range(100):
                if app.state.usage_journal.receipt(job)["status"] == "completed":
                    break
                await asyncio.sleep(.01)
            receipt = (await client.get("/v1/usage/" + job)).json()
            assert receipt["status"] == "completed" and receipt["inference_seconds"] > 0
            assert "Fixture" not in str(receipt)
            duplicate = await client.post("/v1/audio/speech", json={"input": "Fixture", "language": "fr"}, headers={"X-Speech-Job-Id": job})
            assert duplicate.status_code == 409


@pytest.mark.asyncio
async def test_client_retains_cancelled_job_and_reconciles_without_audio_or_tool_replay():
    ledger = PilotUsageLedger(company_id=uuid4(), call_id=uuid4(), rate_usd_per_compute_second="0.01", source="fixture-allocation")
    seen = []
    async def handler(request):
        seen.append(request.method)
        if request.method == "POST":
            raise asyncio.CancelledError()
        return httpx.Response(200, json={"id": request.url.path.rsplit("/", 1)[-1], "model": PARAKEET.model_id,
            "revision": PARAKEET.revision, "role": "asr", "status": "completed", "inference_seconds": 3})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = OpenSpeechClient(OpenSpeechConfig("http://localhost:1", "http://localhost:2", secrets.token_urlsafe(32)),
                                  client=http, usage_ledger=ledger)
        with pytest.raises(asyncio.CancelledError):
            await client.transcribe(b"\0\0" * 2400)
        assert len(client.pending_jobs) == 1
        with pytest.raises(SpeechUnavailable, match="reconciliation"):
            await client.transcribe(b"\0\0" * 2400)
        assert len(await client.reconcile_usage()) == 1
        assert not client.pending_jobs and list(ledger.settlements.values())[0] == Decimal("0.03")
        assert seen == ["POST", "GET"]


def test_usage_endpoint_requires_independent_auth_and_prewarm_is_explicit(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    key = secrets.token_urlsafe(32)
    with TestClient(create_app(role="tts", api_key=key, engine=FixtureEngine(), prewarm_languages=("fr",))) as client:
        assert client.get("/v1/usage/" + str(uuid4())).status_code == 401
        headers = {"Authorization": "Bearer " + key}
        assert client.get("/health", headers=headers).json()["prewarmed_languages"] == ["fr"]
        assert client.get("/v1/usage/" + str(uuid4()), headers=headers).status_code == 404


def test_restart_with_unknown_job_denies_new_inference_until_accounted(monkeypatch, tmp_path):
    monkeypatch.setenv("ENVIRONMENT", "test")
    path = tmp_path / "usage.sqlite"
    job = str(uuid4())
    SpeechJobJournal(path).start(job, CHATTERBOX, "tts")
    key = secrets.token_urlsafe(32)
    with TestClient(create_app(role="tts", api_key=key, engine=FixtureEngine(), journal_path=path)) as client:
        headers = {"Authorization": "Bearer " + key}
        assert client.get("/health", headers=headers).json()["status"] == "unavailable"
        assert client.get("/v1/usage/" + job, headers=headers).json()["status"] == "unknown"
        assert client.post("/v1/audio/speech", headers=headers,
                           json={"input": "Fixture", "language": "fr"}).status_code == 503


def test_budget_override_rejects_remote_inference_even_with_lab_flag():
    from backend.app.config.settings import Settings
    from backend.app.voice.open_speech_runtime import build_lab_adapter
    company = uuid4()
    settings = Settings(_env_file=None, ENVIRONMENT="sandbox", AUTH_JWT_SECRET=secrets.token_urlsafe(48),
                        VOICE_OPEN_SPEECH_LAB_ENABLED=True, VOICE_OPEN_SPEECH_COMPANY_IDS=[company],
                        VOICE_OPEN_SPEECH_ASR_URL="https://remote.example", VOICE_OPEN_SPEECH_TTS_URL="https://remote.example",
                        VOICE_OPEN_SPEECH_API_KEY=secrets.token_urlsafe(32))
    with pytest.raises(SpeechUnavailable, match="Zero-budget"):
        build_lab_adapter(settings, company_id=company)
