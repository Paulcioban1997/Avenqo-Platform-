# Lot 8 — 250 private Central AIs: status report

Date: 2026-10-14  
Branch: `feat/mt-250-private-central-ai`  
Parent: `feat/sandbox-platform-functional-finalization` @ `ab4391d` (PR #60, not overwritten)  
PR target: `promotion/sandbox` — **do not merge** without explicit user Merge/GO.  
Production `avenqo.ca` / `api.avenqo.ca`: **unchanged**.

## 1. Scope

Shared LLM infra with per-request `TenantExecutionContext`. Business context, memory, docs, tools and sessions must not leak across companies. 250 tenants ≠ 250 AI servers.

## 2. Git / environments

| Item | Status |
|---|---|
| Dedicated branch | `feat/mt-250-private-central-ai` |
| PR #60 | Still OPEN vs `promotion/sandbox`; this work is a sibling |
| Railway Sandbox API | Older until #60 Merge/GO |
| Production | Untouched |
| Catalog | Base 29.99 CAD / 6500; Professional 49.99 CAD / 20000; Enterprise custom |

## 3. Tenant identity

**PASS** at application layer: JWT `tenant_id` must match `user.company_id`; `CurrentIdentity` uses the DB user; client headers/query/tool args cannot bind tenant.  
`TenantExecutionContext` is request-scoped and reset by `RequestIDMiddleware`.

## 4. RBAC / tools

**PASS** for wired tools: `ToolAuthorizationPolicy` rechecks membership; executor strips `company_id`/`tenant_id` and rejects a tool context that does not match the bound tenant. Prompt-injected tenant selectors cannot switch company.

## 5. Postgres RLS

**PARTIAL.** 0060 adds reversible FORCE RLS for remaining `company_id` business tables. Users/memberships/auth sessions stay unscoped (login + tenant switch).  
Live Sandbox/Production still connect as table-owner / `avenqo_app` NOLOGIN — **RLS inert until app-role LOGIN GO**. Not applied to Production.

## 6. Caches / files / memory

**PASS** in-process: cache keys include `company_id`; invalidation is per tenant. Model artifacts under `{company_id}/`. Conversations/messages filtered by `company_id` + bound context. No Redis cluster cache.

## 7. Central AI text sessions

**PASS** for wired paths: conversations cannot be listed/read across A/B/C; Central execute refuses a mismatched bound tenant. Shared gateway + router.

## 8. Voice sessions

**PARTIAL.** Websocket now binds tenant + RLS after JWT/session checks. Paid Telnyx/OpenAI realtime **GO not given** — no live provider load. Simulated transport ≠ real audio.

## 9. Credits / quotas

**PASS** for single worker: DB reservation + advisory lock + process lock; settlement idempotent by `avenqo_request_id`; cannot reserve for a foreign bound tenant.  
**PARTIAL** if workers scale: in-process lock is not cluster-wide.

## 10. Concurrency / backpressure / circuit breakers

**PARTIAL.** In-memory LLM circuit breaker, request timeouts, Railway `workers 1`, pool 10+20. No distributed fair scheduler. Not proven at 250 concurrent companies.

## 11. Multi-model router

**PASS** as existing `SmartModelRouter` + provider registry. Cost attribution already on `tenant_ai_provider_attempts`. No catalog/price change.

## 12. Retail P0 (live screenshot)

**PARTIAL / mitigated in this branch.** `/retail` no longer blanks the module when one sibling API fails (inventory 503 still shows status/products). Live Vercel preview still talks to **older Sandbox API** until #60 is merged — remaining 500s on the old API are **BLOCKED on user Merge/GO**.

## 13. Security tests (companies A/B/C)

**PASS** (SQLite app-layer): A cannot list/read B or C conversations; `X-Company-Id` / `X-Avenqo-Tenant-Id` on a user JWT does not switch tenant; tool args cannot select a foreign company; credit reserve refuses foreign bound tenant.

Postgres FORCE RLS with `avenqo_app`: **NOT TESTED** here (requires isolated Postgres URL + LOGIN role GO).

## 14. Load tests

**NOT TESTED.** Scripts: `loadtest/k6-mt-250.js`, `loadtest/locustfile.py`. They refuse Production. No palier was executed in this run. Do not treat this as 250 real voice sessions.

| Palier | Result |
|---|---|
| A — health smoke | NOT TESTED |
| B — authenticated reads | NOT TESTED |
| C — Central AI text | NOT TESTED / would need non-prod keys |
| Real audio provider | BLOCKED (no paid GO) |

## 15. Capacity (code, not measured)

Single API worker, ~30 DB clients, in-memory rate limits. **FAIL** as a production 250-tenant SLO until load is measured and workers/pool/Redis are designed. Isolation ≠ capacity.

## 16. Requirement matrix

| Requirement | Result |
|---|---|
| Two companies cannot read/modify/infer each other (app layer) | PASS |
| Same at live Postgres role | PARTIAL (RLS prepared, inert until GO) |
| company_id only from server session | PASS |
| Tool/prompt cannot switch tenant | PASS |
| Shared LLM, private context | PASS (wired) |
| Additive reversible migrations | PASS (0060 downgrades) |
| RLS on Production | NOT DONE (forbidden) |
| 250 concurrent proven | NOT TESTED |
| Paid voice/OpenAI GO | BLOCKED |
| Catalog prices unchanged | PASS |
| Merge to main / Production deploy | NOT DONE (forbidden) |

## 17. BLOCKED on user GO

- Merge PR #60 and/or this PR to `promotion/sandbox`
- Sandbox `avenqo_app` LOGIN cutover (not Production)
- Isolated Postgres RLS rehearsal with the real app role
- Any Locust/k6 palier against Sandbox
- Paid Telnyx / OpenAI realtime
- Production RLS or secret/DB cutover

## 18. Commits on this branch

1. Lot 1 — Phase 0 audit  
2. Lot 2 — `TenantExecutionContext`, tool hardening, Retail fail-soft  
3. Lot 3 — reversible 0060 RLS expansion + cache isolation test  
4. Lot 4–6 — Central/voice/credit bind + A/B/C tests  
5. Lot 7–8 — load-test harness (unrun) + this report  
