# AVENQO — PHASE 8.0 POSTGRESQL MULTI-TENANT SECURITY AUDIT
## Database Security Architecture, Role Least-Privilege & RLS Hardening Report

**Date:** 2026-10-17  
**Auditor:** Principal SaaS Architect & PostgreSQL Security Engineer  
**Target Environment:** Railway Sandbox (`alert-tenderness` / `sandbox`)  
**PostgreSQL Instance:** `altaria.proxy.rlwy.net:17860` (internal: `postgres.railway.internal:5432`)  
**Engine Version:** PostgreSQL 18.6 (Debian 18.6-1.pgdg13+2) on x86_64-pc-linux-gnu  
**Git Branch / Commit:** `promotion/sandbox` @ `6523f80`  

---

## 1. Live Database Session & Role Identity Inspection

A comprehensive read-only diagnostic was conducted directly against the active Railway Sandbox PostgreSQL database:

```json
{
  "current_user": "postgres",
  "session_user": "postgres",
  "version": "PostgreSQL 18.6 (Debian 18.6-1.pgdg13+2) on x86_64-pc-linux-gnu, compiled by gcc (Debian 14.2.0-19) 14.2.0, 64-bit",
  "current_database": "railway",
  "current_schema": "public"
}
```

### Application Connection Role Attributes
```json
{
  "rolname": "postgres",
  "rolsuper": true,
  "rolinherit": true,
  "rolcreaterole": true,
  "rolcreatedb": true,
  "rolcanlogin": true,
  "rolreplication": true,
  "rolconnlimit": -1,
  "rolbypassrls": true
}
```

### Architectural Finding & Vulnerability Disclosure
> [!CRITICAL]
> **RLS Engine Bypass by Superuser Connection:**  
> The deployed application runtime connects using the PostgreSQL cluster owner role `postgres`. Because `rolsuper = true` and `rolbypassrls = true`, PostgreSQL's internal database engine automatically bypasses Row-Level Security evaluation on all tables, regardless of `FORCE ROW LEVEL SECURITY`.  
> 
> **Current Tenant Isolation Mechanism:**  
> Tenant isolation currently relies **entirely on the application layer** (SQLAlchemy query constraints with explicit `WHERE company_id = :cid` and FastAPI dependency route validation).  
> 
> **Remediation Priority:** **HIGH (Pre-Production Blocker)**. To achieve true defense-in-depth where a database-level breach or raw SQL injection cannot cross tenant boundaries, the application must connect via a constrained least-privilege role (`avenqo_app`).

---

## 2. Table Inventory & Row-Level Security (RLS) Status

- **Total Public Tables:** 92
- **RLS Enabled Tables:** 81
- **Tables with FORCE ROW LEVEL SECURITY:** 81

All 81 business and tenant-sensitive tables have RLS policies configured:
```sql
CREATE POLICY {table}_tenant_isolation ON public.{table}
AS PERMISSIVE
FOR ALL
TO public
USING (company_id = avenqo_tenant_id())
WITH CHECK (company_id = avenqo_tenant_id());
```

And for dataset child tables without direct `company_id` (`dataset_profiles`, `dataset_versions`, `data_quality_reports`, `mappings`):
```sql
CREATE POLICY {table}_tenant_isolation ON public.{table}
AS PERMISSIVE
FOR ALL
TO public
USING (dataset_id IN (SELECT id FROM datasets WHERE company_id = avenqo_tenant_id()))
WITH CHECK (dataset_id IN (SELECT id FROM datasets WHERE company_id = avenqo_tenant_id()));
```

---

## 3. Tenant Context Function & Setting Convention Analysis

### PostgreSQL Resolver Function
The active database function `avenqo_tenant_id()` is defined as:
```sql
CREATE OR REPLACE FUNCTION public.avenqo_tenant_id()
RETURNS uuid
LANGUAGE plpgsql
STABLE
AS $function$
BEGIN
  RETURN NULLIF(current_setting('app.current_company_id', true), '')::uuid;
EXCEPTION WHEN others THEN
  RETURN NULL;
END;
$function$;
```

### Convention Resolution: `app.current_company_id` vs `app.current_tenant_id`
1. The 81 existing PostgreSQL policies call `avenqo_tenant_id()`.
2. `avenqo_tenant_id()` queries `current_setting('app.current_company_id', true)`.
3. Some newer AI modules referenced `app.current_tenant_id`.
4. **Hardening Action Taken:**  
   In `backend/app/services/tenant_rls.py`, the transaction context binding SQL was updated to:
   ```python
   _CONTEXT_SQL = text(
       "SELECT set_config('app.current_company_id', :cid, true), "
       "set_config('app.current_tenant_id', :cid, true), "
       "set_config('app.bypass_rls', :flag, true)"
   )
   ```
   Setting both GUC parameters transaction-locally (`is_local=true`) ensures that any policy, trigger, stored procedure, or application layer code referencing either `app.current_company_id` or `app.current_tenant_id` receives the identical, authenticated UUID.

