# Avenqo V1 Production recovery rehearsal — 2026-10-28

This is a **local, isolated rehearsal**. No Production database, service, secret,
volume, domain, Telnyx route, or Stripe object was changed.

## Evidence

- Source: Railway Production `avenqo-daily-backup` cron log, backup ID
  `20261027T070025879383Z`. The real SQL archive and JSON metadata were
  downloaded read-only from `avenqo-backups-u7bgklgz2` at the bucket root.
- S3 `ContentLength`, metadata `size_bytes`, and local size: **2,227,691 bytes**.
  Local SHA-256 matched metadata:
  `a4025dcace3f3a443d2fced8308e3f9a1c83eada9caf1ae2d66498ccf2ddc93e`.
- The dump header identifies PostgreSQL **18.6**. It restored with
  `ON_ERROR_STOP=1` and one transaction into a new loopback-only PostgreSQL
  **18.6** cluster. No Production connection URL was used for the restore.
- Restored state: Alembic `0048_billing_test_documents`, 77 tables, 17 users,
  17 companies, 4,831 rows, 310 indexes, 1,006 constraints, one sequence,
  and 11 enum types. All 77 table owners were `postgres` in the restored dump.
- Ownership dry run enumerated 77 tables, one sequence, and 11 enum types. The
  explicit apply on the isolated copy transferred them to `avenqo_owner`.
- PostgreSQL 18 initially retained a membership with `INHERIT FALSE` even after
  `ALTER ROLE avenqo_migrate INHERIT`. An explicit membership grant with
  `WITH INHERIT TRUE` fixed the migrator's owner privilege. The owner role also
  needed `CREATE` on `public` to own the resolver function in revision 0067.
- An Alembic upgrade as **`avenqo_migrate`** then reached
  `0069_crm_service_approval_columns`. The existing 0067 migration masked its
  first privilege error and poisoned the transaction; it now fails clearly
  and does not silently fall back to a superuser-owned function.
- Final migrated copy: 93 tables, 379 indexes, 1,210 constraints, one sequence,
  11 enum types. All original 76 business-table rows were compared on their
  original columns by in-memory SHA-256 fingerprints: **none missing or
  modified**. The Alembic version row changed as intended. Three extra
  `tenant_ai_credit_balances` rows were initialized by HTTP credit GETs
  **in the isolated copy only**; these GETs have a local initialization side effect.
- FastAPI started on loopback with `avenqo_app` and Production-mode startup.
  `/api/v1/health` and `/api/v1/ready` returned 200; readiness reported
  `database=ok`, `migrations=ok`, `artifact_storage=ok`. Unauthenticated
  `/auth/me` and `/billing/ai-credits` returned 401. Two synthetic local
  sessions bound to two existing company identities returned 200 for identity,
  CRM clients, appointments, and credit balance; returned CRM record IDs were
  checked against their company IDs. The synthetic sessions were removed from
  the copy. No real credential or token was used.
- Application rollback rehearsal: the archived source at
  `d10083fa3ebb8436fc8020dd1bea7e7e4825503c` ran its historical Alembic
  startup step as a **no-op** against schema 0069, then started FastAPI as
  `avenqo_app`. Health/readiness and the same two-tenant HTTP checks passed.
  This proves local schema compatibility, **not** a Production rollback.
- The runtime tests used inert local fixture values for Stripe and JWT.
  `stripe_configured=true` in local readiness does **not** validate live Stripe.

## Remaining Production gates

1. Obtain an explicit, separate founder authorization for the Production
   intervention. The existing Production API is crashed; this rehearsal did
   not restart or deploy it.
2. Capture a fresh pre-intervention Production backup and verify S3 bytes and
   SHA-256. Keep the 2026-10-27 archive and all historical backups untouched.
3. Pause inbound PSTN through the separately approved Telnyx procedure and
   confirm the actual routing state. No telephone change was made here.
4. Confirm the exact Production database name, revision 0048, current owners,
   active connections, and privileged administrator account. Run the guarded
   ownership script first with `--dry-run`, then only with explicit approval
   using `--apply --expect-database <exact-name>`.
5. Enable the existing constrained `avenqo_migrate` login through an approved
   secret-management step. Never grant DDL to `avenqo_app`.
6. Perform one controlled Alembic 0048 → 0069 upgrade with the migrator,
   verify revision and preserved row counts, then start the pinned backend
   image with the migration-free start command. Verify health, ready, auth,
   CRM, credits, logs, and tenant isolation.
7. Promote the matching frontend only after backend readiness and confirm
   `avenqo.ca`/`api.avenqo.ca`. Re-enable PSTN only after a separate functional
   acceptance and authorization.
8. On failure after schema 0069, roll back **application code only** to the
   specifically tested compatible image; do not automatically run an Alembic
   downgrade. If data restoration becomes necessary, stop and obtain a new
   explicit approval for the exact isolated recovery plan.
