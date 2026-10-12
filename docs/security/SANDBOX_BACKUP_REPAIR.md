# Sandbox cron repair — approval required, no deployment performed

Target: alert-tenderness / sandbox / avenqo-daily-backup only.
Service ID: 95b8c1d8-aa9a-4d88-9e12-401ffaefd997.
Current failed source: main / ba2dda1.
Runtime command remains `python scripts/backup_db.py`.

## Cause and minimal runtime change

The old S3 download method did not create the destination parent. Retention encounters
historical keys under sandbox/ and boto3 opens a temporary file under a missing
directory, causing FileNotFoundError after the archive has already been uploaded.

9d05eb3 already contains `local_path.parent.mkdir(parents=True, exist_ok=True)`,
paginated S3 listing, environment-prefixed new archives, legacy flat-key reads,
and retention scoped to this environment. This branch reuses that validated baseline,
and adds a retention pause: BACKUP_RETENTION_ENABLED defaults true, preserving existing
behavior, but will be set false ONLY on the Sandbox cron after approval. While false,
retention performs no storage listing or deletion. No historical object is edited,
renamed, overwritten or deleted as part of repair.

No migration, API change, Telnyx change, secret change, database replacement, bucket
replacement, volume change or Production update is required. All three Vercel Git
configs explicitly disable deployments for this repair branch. No merge is required.

## Validations before approval

- Tests reproduce the original nested-path failure and verify the corrected download.
- New backup with pruning disabled preserves old, legacy and other-environment fixture
  objects byte-for-byte, then verifies the checksum and restores to isolated SQLite.
- Existing retention tests still pass with default behavior enabled.
- Read-only verification of an actual Sandbox S3 SQL archive matches its stored SHA256.
- Actual PostgreSQL restore to a new localhost-only database: 87 table row counts match,
  Alembic 0053; existing S3 inventory unchanged, no uploads or deletions.
- Historical mislabeled/flat objects are retained; no automatic rewrite of their metadata.

## Exact proposed lot (stage only after owner confirms target)

Only avenqo-daily-backup in sandbox:
1. Branch → codex/avenqo-sandbox-backup-repair-20261012.
2. Pin commit → reviewed HEAD of this branch.
3. BACKUP_RETENTION_ENABLED → false (non-secret setting).

Preserve repo, cron, start command, all other variables, volumes and bucket. Do not
change the API source or apply any Telnyx-variable lot. Railway accept-deploy applies
the entire environment patch: re-read pending changes immediately before activation
and stop if any other service/variable is included.

## After explicit deployment authorization

Verify the resolved Sandbox database/bucket and all GitHub checks again; read exact
candidate SHA from Railway. Apply only the reviewed cron lot, then run it once (ensure
no simultaneous scheduled/manual invocation). Verify exit 0 / successful completed
cron, not continuous uptime: this is a scheduled one-shot service. Confirm new objects
under sandbox/, metadata environment sandbox, compare stored SHA256 to downloaded SQL,
restore to a fresh isolated database and compare every table count. Compare all prior
S3 keys, sizes and ETags to the pre-run inventory; all must remain unchanged.

Do not enable pruning after this repair without a separate retention-policy review.
Accumulated storage is the deliberate tradeoff of pausing deletion.

## Failure and rollback

Stop further manual executions. Preserve logs and all S3 objects. Never restore over
an active database and never downgrade schema. The previous main build is known to
crash; rolling back to it does not restore service health. If continued schedules need
to be paused, obtain owner approval for that cron-only operation. Repair on a new
branch and revalidate rather than deleting archives to make the job green.
