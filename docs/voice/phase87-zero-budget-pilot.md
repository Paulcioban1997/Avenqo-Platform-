# Phase 8.7 — zero-additional-infrastructure-budget preparation

**LIVE_VOICE_HF_PENDING.** The founder's budget override supersedes the earlier
request to consider paid GPU hosting. No paid GPU, endpoint, recurring service,
phone call, number or customer charge is authorized. No public tunnel to the
developer computer. OpenAI remains the current telephone provider. HF telephone
selection stays blocked. Production remains outside the scope.

## Recovered baseline and focused work

Recovered clean `promotion/sandbox` at
`afa32619e0e0ea0562a5984920237a07fa875ebc`, matching the remote. Reused Phase 8.6
models, downloads, 212 local regression results, green full CI, active Sandbox
and measurements. No repeated model survey, installation, paid-provider shopping
or full data audit. Exact reviewed pins remain:

- ASR `nvidia/parakeet-tdt-0.6b-v3@541d1f99c6b0c3cd0b11a95167540bb8edefd82b`, CC-BY-4.0.
- TTS `hexgrad/Kokoro-82M@f3ff3571791e39611d31c381e3a41a3af07b4987`, Apache-2.0,
  Kokoro v1.0 / library 0.9.4. French voice `ff_siwis` remains Swiss French,
  not a certified Quebec voice. Existing compatible fallback is unchanged.

## Implemented

- `speech_jobs.py`: bounded persistent worker-local SQLite compute journal.
  It stores opaque IDs, model/revision, status and measured inference wall time;
  no company ID, audio, transcript, tool or secret. No active PostgreSQL changes.
- Workers accept `X-Speech-Job-Id`, reserve before inference and finalize even
  after HTTP cancellation. Authenticated receipt retrieval enables reconciliation.
  Duplicate IDs return 409; busy workers return 429. No automatic inference replay.
- Interrupted processes leave unknown work, which blocks new admission. Unknown
  cost never becomes zero. Accounting failures also block readiness/admission.
- Client retains job IDs on cancellation or request failure and blocks further
  inference until explicit receipt reconciliation. Model/role/revision checks
  protect receipt acceptance. No business tool is replayed during reconciliation.
- Server-bound unpaid pilot ledger attributes receipts to a company/call and
  reconciles idempotently with explicit decimal allocation rates. Unknown rates,
  other calls' unregistered receipts and conflicting settlements are refused.
- A zero allocation rate is permitted only for an explicitly unpaid existing
  local experiment. That describes additional provider invoices, not free power,
  total economic cost or a commercial price.
- Optional prewarming completes before readiness; the normal worker process
  requires an independent persistent journal file. One process per journal.
- The existing backend lab factory now refuses non-loopback inference origins.
  The budget override cannot be bypassed simply by enabling a feature flag.

**Accounting limits:** the pilot allocation ledger is an in-memory laboratory
component, not the persistent customer billing/credit ledger. Durable worker
receipts survive a restart, but trusted persistent call-to-job attribution and
live credit settlement are not yet integrated. Kernel wall time is not GPU
utilization, rented-host idle time or an actual supplier invoice. The telephone
readiness gate remains closed for these reasons. No claim of commercially ready
billing, distributed concurrency or a guaranteed cloud spend cap.

## Real CPU inference, no additional hosted service

Reused existing local Python environments and cached weights. No download or
new dependency was required. Public FLEURS test data remains CC-BY-4.0, with the
same pinned provenance as Phase 8.6. Results are in `evidence/phase87/`.

| Real local measurement | Result | Limit |
|---|---|---|
| Parakeet CPU, one French FLEURS clip, 10.2 s | 1.507 s inference/request; WER 0 on this clip | Single France-French clip, not QC certification; excludes live network/LLM |
| Kokoro CPU, French dates/time/Montréal phrase | 2.306 s first audio, 5.175 s generated audio | Warmed local worker; no human naturalness score |
| Kokoro CPU, CAD amount/product/unknown stock | 2.526 s first audio, 7.65 s generated audio | Synthetic business text, no actual company transaction |
| Persistent receipts after both real TTS requests | Completed, positive measured compute times | Actual neural inference; cancellation correctness tested separately with fixtures |

