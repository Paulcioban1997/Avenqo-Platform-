# Lot 1 — Phase 0 audit: 250 private Central AIs

Date: 2026-10-14  
Branch: `feat/mt-250-private-central-ai` (sibling of PR #60, not a rewrite)  
PR #60: https://github.com/Paulcioban1997/Avenqo-Platform-/pull/60  
Base of this work: `feat/sandbox-platform-functional-finalization` @ `ab4391d`  
Target: `promotion/sandbox` only. Production `avenqo.ca` / `api.avenqo.ca` is unchanged and must stay unchanged.

## 1. Git and environment map

| Surface | State (this audit) |
|---|---|
| `main` | `ba2dda1` — production line. Do not merge here. |
| `promotion/sandbox` | `1bfb9ff` — last merged #59. Behind origin by local fetch; live Railway Sandbox tracks this until #60 merges. |
| PR #60 | OPEN, MERGEABLE, CI green on `dc93eeb` / `ab4391d`. Head `feat/sandbox-platform-functional-finalization`. |
| Merged onto sandbox recently | #59 retail reset/backup, #58 app-role cutover rehearsal (no live LOGIN), #57 constrained roles, #56 RLS 0057, #55 OAuth/Stripe/admin RLS/0056, #54 #53+#52. |
| Open siblings | #53 security P1, #52 i18n, plus several voice/calendar drafts. Do not overwrite. |
| Vercel preview | Serves PR #60 Next.js. `/api/v1` is routed to Railway Sandbox, not Production (`6f9eae0`). |
| Railway Sandbox API | Older than #60 until explicit Merge/GO. |
| Production API | Unchanged. |

## 2. Runtime topology (what actually runs)

- **Web**: Next.js in `web/` on Vercel. Cookie + Bearer auth. Preview API origin is Sandbox.
- **API**: FastAPI `backend.main:create_application`, Railway `uvicorn --workers 1` after `alembic upgrade head`.
- **DB**: PostgreSQL on Railway (Sandbox vs Production are separate). Tests use SQLite + optional CI Postgres.
- **Flutter**: `frontend/` mobile client against the same API. Not a second tenant authority.
- **Workers**: no Redis/Celery. `BackgroundTasks`, one-thread retail KPI pool, optional voice provisioning worker (default off).
- **Cache**: in-process `TenantMemoryCache` keyed `namespace:company_id:key`. Isolation by key, not by process boundary.
- **AI**: shared LLM gateway (`openai` / `anthropic` / `gemini` / optional Vertex) + `SmartModelRouter` + in-memory circuit breaker. Central AI is one orchestrator per request, not 250 model servers.
- **Voice**: Telnyx/Retell paths exist; paid live GO is out of scope.
- **Connectors**: Shopify/WooCommerce and others; tenant from connection row after webhook signature, then `bind_webhook_tenant`.

250 private Central AIs = **shared compute + strict tenant context**, not 250 GPUs.

## 3. Existing tenant identity (what is already reliable)

- JWT access token carries `sub`, `tenant_id`, `session_id`. `AuthService.authenticate` requires `auth_session.user.company_id == claims["tenant_id"]`. Tampered JWT tenant fails closed.
- `CurrentIdentity.company_id` comes from `user.company_id` (DB session), never from query/body.
- `get_tenant_context` builds `TenantContext` from that identity and calls `apply_tenant_rls(..., bypass=False)`.
- `ToolExecutionContext` is documented as backend-only. Tools read `context.tenant.company_id`. `ToolArguments` uses `extra="forbid"`.
- Conversations/messages are queried with `company_id` + `user_id`.
- Artifacts: `var/models/{company_id}/...`.
- Credits: DB rows + `pg_advisory` / SQLite lock + in-process `_tenant_credit_lock`. Settlement is idempotent by `avenqo_request_id`.
- Internal `/internal/*` requires `X-Avenqo-Scheduler-Token`; `X-Avenqo-Tenant-Id` is accepted only after that token. Not a user JWT bypass.
- Platform admin `/admin` is `is_platform_admin` (not tenant owner). RLS bypass is explicit after that gate.
- Catalog prices (must remain): Base 29.99 CAD / 6500 credits, Professional 49.99 CAD / 20000, Enterprise custom.

## 4. RLS and database roles (truth, not aspiration)

Alembic head on this line: **0059**.

FORCE RLS policies exist on a **subset** of tenant tables (0049, 0054, 0056, 0057): workspace, some CRM, datasets, commerce_connections, invoices, AI chats, voice_calls, voice provisioning.

`avenqo_tenant_id()` reads `app.current_company_id` (SET LOCAL). `get_db` does **not** enable bypass. Session `after_begin` restores GUC so pooled connections do not leak tenant.

**However:**

1. Roles `avenqo_app` / `avenqo_migrate` / `avenqo_owner` are created **NOLOGIN** (0058). PR #58 rehearsed isolated LOGIN; it did **not** rotate live `DATABASE_URL`.
2. Table-owner / superuser connections **bypass FORCE RLS**. Until an authorized Sandbox app-role cutover, RLS on live Sandbox/Production is **inert**.
3. Many `company_id` tables still have **no** policy: CRM leads/opportunities/contacts/employees, normalized commerce, credit balances/reservations, voice sessions/numbers/PINs, source selections, datasets versions/mappings, tool executions, accounting, support chats, etc.
4. 0056/0057 `downgrade()` raises (forward-only). Lot 3 must add a **reversible** companion (disable policy / drop policy) without applying anything to Production.

SQLite tests skip RLS. Postgres security tests use isolated URL + probe tables, often `SET LOCAL ROLE avenqo_app`, and skip without `AVENQO_ROTATION_TEST_ADMIN_URL`.

## 5. Central AI — wired vs UI-only

**Wired (do not reimplement):** `CentralAIService` + `ChatService` + tool orchestrator + usage reservation/settlement + module entitlements + voice tool guard. Stream chat, history, follow-ups, selected-agent tools, credit claim.

**Partial:** multimodal = text + bounded voice/realtime sockets. Image/audio understanding is provider-capability routed, not a per-tenant model farm.

**Not a GO:** paid Telnyx minutes, paid OpenAI realtime load, 250 concurrent real voice sessions.

## 6. Capacity as measured vs not measured

| Resource | Observed in code | 250-tenant implication |
|---|---|---|
| API workers | Railway `workers 1` | Single process; crash = all tenants. |
| SQL pool | `pool_size=10`, `max_overflow=20` | ~30 DB clients. Will stall under many simultaneous Central AI requests. |
| Credit lock | process dict + advisory lock | Safe on 1 worker; racy if workers scale without Redis/DB-only lock. |
| Rate limit / circuit breaker / LLM health | in-memory | Per process only. |
| Retail KPI | 1 worker thread | Backpressure exists locally, not cluster-wide. |
| Load tests | none checked in for 250 | Lot 7: Locust/k6 vs non-prod only. **NOT TESTED** until run. |

Do not invent load numbers here.

## 7. P0 live regression (screenshot, 2026-10-14)

URL: Vercel preview `/retail` with **Superstore-utf8.csv** selected.  
UI: `RequestFailure` — “Une erreur inattendue est survenue. Veuillez réessayer.”

Cause class (code): `RetailIntelligenceView.loadData` uses `Promise.all` + `apiFetch`, which **throws on any non-2xx**. One failing sibling (`/retail/inventory?limit=500`, `/sales/summary`, `/recommendations`, …) blanks the whole module. Preview frontend is #60; Sandbox API is pre-#60. That mismatch is sufficient to 500/404 one of those calls.

This is **P0 functional** for PR #60 preview. Isolation audit is not replaced by this fix. Lot 2 includes fail-soft loads so a stale API cannot hide the rest of Retail.

## 8. Findings

### P0

1. **Retail preview blank** when any of the parallel Retail fetches fail (live evidence).
2. **DB isolation is application-filter only** on live Sandbox/Production: RLS policies are incomplete and inert under the current DB role. A missed `company_id` filter is a cross-tenant read. Pass criterion “two companies can never read/modify/infer each other” is **not proven at the Postgres role**.
3. **No request-scoped `TenantExecutionContext`**: tenant is passed by argument. Thread-pool / background tasks can drop it. Tool calls do not assert a bound context matching `ToolExecutionContext.tenant`.

### P1

4. RLS coverage gaps listed in §4.3. Lot 3 must add FORCE RLS + default-deny, reversible, SQLite-noop, **not** applied to Production.
5. `avenqo_app` still NOLOGIN on live DBs. Cutover is **BLOCKED on user GO**.
6. Single worker + tiny pool + in-memory fair-share: will not serve 250 concurrent Central AI sessions. Need quotas, queue, backpressure (Lot 5) and measured load (Lot 7).
7. Internal tenant header is token-gated; if the scheduler token leaks, any company UUID is impersonable. Bind RLS on that path (missing today).
8. Credit reservation uses in-process locks in addition to DB. Multi-replica would double-bill or over-reserve.

### P2

9. In-memory tenant cache / rate limits / circuit breaker: OK isolation if keys include `company_id`; not shared across instances.
10. JWT `tenant_id` is dual-sourced with DB user; mismatch fails closed (good) but clients might assume header/query company_id works (`tenant_locale` already 404s mismatch).
11. Flutter and web both must keep using cookies/Bearer only — no client tenant picker except membership switch (already 403 without membership).

### P3

12. Railway start always migrates to head — fine for Sandbox, dangerous if Production URL is pointed at this service. Keep env isolation.
13. Docs sprawl; this file is the audit of record for the 250-tenant program.

## 9. What this program will not do

- No Production deploy, secret rotation, Stripe charges, paid Telnyx/OpenAI GO, merge to `main`, or merge to `promotion/sandbox` without explicit user Merge/GO.
- No catalog price changes.
- No claim of 250 real voice sessions from mocks.
- No RLS enablement on Production.

## 10. Lot plan (execution order)

1. **Lot 1** — this audit.  
2. **Lot 2** — `TenantExecutionContext` ContextVar, bind on identity/internal/admin, tool-arg tenant strip + bind check, Retail fail-soft.  
3. **Lot 3** — reversible RLS expansion + cache/file notes; Sandbox copy only.  
4. **Lot 4** — bind Central AI text/voice sessions to execution context (wired paths only).  
5. **Lot 5** — atomic quotas, fair scheduling, attribution (design + code, no fake load).  
6. **Lot 6** — companies A/B/C security tests.  
7. **Lot 7** — Locust/k6 non-prod; label NOT TESTED/BLOCKED if a palier cannot run.  
8. **Lot 8** — 18-section report + PR to `promotion/sandbox`, unmerged.
