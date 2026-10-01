# Avenqo AI Central Voice — Phase 6

Phase 6 adds a provider-neutral Voice Central session path without changing the existing Retell/Telnyx inbound integration.

## Path

Browser or Flutter speech adapter -> canonical transcript -> `/api/v1/ai/voice/sessions/{id}/turn` -> AI Central -> Universal Agent Registry -> existing authorized tools -> text response.

Voice sessions are tenant/user/conversation scoped. They reuse AI Central request IDs, Phase 2 authorization, Phase 3 routing, Phase 4 credit reservation/settlement, and Phase 5 locale continuity. Raw audio is not stored.

## Provider registry

`backend/app/voice/central.py` exposes configured capabilities for realtime audio, STT, TTS, streaming and interruption. Retell remains an external inbound provider and is not claimed as available for browser Voice Central unless configured. The browser SpeechRecognition adapter provides transcript input; TTS/realtime are reported as `external_configuration_required` until a provider is configured.

## External configuration required

Live provider Voice requires provider credentials, supported locale/voice metadata, billing, browser/mobile permissions and provider dashboard configuration. Tests use registry metadata and mocks; no production audio, phone call, SMS, appointment or credit mutation is created.