CPU synthesis is feasible locally but these results do not establish satisfactory
real-time telephone latency. The complete response also includes end-of-turn
detection, ASR, Central/tools and telephone transport. No 44-language, p95,
concurrent-call, French Canadian or 60-minute certification is claimed.

## Exact CRM mismatch — no business-data edits

One targeted read-only Sandbox query confirmed that the CRM has active services
`Consultation initiale` and `Suivi de traitement`, whereas Voice's allowlist
contains `Rendez-vous test Sandbox` with no matching canonical CRM service ID.
The intersection is empty. This is a genuine business catalogue inconsistency,
not a reason to weaken matching or permit fabricated medical bookings.

Founder input required: specify what Produits_Ero actually books, the real
service name, duration and relevant employee/calendar. Configure that legitimate
CRM service and select its canonical ID in Voice. No automatic rename, service
creation, permission expansion or deletion was performed. Existing synthetic
CRM fixtures cover valid booking and unsupported-service refusal without
writing any live calendar event or changing another company.

## A/B protocol and local setup

Configuration A is the existing OpenAI telephone stack, unchanged and not called
by this phase. Configuration B is the isolated **local** Parakeet → existing
authorized Central/tool boundary → Kokoro laboratory adapter. No independent
voice LLM or business tool registry is introduced. The B telephone selector
remains unavailable; a lab feature flag alone cannot activate it.

For local-only B testing, run the two existing isolated environments bound to
`127.0.0.1`, ports 9001/9002, with independent secrets entered directly into the
process environment. Set `ENVIRONMENT=sandbox`, the corresponding worker role,
`VOICE_SPEECH_DEVICE=cpu`, pinned cache directory, and separate
`VOICE_SPEECH_USAGE_DB` files. Use `VOICE_SPEECH_PREWARM_LANGUAGES=fr` initially.
No production key or connection is needed. Do not configure Railway loopback
URLs expecting them to reach this computer.

Before a future separately authorized phone A/B, use identical authorized
company context and these utterances for both arms:

1. « Bonjour, que vend votre entreprise ? » — ground products; no invented clinic.
2. « Quels produits se vendaient le mieux entre 2014 et 2017 ? » — private
   analytics denied publicly, permitted only after personal authentication.
3. « Combien en avez-vous en stock ? » — explicitly unknown if unverified.
4. « Et les ventes de cette année ? » — historical data must not become current.
5. Interrupt and switch topic — stop old audio; no duplicate tool execution.
6. « Je veux un rendez-vous de physiothérapie demain à 14 heures. » — refuse
   an unconfigured service; no fabricated booking confirmation.

Keep a per-arm worksheet: model/revision, exact prompt, expected authorized
facts, reference transcript, WER, end-of-turn→first-audio time, interruptions,
tool-call count, factual errors, human naturalness/accent score and measured
provider usage. Separate cold and prewarmed trials. Use multiple matched trials
before computing p50/p95 or declaring a winner. Do not export private company
data unnecessarily into recordings. Personal NIP/password stays in Avenqo.

## Budget, deployment and rollback

Authorized **additional hosted infrastructure spend: 0**. Authorized new
telephone spend: 0. No paid provisioning or calls performed. Existing laptop
resources are used locally; current Railway subscription/usage is not described
as globally free. Running models on its existing API could add billed CPU/RAM
usage, so that has not been enabled. No cloud provider is recommended for
activation under this override. Unavoidable future telephone, hosted inference
or extra resource charges must be disclosed and separately approved first.

Commit the safe code to `promotion/sandbox`, run full CI once and allow the
authorized existing Sandbox deployment only. No new migration: expected Alembic
head remains `0067_resolve_voice_call_tenant_owner`. No model dependencies or
weights are added to the API image; worker code runs locally only.

After deployment, verify actual SHA, health/readiness, flags and routing.
Retain `VOICE_OPEN_SPEECH_LAB_ENABLED=false` on Railway. Rollback uses the prior
Sandbox deployment `42e9e548-4d1e-4db3-afbd-f03e0d7d18f3` / `afa3261`, after the
required approval, without DB downgrade or data restore. No number rerouting.

The 3–5 minute telephone pilot, A/B audio comparison and long-call certification
are **not authorized or performed**. Until the founder verifies an actual HF
telephone call, the verdict remains **LIVE_VOICE_HF_PENDING**.
