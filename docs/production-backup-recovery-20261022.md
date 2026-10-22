# Production backup recovery — approval required

## Evidence recovered

Project alert-tenderness: 062bbe91-68e7-4e79-8de7-cffeb8a5f5cd.
Production: b9b03d41-2a67-4aab-a6f6-32939d8b81e0.
Only delivery target: avenqo-daily-backup, 95b8c1d8-aa9a-4d88-9e12-401ffaefd997.
Current image: ba2dda1bcff47a3c748acad7d1c306ef53db1bd0.
Current deployment: 060aad52-a3a3-4956-91b7-042f16d4f793, created 19 October, CRASHED.
Successful jobs continued on 19, 20 and 21 October; latest observed success:
20261021T070037733097Z, 2,227,236 bytes,
SHA256 dcc7bfad2b26cc5b459d583dca4c24e31c5f980ecd80508115f4314fdf9d5428.
These are log facts, not a fresh S3 read/restore certification.
22 October 07:02 UTC: pg_dump reached the upload stage, then PutObject SignatureDoesNotMatch.
Current bucket credentials were issued 22 October 13:19:20 UTC; no subsequent service deployment.

The bucket API reports endpoint https://t3.storageapi.dev, S3 region auto, virtual-host style.
Service BACKUP_S3_REGION renders iad through ${{avenqo-backups.REGION}}.
The access and secret reference fields were inspected without displaying credentials:
${{avenqo-backups.ACCESS_KEY_ID}} and ${{avenqo-backups.SECRET_ACCESS_KEY}}.
OAuth deliberately withholds values. No authenticated S3 probe using current keys was performed.

Confirmed configuration mismatch plus stale runtime credentials after provider reset.
The exact contribution of each to the failed signature requires the post-approval live verification.
Do not claim changing region alone fixes the incident.

## Code safeguards

- Explicit SigV4, virtual-host addressing for Railway endpoints; reject physical signing region.
- Bounded SDK retries/timeouts, credential-free failure reporting.
- Read back uploaded bytes and check length/SHA256 before publishing the manifest last.
- Failed/verified uploads clean only the current attempt's local staging files.
- Cron retention is OFF by default; recovery must explicitly keep it false.
- Existing object names, metadata format and bucket are preserved; paginated listing and nested download directories supported.
- PostgreSQL credentials removed from pg_dump/psql argv; SSL query options preserved.
- Restore stops on SQL errors; success output contains no connection URL.
- Dockerfile remains backend/Dockerfile: PostgreSQL client 18, no migration/startup API command when cron overrides it.
- No Voice code, migration, API deployment or active database change.

## Exact proposed Production lot — NOT STAGED/APPLIED

Only this service, in this Production environment:
1. Source branch: codex/production-backup-recovery-20261022.
2. Pin the PR's validated final full SHA; never deploy an unverified newer head.
3. BACKUP_S3_REGION: literal auto (physical bucket stays iad).
4. BACKUP_RETENTION_ENABLED: literal false.
Preserve repository, /backend/Dockerfile, python scripts/backup_db.py, cron 0 7 * * *,
region us-east4-eqdc4a, all credential/database references, bucket, volumes and other services.
No main merge is needed or authorized. Do not apply a shared pending patch containing anything else.
Build availability and GitHub source authorization must be checked at delivery time.
A new deployment must resolve the existing references anew; do not rotate the bucket again.

## Post-approval acceptance

Capture pre-run S3 object keys/sizes/ETags without content disclosure, runtime SHA and current deployment IDs.
Deploy only this pinned backup service, then run one backup with retention false.
Require pg_dump exit zero, non-empty SQL, verified remote SHA256, manifest, and job exit zero.
Independently re-read object metadata and SHA256; compare preexisting objects and assert none disappeared.
Restore the new archive only into a newly created, approved isolated PostgreSQL 18 target,
then inspect schema, Alembic version, row counts and tenant relationships without logging client data.
Never use the Production DATABASE_URL as a restore target; never use --force against active data.
Check the next scheduled run separately. A green build is not a successful backup or restore.

If a step fails, stop rollout: preserve remote archives and active data. Do not redeploy a pre-reset
snapshot or restore a backup over Production. The old image also lacks the retention guard;
rollback/pausing this cron alone must be explicitly approved rather than silently restarting unsafe code.

## Security follow-up (no rotations performed)

Railway reset bucket keys; preserve the founder's replacement and refresh only the consumer runtime.
Old Railway API/project tokens are invalidated. Existing connected account works for read-only inspection.
Review PostgreSQL credentials and other provider secrets against Railway's incident guidance;
coordinate rotations and backup consumers separately with approval. Do not revoke keys here.
No new infrastructure, bucket or subscription is provisioned.

References:
- https://docs.railway.com/storage-buckets
- https://status.railway.com/incident/QH8L8B3E
- https://blog.railway.com/p/security-disclosure-recommendation-redeploy-buckets-and-reconnect-github-after-the-credential-reset
