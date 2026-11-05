# Avenqo P0 remediation changelog — 2026-11-05

## Fixed in isolated audit branch

| Severity | Reproduction and root cause | Change | Evidence | Limitation |
|---|---|---|---|---|
| P0 | A user with `is_platform_admin=True` and `platform_role=None` was treated as `PLATFORM_SUPER_ADMIN` by `require_platform_role`. | `backend/app/dependencies/auth.py`: require one of four explicit platform roles; reject missing/unknown roles with 403. | New `test_platform_admin_without_explicit_role_cannot_use_executive_endpoints`; targeted backend suite 27/27 PASS. | Role assignment provenance and live sessions were not tested. |
| P0 | Countersign route used `require_platform_admin`, admitting every platform admin role. | `backend/app/routers/contracts.py`: require `PLATFORM_SUPER_ADMIN`. | Dependency code inspection and targeted suite 27/27 PASS. | End-to-end HTTP negative test and founder signature authorization remain outstanding. |

Remediation commit SHA: recorded in the audit branch Git history after commit; these files are generated before commit. No deployed artifact exists.

## Confirmed but unresolved

- Signature challenge omission, same-channel code exposure, in-memory challenge persistence and legal gate bypass.
- Tenant wet-ink self-approval, missing independent verifier and unsigned PDF byte integrity.
- Subscription gate regression for existing active customers without new contracts.
- Financial and connector health values presented as real despite incomplete source verification.
- Contract record cascading deletion and unvalidated 0072 PostgreSQL migration.

These require separate focused fixes and a verified integration gate. No real customer records, subscriptions, signatures, legal flags or Production configuration were changed.
