# Phase 8.8 — universal business configuration and persistent lab usage

Status: **LIVE_VOICE_HF_PENDING**. OpenAI remains the telephone provider.
Additional infrastructure budget: **0 CAD**. No paid inference, number purchase,
telephone call, new hosting or Production operation is part of this delivery.

## Recovered state and root causes

Recovered `promotion/sandbox` at `1f9824a59eaee9e5aa99f8c3fbc3583495a5a1c8`.
Company grounding and Retail protections already existed. The remaining gaps
were a workspace configuration flow, a Voice allowlist with names that did not
match the CRM catalog, and lab receipts held only in a process-local ledger.
Produits_Ero is explicitly a mixed demonstration company, not a retail-only
template. Its two legacy CRM services must remain intact.

## Implementation

The Voice workspace now has a guided business configuration form: identity,
custom industry, description, activities, public locations, contact, timezone,
weekly hours, main/secondary languages, communication style, vocabulary,
cancellation policy, canonical CRM service selection and capability preferences.
Existing CRM screens remain authoritative for service prices, durations and
resources. Existing Voice customization and permission screens remain in place.
French and English copy are supplied; other UI locales use the existing fallback
mechanism. Language selection is not telephone-language certification.

GET/PUT `/api/v1/voice/business-profile` use the authenticated server company,
active subscription and management permission. Writes additionally require an
active owner/admin membership. Unknown tenant fields are rejected. The saved
capability list can only restrict existing grants; it cannot grant a module,
subscription or action. The guard and tool registry enforce this server-side.
Public callers and routing-PIN-only callers remain excluded from private data.

Configuration extends `CompanyOnboarding.draft_payload.voice_business`, preserving
other onboarding data. A version check rejects stale writes. Company context
includes a fingerprint, canonical services and tenant-owned calendar resources;
private resources are omitted from public context. Canonical service IDs are
validated again before booking; another tenant's ID is rejected.

`PersistentSpeechUsage` attaches inference tasks to the existing `VoiceCall`
and settles through Avenqo's existing credit reservations, provider attempts
and credit ledger. Tenant, call, session, task, model revision and reviewed
pricing provenance are checked. Unknown work stays unresolved; it is not
assumed free. Retries reconcile receipts without replaying inference or tools.
Crash recovery avoids duplicate settlement. Nonbillable lab events preserve
measured allocation estimates and debit zero credits. No conversion rate or
customer charge is invented. This is server-only integration, not an exposed
settlement API. The lab factory accepts a matching nonbillable persistent
ledger; default standalone local tests retain their unpaid journal.

No database schema or Alembic migration is introduced. Expected head remains
`0067_resolve_voice_call_tenant_owner`. HF phone selection remains blocked and
workers remain loopback-only. Model dependencies/weights are not in the API image.

### Post-deployment correction: canonical CRM schedules

Real validation of `8295dd1` exposed a legacy-format assumption: the business
profile rejected existing CRM `{weekly, date_overrides}` schedules. The read-only
preflight failed before any tenant update. The follow-up fix accepts and validates
canonical CRM periods, displays them without flattening split shifts, retains
dated exceptions and test restrictions, and directs edits to CRM. Saving Voice
preferences cannot overwrite an existing canonical schedule; stale or simplified
replacements are rejected. CRM remains the live source when reloading a profile.
Regression tests cover preservation, malformed periods and the UI save payload.
The follow-up commit requires its own Sandbox deployment authorization.

## Validation and delivery evidence

Local focused backend runs: 115 existing/new regression cases passed, then 45
final targeted cases passed, including the HTTP cancellation → persisted receipt
→ existing credit ledger path. Four new UI cases and TypeScript passed.
These tests use isolated databases and mocked providers, not paid inference or
Google/Telnyx calls. Full CI and actual deployment evidence are recorded in the
delivery report after publication; this file does not claim they have passed
before execution.

Authorized tenant configuration: add an explicitly nonmedical product demo
service, keep the legacy services, select its canonical ID for Voice and preserve
existing grants. Do this only after the new backend is deployed and verified.
Do not create appointments or modify another company as part of configuration.

## Acceptance and rollback

Verify SHA, `/health`, readiness, Alembic, logs, unchanged provider/routing/flags,
and the target tenant's canonical service IDs after deployment. Preview web must
rewrite exclusively to the Sandbox API. Production remains on `main`.
Rollback target is the prior Sandbox deployment
`6ba24238-05c5-43f5-b03a-7f2ca9c8ecb7` / `1f9824a`; no database downgrade,
restoration, secret change or number rerouting is required. Saved JSON is
backward-compatible; restore only the recorded target-company configuration
if specifically needed and authorized, never overwrite active data globally.

After separate phone/spending approval, request a configured product demo in
French, confirm the exact service/time/timezone, verify CRM and actual Calendar
status, interrupt/switch topics and request an unsupported medical service.
Public callers must not receive private historical sales. Private analytics
require the owner's individual phone identity/NIP and role, which the founder
has deferred configuring. Superstore is historical 2014–2017, not current sales;
inventory and unmapped source currency must not be invented. No HF real-phone
quality, 60-minute continuity or live Calendar write is certified by this phase.
