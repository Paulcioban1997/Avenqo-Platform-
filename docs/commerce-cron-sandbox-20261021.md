# Sandbox Commerce cron — incident and prepared hardening

## Verified incident, not a successful repair claim

Service `94d672b3-84c4-48b5-8622-6cc23153417a`, Sandbox
`e5adc24d-23b9-4275-84de-91a7801649b8`, schedule `*/15 * * * *`.
Deployment `60dc7c92-2fd6-421c-bf66-a7cd09e6c34d` is SUCCESS at `40af97b`.
That says nothing about the success of individual scheduled runs.

Official Railway incident: https://status.railway.com/incident/QH8L8B3E
"Dashboard and API unavailable, builds paused". Started October 21, 07:24 UTC
(03:24 Montreal); identified at 09:28 UTC, builds paused in all regions. At
13:40 UTC (09:40 Montreal), builds were still paused and some API features
unavailable. This provider incident overlaps the failures, but is not a
per-execution error code proving the precise provisioning failure.

Read-only `railway cron list` recovered, among others:

| Execution | Started UTC | Result | Duration |
|---|---|---|---|
| `fe3af9c4-41d1-4d26-8bce-961453afba6d` | 14:17:59 | CRASHED | 150 s |
| `1e35c175-5cd4-4757-aa2c-d4ee69afdce8` | 14:00:29 | CRASHED | 151 s |
| `49393f38-a2ba-484b-a1a1-69e32f96f6c4` | 13:47:14 | CRASHED | 150 s |
| `4c52b01c-9ee8-4c4f-b030-8ff53caf8c2f` | 13:31:54 | CRASHED | 150 s |
| `aea1fad7-55b3-481f-9a08-d14170eca185` | 13:15:56 | CRASHED | 150 s |
| `f66564ff-0454-40f0-a1cd-ad728e8a5d8d` | 13:00:53 | CRASHED | 247 s |

No application runtime logs were returned for 12:40–14:35 UTC, by either the
connector or CLI. The API's sampled HTTP logs contain no matching reconciliation
requests in that window. Four-hour cron CPU/memory samples were zero. Older
successful runs have a start and `completed claimed=0`, including 12:31:02 UTC.
The evidence suggests a pre-process/platform startup failure; DNS, authentication,
an HTTP timeout or business-code failure is not established by these traces.
Exact per-run platform failure details remain unavailable. Do not invent them.

## Prepared correction

- Dedicated `backend/Dockerfile.commerce-cron`: stdlib Python only, unprivileged
  UID, two source modules. No API/ML/database packages, volume, migration or
  API HTTP healthcheck. Does not change the repaired Connector AI image.
- Commerce startup no longer loads the full API settings. It emits flushed JSON
  startup/completion/failure records, correlation ID, elapsed time and exit code.
  No URL, token, headers, response body or exception text in these records.
- Sandbox target guard prevents accidental Production targeting.
- Shared HTTP helper keeps the old default behavior for other callers. Commerce
  explicitly selects only safe pre-connect retries: DNS failure or connection
  refused, at most three attempts, backoff 1/2 seconds. No retry of an ambiguous
  timeout, reset, HTTP 502/503/504, authorization failure or malformed success.
- Existing 600-second request timeout retained: the API synchronously awaits
  reconciliation for every candidate, so reducing it to a few seconds could
  abandon legitimate accepted work. Retry admission window 660 seconds leaves
  room in the 900-second schedule; request timeout shrinks to the remaining
  window. This is not a guaranteed end-to-end deadline for platform provisioning
  or operating-system DNS. No schedule change or manual execution introduced.
- Existing per-connection leases and record/webhook idempotency are unchanged.
  These leases do not constitute a durable receipt for the entire HTTP request,
  which is why arbitrary POST retries are not considered safe.

Twenty local focused cases passed (new cron, shared helper, protected commerce
endpoint). A subprocess starts with `python -S` using only the two worker files.
Local Docker daemon was unavailable. Full CI therefore includes a Docker build
and a network-disabled startup test: missing credentials must fail cleanly with
exit 1 and structured diagnostics, without any outgoing request. Full CI evidence
and the candidate SHA are recorded in the delivery report after completion.

No new infrastructure or paid service is provisioned. Normal existing Railway
and CI resource usage is not described as free. The dedicated source branch
disables its own Vercel auto-deploy in the three existing configurations. No merge
to main or automatic update of the running cron is performed by publication.

## Potentially exposed scheduler token — rotation prepared, not performed

Sandbox consumers found by code and variable inspection:

1. API `24a2afc3-36f8-46d0-b79d-b323755a83f3`: validates the token for
   `/internal/connector-ai/evaluate` and `/internal/commerce/reconcile`.
2. Commerce cron `94d672b3-84c4-48b5-8622-6cc23153417a`.
3. Connector AI cron `00d0f7c9-fb7e-4de1-a5e9-515bc1bb60f8`.

All three Sandbox values were present and equal, compared in process without
printing or persisting values. Both cron URLs target the correct Sandbox API.
Production values were neither retrieved nor modified. Current equality does
not make a potentially exposed credential safe; revocation remains outstanding.

The current API accepts only one token. An uncoordinated rotation could break
both schedulers. Wait for Railway recovery, then obtain approval for this order:

1. Add and test temporary dual-key validation in a separate API change. It must
   remain constant-time, fail closed on empty keys, and be Sandbox-scoped for
   delivery. This compatibility change is a plan, not code in this cron patch.
2. Generate a new independent Sandbox token directly in the approved secret
   interface; never put it in chat, source or command arguments.
3. Deploy API accepting new primary plus old temporary fallback; validate health.
4. Update Commerce and Connector AI Sandbox consumers to the new key together,
   preserving every other variable, source and schedule.
5. Observe successful scheduled executions of both services; compare request
   IDs and exclude old-key requests. Do not trigger repeated manual jobs.
6. Remove the old fallback only after those checks, then verify the old token
   is rejected and new-token scheduled requests succeed. Erase temporary secret
   storage using its normal recovery/lifecycle policy. Declare revocation only
   after effective rejection is verified.

Rollback during overlap restores consumer configuration to the still-accepted
old key, if approved. After old-key revocation, prefer roll-forward with the new
key; never quietly re-enable a compromised credential. No Production rotation.

## Phase 8.8 and release gate

The API source configuration says `40af97b`, but the latest actual API deployment
is still `074ccdb4-ff2f-41a4-b003-ce51961a8cf6` / `8295dd1`, also returned by
`/health`. No `40af97b` API deployment appears in recent history. Selecting a
source commit has not produced a running artifact. Builds are currently paused
by Railway, so a fresh build/deployment must be verified after recovery; simply
redeploying the old build will continue to serve `8295dd1`.

Do not change or align tenant data against the old broken onboarding. After the
approved `40af97b` API and matching preview are live, run the already-prepared
target-company configuration with snapshot, preserve both legacy services,
select the nonmedical demonstration service's canonical ID and test reload.
No real Calendar event or paid Voice call is part of this incident response.

Before applying a release, review the pending patch: Commerce cron only, dedicated
source SHA/branch and Dockerfile path (including the existing nonsecret
`RAILWAY_DOCKERFILE_PATH` override). Keep the 15-minute schedule, token, replicas
and Production untouched. Platform approval remains mandatory. After successful
deployment, observe at least two subsequent scheduled runs and verify startup,
request correlation, completion and exit code. A build alone is not FIXED.

Rollback uses the recorded previous cron source/image configuration after
approval, without database restore, archive deletion or secret replacement.
