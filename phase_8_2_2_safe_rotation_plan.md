# PHASE 8.2.2 — ZERO-DOWNTIME SAFE ROTATION PLAN
## POSTGRESQL PRODUCTION CREDENTIAL REMEDIATION

**Target Database:** Railway Production PostgreSQL (`alert-tenderness` / `production`)  
**Host:** `postgres.railway.internal:5432` / `tramway.proxy.rlwy.net:25367`  
**Current State:** **`AWAITING_FOUNDER_APPROVAL`**  
**Estimated Execution Window:** ~3 to 5 minutes  
**Target Downtime:** **Zero Seconds**  

---

> [!IMPORTANT]
> **MANDATORY HOLD — AWAITING EXPLICIT FOUNDER AUTHORIZATION**
>
> In accordance with non-negotiable mission constraints, this document outlines the **exact, tested, step-by-step rotation plan**. 
> **NO MODIFICATIONS WILL BE MADE TO PRODUCTION CREDENTIALS OR RAILWAY CONFIGURATION WITHOUT SEPARATE EXPLICIT FOUNDER APPROVAL.**

---

## 1. Pre-Rotation Safety Checklist

Before executing the rotation command sequence:

1. **Verify Backup Status:**
   - Confirm Railway volume snapshot for `postgres-volume` (`98d55c95-78c2-44de-955c-0870e562884b`) is recent (< 24h).
   - Execute an on-demand logical backup (`pg_dump`) to secure S3 storage prior to role alterations:
     ```bash
     pg_dump -h tramway.proxy.rlwy.net -p 25367 -U postgres -d railway -F c -b -v -f pre_rotation_backup.dump
     ```
2. **Confirm Sandbox Unaffected:**
   - Confirm that active Sandbox development (`altaria.proxy.rlwy.net:17860`) remains decoupled.

---

## 2. Target Architecture Post-Rotation

To permanently eliminate single-point superuser exposure, production will adopt the dual-role security architecture established in Sandbox:

| Role Name | Privileges | Purpose | Connection Target |
| :--- | :--- | :--- | :--- |
| **`postgres`** | `rolsuper = True`, `rolbypassrls = True` | Migrations & Maintenance Only | `DATABASE_ADMIN_URL` |
| **`avenqo_app`** | `rolsuper = False`, `rolbypassrls = False` | Application Runtime Traffic | `DATABASE_URL` (FastAPI backend) |

---

## 3. Coordinated Zero-Downtime Execution Sequence

Upon receiving explicit founder authorization, the following sequence will be executed:

### Step 1: Role Creation & Privilege Provisioning
Connect via administrative connection and create the least-privilege role:
```sql
-- 1. Create runtime application role
CREATE ROLE avenqo_app WITH LOGIN PASSWORD '<NEW_AVENQO_APP_PASSWORD>' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;

-- 2. Grant schema and table access
GRANT CONNECT ON DATABASE railway TO avenqo_app;
GRANT USAGE ON SCHEMA public TO avenqo_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO avenqo_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO avenqo_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO avenqo_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO avenqo_app;
```

### Step 2: Rotate Administrative `postgres` Password
Invalidate the compromised credential by altering the superuser account:
```sql
-- 3. Invalidate compromised credential immediately
ALTER USER postgres WITH PASSWORD '<NEW_POSTGRES_SUPERUSER_PASSWORD>';
```

### Step 3: Update Railway Production Environment Variables
Update the production service environment via Railway CLI:
```bash
# 4. Set application connection string to use restricted avenqo_app role
railway variables --environment production --service Avenqo-Platform- \
  DATABASE_URL="postgresql://avenqo_app:<NEW_AVENQO_APP_PASSWORD>@postgres.railway.internal:5432/railway"

# 5. Set administrative password on Postgres service
railway variables --environment production --service Postgres \
  POSTGRES_PASSWORD="<NEW_POSTGRES_SUPERUSER_PASSWORD>"
```

### Step 4: Graceful Application Restart & Connection Pool Drain
Railway automatically triggers a rolling deployment when service variables are updated:
- New container spins up and establishes connection pool using `avenqo_app`.
- Health check on `api.avenqo.ca/health` confirms database connectivity.
- Old container drains in-flight requests and terminates gracefully.

### Step 5: Terminate Public TCP Proxy (Optional & Highly Recommended)
In Railway Console -> Postgres -> Settings -> Networking:
- Delete the public TCP proxy domain (`tramway.proxy.rlwy.net:25367`).
- All production microservices communicate via internal DNS (`postgres.railway.internal:5432`), eliminating the public attack surface entirely.

---

## 4. Post-Rotation Verification & Invalidation Proof

Immediately following rotation:
1. **Invalidation Check:**
   Attempt connection to `tramway.proxy.rlwy.net:25367` using the compromised password:
   - Expected Result: `OperationalError: password authentication failed for user "postgres"`.
2. **Production API Health Check:**
   ```bash
   curl -I https://api.avenqo.ca/health
   ```
   - Expected Result: `HTTP/2 200 OK` (Database connected, RLS active).
3. **Backup Cron Job Check:**
   Verify `avenqo-daily-backup` receives updated connection string.

---

## 5. Rollback Strategy

If an unexpected permission issue arises during `avenqo_app` deployment:
1. Revert `Avenqo-Platform-` `DATABASE_URL` to connect as `postgres` using the **newly rotated** password (`<NEW_POSTGRES_SUPERUSER_PASSWORD>`).
2. **STRICT RULE:** Under no circumstances will the compromised password (`aVxF...`) be restored as a rollback mechanism.

---

## 6. Formal Founder Authorization Request

```text
================================================================================
REQUEST FOR FOUNDER AUTHORIZATION — PRODUCTION CREDENTIAL ROTATION
================================================================================
Project: alert-tenderness (062bbe91-68e7-4e79-8de7-cffeb8a5f5cd)
Environment: production (b9b03d41-2a67-4aab-a6f6-32939d8b81e0)
Target Database: PostgreSQL 18.6 (tramway.proxy.rlwy.net:25367)
Affected Service: api.avenqo.ca (Avenqo-Platform-)

Action Requested:
1. Create least-privilege role 'avenqo_app' on production database.
2. Rotate 'postgres' superuser password, immediately invalidating GitGuardian secret.
3. Update production Railway variables with zero downtime.
4. Remove public TCP proxy port 25367.
================================================================================
```
