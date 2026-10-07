# Avenqo AI Central Voice — Phase 6

Phase 6 adds a Voice Central session path without changing the existing Retell/Telnyx inbound integration.

## Native plan-aware Voice

Voice is an Avenqo module and registry agent, not a separate AI platform. The shared `TenantCapabilityContext` derives its plan/status from Billing, modules from entitlements, agents from the existing registry, permissions from active membership, credits from the existing ledger and sources from server-side selection. `GET /api/v1/voice/capabilities` requires authenticated active membership, AI permission and an active subscription.

Browser Voice requires an active Voice module. WebSockets revalidate membership, subscription and module access before processing turns. Phone business requests use `/api/v1/voice/tools/central_ai` only after verified owner/employee identity; customer/unknown callers cannot access internal analytics, invoices or subscriptions. Existing customer appointment tools retain ownership and confirmation rules.

The `get_subscription_options` tool reads the canonical plan/module catalog only. It cannot change Billing, Stripe or modules. The authenticated `/api/v1/ai/central/conversations/{id}/sms` adapter shares the Web handler; this does not certify a live carrier SMS transport. Phone, browser and SMS-adapter business requests use the same tools, metrics and freshness services.

The Voice page shows plan/agents, usage and recent calls, generic international number search and explicit number selection. Search/selection never purchases a number. The language matrix distinguishes UI, STT, LLM, TTS and live audio validation; unverified dimensions remain unknown and no locale is currently certified as fully validated audio.

## Path

When OpenAI realtime is configured, the browser sends 24 kHz PCM frames through the authenticated Voice session WebSocket. OpenAI provides VAD and final transcription, but automatic replies and provider tools are disabled. Only completed transcripts enter AI Central, which selects the Universal Agent Registry agent, enforces tool permissions and confirmation challenges, and settles usage through its existing request ID. The authorized answer is sent back to the realtime adapter for audio rendering and streamed to browser playback. The provider never executes Avenqo tools.

Browser authentication uses a 30-second, session-bound WebSocket ticket obtained with the existing HttpOnly-cookie-authenticated HTTP route. The ticket is sent as a WebSocket subprotocol, not in a URL. Membership and session validity are checked again on the socket and before executing a finalized transcript. Duplicate provider item IDs and browser audio sequence numbers are ignored within each connection; AI Central request IDs are derived from provider item IDs for retry-safe settlement. Transport disconnects leave the Voice session active for reconnect; explicit close/end terminates it.

On barge-in the server cancels the current provider response and clears provider output. The browser closes its playback context, dropping queued audio. Interim and interrupted transcripts are never passed to AI Central. Provider outage, missing configuration, or unsupported locale uses browser SpeechRecognition and the authenticated `/api/v1/ai/voice/sessions/{id}/turn` endpoint instead.

Voice sessions are tenant/user/conversation scoped. They reuse AI Central request IDs, Phase 2 authorization, Phase 3 routing, Phase 4 credit reservation/settlement, and Phase 5 locale continuity. Raw audio is not stored.

## Provider registry

Retell remains an external inbound provider and is not claimed as available for browser Voice Central. The session response reports realtime only when all OpenAI Voice provider settings and credentials are present and its locale is explicitly included in `VOICE_REALTIME_SUPPORTED_LOCALES`. Membership in the canonical UI catalog is not audio evidence. Otherwise it reports browser speech/text fallback.

## Experimental Telnyx Media Transport

The local media prototype is disabled by default (`TELNYX_MEDIA_ENABLED=false`
and `TELNYX_MEDIA_INBOUND_ENABLED=false`). With both flags explicitly enabled in
local fixtures, the signed inbound webhook resolves the tenant's owned active
number/configuration, validates the configured Voice connection and audio locale,
answers, and starts media only after `call.answered`. The default Retell path and
production configuration remain unchanged. No real call has been performed.

`/api/v1/voice/telnyx/media/{call_id}` accepts Telnyx `start`, `media`, `dtmf`,
and `stop` frames. A trusted backend must first issue a 60-second single-use
`client_state`, bound to an active call, tenant, owned number and Voice connection.
Staff tickets additionally bind to the verified authentication epoch. Public
tickets authorize transport only, never internal tools. Browser JWTs are not used.
Only one media connection per call is allowed; normal disconnect releases its
reservation. A process crash requires stale-reservation reconciliation before
reconnecting the same call. UNKNOWN/customer callers receive the configured
tenant greeting and allowlisted public hours/services or appointment-request
information without a mandatory owner PIN. No booking is asserted or performed.
Personal data and appointment mutations require customer identity verification.

The anonymous conversation is the tenant's `VoiceCall`, not an invented owner
`AIConversation`. Anonymous audio usage is tenant/call-scoped with null user and
conversation IDs. An internal `AIConversation` is created only after verified
staff authentication, with current role permissions and active agent entitlements.

An internal-access request quarantines audio before the keypad-only prompt.
After Telnyx acknowledges the prompt's playback mark, the existing gather command
starts. Signed `call.gather.ended` digits go directly to `VoiceCallerAuth`/Argon2,
never through a transcript, Central AI, or TTS. The bridge polls only safe outcome
state, clears buffers, announces success/refusal, and resumes after quarantine.
Digit exclusion has been verified with simulated frames, not a real carrier call.
Caller ID only hints which tenant principal to check; it never establishes identity.
Staff PINs can only be created/changed through authenticated Voice security, with
ASCII 6–12 digits, nontrivial-pattern rejection, Argon2 hashes, attempt limits,
lockout, audit and expiring call-bound sessions. There is no oral PIN enrollment.

PCMU mono 8 kHz frames are converted to/from the existing OpenAI PCM 24 kHz
adapter with Python 3.11 `audioop`. Other codecs and missing/out-of-order chunks
fail closed; a production jitter/reordering policy remains necessary. Final
transcriptions use the existing Central AI registry and Voice usage ledger.
Barge-in clears queued audio without cancelling a running Central AI operation.
DTMF frames never become transcript input: they clear input/output and quarantine
audio during authentication. In-band tone removal is not certified.

Customer identity verification and booking completion, crash recovery, RTP
reordering, carrier-side buffer behavior, latency, codecs and supported spoken
locales still need dedicated validation before enabling this prototype.
No paid call, production setting change or real provider audio validation is
implied by the mocked endpoint and SDK tests.

## External configuration required

Live provider Voice still requires provider credentials, supported locale/voice metadata, billing, browser/mobile permissions and provider dashboard configuration. The realtime adapter and WebSocket tests use mocks; an actual provider audio round trip has not been run. Flutter continues to use the same Voice session and authenticated text-turn contract; native microphone capture and playback require device/platform integration and are not claimed as live-tested. No production audio, phone call, SMS or appointment was created by these tests.
