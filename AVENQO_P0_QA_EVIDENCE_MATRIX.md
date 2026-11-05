# Avenqo P0 QA evidence matrix — 2026-11-05

## PR #88 CEO API hotfix revalidation

| Requirement | Evidence | Result |
|---|---|---|
| Revenue HTTP API | Synthetic invoices with different issue dates and amounts; platform CEO and tenant principal | 200, newest first, mapped amount/currency/date; tenant principal 403 |
| Security audit HTTP API | Empty and populated safe metadata, nested sensitive keys, finance principal | 200 for CEO; nested sensitive values redacted; finance principal 403 |
| AI usage HTTP API | Two recorded credit settlements and provider attempts, 7d/30d filters | Recorded credits and USD costs vary by window; CAD conversion, model tiers and anomaly count explicitly unavailable |
| Focused CEO tests | `python -m pytest -q tests/backend/test_ceo_api_hotfix.py --tb=short` | 3 PASS |
| Contract/security/migration tests | `python -m pytest -q tests/backend/test_ceo_api_hotfix.py tests/backend/test_enterprise_contracts_and_ceo_command_center.py tests/backend/test_contracts_and_onboarding.py tests/backend/test_subscription_gate.py tests/backend/test_phase34_migrations.py --tb=short` | 42 PASS |
| Billing regressions | `python -m pytest -q tests/backend/test_billing.py tests/backend/test_master_security_and_billing.py tests/backend/test_phase33_billing_admin.py --tb=short` | 54 PASS |
| Frontend | `npx tsc --noEmit`; `npm run build` in `web` | PASS; 57 static pages |

All fixtures are synthetic. No Production API, customer record or credit balance was changed. Prior baseline sections below describe historical states, not the current PR verdict.

## Re-audit results (newer than the baseline table below)

| Requirement | Evidence | Test | Actual result | Status |
|---|---|---|---|---|
| Published source SHA | GitHub remote branch and local graph | `git fetch origin feat/p0-enterprise-contracts-ceo-command-center`; `git rev-parse origin/feat/...` | Exact `4e4e2130ded9c49ac66ae98bbaf5ae4e88d0ed28` | VERIFIED |
| Security/contracts/subscription regressions | Synthetic SQLite fixtures | `python -m pytest -q tests/backend/test_enterprise_contracts_and_ceo_command_center.py tests/backend/test_contracts_and_onboarding.py tests/backend/test_subscription_gate.py --tb=short` | 30 passed after remediation | VERIFIED |
| Billing regressions and contract gate | Synthetic billing fixtures | `python -m pytest -q tests/backend/test_billing.py tests/backend/test_master_security_and_billing.py tests/backend/test_phase33_billing_admin.py --tb=short` | 54 passed; separate negative checkout test rejects unapproved legal governance with 403. Two billing-only positive tests use a local dependency override to isolate currency/subscription mechanics. | VERIFIED in test |
| Out-of-band challenge | Fake notifier and direct route test | `test_challenge_is_sent_out_of_band_and_not_returned_to_browser` | Browser result contains ID/expiry only; one fake email captured | VERIFIED in mock |
| Legal release | Default settings false; synthetic approved settings confined to test objects | `test_unpublished_provider_and_absent_challenge_fail_closed` | Unpublished signing and missing challenge rejected | VERIFIED in test |
| PDF tampering | Synthetic signed PDF under temporary artifact root | `test_electronic_signature_flow` | Stored digest matches; modified bytes produce HTTP 500 | VERIFIED in test |
| CEO financial provenance | Inactive synthetic BillingAccount | `test_ceo_financials_do_not_invent_paid_customers_or_mrr` | Paying count 0; MRR/ARR/churn unavailable; connector heartbeat UNKNOWN | VERIFIED in test |
| SQLite migration compatibility | Disposable SQLite file | `python -m alembic upgrade 0073_contract_signing_challenges`; `python -m alembic current` | Chain 0071→0072→0073 succeeded; head 0073 | VERIFIED on SQLite |
| PostgreSQL migration and concurrency | No local PostgreSQL daemon; Docker Desktop daemon unavailable | Isolated PostgreSQL rehearsal | Not run; no active DB touched | NOT_VERIFIED |
| Web checks | Modified contract/CEO components | `npx tsc --noEmit`; `npm run build` | Both exit 0 | VERIFIED |
| Source secret scan | Staged changes and source directories | Gitleaks v8.30.1 | Prior staged and source scans found no leaks; rerun required on final diff | PENDING |

