# PHASE 8.2.2 — DATABASE DEPENDENCY MAP
## RAILWAY PRODUCTION DATABASE (`alert-tenderness` / `production`)

**Target Database:** `Postgres` (PostgreSQL 18.6)  
**Host (Internal):** `postgres.railway.internal:5432/railway`  
**Host (Public Proxy):** `tramway.proxy.rlwy.net:25367/railway`  
**Compromised Account:** `postgres` (Superuser / BypassRLS)  

---

## 1. System Dependency Architecture

```mermaid
graph TD
    subgraph "Railway Project: alert-tenderness (Production Environment)"
        DB["PostgreSQL 18.6 (6f290d34)<br/>tramway.proxy.rlwy.net:25367<br/>User: postgres (Superuser)"]
        API["Avenqo-Platform- (24a2afc3)<br/>api.avenqo.ca<br/>avenqo-platform-production.up.railway.app"]
        CRON_BACKUP["avenqo-daily-backup (95b8c1d8)<br/>Schedule: 0 7 * * *"]
        BUCKET["S3 Bucket: avenqo-backups"]

        API -->|"DATABASE_URL (Active Pool: 8 connections)"| DB
        CRON_BACKUP -->|"DATABASE_URL (pg_dump daily)"| DB
        CRON_BACKUP -->|"Upload Archive"| BUCKET
    end

    subgraph "Public Internet"
        GG["GitGuardian Scanner #38085288"]
        EXT_USERS["External Traffic (api.avenqo.ca)"]
        GG -->|"Probing TCP 25367 (VALID)"| DB
        EXT_USERS --> API
    end

    subgraph "Sandbox Environment (Isolated)"
        SANDBOX_API["Avenqo-Platform- (Sandbox)"]
        SANDBOX_DB["PostgreSQL (Sandbox)<br/>altaria.proxy.rlwy.net:17860<br/>User: avenqo_app (Least Privilege)"]
        SANDBOX_API --> SANDBOX_DB
    end
```

---

## 2. Production Service Dependency Matrix

| Service Name | Service ID | Dependent Variable | Current Value Pattern | Outage Impact if Password Revoked Abruptly |
| :--- | :--- | :--- | :--- | :--- |
| **`Avenqo-Platform-`** | `24a2afc3-36f8-46d0-b79d-b323755a83f3` | `DATABASE_URL` | `postgresql://${DB_USER}:${DB_PASSWORD}@postgres.railway.internal:5432/railway` | **CRITICAL OUTAGE.** Immediate HTTP 500 across all `api.avenqo.ca` endpoints. All tenant API transactions fail. |
| **`avenqo-daily-backup`** | `95b8c1d8-aa9a-4d88-9e12-401ffaefd997` | `DATABASE_URL` | Inherited from project production environment variables | **HIGH IMPACT.** Scheduled backup cron jobs (0 7 * * *) fail with authentication error. |
| **`Postgres` Service** | `6f290d34-03f3-4489-bf58-0713ee5fffa1` | `POSTGRES_PASSWORD` | Defined in database service container environment | Container restart loops if password env does not match underlying cluster role. |

---

## 3. Environment Isolation Analysis

### Sandbox Environment Independence
- **Railway Sandbox Project Environment ID:** `e5adc24d-23b9-4275-84de-91a7801649b8`
- **Sandbox Database Host:** `altaria.proxy.rlwy.net:17860`
- **Sandbox Database User:** Configured with `avenqo_app` (least-privilege application role)
- **Shared Secrets:** **NONE.** Sandbox credentials and secrets are 100% physically isolated from production.
- **Blast Radius:** Rotating or revoking credentials on `tramway.proxy.rlwy.net:25367` will have **ZERO effect** on Sandbox services or active CI runs.

---

## 4. Connection Pool & Session Footprint

Audit of active connection handles on the target production database:
- **FastAPI SQLAlchemy Engine Pool:**
  - Configured: `pool_size = 10`, `max_overflow = 20`
  - Active connections at audit: `8` idle pooled connections
  - Client Address: `fd12:73ee:1d4:1:d000:276:90d2:207e` (Railway internal IPv6)
- **External Public Connections:** `0` (Public proxy port `25367` is open but currently unattached to persistent clients).

---

## 5. Architectural Remediation Requirement

Currently, production runs `Avenqo-Platform-` directly as the superuser `postgres`.
The rotation plan must introduce the **least-privilege role (`avenqo_app`)** to production, mirroring the architecture already proven in Sandbox:
1. `postgres` (Reserved strictly for administrative tasks / migrations).
2. `avenqo_app` (`rolsuper=False`, `rolbypassrls=False`, scoped strictly to application DML operations).
3. Revocation of the public TCP proxy domain on `Postgres` if direct Internet access is unnecessary.
