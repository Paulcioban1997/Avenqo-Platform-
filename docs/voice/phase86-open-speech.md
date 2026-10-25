# Phase 8.6 — open speech integration, 2026-10-20

**Verdict: LIVE_VOICE_HF_PENDING.** Real local neural inference has succeeded.
HF telephone inference is not activated. No paid call, hosted GPU, number
purchase, production change or claim of French Canadian certification.

## Recovered state and actual changes

Recovered the uncommitted speech lab from branch
`codex/avenqo-voice2-open-speech-sandbox`, based on
`7fa5ffab488f4cd34c013e1b6969a54c1753de27`. Remote `promotion/sandbox` and the
active Sandbox API still matched that baseline at recovery. The baseline CI
[39336447008](https://github.com/Paulcioban1997/Avenqo-Platform-/actions/runs/39336447008)
was green. No assumption was made that the new lab had already been deployed.

The existing phone path uses OpenAI Realtime, not the separately configured
batch TTS model. The saved company voice `alloy` overrides global `marin`.
The current Central turn is completed before speech synthesis. Those are
configuration/latency findings, not proof that a particular voice causes the
founder's perceived quality problem. No baseline paid comparison was run.

Implemented:

- `backend/app/voice/open_speech_catalog.py`: exact reviewed model revisions.
- `open_speech.py`: authenticated bounded HTTP client and event adapter,
  per-session VAD/input/output state, language checks, barge-in cancellation.
  The adapter never owns a business LLM or executes tools.
- `open_speech_runtime.py` and Settings: disabled-by-default, Sandbox-only,
  server-side company allowlist for the lab; explicit telephone readiness block.
- `audio_codec.py`: extracted existing Telnyx codec without changing its
  algorithm; old imports remain available from `telnyx_media.py`.
- `telnyx_media.py`: existing provider passed through the guarded selection
  boundary, including long-call rotation; no new live HF provider selected.
- `services/voice_speech/`: isolated real Parakeet, Chatterbox V3 and Kokoro
  workers, independent authentication, no DB/tools/tenant identity, bounded
  payloads and one inference at a time. Disconnects do not release a still-busy
  GPU slot prematurely.
- Three preparation/measurement scripts, CI contract tests and evidence JSON.
  A regression fix purges already-queued output after interruption and queued
  input transcriptions after PIN/input clearing.

No migration, company-data write or new Railway variable is required by this
code delivery. Existing Phase 8.5 permissions and business tools are preserved.

## Selection and compared alternatives

**Selected experimental architecture: Parakeet ASR → existing Avenqo Central
and authorized tools → Kokoro TTS.** It is a modular candidate, not a certified
commercial replacement. Chatterbox remains a tested comparator. OpenAI remains
the actual telephone provider and fallback. No model has proved globally best
or superior in a blind French Canadian telephone listening test.

| Technology | Exact reviewed artifact/version | License | Decision / evidence |
|---|---|---|---|
| [Parakeet](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) | `nvidia/parakeet-tdt-0.6b-v3@541d1f99c6b0c3cd0b11a95167540bb8edefd82b` | CC-BY-4.0 | Selected ASR candidate; actual GPU inference; 25 languages include FR/EN/RO; no QC certification |
| [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M) | `hexgrad/Kokoro-82M@f3ff3571791e39611d31c381e3a41a3af07b4987`, v1.0, Python 0.9.4 | Apache-2.0 | Selected TTS candidate; actual CPU/GPU inference; reviewed voices FR `ff_siwis`, EN `af_heart`, ES `ef_dora`; French voice is Swiss, not Quebec |
| [Chatterbox](https://huggingface.co/ResembleAI/chatterbox) | `ResembleAI/chatterbox@5bb1f6ee58e50c3b8d408bc82a6d3740c2db6e18`, explicit `t3_mtl23ls_v3.safetensors` | MIT | Actual GPU comparator; V3 explicitly selected because default upstream was V2; 23 languages, no RO; watermark preserved; latency unsuitable in this trial |
| [Whisper turbo](https://huggingface.co/openai/whisper-large-v3-turbo) | `openai/whisper-large-v3-turbo@41f01f3fe87f28c78e2fbf8b568835947dd65ed9` | MIT | Multilingual alternative; not locally benchmarked here; no native bidirectional agent or QC certification |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | code `9e472ae9de8bb374552f531f752654554b76b2d6`; converted `mobiuslabsgmbh/faster-whisper-large-v3-turbo@0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf` | MIT | CTranslate2 supports CPU/GPU INT8; publisher comparison is not our benchmark. Current GPU runtime needs CUDA 12 / cuDNN 9. Not installed or selected in this phase |
| [Moshi](https://github.com/kyutai-labs/moshi) | `kyutai/moshiko-pytorch-bf16@2bfc9ae6e89079a5cc7ed2a68436010d91a3d289` | Python MIT / Rust Apache-2.0 / weights CC-BY-4.0 | Complete speech-to-speech, English 7B; publisher latency not reproduced; not selected as independent business brain |
| [PersonaPlex](https://huggingface.co/nvidia/personaplex-7b-v1) | `nvidia/personaplex-7b-v1@fdaf4090a61cb315c138a1faee287ffd6c716309` | NVIDIA Open Model License, gated | English; terms/access and FR support unsuitable for immediate default; no gate bypass or inference claim |
| [Kyutai TTS](https://huggingface.co/kyutai/tts-1.6b-en_fr) | `kyutai/tts-1.6b-en_fr@f65439609986c392cb12df63938abcc550c3fb15` | CC-BY-4.0 | Streaming FR/EN alternative, not RO; no local benchmark |
| [Unmute](https://github.com/kyutai-labs/unmute) | Reviewed official framework | MIT | Modular streaming option; documented >=16 GB GPU and Linux/WSL; available native Windows 8 GB lab does not meet that deployment profile |
| [Pocket TTS](https://huggingface.co/kyutai/pocket-tts) | `kyutai/pocket-tts@a0172fa05a0725a745539c88e4b58f1ee19cb9a7` | CC-BY-4.0, gated | FR/EN/ES among supported languages, no RO; publisher CPU latency not reproduced; gated terms require human action |
| [HF speech-to-speech](https://github.com/huggingface/speech-to-speech) | code `0ed1bb95bd335aa89bb7c172b6a347b6dae596f8` | Apache-2.0 | Complete modular reference, including Parakeet; default independent LLM must not replace Central. Reviewed, not deployed |
| [Pipecat](https://github.com/pipecat-ai/pipecat) | code `5558d26dca636e09b768cfb7f70b87e259f7c188`, package 1.13.0 | BSD-2-Clause | Telnyx/orchestration alternative; not installed. Replacing the existing authorized bridge adds risk without a measured benefit yet |

Weights are downloaded only to ignored local scratch storage, pinned and
hashed. Licenses require their respective notices/attribution; no claim that
all models share one license or that gated terms have been accepted.

## Measured evidence, not projections

Public human ASR data: [Google FLEURS](https://huggingface.co/datasets/google/fleurs),
revision `70bb2e84b976b7e960aa89f1c648e09c59f894dd`, CC-BY-4.0.
One test utterance each from `fr_fr`, `en_us`, `ro_ro`, linked to the supplied
human transcript. Converted PCM32 to PCM16, no company recordings. References,
transcripts, timings and hashes are in `evidence/phase86/`.

Windows lab, RTX 5070 Laptop 8 GB, Torch 2.11.0+cu128. Measurements exercise real
models via the worker's in-process ASGI HTTP application. They exclude physical
networking, Central inference, Telnyx, provider charges and audio listening.

| Actual inference | Time / quality | Memory / caveat |
|---|---|---|
| Parakeet FR, 10.2 s clip | 0.777 s, WER 0% | Peak CUDA allocated 2,470 MiB; one France-French clip |
| Parakeet EN, 10.56 s | 0.205 s, WER 10.53% | Single clip, not population accuracy |
| Parakeet RO, 6.3 s | 0.212 s, WER 26.67% | Includes a substantive recognition error; not certified |
| Chatterbox V3 GPU FR | First audio 19.912 s cold, 4.447 s next phrase | Peak CUDA allocated 3,229 MiB; fails target latency |
| Chatterbox GPU EN / ES | 4.194 / 3.544 s | Utterance-batch TTS, not native streaming |
| Kokoro CPU FR | 2.086 / 2.165 s | Four CPU threads; EN first-use 13.629 s, ES 1.567 s |
| Kokoro GPU FR | 2.771 s first phrase; **0.108 s next phrase** | Peak CUDA allocated 675 MiB; different phrases, not a statistical p95 |
| Kokoro GPU EN / ES | 1.456 / 0.222 s | First-use pipelines; no human naturalness score |

Model loads: Parakeet 20.295 s, Chatterbox 48.161 s, Kokoro CPU 40.795 s / GPU
32.752 s, excluding some Python import time. Peak allocated GPU is not total
process/reserved/device memory. Combined resident capacity and parallel neural
calls were not benchmarked. Worker overload returns 429 rather than overlapping
unbounded GPU work. These few samples do not establish p95, 250-company call
capacity or reliable end-to-end <1.5 seconds. Audio was also encoded through the
unchanged Telnyx 8 kHz G.711 codec, but never sent over a phone call.

## Security and company regression boundary

The speech worker has no business profile, company ID, API tool registry or
data access. Existing server-resolved tenant context, module entitlements,
personal authentication, roles and explicit Voice permissions remain in Central.
A routing PIN is still insufficient for private sales analytics. The lab
factory additionally rejects production, disabled flags and unlisted tenants.
No per-tenant model state or reference voice upload is accepted.

Produits_Ero's existing Retail permissions and historical Superstore source
are preserved: 9,994 rows / 5,009 orders / 1,862 products, 2014–2017. Stock is
unknown, not zero. Native dataset currency remains unverified; no conversion.
The previously detected CRM catalogue mismatch still prevents fabricated
medical/service bookings. No records were edited to make a test pass.

Contract tests use explicit fake engines. Actual neural tests are the separate
measurements above. Business/tenant regression tests execute existing services
without paid LLM calls. Acceptance scenarios to retain before real activation:

| Scenario group | Cases / required assertions |
|---|---|
| Public retail | Products; unknown stock; private revenue denied; routing PIN does not elevate |
| Authenticated retail | Historical best sellers; 2014–2017 revenue; missing current period; tenant B denied |
| CRM | Unsupported physiotherapy denied; catalogue mismatch denied; verified service only; no false booking confirmation |
| Mixed modules | Enabled module only; disabled module denied; explicit action permission required; employee role checked |
| Conversation | Follow-up after a tool; topic switch; barge-in purges stale audio; PIN clear purges queued transcript |

These are 20 acceptance cases, not 20 completed real telephone calls.
Automated authorization/transport cases are CI-covered; natural multi-turn
speech, noisy end-of-turn detection, physical barge-in and accent quality
remain live-test pending. Energy VAD is experimental, with 500 ms silence and
30 s utterance chunks; this is not a fixed whole-call duration limit.

## Costs and hosting blockers

No GPU is exposed by the current Railway Sandbox API. The local laptop is a
measurement rig, not an always-on secure inference service. No paid hosting was
created. API delivery therefore ships the gated code only, with OpenAI retained.

Published [HF dedicated endpoint pricing](https://huggingface.co/docs/inference-endpoints/pricing)
lists AWS L4 24 GB at USD 0.80/hour. At one fully occupied concurrent stream,
that is about USD 0.01333/minute GPU alone, or USD 584/month if continuously
running for 730 hours. At 10% useful utilization it becomes about USD 0.13333
per useful minute. These are allocation examples, not measured capacity or a
quote for a configured endpoint.

[Telnyx pricing](https://telnyx.com/pricing/voice-api) lists Voice API USD
0.002/minute plus SIP trunking, and media streaming USD 0.0035/minute. The
illustrative fully utilized one-stream subtotal is USD 0.01883/minute **before**
SIP, Central LLM, storage, idle time, other infrastructure and taxes. No CAD
conversion or guaranteed cumulative CAD 2 cap is asserted. Managed Telnyx
model prices are not assumed to be this exact self-hosted checkpoint.

The current Voice ledger prices OpenAI events. HF inference, including GPU work
that completes after cancellation, requires a measured allocation/rate card and
settlement design before live promotion. Missing cost data must not become
zero/free usage. Automatic mid-turn fallback would risk tool replay or duplicate
charges, so no such replay is implemented. Existing OpenAI behavior is retained
at initial phone-provider selection. Actual OpenAI costs still require observed
usage; see [official pricing](https://developers.openai.com/api/docs/pricing).

## Delivery, rollback and next telephone test

Commit verified code to `promotion/sandbox` only. Existing full CI must pass
before its Railway Sandbox source deploys. No new model dependency enters the
API requirements, no new migration is introduced, and Alembic must remain
`0067_resolve_voice_call_tenant_owner`. Production tracks `main`; Vercel already
disables automatic `promotion/sandbox` previews. Never apply unrelated staged
changes. Record actual post-deploy SHA, health and logs separately; this document
does not assert that a deployment has succeeded before it happens.

Rollback: leave lab disabled (default), retain OpenAI provider, and if the API
release regresses, use the prior Sandbox deployment
`f3577ce4-7726-4e58-8291-7ccd61d18416` / `7fa5ffa` after the required approval.
No downgrade, data restore, secret rotation or number rerouting is required.

Before a **HF** telephone acceptance test:

1. Approve secure inference hosting and its budget, or satisfy any gated model
   terms personally. Configure independent worker credentials in the secret
   manager, prewarm languages and verify pinned authenticated readiness.
2. Complete cancellation-aware metering, load/noise trials and a listening
   comparison of French voices. Certify latency and caller privacy; do not
   simply flip the lab flag to bypass the telephone block.
3. Configure the founder's personal phone credential/NIP in Avenqo (not in chat)
   for private analytics. Resolve/approve genuine company CRM services before
   a booking test; do not invent a clinical service for Produits_Ero.
4. Request distinct authorization for paid audio and verify number
   `+14386075438` still routes to Sandbox connection `3069110156336826311`.
   Save the initial production return connection `3064471945866118148`.
5. Founder calls, asks in French about products, historical best sellers and
   unknown stock; public/private denial must differ correctly. Test an
   interruption, follow-up and authorized configured appointment. Check CRM
   and Google event identity/status, not merely an HTTP 200.
6. Observe actual Telnyx/OpenAI/inference usage and stop on wrong tenant,
   fabricated data, dead audio, provider error or budget threshold. An initial
   short test is not a permanent 90-second commercial limit. A 60-minute trial
   requires a separate explicit cost estimate and authorization.

Until those actual telephone assertions are observed, the verdict remains
**LIVE_VOICE_HF_PENDING**.
