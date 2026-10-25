# Isolated speech lab — Phase 8.6

This worker performs real local ASR or TTS. It has no database, business tools,
tenant identity, telephone routing or independent LLM. Only Avenqo Central may
authorize and execute business actions. It is not a replacement business agent.

## Deployment boundary

The normal API image does **not** install these model dependencies or download
weights. `ENVIRONMENT=sandbox` is mandatory for the standalone worker. Its
independent `VOICE_SPEECH_API_KEY` must be generated in the secret manager and
must not reuse an Avenqo, OpenAI, Telnyx or connector key. Bind to loopback for a
local experiment; remotely, use authenticated HTTPS and restrict network access.
Do not expose the plaintext worker directly to the Internet.

Run two separate Python 3.11 environments. The tested lab reused Torch
2.11.0+cu128 / torchaudio 2.11.0 on a local RTX 5070 Laptop 8 GB.
Model libraries must remain separate because their Transformers dependencies
conflict. No hosted GPU has been provisioned or authorized.

| Worker | Tested model runtime |
|---|---|
| Parakeet | transformers 5.20.2, soundfile 0.13.1, librosa 0.11.0 |
| Kokoro | kokoro 0.9.4, misaki 0.9.4, espeakng-loader 0.2.4, phonemizer-fork 3.3.2 |
| Chatterbox comparator | source `5de7a54aa4e5e2baadb0182dde554908b48b85c2`, transformers 5.2.0, numpy 1.26.4, diffusers 0.29.0, resemble-perth 1.0.1 |

HTTP runtime tested: FastAPI 0.136.3, uvicorn 0.34.3, httpx 0.28.1,
Pydantic 2.13.4. These are **observed lab versions**, not a vendor-certified
production lock. In particular, Chatterbox upstream pins Torch 2.6 and
safetensors 0.5.3; our experimental Torch 2.11 / safetensors 0.8 overrides
worked, but do not pass upstream dependency conformance. Do not deploy that
environment commercially as-is.

Prepare reviewed, pinned weights explicitly (never in an API request):

```powershell
python scripts/voice_speech_prepare.py --role asr --transport urllib --cache-dir scratch/voice2-model-cache --proof scratch/asr-artifacts.json
python scripts/voice_speech_prepare.py --role tts --tts-backend kokoro --transport urllib --cache-dir scratch/voice2-model-cache --proof scratch/tts-artifacts.json
```

Set these directly in the worker process environment, not in Git:

| Variable | Purpose |
|---|---|
| `ENVIRONMENT` | `sandbox` |
| `VOICE_SPEECH_ROLE` | `asr` or `tts` |
| `VOICE_SPEECH_API_KEY` | Independent secret, at least 32 characters |
| `VOICE_SPEECH_DEVICE` | `cuda` for measured Parakeet; `cpu` or `cuda` for Kokoro |
| `VOICE_SPEECH_TTS_BACKEND` | `kokoro` for selected candidate; `chatterbox` comparator |
| `HF_HUB_CACHE` | Absolute path of prepared model cache |
| `VOICE_SPEECH_USAGE_DB` | Separate worker-local persistent SQLite journal, required by the process factory; never the Avenqo application DB |
| `VOICE_SPEECH_PREWARM_LANGUAGES` | Optional explicit `fr,en,es`; warmup must finish before readiness |

From the repository root, start the appropriate environment:

```powershell
python -m uvicorn services.voice_speech.app:from_environment --factory --host 127.0.0.1 --port 9001 --no-access-log
```

Use another process/port (9002) for TTS. No business API credentials are needed.
Readiness verifies exact model/revision/role/language. HTTP bodies and output
audio are bounded; one inference runs at a time per worker. A client disconnect
does not abort a CUDA kernel: the slot remains occupied until it completes.
No application-level audio/transcript persistence is implemented. This does
not make guarantees about the host's swap, diagnostics or external proxy logs.

Kokoro's English pipeline can load its language package at first use; prewarm
each language before a latency trial. Chatterbox additionally fetches the
spacy-pkuseg tokenizer model on first use, outside the HF snapshot. The initial
lab used its user cache. Use a dedicated `PKUSEG_HOME` and audit/prewarm that
asset before attempting an offline deployment. No fully offline startup is
claimed for those pipelines.

## Backend feature gate

`build_lab_adapter()` uses server Settings and a server-resolved company UUID:

- `VOICE_OPEN_SPEECH_LAB_ENABLED=false` by default;
- `VOICE_OPEN_SPEECH_COMPANY_IDS=[]` by default;
- `VOICE_OPEN_SPEECH_ASR_URL` / `VOICE_OPEN_SPEECH_TTS_URL`: private HTTPS
  origins or explicit loopback HTTP for the local lab;
- `VOICE_OPEN_SPEECH_API_KEY`: separate worker credential, hidden from repr;
- `VOICE_OPEN_SPEECH_TTS_BACKEND=kokoro`.

No public endpoint exposes this factory. These variables have **not** been
created on Railway. Do not set them to production credentials or localhost on a
remote API expecting it to reach this laptop.

**Phase 8.7 budget override:** the backend lab factory now allows loopback
workers only; remote inference is refused even with the lab flag. No public
tunnel, paid endpoint or additional infrastructure is authorized. Run one worker
process per usage journal, with an independent journal file for ASR and TTS.
`GET /v1/usage/{opaque-job-uuid}` requires the same independent authentication.
No text/audio is retained in receipts. Duplicate job IDs return 409 rather than
replaying inference; a full journal denies work without deleting old receipts.
After a worker restart, unfinished receipts become unknown and block admission.
They require investigation, not an automatic reset or zero-cost settlement.
Client cancellation retains job IDs for explicit reconciliation. The unpaid
pilot ledger records server-bound company/call allocation estimates, not customer
charges; it does not replace the live Avenqo credit ledger. See the Phase 8.7
report for these accounting limits and the offline A/B protocol.

The Telnyx bridge uses `build_phone_adapter()` and retains the existing OpenAI
provider, including its existing long-call rotation. The lab flag alone cannot
activate HF telephone inference. Live selection remains blocked until hosted
inference, cancellation-aware cost settlement and actual telephone quality are
validated. There is no hidden free/unmetered provider or automatic tool replay.

## Reproducible measurements

```powershell
python scripts/voice_speech_prepare_references.py --help
python scripts/voice_speech_benchmark.py --role asr --cache-dir scratch/voice2-model-cache --output-dir scratch/asr-benchmark --asr-manifest scratch/voice2-human-asr/manifest.json --device cuda
python scripts/voice_speech_benchmark.py --role tts --tts-backend kokoro --cache-dir scratch/voice2-model-cache --output-dir scratch/tts-benchmark --device cpu
```

The benchmark uses actual engines through the worker ASGI HTTP application,
not mocks. It excludes physical networking, Central LLM, Telnyx and human
listening scores. Unit tests intentionally use labeled fixtures and are not
quality evidence. See `docs/voice/phase86-open-speech.md` for measured results,
licenses, public data attribution, limits and next-call acceptance criteria.
