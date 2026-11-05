# Avenqo P0 remediation changelog — 2026-11-05

## Re-audit changes on the same isolated branch

| Severity | Change and test evidence | Remaining limitation |
|---|---|---|
| P0 | Published implementation ancestry verified; typing fix `93316c4` cherry-picked as `876a983`. | PR #87 remains unchanged; separate remediation PR must target the feature branch. |
| P0 | New `ContractSigningChallenge` table and additive 0073 migration; eight-digit salted PBKDF2 code, 15-minute expiry, five attempts, tenant/user/document/version/commercial snapshot binding and conditional single-use SQL update. Adversarial tests cover wrong code, cross-tenant, altered terms, expiry, lockout and replay. | PostgreSQL concurrency and multi-worker tests not run; real out-of-band email configuration not tested. |
| P0 | API sends code to verified email only, returns no code; frontend requires manual entry. Signing requires challenge, verified email, consent, and provider incorporation/publication release; countersign and wet-ink review require explicit platform superadmin. Synthetic-only approval fixtures exercise the positive path. | Legal templates are not approved; no real signature was made. |
| P0 | Customer-only signing uses `CUSTOMER_SIGNED`; only that state may be countersigned. Pending wet-ink documents cannot be countersigned; tenant owner cannot self-approve. | Existing legacy `SIGNED` records need separate adjudication; do not auto-promote. |
| P0 | Generic active subscription check no longer blocks established customers for missing new contracts. New checkout and plan-change routes require the separate legal/contract gate. | Stripe webhook activation and all onboarding paths still need full integration review. |
| P0 | Billing regression suite 54/54 PASS. A negative checkout test confirms 403 when legal governance is unavailable; two currency/subscription-flow tests bypass the legal dependency only within their synthetic fixtures. | Real Stripe checkout remains prohibited until legal release and end-to-end validation. |
| P1 | Final PDF digest stored in `pdf_sha256`, checked on download; synthetic tamper test returns 500. | Legacy PDFs without digest remain unverified; retention and external timestamping unresolved. |
| P1 | CEO MRR/ARR/churn and connector heartbeat are marked unavailable/unknown rather than fabricated; synthetic inactive-billing test passes. | Authoritative Stripe totals, discounts, currency conversion and dated churn are not implemented. |
| P1 | Removed stale extra-credit amounts from agreement prose; no commercial price or entitlement changed. | Approved add-on catalog still differs from `payments/plans.py`. |
| P1 | Portable JSON defaults in migrations 0071/0072; disposable SQLite chain through 0073 passed. | Isolated PostgreSQL run not yet possible with the available local daemon. |

All remediation was on the audit branch. No Production data, legal flag, customer agreement, payment or infrastructure was changed.

## Fixed in isolated audit branch

| Severity | Reproduction and root cause | Change | Evidence | Limitation |
|---|---|---|---|---|
| P0 | A user with `is_platform_admin=True` and `platform_role=None` was treated as `PLATFORM_SUPER_ADMIN` by `require_platform_role`. | `backend/app/dependencies/auth.py`: require one of four explicit platform roles; reject missing/unknown roles with 403. | New `test_platform_admin_without_explicit_role_cannot_use_executive_endpoints`; targeted backend suite 27/27 PASS. | Role assignment provenance and live sessions were not tested. |
| P0 | Countersign route used `require_platform_admin`, admitting every platform admin role. | `backend/app/routers/contracts.py`: require `PLATFORM_SUPER_ADMIN`. | Dependency code inspection and targeted suite 27/27 PASS. | End-to-end HTTP negative test and founder signature authorization remain outstanding. |

Remediation commit SHA: `11ed7d9d7a6035a3655a26eef7b50a44255a9438`. No deployed artifact exists.

## Prior audit findings and remaining gaps

- Challenge omission, same-channel code exposure, in-memory persistence, legal gate bypass, wet-ink self-approval, existing-customer access regression, and invented financial displays are addressed in the unmerged remediation above. They still require review and deployment validation.
- Contract record cascading deletion and isolated PostgreSQL migration/concurrency validation remain open.
- PDF digest is now checked for new documents; legacy PDFs remain unverified and retention remains open.

These require separate focused fixes and a verified integration gate. No real customer records, subscriptions, signatures, legal flags or Production configuration were changed.
