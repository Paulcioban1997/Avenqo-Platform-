# Avenqo P0 independent audit — 2026-11-05

## Scope and provenance

Repository: `Paulcioban1997/Avenqo-Platform-`. PR #87 is OPEN, head `fix/p0-stripe-billing-account-context-mismatch` at `ed07cf39474cd2e1deed6bd2f72e8bfd4b032d97`, base `integ/phase-f-pr83-pr84-sandbox` at `3dc87e7fb32f8b1b0c130693df300e5f9a464555`. The claimed implementation `4e4e2130ded9c49ac66ae98bbaf5ae4e88d0ed28` is a *child* of the PR head on `feat/p0-enterprise-contracts-ceo-command-center`; it is not in PR #87. The cited Antigravity report was not found in the repository. Review used the implementation commit, not the PR preview, as source of truth.

This is a code and local synthetic-test audit. No live Stripe, tenant, legal, database, Vercel, or Railway operation was performed. It does not certify legal validity or live financial accuracy.

## Evidence and claims

| Claim | Status | Evidence |
|---|---|---|
| 26 backend tests | VERIFIED locally | `python -m pytest -q tests/backend/test_enterprise_contracts_and_ceo_command_center.py tests/backend/test_contracts_and_onboarding.py tests/backend/test_subscription_gate.py`: 26 passed on unmodified `4e4e213`; 27 passed after the audit RBAC fix. |
| TypeScript and web build | VERIFIED locally | `npx tsc --noEmit` and `npm run build` exited 0 after `npm ci --ignore-scripts --no-audit --no-fund`. |
| Gitleaks zero secrets | NOT_TESTED | Gitleaks not installed; PR #87 GitGuardian SUCCESS applies to `ed07cf3`, not `4e4e213`. |
| Four-step onboarding and eight FR/EN templates | PARTIALLY_VERIFIED | Routes, models and templates exist; legal review, email verification, end-to-end real consent and live persistence were not established. |
| CEO 10 modules | PARTIALLY_VERIFIED | Ten route families exist in `backend/app/routers/ceo_command_center.py`; several reported values are derived from plan labels or static defaults rather than authoritative billing/health state. |
| Commercial/Stripe reconciliation | FAILED | `backend/app/services/commercial_reconciler.py` checks presence of a Price ID, not Stripe's actual amount, status, cadence or currency. Old add-on prices conflict with the approved catalog. |
| 15-minute single-use challenge | PARTIALLY_VERIFIED | Unit test covers expiry/replay, but `sign_contract_electronic()` skips challenge validation when omitted, the endpoint returns the code to the same caller, and `_CHALLENGES` is process memory. |
| Wet-ink independent verification | FAILED | A tenant owner/admin can approve their own upload through `/{contract_type}/verify-wet-ink`; service marks it `SIGNED` and `COMPLETED`. |
| PDF SHA-256 integrity | PARTIALLY_VERIFIED | Hash is of interpolated contract text, not final stored/downloaded PDF bytes. No trusted timestamp or independent signer verification. |
| Alembic 0072 | NOT_TESTED end-to-end | Disposable SQLite upgrade stopped in 0071 on PostgreSQL `::json`; no isolated PostgreSQL server was available. No active DB was touched. |
| RBAC separation | PARTIALLY_VERIFIED | Synthetic role tests pass after audit correction; broader cross-tenant HTTP attack matrix is incomplete. |
| Legal/incorporation gates | FAILED | `sign_contract_electronic()` has no check of `provider_incorporation_verified` or `provider_contracts_published`; those flags appear in status output only. |

## Critical findings

1. **P0 signature bypass and publication gate** — `backend/app/routers/contracts.py` makes challenge fields optional; `backend/app/services/contract_signature_service.py` verifies only when supplied and does not enforce incorporation/publication. A user can sign without the claimed challenge or legal release. Existing positive tests do precisely that. No real agreement was signed in this audit.
2. **P0 challenge exposure and durability** — `POST /signing-challenge` returns `verification_code` in its own response; `backend/app/services/signing_challenge_service.py` holds challenges in a process-local dictionary. This is not an independently verified or durable second factor.
3. **P0 wet-ink self-approval** — tenant owner/admin may approve a tenant's own uploaded signature. Independent verification and audit evidence are absent.
4. **P0 existing-customer access regression** — `backend/app/dependencies/subscription.py` requires new signed contract rows for every active/trialing account. Existing customers without those rows receive 403. No migration/backfill or grandfathering policy is established.
5. **P0/P1 evidence retention** — `CompanyContract.company_id` and `CompanyLegalProfile.company_id` use cascading company deletion, risking destruction of contractual evidence. The migration requires a retention design before activation.
6. **P1 executive metrics** — `get_executive_overview()` counts active companies with a named plan as paying and computes MRR from fixed Base/Professional list prices without confirmed active Stripe subscriptions, annual normalization, discounts, enterprise terms or currency. Connector heartbeat and encryption fields are hardcoded. These numbers must not be used as verified financial or operational data.
7. **P1 commercial configuration** — reconciler's extra-credit terms list 6,500/25,000/65,000 packs whereas the founder-approved catalog is 1,000/4,000/10,000. It asserts Quebec taxes solely from CAD currency. No live Stripe catalog comparison was made. Mark `COMMERCIAL_CONFIG_MISMATCH` until resolved by the catalog owner.
8. **P1 PDF evidence** — final PDF can be rewritten on countersign and is not byte-hashed. “Certified” and “opposable” language is unsupported by the controls inspected.

## Remediation performed

The audit branch removes the implicit superadmin fallback for a platform-admin user without an explicit platform role and limits the countersign route to `PLATFORM_SUPER_ADMIN`. A negative role test was added. Other findings remain release blockers; broad contract-state, billing and migration changes require coordinated design and independent tests rather than speculative edits.

## Residual risk

No live multi-tenant HTTP attack suite, real Stripe test flows, provider signature verification, isolated PostgreSQL 0072 run, PDF visual review, Gitleaks run or full GitHub CI for `4e4e213` was established. No Production system was modified. Verdict: **NO-GO**.

The existing `web` lint command exited 1 with 5,524 errors, including the vendored CanvasKit browser bundle and application files. No lint rule was weakened to make the audit pass.
