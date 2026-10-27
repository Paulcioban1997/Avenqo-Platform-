"""Authenticated ASR/TTS only. Run on loopback for the isolated Sandbox lab.

No LLM, connector credentials, company identifiers, tools, audio files or transcripts
are retained here. Concurrency is one GPU operation per worker; busy requests fail.
"""
from __future__ import annotations

import asyncio
import hmac
import os
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from backend.app.voice.open_speech_catalog import CHATTERBOX, KOKORO, PARAKEET, language_code
from services.voice_speech.models import ChatterboxEngine, KokoroEngine, ParakeetEngine
from backend.app.voice.speech_jobs import SpeechJobConflict, SpeechJobJournal


class SpeechInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input: str = Field(min_length=1, max_length=500)
    language: str = Field(min_length=2, max_length=16)


def create_app(*, role: str, api_key: str, engine=None, cache_dir=None, device="cuda", tts_backend="chatterbox",
               journal_path=":memory:", prewarm_languages=()) -> FastAPI:
    if role not in {"asr", "tts"} or len(api_key) < 32:
        raise ValueError("Explicit worker role and independent service credential required")
    if os.environ.get("ENVIRONMENT") not in {"sandbox", "test"}:
        raise RuntimeError("Experimental worker is Sandbox only")
    if tts_backend not in {"chatterbox", "kokoro"}:
        raise ValueError("Unknown speech backend")
    artifact = PARAKEET if role == "asr" else (KOKORO if tts_backend == "kokoro" else CHATTERBOX)
    busy = asyncio.Lock()
    journal = SpeechJobJournal(journal_path)
    if any(language_code(locale) not in artifact.locales for locale in prewarm_languages):
        raise ValueError("Unsupported prewarming language")

    @asynccontextmanager
    async def lifespan(app):
        app.state.engine = engine or await asyncio.to_thread(
            ParakeetEngine if role == "asr" else (KokoroEngine if tts_backend == "kokoro" else ChatterboxEngine),
            cache_dir=cache_dir, device=device,
        )
        for locale in prewarm_languages:
            if role == "tts":
                await run_model(app.state.engine.synthesize, "Avenqo.", locale)
            else:
                from backend.app.voice.open_speech_catalog import pcm_wav
                await run_model(app.state.engine.transcribe, pcm_wav(b"\0\0" * 8000, 16000), "auto")
                break  # Automatic-language ASR needs only one synthetic warmup.
        yield
        app.state.engine = None

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.usage_journal = journal

    class BoundedBody:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http":
                return await self.app(scope, receive, send)
            limit = 16_384 if scope.get("path") == "/v1/audio/speech" else 3_000_000
            total = 0

            async def bounded_receive():
                nonlocal total
                message = await receive()
                total += len(message.get("body", b""))
                if total > limit:
                    raise HTTPException(413, "Speech request too large")
                return message

            await self.app(scope, bounded_receive, send)

    app.add_middleware(BoundedBody)

    async def authorized(request: Request):
        supplied = request.headers.get("authorization", "")
        if not hmac.compare_digest(supplied.encode(), ("Bearer " + api_key).encode()):
            raise HTTPException(401, "Speech worker authentication required")

    async def run_model(function, *args, job_id=None):
        if journal.has_unknown() or getattr(app.state, "usage_fault", False):
            raise HTTPException(503, "Usage reconciliation required")
        if busy.locked():
            raise HTTPException(429, "Speech worker busy", headers={"Retry-After": "1"})
        await busy.acquire()
        job_id = job_id or str(uuid4())
        try:
            journal.start(job_id, artifact, role)
        except (SpeechJobConflict, ValueError):
            busy.release()
            raise HTTPException(409, "Job unavailable; reconcile usage receipt before retry") from None
        except Exception:
            busy.release()
            app.state.usage_fault = True
            raise HTTPException(503, "Durable usage accounting unavailable") from None
        started = time.perf_counter()
        task = asyncio.create_task(asyncio.to_thread(function, *args))
        # A disconnected HTTP client does not stop a CUDA kernel. Keep the GPU slot
        # occupied until inference actually completes; never start overlapping work.
        def completed(finished):
            try:
                status = "failed" if finished.cancelled() or finished.exception() else "completed"
                journal.finish(job_id, time.perf_counter() - started, status)
            except Exception:
                # Preserve the running/unknown receipt and block new work if
                # durable accounting fails. Never silently settle it as zero.
                app.state.usage_fault = True
            finally:
                busy.release()
        task.add_done_callback(completed)
        return await asyncio.shield(task)

    @app.get("/health", dependencies=[Depends(authorized)])
    async def health(request: Request):
        return {"status": "unavailable" if journal.has_unknown() or getattr(app.state, "usage_fault", False) else "ready", "role": role, "model": artifact.model_id,
                "revision": artifact.revision, "license": artifact.license_id,
                "languages": sorted(artifact.locales), "native_streaming": False,
                "generation": "utterance_batch", "retains_audio": False,
                "retains_transcripts": False, "durable_usage_journal": journal.durable,
                "prewarmed_languages": list(prewarm_languages)}

    @app.get("/v1/usage/{job_id}", dependencies=[Depends(authorized)])
    async def usage(job_id: str):
        receipt = journal.receipt(job_id)
        if receipt is None:
            raise HTTPException(404, "Usage receipt unavailable")
        return receipt

    @app.post("/v1/audio/transcriptions", dependencies=[Depends(authorized)])
    async def transcribe(request: Request):
        if getattr(app.state, "usage_fault", False):
            raise HTTPException(503, "Usage accounting unavailable")
        if role != "asr":
            raise HTTPException(409, "Not an ASR worker")
        if len(request.headers.get("content-length", "0")) > 10:
            raise HTTPException(413, "Audio too large")
        if not request.headers.get("content-length", "0").isdigit():
            raise HTTPException(400, "Invalid content length")
        if int(request.headers.get("content-length", "0")) > 3_000_000:
            raise HTTPException(413, "Audio too large")
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 3_000_000:
                raise HTTPException(413, "Audio too large")
        started = time.perf_counter()
        try:
            job_id = request.headers.get("x-speech-job-id") or str(uuid4())
            result = await run_model(request.app.state.engine.transcribe, bytes(body), "auto", job_id=job_id)
        except ValueError:
            raise HTTPException(422, "Invalid bounded audio") from None
        except HTTPException:
            raise
        except Exception as exc:
            request.app.state.last_failure_class = type(exc).__name__
            raise HTTPException(503, "Speech inference unavailable") from None
        return {**result, "provider": "open_speech", "model": artifact.model_id,
                "revision": artifact.revision, "request_id": job_id,
                "inference_seconds": time.perf_counter() - started}

    @app.post("/v1/audio/speech", dependencies=[Depends(authorized)])
    async def synthesize(payload: SpeechInput, request: Request):
        if getattr(app.state, "usage_fault", False):
            raise HTTPException(503, "Usage accounting unavailable")
        if role != "tts":
            raise HTTPException(409, "Not a TTS worker")
        if language_code(payload.language) not in artifact.locales:
            raise HTTPException(422, "Unsupported speech language")
        started = time.perf_counter()
        try:
            job_id = request.headers.get("x-speech-job-id") or str(uuid4())
            audio = await run_model(request.app.state.engine.synthesize, payload.input, payload.language, job_id=job_id)
        except ValueError:
            raise HTTPException(422, "Invalid bounded speech") from None
        except HTTPException:
            raise
        except Exception as exc:
            request.app.state.last_failure_class = type(exc).__name__
            raise HTTPException(503, "Speech inference unavailable") from None
        return Response(audio, media_type="application/octet-stream", headers={
            "X-Audio-Sample-Rate": "24000", "X-Audio-Encoding": "pcm_s16le",
            "X-Audio-Seconds": str(len(audio) / 48000),
            "X-Inference-Seconds": str(time.perf_counter() - started),
            "X-Speech-Request-Id": job_id,
        })

    return app


def from_environment():
    if not os.environ.get("VOICE_SPEECH_USAGE_DB") or os.environ["VOICE_SPEECH_USAGE_DB"] == ":memory:":
        raise RuntimeError("Independent durable worker usage journal required")
    return create_app(role=os.environ["VOICE_SPEECH_ROLE"],
                      api_key=os.environ["VOICE_SPEECH_API_KEY"],
                      cache_dir=os.environ.get("HF_HUB_CACHE"),
                      tts_backend=os.environ.get("VOICE_SPEECH_TTS_BACKEND", "chatterbox"),
                      journal_path=os.environ["VOICE_SPEECH_USAGE_DB"],
                      prewarm_languages=tuple(filter(None, os.environ.get("VOICE_SPEECH_PREWARM_LANGUAGES", "").split(","))),
                      device=os.environ.get("VOICE_SPEECH_DEVICE", "cuda"))
