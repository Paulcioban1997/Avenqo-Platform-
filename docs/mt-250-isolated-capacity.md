# Isolated replica capacity — PR #61

Generated: 2026-10-15T02:38:10.444133+00:00
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
  "header_spoof_ignored": true,
  "crm_idor_hidden": true,
  "login_status": 200,
  "login_detail": null
}
```

## Pool

```json
{
  "pool_size": 16,
  "max_overflow": 16,
  "pool_timeout_s": 5,
  "http_sync_thread_limit": 32,
  "aligned_max_connections": 32,
  "previous_misread_pg_waiting": "wait_event IS NOT NULL counted idle ClientRead as saturation"
}
```

## Paliers

| Companies | Pass | RPS | p50 | p95 | p99 | 5xx | CPU % | RSS MB | PG active | idle-in-xact | locks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 10 | True | 87.9 | 90.4 | 212.4 | 452.1 | 0.0 | 128.4 | 440.9 | 1 | 0 | 0 |
| 25 | True | 95.9 | 224.5 | 499.9 | 534.7 | 0.0 | 130.8 | 472.1 | 1 | 0 | 0 |
| 50 | True | 93.2 | 227.9 | 632.5 | 1062.8 | 0.0 | 132.9 | 474.5 | 1 | 0 | 0 |
| 100 | True | 87.9 | 230.8 | 648.9 | 790.5 | 0.0 | 122.3 | 478.3 | 1 | 0 | 0 |
| 150 | True | 88.6 | 307.6 | 686.9 | 775.3 | 0.0 | 132.4 | 477.2 | 1 | 0 | 0 |
| 200 | True | 88.5 | 275.1 | 677.7 | 904.8 | 0.0 | 131.5 | 475.9 | 1 | 0 | 0 |
| 250 | True | 90.4 | 303.9 | 666.0 | 937.6 | 0.0 | 131.2 | 479.0 | 1 | 0 | 0 |

## Burst 250 simultaneous GET /health

```json
{
  "path": "/api/v1/health",
  "simultaneous": 250,
  "logins": 0,
  "requests": 250,
  "failures_5xx_or_timeout": 0,
  "error_rate_5xx": 0.0,
  "elapsed_s": 0.497,
  "rps": 503.2,
  "p50_ms": 229.3,
  "p95_ms": 324.9,
  "p99_ms": 327.7,
  "pg_activity": 17,
  "pg_active": 1,
  "pg_idle": 16,
  "pg_idle_in_xact": 0,
  "pg_lock_waits": 0,
  "pg_app_sessions": 16,
  "pg_waiting": 0,
  "pass": true,
  "note": "one-shot simultaneous wave, isolated replica only"
}
```


## Burst 250 simultaneous GET /auth/me

```json
{
  "path": "/api/v1/auth/me",
  "simultaneous": 250,
  "logins": 250,
  "requests": 250,
  "failures_5xx_or_timeout": 0,
  "error_rate_5xx": 0.0,
  "elapsed_s": 1.912,
  "rps": 130.7,
  "p50_ms": 1006.0,
  "p95_ms": 1549.8,
  "p99_ms": 1557.6,
  "pg_activity": 17,
  "pg_active": 1,
  "pg_idle": 16,
  "pg_idle_in_xact": 0,
  "pg_lock_waits": 0,
  "pg_app_sessions": 16,
  "pg_waiting": 0,
  "pass": true,
  "note": "one-shot simultaneous wave, isolated replica only"
}
```


## Central AI (simulated)

```json
{
  "companies": 25,
  "logins": 25,
  "requests": 50,
  "failures_5xx_or_timeout": 0,
  "error_rate_5xx": 0.0,
  "elapsed_s": 10.309,
  "rps": 4.9,
  "p50_ms": 4401.1,
  "p95_ms": 5961.6,
  "p99_ms": 6050.8,
  "pg_activity": 17,
  "pg_active": 1,
  "pg_idle": 16,
  "pg_idle_in_xact": 0,
  "pg_lock_waits": 0,
  "pg_app_sessions": 16,
  "pg_waiting": 0,
  "pass": true,
  "paid_provider": false
}
```


## k6 palier

```json
{
  "pass": true,
  "vus": 25,
  "hold": "12s",
  "returncode": 0,
  "stdout_tail": "nning (10.0s), 25/25 VUs, 143 complete and 0 interrupted iterations\npalier   [  83% ] 25 VUs  10.0s/12s\n\nrunning (11.0s), 25/25 VUs, 167 complete and 0 interrupted iterations\npalier   [  92% ] 25 VUs  11.0s/12s\n\nrunning (12.0s), 25/25 VUs, 175 complete and 0 interrupted iterations\npalier   [ 100% ] 25 VUs  12.0s/12s\n\n\n  \u00e2\u2013\u02c6 THRESHOLDS \n\n    http_req_failed\n    \u00e2\u0153\u201c 'rate<0.05' rate=0.00%\n\n\n  \u00e2\u2013\u02c6 TOTAL RESULTS \n\n    checks_total.......: 800     64.129795/s\n    checks_succeeded...: 100.00% 800 out of 800\n    checks_failed......: 0.00%   0 out of 800\n\n    \u00e2\u0153\u201c login 200\n    \u00e2\u0153\u201c me\n    \u00e2\u0153\u201c retail\n    \u00e2\u0153\u201c crm\n\n    HTTP\n    http_req_duration..............: avg=384.27ms min=24.35ms  med=276.4ms max=1.31s p(90)=799.66ms p(95)=866.78ms\n      { expected_response:true }...: avg=384.27ms min=24.35ms  med=276.4ms max=1.31s p(90)=799.66ms p(95)=866.78ms\n    http_req_failed................: 0.00%  0 out of 800\n    http_reqs......................: 800    64.129795/s\n\n    EXECUTION\n    iteration_duration.............: avg=1.53s    min=526.13ms med=1.65s   max=2.19s p(90)=1.89s    p(95)=2.13s   \n    iterations.....................: 200    16.032449/s\n    vus............................: 25     min=25       max=25\n    vus_max........................: 25     min=25       max=25\n\n    NETWORK\n    data_received..................: 1.1 MB 89 kB/s\n    data_sent......................: 736 kB 59 kB/s\n\n\n\n\nrunning (12.5s), 00/25 VUs, 200 complete and 0 interrupted iterations\npalier \u00e2\u0153\u201c [ 100% ] 25 VUs  12s\n",
  "paid_provider": false
}
```


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


## Nine connectors / hot-path tables

```json
{
  "connectors": [
    "shopify",
    "woocommerce",
    "etsy",
    "google_calendar",
    "outlook_calendar",
    "stripe",
    "telnyx",
    "openai",
    "internal_commerce_scheduler"
  ],
  "tables_present": {
    "commerce_connections": true,
    "crm_calendar_connections": true,
    "billing_accounts": true,
    "voice_business_configs": true,
    "ai_conversations": true,
    "ai_messages": true,
    "login_events": true,
    "auth_sessions": true,
    "crm_clients": true
  },
  "all_tables_present": true,
  "hotpath_indexes": {
    "ix_ai_conversations_company_user": true
  },
  "sandbox_modified": false,
  "production_modified": false
}
```


## Rollback rehearsal (isolated NOLOGIN)

```json
{
  "login_disabled": true,
  "app_connect_rejected": true,
  "sandbox_modified": false,
  "pass": true
}
```

## Recommendation

RLS with avenqo_app LOGIN holds on the isolated replica. HTTP paliers used 1 worker, pool 16+16, thread cap 32, pool_timeout 5s, simulated LLM. 250 simultaneous HTTP is a separate burst, not the palier concurrency. Live Sandbox still uses the table-owner login and default pool 10+20 / 30 AI req/min. Do not treat this as a Production GO or a 250-client capacity claim.