The baseline table below records the original implementation and should not be read as the status of the remediated branch.

| Requirement | Evidence | Test | Actual result | Status |
|---|---|---|---|---|
| PR/commit identity | `gh pr view 87`, `git show 4e4e213`, GitHub commit API and `git ls-remote` | Compare ancestry and refs | PR head `ed07cf3`; `4e4e213` is later on an unpublished local branch; GitHub returned 422 for its SHA | VERIFIED |
| Backend targeted regression | Three backend test files | `python -m pytest -q tests/backend/test_enterprise_contracts_and_ceo_command_center.py tests/backend/test_contracts_and_onboarding.py tests/backend/test_subscription_gate.py` | 26 PASS baseline; 27 PASS after RBAC fix | VERIFIED |
| TypeScript | `web` | `npx tsc --noEmit` | Exit 0 | VERIFIED |
| Next.js production build | `web` | `npm run build` | Exit 0; 57 static pages generated | VERIFIED |
| Lint | `web` | `npm run lint -- --quiet` | Exit 1: 5,524 errors, including vendored `public/app/canvaskit/canvaskit.js` and application files. No lint rules or tests were disabled. | FAILED |
| Explicit platform role | `backend/app/dependencies/auth.py` | New negative test | Missing platform role returns 403; included in 27 PASS | VERIFIED |
| Cross-tenant legal/document/billing attack matrix | Contract service tests cover selected isolation | Full HTTP negative matrix | Not run; do not infer comprehensive isolation | NOT_TESTED |
| Signature challenge required | `ContractSignRequest`, `sign_contract_electronic()` | Code path and existing positive tests | Challenge omitted and signature still succeeds | FAILED |
| Challenge replay | `SigningChallengeService` | `test_signing_challenge_lifecycle_and_replay_protection` | In-process expiry/replay test passes | PARTIALLY_VERIFIED |
| Independent wet-ink verifier | `verify_wet_ink_contract()` | Code inspection | Tenant owner/admin can self-approve | FAILED |
| Publication/legal gates | `Settings` flags vs signing service | Code inspection | Signature path does not reject unpublished/unverified provider | FAILED |
| Existing active subscriber access | `require_active_subscription()` | Code inspection; targeted subscription tests sign contracts first | Active account with no new contracts receives 403 | FAILED |
| Stripe/credit catalog parity | `CommercialReconciler` | Code vs approved catalog comparison | Extra packs diverge; Stripe actual objects not queried | FAILED |
| CEO MRR/paid customers | `get_executive_overview()` | Query/formula inspection | Uses company plan/status and fixed prices, not confirmed Stripe billing | FAILED |
| PDF byte integrity | PDF generator/signature service | Code inspection | Hash covers text, not final PDF bytes | FAILED |
| Migration 0072 | Disposable local SQLite DB | `python -m alembic upgrade 0072_enterprise_agreements_and_legal_profiles` with isolated `ALEMBIC_DATABASE_URL` | Failed in 0071 on PostgreSQL-only `::json`; no PostgreSQL instance available | NOT_VERIFIED |
| Full GitHub CI/GitGuardian for implementation | PR #87 checks | `gh pr view 87 --json statusCheckRollup` | GitGuardian SUCCESS applies to `ed07cf3`, not `4e4e213` | NOT_VERIFIED |
| Staged secret scan | Audit changes only | Gitleaks v8.30.1 `git --staged --redact=100 --config .gitleaks.toml` via required pre-commit hook | No leaks found in ~15.84 KB staged changes; not a full-history scan | VERIFIED |
| Source secret scan | `backend`, `web/src`, `alembic`, `tests/backend` | Gitleaks v8.30.1 `dir <path> --config .gitleaks.toml --redact=100` | All four source directories exit 0, no leaks; whole-worktree scan found eight `generic-api-key` detections only in ignored, generated `web/.next` build files | PARTIALLY_VERIFIED |
| Production safety | Isolated audit worktree | Git diff and operation log | No deploy, merge, active DB write, payment or real signature | VERIFIED |

Statuses describe this audit only. A passing synthetic test is not live integration evidence.
