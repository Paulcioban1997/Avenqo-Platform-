# AVENQO — PHASE 8.0 FOUNDER APPROVAL GATES
## Formal Authorization Checklist for Production Cutover & Privileged Operations

**Date:** 2026-10-17  
**Principals:** Paul & Andrew (Co-Founders, Avenqo / PMC Solutions AI Inc.)  
**Security Governance Principle:** **Strict Least-Privilege & Zero-Unilateral-Cutover**

---

In accordance with Phase 8.0 governance rules, the engineering team has audited, implemented, and verified all components on the codebase, non-production test suites, and read-only diagnostics.

The following operations are **STRICTLY BLOCKED** until explicit, written founder authorization is granted:

---

### Gate 1: Live Sandbox PostgreSQL Role Cutover (`avenqo_app`)
- **Description:** Activating `LOGIN` for role `avenqo_app` with a high-entropy password in Railway's vault, and switching the live backend `DATABASE_URL` from `postgres` to `avenqo_app`.
- **Why it Requires Approval:** This alters the live database connection string on the Railway Sandbox instance and activates PostgreSQL engine-level RLS enforcement.
- **Risk Assessment:** Low to Moderate. Role has been verified to have full DML grants on all 92 tables and functions. Rollback takes under 60 seconds (reverting `DATABASE_URL` in Railway).
- **Prerequisites Met:**
  - `avenqo_app` role created in PostgreSQL cluster with `NOSUPERUSER, NOBYPASSRLS, NOCREATEDB`.
  - All 81 tenant tables have RLS and FORCE RLS enabled.
  - 92 automated security and session reset tests passed.
  - `_CONTEXT_SQL` updated to bind both `app.current_company_id` and `app.current_tenant_id`.
- **Status:** **PENDING FOUNDER APPROVAL**
- [ ] **Authorized by Founder:** `______________________` **Date:** `__________`

---

### Gate 2: GitGuardian Incident Formal Resolution & Credential Rotation
- **Description:** Marking GitGuardian alert `daea4ce0839e0839f2a44a6ffc6b5e08b1a51166` as resolved in the GitGuardian web console, and optionally rotating the sandbox test user password in the Railway database.
- **Why it Requires Approval:** Involves external security dashboard status changes and live user password updates.
- **Risk Assessment:** Negligible. Forensic investigation confirmed the alert was triggered by placeholder dummy strings on a transient pruned branch. No production keys were exposed.
- **Prerequisites Met:**
  - Commit `daea4ce08` confirmed unreachable on all repository branches.
  - All test scripts parameterized to use environment variables (`AVENQO_E2E_PASSWORD`).
  - Working tree scanned with 0 secrets detected.
- **Status:** **PENDING FOUNDER APPROVAL**
- [ ] **Authorized by Founder:** `______________________` **Date:** `__________`

---

### Gate 3: Live Stripe External Billing Calls & Real Subscriptions
- **Description:** Upgrading Stripe gateway from test mode (`sk_test_...`) to live mode (`sk_live_...`) or initiating real payment charges against customer credit cards.
- **Why it Requires Approval:** Involves real financial transactions, merchant acquiring agreements, and customer credit cards.
- **Current State:** The platform is configured in strict Stripe test mode (`sk_test_51Tg86nK4vojCzpX2...`). All plan upgrades and credit additions are simulated.
- **Status:** **STRICTLY PROHIBITED (Phase 8.0)**
- [ ] **Authorized by Founder:** `______________________` **Date:** `__________`

---

### Gate 4: Telnyx Live Telephony Inbound Number Purchasing
- **Description:** Purchasing real Canadian/US DID telephone numbers and provisioning live SIP trunks on Telnyx for inbound voice bot routing.
- **Why it Requires Approval:** Telephony carrier charges apply per inbound/outbound minute and per DID monthly rental fee.
- **Current State:** Voice prompts, system instructions, caller verification, and audio streaming architecture are verified. Live PSTN telephony purchasing remains staged.
- **Status:** **STRICTLY PROHIBITED (Phase 8.0)**
- [ ] **Authorized by Founder:** `______________________` **Date:** `__________`

---

### Gate 5: Any Changes to the Production Environment
- **Description:** Any modification, deployment, migration, or environment variable change targeting production infrastructure or production customer data.
- **Why it Requires Approval:** Production is strictly off-limits during Phase 8.0 Sandbox verification.
- **Current State:** 100% of operations were confined to branch `promotion/sandbox`, Railway Sandbox, and Vercel Sandbox.
- **Status:** **STRICTLY OFF-LIMITS**
- [ ] **Authorized by Founder:** `______________________` **Date:** `__________`
