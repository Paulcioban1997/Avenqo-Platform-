# AVENQO — PHASE 8.1
## POSTGRESQL ROW-LEVEL SECURITY & TENANT ISOLATION REGRESSION REPORT

**Date:** October 17, 2026  
**Security Standard:** Zero Cross-Tenant Data Leakage  
**Database Role Under Test:** `avenqo_app` (least-privilege application role)  
**Evaluated Tenants:**
1. `Produits_Ero` (`9c97cb94-e9f9-46fb-afd4-8a1d21019cff`)
2. `Avenqo Physio Clinic Sandbox` (`838184d8-77c3-4aeb-a0bf-46394dd5c695`)

---

### 1. ROLE ATTRIBUTES & LEAST-PRIVILEGE AUDIT

An automated SQL role attribute inspection was executed on the active Railway Sandbox PostgreSQL database:

```sql
SELECT rolname, rolsuper, rolbypassrls, rolcanlogin 
FROM pg_roles 
WHERE rolname = current_user;
```

**Results:**
- `current_user`: `avenqo_app`
- `rolsuper`: `False` (Zero superuser privileges)
- `rolbypassrls`: `False` (Zero RLS bypass capability)
- `rolcanlogin`: `True` (Application login enabled)

**Audit Finding:** `avenqo_app` is strictly bounded by all PostgreSQL table Row-Level Security policies.

---

### 2. DUAL-VARIABLE SESSION CONTEXT VERIFICATION

PostgreSQL RLS policies in Avenqo check both `app.current_company_id` and `app.current_tenant_id` to prevent unauthenticated access. 

When a session sets tenant context:
```sql
SELECT set_config('app.current_company_id', :cid, false), 
       set_config('app.current_tenant_id', :cid, false);
```

**Cross-Tenant Isolation Test Matrix:**

| Table Under Test | Query Under Tenant A (`Produits_Ero`) | Query Under Tenant B (`Physio Clinic`) | Direct SQL Cross-Query (`WHERE company_id = Tenant B` under Tenant A) | Isolation Status |
| :--- | :--- | :--- | :--- | :--- |
| `crm_appointments` | 7 records | 15 records | **0 records (Filtered by RLS)** | **PASS** |
| `ai_enterprise_memories` | 1 record | 0 records | **0 records (Filtered by RLS)** | **PASS** |
| `tenant_documents` | 1 record (`facture_fournisseur_bureau_8812.pdf`) | 1 record (`contrat_prestation_physio_2026.pdf`) | **0 records (Filtered by RLS)** | **PASS** |
| `accounting_invoices` | 1 draft + confirmed | 0 records | **0 records (Filtered by RLS)** | **PASS** |
| `automation_workflows` | 0 records | 1 record (`Auto-tâche nouveau doc`) | **0 records (Filtered by RLS)** | **PASS** |
| `voice_calls` | 0 records | 1 record (`VoiceCall` Marie Larouche) | **0 records (Filtered by RLS)** | **PASS** |

---

### 3. ENTERPRISE MEMORY ISOLATION

In Phase 8.1, Central AI can persist strategic facts and operational preferences.
- Company preference stored under Tenant A: `"Préférence stratégique Produits_Ero : Toujours expédier les commandes VIP sous 24h avec emballage premium."`
- Tenant A recall query (`query="expédier commandes VIP"`):
  - Returned: 1 record (`id=5f6dfbe5-8425-483d-939b-e48e2a7afbae`).
- Tenant B probe query (`query="expédier commandes VIP"` under context `838184d8-77c3-4aeb-a0bf-46394dd5c695`):
  - Returned: **0 records**.
  - Content check: Zero occurrences of `Produits_Ero` or VIP shipping text in Tenant B responses.

---

### 4. GITGUARDIAN & CREDENTIAL AUDIT

- **Historical Classification:** A prior GitGuardian scan flagged historical commit references containing test sandbox tokens. These were classified as sandbox-only credentials and isolated.
- **Current Runtime Verification:**
  - Active runtime credentials for `avenqo_app` are dynamically read from Railway environment variables (`DATABASE_URL`).
  - No database passwords, JWT signing keys, or live API credentials are hardcoded in application repository code.
  - Secret scanning (`scripts/check_secrets.py`) confirms clean working tree and zero exposed live production secrets.

---

### 5. REGRESSION VERDICT

**POSTGRESQL RLS ENFORCEMENT IS 100% OPERATIONAL.**  
Zero regressions detected. Multi-tenant isolation is enforced at both the SQLAlchemy ORM layer and the PostgreSQL kernel engine layer.
