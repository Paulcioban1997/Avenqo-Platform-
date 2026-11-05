# Avenqo P0 QA evidence matrix — 2026-11-05

| Requirement | Evidence | Test | Actual result | Status |
|---|---|---|---|---|
| PR/commit identity | `gh pr view 87` and `git show 4e4e213` | Compare ancestry and refs | PR head `ed07cf3`; `4e4e213` is later on another branch | VERIFIED |
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
| Production safety | Isolated audit worktree | Git diff and operation log | No deploy, merge, active DB write, payment or real signature | VERIFIED |

Statuses describe this audit only. A passing synthetic test is not live integration evidence.
