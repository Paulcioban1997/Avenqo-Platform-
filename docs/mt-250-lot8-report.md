# Lot 8 — 250 private Central AIs: security validation (2026-10-14)

Branch: `feat/mt-250-private-central-ai`  
PR #61 vs `promotion/sandbox` — **do not merge** without explicit GO.  
Production `avenqo.ca` / `api.avenqo.ca`: **unchanged**. Live Sandbox DB: **unchanged**.

## Verdict

**Do not merge yet.** Isolation is demonstrated on an isolated Postgres copy and in SQLite app-layer tests. Capacity for 250 **live** companies is **not** demonstrated.

## 1. GitHub PR #61 checks (HEAD `eef2e3e`, run 38665178238)

| Check | Result |
|---|---|
| Backend Core | **PASS** (9m2s) |
| Frontend App (Flutter) | PASS |
| Frontend Web | PASS |
| Secret guard and credential transition | PASS |
| GitGuardian | PASS |
| Vercel previews | PASS |

Previous HEAD `5284339` (run 38663674804) Backend Core was **FAIL** — 10 failed / 491 passed.

Backend Core root cause (measured locally, then fixed):

- Voice FakeSocket never reached `accept` because `apply_tenant_rls` called `session.get_bind()` on the test DB stub → `AttributeError` swallowed by the task, `until(..., timeout=2)` → `TimeoutError` (7 tests).
- Leftover `TenantExecutionContext` after websocket bind made `ConversationService.create` raise `ConversationNotFoundError` (3 included-central tests).
- `permissions_for("owner")` already resolved on CPython 3.11 `str, Enum`; still coerced explicitly.

Local re-run after fix: `tests/backend/test_phase6_voice.py` + `tests/backend/test_included_central.py` + RLS session tests = **44 passed**.

## 2. PR #60 inclusion and Alembic

**PASS.** PR #61 contains every PR #60 commit (`699aa64` … `ab4391d`) plus mt-250 commits.

Alembic linear head (tested):

`0057_rls_invoices_ai_voice` → `0058_sandbox_app_db_roles` → `0059_migrate_role_schema_create` → `0060_rls_remaining_tenant_tables`

No missing revision between #60 and #61. 0060 is reversible (`revoke_force_rls_policies`). Not applied to Sandbox or Production.

## 3. Isolated RLS 0060 rehearsal (localhost Docker Postgres 16, `rotation_test_ci` on `127.0.0.1:54329`)

**PASS.** Role `avenqo_app` LOGIN on a disposable copy only; LOGIN disabled after. `DATABASE_URL` unchanged.

Script `scripts/rehearse_rls_0060_isolated.py` exit 0:

```
host_isolated=true tables_forced=5 app_direct_login=true session_user_is_app=true
rls_hides_foreign_tenant=true empty_guc_sees_zero=true pooled_connection_does_not_leak=true
app_cannot_disable_rls=true app_cannot_set_role_postgres=true login_disabled_after=true
database_url_unchanged=true
```

Pytest with `AVENQO_ROTATION_TEST_ADMIN_URL` (same instance): **31 passed**, including `test_rls_0060_isolated`, `test_postgres_app_role`, `test_rls_transaction_context`.

Non-contournement measured:

| Attempt as `avenqo_app` | Result |
|---|---|
| Tenant A GUC | sees only A rows |
| Tenant B GUC | sees only B rows |
| Empty `app.current_company_id` | 0 rows |
| `ALTER TABLE … DISABLE ROW LEVEL SECURITY` | refused |
| `SET ROLE postgres` | refused |
| `rolsuper` / `rolbypassrls` | false |

## 4. Pooled connections

**PASS** on isolated Postgres `pool_size=1`, `pool_reset_on_return=rollback`.

- After a Session with tenant A commits and closes, the next checkout without GUC sees **0** rows.
- `get_db` rolls back and drops `session.info["avenqo_rls"]` so `after_begin` cannot restore a previous tenant on a recycled Session object.
- HTTP resets `TenantExecutionContext` in `RequestIDMiddleware`; websockets reset in `_stream_session` `finally`; pytest autouse clears leftovers.

