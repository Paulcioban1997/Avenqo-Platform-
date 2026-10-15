# Isolated replica capacity — PR #61

Generated: 2026-10-15T02:12:09.907417+00:00
Production and live Sandbox were **not** modified. Paid providers were **not** called.

**Sandbox cutover recommendation: CONDITIONAL-GO**

## App role

```json
{
  "app_constrained": true,
  "owner_constrained": true,
  "app_superuser": false,
  "app_bypassrls": false,
  "app_can_login": true,
  "tables_reowned": 85,
  "table_owners": [
    "avenqo_owner"
  ],
  "app_is_table_owner": false,
  "database_url_uses_avenqo_app": true
}
```

## Functional

```json
{
  "login_a": true,
  "login_b": true,
  "me_a": true,
  "retail_a": true,
  "crm_a": true,
  "dashboard_a": true,
  "central_a": true,
  "cross_tenant_hidden": true,
  "pooled_logins_isolated": true,
  "app_role_empty_guc": true,
  "app_session_user": true,
  "app_cannot_disable_rls": true,
  "login_status": 200,
  "login_detail": null
}
```

## Paliers

| Companies | Pass | RPS | p50 ms | p95 ms | 5xx rate | CPU % | RSS MB | PG sessions |
|---|---|---|---|---|---|---|---|---|
| 10 | True | 92.5 | 85.4 | 199.9 | 0.0 | 0.0 | 454.2 | 11 |
| 25 | True | 99.6 | 184.4 | 488.0 | 0.0 | 0.0 | 469.8 | 26 |
| 50 | True | 92.6 | 177.1 | 757.8 | 0.0 | 0.0 | 458.4 | 41 |
| 100 | True | 96.0 | 296.4 | 799.3 | 0.0 | 0.0 | 489.9 | 41 |
| 150 | True | 99.7 | 313.6 | 777.4 | 0.0 | 0.0 | 478.3 | 41 |
| 200 | True | 94.1 | 339.4 | 838.4 | 0.0 | 0.0 | 482.8 | 41 |
| 250 | True | 92.8 | 319.2 | 848.0 | 0.0 | 0.0 | 471.4 | 41 |

## Voice (simulated, no paid STT/TTS)

```json
{
  "concurrent": 10,
  "ok": 10,
  "failed": 0,
  "text_fallback": 10,
  "pass": true,
  "samples": [
    {
      "ok": true,
      "fallback": true,
      "first": "lifecycle"
    },
    {
      "ok": true,
      "fallback": true,
      "first": "lifecycle"
    },
    {
      "ok": true,
      "fallback": true,
      "first": "lifecycle"
    },
    {
      "ok": true,
      "fallback": true,
      "first": "lifecycle"
    },
    {
      "ok": true,
      "fallback": true,
      "first": "lifecycle"
    }
  ],
  "paid_provider": false
}
```

## Voice (simulated)

10 concurrent websocket sessions: **PASS**, `text_fallback=true`, no paid STT/TTS/realtime.

## Tools installed in this isolated run

- k6 2.3.0 (Windows)
- locust (pip)
- Python palier harness against the **real isolated API** (not the stdlib mock)

## Quotas and saturation

- Replica rate limits were raised to 10 000/min so the limiter would not hide app/DB capacity. Default Avenqo is 10 login/min and 30 AI/min **per process**.
- Postgres sessions peaked at **41** with `AVENQO_DB_POOL_SIZE=40` (default in code remains 10+20). At 250 companies, `pg_waiting` reached 40 — the pool is the limiter, not 5xx.
- RSS ~450–500 MB for one uvicorn worker. CPU sampling after each palier under-reported (often 0%).
- Professional included credits + simulated LLM; no Stripe/OpenAI/Telnyx calls.

## Recommendation

| Decision | Verdict |
|---|---|
| Isolation proof (`avenqo_app` LOGIN + FORCE RLS, not table owner) | **PASS** |
| Sandbox `avenqo_app` cutover (after backup GO) | **CONDITIONAL-GO** |
| Announce 250 live companies on current Sandbox/Production | **NO-GO** |
| Production | **NO-GO** (forbidden, untested) |

RLS with `avenqo_app` LOGIN holds on the isolated replica. HTTP paliers 10→250 passed here with 1 worker, pool 40+40, simulated LLM, and raised rate limits. Live Sandbox still uses the table-owner login and default pool 10+20 / 30 AI req/min. Do not treat this as a Production GO. Need an explicit owner GO before backup + LOGIN on the real Sandbox copy.
