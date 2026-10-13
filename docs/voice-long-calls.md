# Voice long-call candidate — not activated

The commercial default is 3,600 seconds. Ninety seconds belongs solely to the
historical Sandbox QA guard, controlled by `VOICE_SANDBOX_TEST_GUARD_ENABLED`.
Never disable that guard to run a paid test without explicit authorization.

## Rules and admission

`GET/PUT /api/v1/voice/call-policy` requires an active subscription, Voice
entitlement, and owner/admin membership of the authenticated company. The body
cannot supply a company ID, operator rate, or activation flag. A company can
lower its duration and concurrency; raising plan caps requires an operator
contract. Defaults for Base and Professional are one hour; existing concurrency
limits remain Base 1 / Professional 2. Included credits and prices are unchanged.

Enterprise may have no fixed duration cap, but every admitted call still has a
finite spending reservation, monthly minutes, and an idle limit. This is not
unlimited free calling. Operator duration caps are configurable with
`VOICE_PLAN_MAX_CALL_SECONDS`; unknown plans fail to a one-hour ceiling.

PostgreSQL serializes admissions with a company-scoped transaction lock. A
durable `runtime_policy` snapshot on the stored call reserves the available
budget before answering. The same stored call cannot reserve twice. Another
company's payload cannot choose that snapshot or spend that reservation.

Rate configuration is mandatory when `VOICE_LONG_CALLS_ENABLED=true`:
`VOICE_BUDGET_RATE_CEILING_USD_PER_MINUTE` must be reviewed against the selected
Telnyx route, STT, TTS, reasoning model, exchange rate, and other services. It is
an operator assumption, not a guaranteed maximum supplier price. Tenant budgets
are explicitly USD provider spending, not a CAD retail price or automatic
overage charge. Calls stop when duration, idle, credits, authentication, or
permissions expire. Alert state appears in the call's runtime snapshot.

Reservations remain conservative until final cost reconciliation is available:
completed calls currently retain their full allowance for the billing month.
This prevents unverified costs from reopening a spend quota. Automatic release
of unused reservations and provider invoice reconciliation are not certified.
Actual metered AI attempts are attributed by request, category, company, and
call; their `provider_cost_usd` comes from measured usage and a price catalogue,
not an OpenAI supplier invoice. Signed Telnyx `call.cost` receipts are retained
by currency separately. Missing or delayed receipts must not be called zero.

## Realtime and authentication

OpenAI documents a 60-minute Realtime session maximum. The candidate opens a
replacement session around minute 50, only at a quiet speech/response boundary.
The audio adapter has no business tools and no private conversation history.
Central's existing tenant-owned conversation and action idempotency remain
outside the socket. Provider IDs are namespaced by connection generation.

Permissions are checked again before opening a replacement session and every
five seconds during the call. Opening/closing/sending has bounded timeouts;
renewal has at most three attempts. An ambiguous mid-turn disconnect stops the
session without replaying audio or CRM actions. A renewal may produce an audible
gap. If no quiet boundary appears before provider expiry, the call stops cleanly.

PIN authorization does not renew silently. Tenant `auth_seconds` cannot exceed
`VOICE_AUTH_MAX_SESSION_SECONDS` (default 600), nor outlive the admitted call.
A 60-minute owner test requires an explicitly approved one-hour auth allowance.
After auth expiry, private tools stop; in-call reauthentication after a changed
auth epoch is not certified. Public receptionist turns remain scoped to the
existing public permissions, not owner's private history.

Accepted provider hangup is not proof of termination: in long-call mode,
concurrency remains reserved until a signed hangup is received. The local timer
and optional worker can retry stopping an expired call. They are not independent
of backend availability. A verified provider-side/manual stop plan is still
required before paid testing. No strict cumulative 2 CAD cap is claimed.

## Migration and delivery

PR #48 adds 0054 provisioning tables. This stacked candidate adds only nullable
`voice_business_configs.call_policy` in 0055, with 0054 as its parent. Existing
configuration is untouched until an owner saves a policy. All activation flags
remain off; no purchased numbers, paid calls, provider writes, production writes,
or deploys are part of this preparation. Vercel auto-deployment is disabled for
the candidate branch in all three configuration files.

Fresh Sandbox backup was appended to S3 on 2026-10-13 at 19:22 UTC, downloaded,
SHA-256 verified, and restored in a loopback-only isolated PostgreSQL database.
0053 -> 0054 -> 0055 was rehearsed there without changing preexisting company,
user or connector records. Historical archives were preserved. A separate
0048 -> 0050 -> head rehearsal checks real RLS and simultaneous admission.
Private proof records contain the checksum and object key; no credentials are
included in repository documentation.

Release sequence: approve exact PR48 commit first, recheck fresh backup,
apply only API Sandbox source, verify 0054 and the same-commit web preview;
then separately approve this candidate and 0055. Keep long-call, commercial,
payment, purchase, worker and audio gates off until their individual checks
and approvals succeed. Application rollback uses the previously pinned image
and keeps additive tables/policies; do not downgrade or overwrite live data.

## Proposed real 60-minute test — BLOCKED pending approval and rate proof

1. Verify Produits_Ero binding, CRM/Voice grants, credits, fake CRM service and
   available slot; no other company or Production writes.
2. Review the complete per-minute cost envelope and a maximum turn/output budget.
   Compute `60 * approved_USD_per_minute + billing/FX margin`; obtain explicit
   approval of that estimate. Do not reuse the old 2 CAD trial budget blindly.
3. Approve Sandbox deployment, then separately approve streaming and exactly one
   call. Configure the one-hour policy, approved auth window, and one concurrent
   call; disable only the historical QA guard after approval.
4. Monitor phone and media elapsed time, permissions, usage attempts, credits,
   provider errors and the renewal near minute 50. An operator remains ready to
   terminate the actual Telnyx call independently of the Avenqo backend.
5. French conversation, deliberate interruption, occupied-slot refusal, one
   fictitious appointment and oral confirmation. Check its company ID and avoid
   claiming Google Calendar sync while OAuth is missing.
6. Confirm signed termination, reconcile delayed Telnyx cost, metered OpenAI
   usage, CRM idempotency and no other tenant changes. English/Spanish and
   provider disconnect recovery require their own actual audio validation.

Official references:
- https://developers.openai.com/api/docs/guides/realtime-conversations
- https://developers.openai.com/api/docs/models/gpt-realtime-2.1