### Fail-Closed Behavior Verification
- When no transaction context is set, `current_setting('app.current_company_id', true)` returns `NULL`.
- `avenqo_tenant_id()` returns `NULL`.
- The RLS condition `company_id = NULL` evaluates to `UNKNOWN` in SQL 3-valued logic.
- Result: **0 rows returned, all inserts/updates/deletes denied**. The policy is strictly fail-closed.

---

## 4. Connection Pooling & Context Isolation Analysis

### Connection Lifecycle & Leakage Prevention
1. **Transaction Scoping:**  
   Context is bound via PostgreSQL `set_config(..., true)` (equivalent to `SET LOCAL`), which automatically expires when the SQL transaction commits or rolls back.
2. **Session Reset Event:**  
   In `backend/app/database/session.py`, `get_db()` runs:
   ```python
   finally:
       session.rollback()
       info = getattr(session, "info", None)
       if isinstance(info, dict):
           info.pop("avenqo_rls", None)
       session.close()
   ```
   This ensures that when a physical database connection is returned to SQLAlchemy's connection pool, no residual tenant context remains.
3. **Automated Pool Tests:**  
   The test suite `tests/security/test_tenant_execution_reset.py` and `test_rls_session_context.py` validated that subsequent transactions cannot see or inherit previous tenant bindings (92 passed tests).

---

## 5. Dedicated Application Role Design (`avenqo_app`)

The least-privilege role architecture is codified in `backend/app/services/postgres_app_role.py` and Alembic migration `0058_sandbox_app_db_roles.py`:

```sql
-- 1. Schema Owner Role (No Login)
CREATE ROLE avenqo_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;

-- 2. Privileged Migration Role (Used by Alembic runner)
CREATE ROLE avenqo_migrate NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
GRANT avenqo_owner TO avenqo_migrate;
GRANT USAGE, CREATE ON SCHEMA public TO avenqo_migrate;
GRANT CONNECT ON DATABASE railway TO avenqo_migrate;

-- 3. Application Runtime Role (Used by FastAPI backend)
CREATE ROLE avenqo_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
GRANT USAGE ON SCHEMA public TO avenqo_app;
GRANT CONNECT ON DATABASE railway TO avenqo_app;

-- 4. Granular DML Grants
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO avenqo_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO avenqo_app;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO avenqo_app;
REVOKE CREATE ON SCHEMA public FROM avenqo_app;
```

### Role Attribute Verification
```
avenqo_app: super=False, bypassrls=False, canlogin=False, createdb=False, createrole=False
avenqo_migrate: super=False, bypassrls=False, canlogin=False, createdb=False, createrole=False
```

---

## 6. Staged Migration Plan to Live Non-Superuser Role

To transition the live Railway Sandbox database from `postgres` to `avenqo_app` without downtime or service disruption:

### Step 1: Pre-Cutover Verification (Current Phase 8.0 State)
- `avenqo_app` role created with correct privileges.
- All 81 tenant tables have RLS and FORCE RLS enabled.
- `tenant_rls.py` binds transaction context on every checkout/autobegin.
- Background tasks and Celery runners explicitly initialize tenant context.

### Step 2: Role Password Provisioning (Requires Founder Approval)
1. Generate high-entropy cryptographic password for `avenqo_app` (stored in Railway secret vault, never in Git).
2. Execute role login activation:
   ```sql
   ALTER ROLE avenqo_app WITH LOGIN PASSWORD '<CRYPTO_SECURE_PASSWORD>';
   ```

### Step 3: Canary Rehearsal on Disposable Staging Database
Execute full test suite against an isolated PostgreSQL instance connected as `avenqo_app` to verify that all reads, writes, and migrations function seamlessly without superuser privileges.

### Step 4: Railway Variable Cutover
1. Update `DATABASE_URL` in Railway service environment:
   ```
   postgresql://avenqo_app:<PASSWORD>@postgres.railway.internal:5432/railway
   ```
2. Monitor Railway deployment health checks (`/api/v1/health/liveness`).

### Step 5: Rollback Procedure
If any unexpected query failures occur due to table permissions:
1. Revert `DATABASE_URL` in Railway dashboard back to `postgresql://postgres:...`.
2. Railway redeploys the service within 60 seconds.

> [!CAUTION]
> **Approval Gate Status:**  
> The migration script and role design are complete and verified. Per mission constraints, **no live database credentials or role cutovers will be executed without explicit founder authorization**.
