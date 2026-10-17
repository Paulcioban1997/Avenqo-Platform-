# AVENQO — PHASE 8.2.1
## GITGUARDIAN ACTIVE TEST CREDENTIAL ROTATION & REMEDIATION PLAN

**Priority:** P0 — SECURITY INCIDENT RESOLUTION  
**Role:** Senior DevSecOps Incident Responder  
**Repository:** `Paulcioban1997/Avenqo-Platform-`  
**Branch:** `promotion/sandbox`  
**Environment:** STRICTLY SANDBOX ONLY  
**Current Status:** **`PREPARED_AWAITING_APPROVAL`**

---

## 1. Incident Forensics & Target Account Identification

A dedicated forensic investigation was conducted to pinpoint the target account and credentials flagged in GitGuardian incident alerts for commits `1d1065bb0b0a37eca89d79226f83167131979fa5` and `daea4ce0839e0839f2a44a6ffc6b5e08b1a51166`.

### Target Account Classification

| Property | Value / Finding |
| :--- | :--- |
| **Account Email** | `alex.physio.sandbox@avenqo.ca` |
| **Database User ID** | `5eaacdf7-e8dd-458c-86de-7e5527188309` |
| **Associated Company** | `838184d8-77c3-4aeb-a0bf-46394dd5c695` (Avenqo Physio Clinic Sandbox) |
| **User Role** | `OWNER` (Scoped strictly to the sandbox company) |
| **Production Risk** | **ZERO.** Account has no access to production databases, Stripe live keys, AWS/Railway cloud infrastructure, or real customer data. |
| **Credential Classification** | **`TEST_CREDENTIAL_ACTIVE`** |
| **Credential Validity Check** | Verified: The account in the Sandbox PostgreSQL instance remains active with a valid Argon2 hash. |

---

## 2. Comprehensive Dependency Mapping

Every test script, automation fixture, and CI workflow referencing or depending upon `alex.physio.sandbox@avenqo.ca` was audited:

| Script / Component | Purpose | Current Credential Resolution Method | Action Required |
| :--- | :--- | :--- | :--- |
| **`scripts/run_playwright_e2e.mjs`** | Legacy Playwright smoke test runner | Parameterized via `process.env.AVENQO_E2E_PASSWORD` | **REMEDIATED** (Hardcoded string removed) |
| **`scripts/verify_phase7_8_playwright.mjs`** | Phase 7.8 UI & CRM verification | Parameterized via `process.env.AVENQO_E2E_PASSWORD` | Clean (Uses env variable) |
| **`scripts/verify_phase7_9_playwright.mjs`** | Phase 7.9 CRM wizard & hours verification | Parameterized via `process.env.AVENQO_E2E_PASSWORD` | Clean (Uses env variable) |
| **`scripts/verify_phase8_0_commercial_acceptance.mjs`** | Commercial landing & multi-tenant acceptance | Parameterized via `process.env.AVENQO_E2E_PASSWORD` | Clean (Uses env variable) |
| **`scripts/prepare_playwright_user.py`** | Database user provisioner | Parameterized via `os.environ.get("AVENQO_E2E_PASSWORD")` | Clean (Uses env variable) |
| **GitHub Actions Workflows** | CI test runners | Uses isolated ephemeral PostgreSQL containers with `test-only-password` | No dependency on live sandbox user |

---

## 3. Cryptographically Secure Replacement Preparation

Per policy constraints, no plaintext password values are printed to terminal outputs, reports, or commit history.

- **Entropy Standard:** Generated using Python's `secrets.choice` across a 28-character space including uppercase, lowercase, numbers, and high-entropy symbols (`len >= 28`, entropy > 140 bits).
- **Hashing Function:** Processed using `backend.app.core.security.hash_password` (Argon2id default scheme, memory cost 64MB, time cost 3 iterations).
- **Automated Tool Created:** `scripts/rotate_sandbox_e2e_credential.py`

### Dry-Run Verification Evidence

```
================================================================================
AVENQO PHASE 8.2.1: SANDBOX CREDENTIAL ROTATION AUDIT
Target Account: alex.physio.sandbox@avenqo.ca
Mode: DRY RUN (INSPECTION ONLY)
================================================================================
User Record Found: ID=5eaacdf7-e8dd-458c-86de-7e5527188309, Role=UserRole.OWNER, CompanyID=838184d8-77c3-4aeb-a0bf-46394dd5c695
Current Password Hash Scheme: $argon2id$v=... (length=97)
New Password Hash Scheme: $argon2id$v=... (Argon2 / Recommended)

[DRY RUN SUMMARY]
1. Target account verified in Sandbox database.
2. Cryptographically secure replacement generated in memory.
3. Live database was NOT modified (awaiting founder approval).
4. To commit rotation, obtain authorization and run with '--execute'.
```

---

## 4. Formal Founder Approval Request

> [!IMPORTANT]
> **MANDATORY HOLD — AWAITING FOUNDER AUTHORIZATION**
>
> In accordance with user instruction Rule 7 (*"STOP before changing any live account password or credentials and request explicit founder approval identifying the affected account and services"*), the live database mutation has been held.
>
> **Affected Account:** `alex.physio.sandbox@avenqo.ca`  
> **Target Environment:** Sandbox PostgreSQL (`altaria.proxy.rlwy.net:17860`)  
> **Downstream Services Affected:** Playwright E2E verification suites (requires setting the new `AVENQO_E2E_PASSWORD` in the execution environment).  
> **Production / Customer Impact:** None.  
>
> **Action Requested from Founder:**
> Grant explicit written authorization to execute:
> ```bash
> python scripts/rotate_sandbox_e2e_credential.py --execute
> ```

---

## 5. Execution & Verification Workflow (Post-Approval)

Once founder approval is confirmed:

1. **Database Rotation:**
   Execute `python scripts/rotate_sandbox_e2e_credential.py --execute`.
2. **Invalidation Verification:**
   The script automatically verifies:
   - `verify_password(new_password, updated_hash) == True`
   - `verify_password(old_password, updated_hash) == False`
3. **Secret Storage Update:**
   Update repository secret `AVENQO_E2E_PASSWORD` via GitHub CLI:
   ```bash
   gh secret set AVENQO_E2E_PASSWORD --body "<new_entropy_string>"
   ```
4. **Scanner Re-validation:**
   - Execute `python scripts/check_secrets.py` (Must report 0 leaks).
   - Execute `gitleaks detect` (Must report 0 leaks).
5. **GitGuardian Incident Closure:**
   Navigate to GitGuardian console for incidents #14800366 and mark as **Resolved (Credential Rotated)**.

---

## 6. Status Determination

- `PREPARED_AWAITING_APPROVAL` — **CURRENT STATUS** (All tooling, dry-run checks, and dependency mappings are complete; live write held awaiting founder approval).
- `ROTATED_PENDING_CLOSURE` — Status once rotation is executed and verified.
- `RESOLVED_AND_VERIFIED` — Status once GitGuardian incident dashboard is confirmed closed.
