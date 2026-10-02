# Avenqo AI Central Voice — Phase 6

Phase 6 adds a Voice Central session path without changing the existing Retell/Telnyx inbound integration.

## Path

When OpenAI realtime is configured, the browser sends 24 kHz PCM frames through the authenticated Voice session WebSocket. OpenAI provides VAD and final transcription, but automatic replies and provider tools are disabled. Only completed transcripts enter AI Central, which selects the Universal Agent Registry agent, enforces tool permissions and confirmation challenges, and settles usage through its existing request ID. The authorized answer is sent back to the realtime adapter for audio rendering and streamed to browser playback. The provider never executes Avenqo tools.

Browser authentication uses a 30-second, session-bound WebSocket ticket obtained with the existing HttpOnly-cookie-authenticated HTTP route. The ticket is sent as a WebSocket subprotocol, not in a URL. Membership and session validity are checked again on the socket and before executing a finalized transcript. Duplicate provider item IDs and browser audio sequence numbers are ignored within each connection; AI Central request IDs are derived from provider item IDs for retry-safe settlement. Transport disconnects leave the Voice session active for reconnect; explicit close/end terminates it.

On barge-in the server cancels the current provider response and clears provider output. The browser closes its playback context, dropping queued audio. Interim and interrupted transcripts are never passed to AI Central. Provider outage, missing configuration, or unsupported locale uses browser SpeechRecognition and the authenticated `/api/v1/ai/voice/sessions/{id}/turn` endpoint instead.

Voice sessions are tenant/user/conversation scoped. They reuse AI Central request IDs, Phase 2 authorization, Phase 3 routing, Phase 4 credit reservation/settlement, and Phase 5 locale continuity. Raw audio is not stored.

## Provider registry

Retell remains an external inbound provider and is not claimed as available for browser Voice Central. The session response reports realtime only when all OpenAI Voice provider settings and credentials are present and its locale resolves in the canonical 44-locale catalog. Otherwise it reports browser speech fallback.

## External configuration required

Live provider Voice still requires provider credentials, supported locale/voice metadata, billing, browser/mobile permissions and provider dashboard configuration. The realtime adapter and WebSocket tests use mocks; an actual provider audio round trip has not been run. Flutter continues to use the same Voice session and authenticated text-turn contract; native microphone capture and playback require device/platform integration and are not claimed as live-tested. No production audio, phone call, SMS or appointment was created by these tests.
