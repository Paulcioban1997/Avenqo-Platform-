# Isolated replica capacity — PR #61

Generated: 2026-10-15T03:55:11.898387+00:00
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
| 25 | True | 84.3 | 237.6 | 515.2 | 544.6 | 0.0 | 137.2 | 451.3 | 1 | 0 | 0 |
| 50 | True | 90.3 | 239.5 | 669.3 | 1242.4 | 0.0 | 132.3 | 471.0 | 1 | 0 | 0 |
| 100 | True | 82.7 | 283.8 | 681.6 | 803.1 | 0.0 | 125.8 | 473.2 | 1 | 0 | 0 |
| 250 | True | 70.7 | 378.1 | 857.3 | 1082.2 | 0.0 | 131.0 | 475.4 | 1 | 0 | 0 |

## Burst 250 simultaneous GET /health

```json
{
  "path": "/api/v1/health",
  "simultaneous": 250,
  "logins": 0,
  "requests": 250,
  "failures_5xx_or_timeout": 0,
  "error_rate_5xx": 0.0,
  "elapsed_s": 0.696,
  "rps": 359.1,
  "p50_ms": 305.7,
  "p95_ms": 448.2,
  "p99_ms": 449.1,
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
  "elapsed_s": 2.452,
  "rps": 102.0,
  "p50_ms": 1284.1,
  "p95_ms": 2170.0,
  "p99_ms": 2178.6,
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
[
  {
    "companies": 25,
    "logins": 25,
    "requests": 26,
    "failures_5xx_or_timeout": 0,
    "error_rate_5xx": 0.0,
    "elapsed_s": 7.972,
    "rps": 3.3,
    "p50_ms": 7142.6,
    "p95_ms": 7955.6,
    "p99_ms": 7955.6,
    "pg_activity": 17,
    "pg_active": 1,
    "pg_idle": 16,
    "pg_idle_in_xact": 0,
    "pg_lock_waits": 0,
    "pg_app_sessions": 16,
    "pg_waiting": 0,
    "peak_pg_active": 2,
    "peak_pg_idle_in_xact": 25,
    "peak_pg_app_sessions": 25,
    "peak_pg_lock_waits": 0,
    "pg_samples": 42,
    "pass": true,
    "paid_provider": false,
    "note": "LLM mock holds 0.4s; pool connections must not stay idle-in-transaction during that await"
  },
  {
    "companies": 50,
    "logins": 50,
    "requests": 69,
    "failures_5xx_or_timeout": 0,
    "error_rate_5xx": 0.0,
    "elapsed_s": 17.825,
    "rps": 3.9,
    "p50_ms": 5960.8,
    "p95_ms": 10590.9,
    "p99_ms": 10592.5,
    "pg_activity": 17,
    "pg_active": 1,
    "pg_idle": 16,
    "pg_idle_in_xact": 0,
    "pg_lock_waits": 0,
    "pg_app_sessions": 16,
    "pg_waiting": 0,
    "peak_pg_active": 3,
    "peak_pg_idle_in_xact": 32,
    "peak_pg_app_sessions": 32,
    "peak_pg_lock_waits": 0,
    "pg_samples": 94,
    "pass": true,
    "paid_provider": false,
    "note": "LLM mock holds 0.4s; pool connections must not stay idle-in-transaction during that await"
  },
  {
    "companies": 100,
    "logins": 100,
    "requests": 122,
    "failures_5xx_or_timeout": 0,
    "error_rate_5xx": 0.0,
    "elapsed_s": 31.663,
    "rps": 3.9,
    "p50_ms": 8029.0,
    "p95_ms": 9926.8,
    "p99_ms": 11562.8,
    "pg_activity": 17,
    "pg_active": 1,
    "pg_idle": 16,
    "pg_idle_in_xact": 0,
    "pg_lock_waits": 0,
    "pg_app_sessions": 16,
    "pg_waiting": 0,
    "peak_pg_active": 3,
    "peak_pg_idle_in_xact": 31,
    "peak_pg_app_sessions": 32,
    "peak_pg_lock_waits": 0,
    "pg_samples": 167,
    "pass": true,
    "paid_provider": false,
    "note": "LLM mock holds 0.4s; pool connections must not stay idle-in-transaction during that await"
  },
  {
    "companies": 250,
    "logins": 250,
    "requests": 254,
    "failures_5xx_or_timeout": 0,
    "error_rate_5xx": 0.0,
    "elapsed_s": 68.573,
    "rps": 3.7,
    "p50_ms": 7695.6,
    "p95_ms": 11302.9,
    "p99_ms": 13799.2,
    "pg_activity": 17,
    "pg_active": 1,
    "pg_idle": 16,
    "pg_idle_in_xact": 0,
    "pg_lock_waits": 0,
    "pg_app_sessions": 16,
    "pg_waiting": 0,
    "peak_pg_active": 2,
    "peak_pg_idle_in_xact": 32,
    "peak_pg_app_sessions": 32,
    "peak_pg_lock_waits": 0,
    "pg_samples": 359,
    "pass": true,
    "paid_provider": false,
    "note": "LLM mock holds 0.4s; pool connections must not stay idle-in-transaction during that await"
  }
]
```


## k6 palier

```json
{
  "pass": true,
  "vus": 25,
  "hold": "12s",
  "returncode": 0,
  "stdout_tail": "2s\n\nrunning (10.0s), 25/25 VUs, 116 complete and 0 interrupted iterations\npalier   [  83% ] 25 VUs  10.0s/12s\n\nrunning (11.0s), 25/25 VUs, 124 complete and 0 interrupted iterations\npalier   [  92% ] 25 VUs  11.0s/12s\n\nrunning (12.0s), 25/25 VUs, 143 complete and 0 interrupted iterations\npalier   [ 100% ] 25 VUs  12.0s/12s\n\n\n  \u00e2\u2013\u02c6 THRESHOLDS \n\n    http_req_failed\n    \u00e2\u0153\u201c 'rate<0.05' rate=0.00%\n\n\n  \u00e2\u2013\u02c6 TOTAL RESULTS \n\n    checks_total.......: 672     52.284798/s\n    checks_succeeded...: 100.00% 672 out of 672\n    checks_failed......: 0.00%   0 out of 672\n\n    \u00e2\u0153\u201c login 200\n    \u00e2\u0153\u201c me\n    \u00e2\u0153\u201c retail\n    \u00e2\u0153\u201c crm\n\n    HTTP\n    http_req_duration..............: avg=471.66ms min=22.04ms  med=355.28ms max=1.21s p(90)=890.04ms p(95)=1s   \n      { expected_response:true }...: avg=471.66ms min=22.04ms  med=355.28ms max=1.21s p(90)=890.04ms p(95)=1s   \n    http_req_failed................: 0.00%  0 out of 672\n    http_reqs......................: 672    52.284798/s\n\n    EXECUTION\n    iteration_duration.............: avg=1.88s    min=688.84ms med=2.06s    max=2.37s p(90)=2.29s    p(95)=2.29s\n    iterations.....................: 168    13.071199/s\n    vus............................: 25     min=25       max=25\n    vus_max........................: 25     min=25       max=25\n\n    NETWORK\n    data_received..................: 936 kB 73 kB/s\n    data_sent......................: 618 kB 48 kB/s\n\n\n\n\nrunning (12.9s), 00/25 VUs, 168 complete and 0 interrupted iterations\npalier \u00e2\u0153\u201c [ 100% ] 25 VUs  12s\n",
  "paid_provider": false
}
```


## Voice (simulated, no paid STT/TTS)

```json
null
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
