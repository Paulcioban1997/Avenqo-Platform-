# Tenant-owned Voice settings

Every company configures its own reception in the existing Avenqo Voice workspace.
This change does not provision another provider or create a parallel settings DB.

- Business onboarding already owns primary/secondary locales. Incoming calls use
  the server-side tenant profile, not the caller's metadata or Avenqo UI language.
  Secondary languages are explicit allowlists; they do not grant data permissions.
- A new validated noise mode (off, near_field, far_field) is stored in the same
  tenant onboarding JSON. No migration or modification of existing tenant rows.
  This controls incoming background-noise filtering, not output volume in dB.
- Existing customization owns voice ID and speech speed. The telephone socket
  now sends the company's speed and noise setting to Realtime. Session renewal
  uses the same settings snapshot. Changes apply to new calls, not mid-utterance.
- The saved tone guides the Realtime delivery through a bounded style mapping.
  Its actual expressiveness is a provider behavior requiring an audio test.
- The telephone catalog excludes TTS-only voices. The existing provider and model
  remain unchanged. Preview support is not telephone certification.
- Realtime speed is supported up to1.5x. New writes reject higher speeds; legacy
  records above that value are preserved and bounded to1.5x on the telephone path.
- Selecting a new primary language refreshes only an automatically generated
  greeting. Explicit custom greetings are preserved; companies must write those
  messages in their chosen language themselves.
- Voice previews no longer force a French sample. They use the company language,
  localized greeting and selected speed. Preview generation may incur existing
  provider costs when the user requests it; no preview/inference call was made here.
- Existing management permissions and server-derived company IDs remain in force.

Provider contracts checked against official documentation:
https://developers.openai.com/api/reference/resources/realtime/client-events

Automated tests use isolated SQLite tenants and mocked provider connections.
They check persistence, different tenant settings, allowed languages, generated
versus custom greetings, GA/preview payloads and UI save/reload. Audio quality,
latency, accents and real telephone behavior still require authorized live tests.

Delivery is separate from Commerce PR63 and confirmation PR64. No merge, service
source update, migration, deployment, secret rotation, new infrastructure or paid
telephone call is included. Railway Hobby recovery and the security review remain
delivery gates. The source branch has automatic Vercel deployment disabled.
