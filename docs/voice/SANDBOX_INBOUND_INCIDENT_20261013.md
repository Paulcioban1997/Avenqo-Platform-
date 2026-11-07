# Sandbox inbound incident — 2026-10-13

## Demonstrated cause

Telnyx delivery at 16:37:49 UTC reached the Sandbox webhook and received HTTP 200 with `received=true`, `routed=false`, `status=READY_FOR_OWNER_ACTION`. Railway recorded the same request. The caller hung up at 16:38:33 UTC. The database contains that Garage Montreal QA call and no successful route receipt.

Both media flags were deliberately false and RETELL_API_KEY was absent. The unconfigured transport path acknowledged the event without sending answer, reject or hangup. This was not a missing webhook or signature failure.

The number remains active on Telnyx connection 3069110156336826311, API v2, with the Sandbox webhook. No provider routing was changed during this repair. Unsigned webhook requests return 401. OpenAI model retrieval returned 200; that proves key/model readability, not an authenticated audio session or a certified language.

## Candidate behavior

- In Sandbox only, an authenticated, entitled inbound call with no usable Retell transport and disabled local media is rejected before answer. It must not ring indefinitely or incur answered audio costs.
- Rejection failures return 502 and permit a signed retry with the same command ID. Logs omit exception messages and secrets.
- A failed streaming-start command on an already answered Sandbox call requests hangup and returns 502. No fabricated ended_at; the provider hangup event remains authoritative.
- Extend the prepared 90-second elapsed-call protections to the explicitly approved Produits_Ero agent/tenant pair, with exact connection and phone-binding checks. Retain garage compatibility and fail closed for foreign pairs. Independent watchdog remains prepared, not deployed.
- No migrations, provider secrets, Production behavior or connector-cron changes.

## Authorized configuration changes already executed

Produits_Ero Sandbox was verified separately from the garage: Base active; four legacy active modules; no Voice configuration/grants. With owner approval, Retail/Workflow/Accounting were deactivated for this tenant, CRM + Voice are active, and the French Voice agent has only CRM read_availability/list_slots/create_appointment grants.

The owner separately approved clearing only the old garage agent phone field and moving the single existing number binding to Produits_Ero. Garage enabled state, language, greeting, services, hours, modules and grants are preserved. No Telnyx provider routing change. Private before/after snapshots support reversal.

Read-only readiness found tomorrow's 16 CRM slots, 12,998 available credits (6,500 included minus 2 used plus 6,500 purchased, no reservations), and no Google Calendar OAuth configuration. No appointment was created.

## Delivery gates

Candidate branch is separate from all Railway source branches. All three Vercel configs explicitly disable automatic deployment for this branch. No main merge. No API deployment without separate approval. PR is stacked on PR #45; deploying this candidate would include the previous undeployed Voice preparation from PR #43/#45, not merely the rejection change.

1. Finish local and GitHub checks, including signed inbound, retry, audio-init failure, tenant isolation and CRM simulation tests.
2. Ask permission for only the API Sandbox candidate deployment; keep both media flags false and all other services unchanged.
3. Verify deployed SHA, health and signed simulations with provider commands mocked; do not replay a real call-control ID or send paid provider commands.
4. Separately ask for streaming activation, then one real inbound test. Do not declare Voice operational before bidirectional speech and a fictitious CRM appointment are observed.

## 90-second test limit and rollback

The prepared backend timer starts at the signed event recorded by Avenqo. Provider/network/backend outages can delay termination; neither a strict physical 90-second cap nor a combined 2 CAD supplier cap is proven. Use a supervised manual countdown from first ringing and hang up by 90 seconds. No paid trial is authorized by this PR.

API rollback: restore the previously pinned 9d05eb37a20cfe4ff6f0a5485e92a8df980bbce7, keeping streaming disabled; no database downgrade. The authorized Sandbox configuration changes persist unless separately reversed from the private snapshot. Provider-number rollback to Production uses the previously saved connection 3064471945866118148 and original webhook; execute only with the owner's approval or the previously authorized security failure procedure.
