# API-only rollback snapshot

This snapshot retains the migration graph needed by a database already at 0055_voice_call_policy.
The application is the previous validated version, without deleting or downgrading data.
Local PostgreSQL restore rehearsal verifies predeploy upgrade, readiness, ORM reads and CRM availability.
The snapshot is not deployed and must not be used for the web preview: historical frontend dependencies are not certified here.
Vercel auto-deploy is disabled for this branch. Use only on the Sandbox API under explicit authorization.

Read the actual database revision before choosing the snapshot. A database still at 0053 uses the original 2c75b47 release;
a database at 0054 uses this retained-0054 graph; a database at 0055 uses the retained-0055 snapshot.
Never overwrite an active database. Commercial/audio/purchase gates remain off during this release validation.
Reverting to the pre-commercial app after any paid provisioning order exists requires a separate reconciliation plan.