Live Sandbox/Production still connect as table owner: **RLS remains inert there** until a LOGIN cutover GO.

## 5. Sandbox role cutover

**PREPARED, NOT EXECUTED.** Procedure: `docs/security/sandbox-app-role-cutover.md`.

Isolated cutover rehearsal `scripts/rehearse_app_role_cutover.py` exit 0 (localhost only):

```
app_direct_login=true session_user_is_app=true rls_hides_foreign_tenant=true
worker_guc_bypass_sees_all=true app_cannot_create_table=true
app_cannot_set_role_postgres=true migrate_can_create_table=true
app_reads_migrate_table=true login_disabled_after=true database_url_unchanged=true
```

No Sandbox `ALTER ROLE`, no Railway `DATABASE_URL` change.

## 6. Load paliers (loopback mock, simulated AI, no paid providers)

k6 and Locust are **not installed** on this machine. Harnesses exist: `loadtest/k6-mt-250.js`, `loadtest/locustfile.py` (refuse Production; paliers ≥50 refuse non-loopback).

Measured with `python loadtest/run_isolated_paliers.py` against `127.0.0.1` mock (health + simulated login + simulated `/ai/chat`):

| Companies | Concurrency | Requests | Failures | RPS | p50 ms | p95 ms | Result |
|---|---|---|---|---|---|---|---|
| 10 | 10 | 90 | 0 | 145.5 | 6.8 | 243.4 | PASS mock |
| 25 | 25 | 225 | 0 | 136.8 | 8.2 | 524.4 | PASS mock |
| 50 | 50 | 450 | 0 | 122.2 | 8.2 | 1542.5 | PASS mock |
| 100 | 100 | 900 | 28 | 172.6 | 7.7 | 2040.4 | FAIL mock (timeouts) |
| 150 | 150 | 1350 | 45 | 253.8 | 8.0 | 2046.0 | FAIL mock (timeouts) |
| 200 | 200 | 1800 | 52 | 339.5 | 8.0 | 2044.7 | FAIL mock (timeouts) |
| 250 | 250 | 2250 | 95 | 425.1 | 7.9 | 2034.6 | FAIL mock (timeouts) |
| 100 | 25 | 900 | 0 | 421.0 | 6.8 | 22.9 | PASS mock (capped) |
| 150 | 25 | 1350 | 0 | 505.3 | 7.0 | 10.7 | PASS mock (capped) |
| 200 | 25 | 1800 | 0 | 679.7 | 7.0 | 14.5 | PASS mock (capped) |
| 250 | 20 | 2250 | 0 | 730.1 | 7.3 | 10.0 | PASS mock (capped) |

**These numbers are not Avenqo API capacity.** They are a stdlib mock. Live Sandbox/Production load is **NOT TESTED** (forbidden without GO).

## 7. Merge gate

| Item | Result |
|---|---|
| Two tenants cannot read each other (app layer, SQLite) | PASS |
| Two tenants cannot read each other (`avenqo_app` + FORCE RLS, isolated PG) | PASS |
| Pooled connection does not keep the previous tenant | PASS (isolated PG) |
| Alembic 0060 present and reversible | PASS |
| PR #60 commits included | PASS |
| GitHub Backend Core on pushed HEAD `eef2e3e` | **PASS** (run 38665178238) |
| Live Sandbox RLS / `avenqo_app` LOGIN | **NOT DONE** (no GO) |
| 250 live companies on shared infra | **NOT TESTED** |
| Paid OpenAI/Telnyx | **BLOCKED** |
| Merge / Production | **FORBIDDEN** |

## 8. Remaining blockers

1. Owner GO before Sandbox backup + `avenqo_app` LOGIN + `DATABASE_URL` cutover (`docs/security/sandbox-app-role-cutover.md`).
2. Owner GO before any Locust/k6 palier against Sandbox.
3. Workers, pool, and rate limits are still sized for one API replica — isolation ≠ 250-tenant SLO.
4. Do not merge PR #60 or #61 without an explicit Merge/GO.
