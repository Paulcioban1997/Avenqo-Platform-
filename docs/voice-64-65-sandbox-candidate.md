# Candidate Sandbox: confirmation and tenant audio

## Integration

PR64 contains the booking confirmation correction, including the executor
boundary and latest-exact-proposal confirmation. PR65 contains tenant-owned
voice, speed, tone, noise filtering, greeting and language propagation.
Both extend promotion/sandbox at40af97b. No migration is added.

Four textual conflicts exist when combining them: the workflow test list and
root/web/frontend vercel.json. Resolve by keeping BOTH new regression files and
BOTH branch deployment guards. The candidate adds its own Vercel guard. No test,
approval gate, authorization check or provider fallback is removed.

Recommended order: PR64, then PR65 with this conflict resolution, or validate
and deliver this combined candidate directly after explicit approval. This local
integration is not a merge into main or promotion/sandbox.

## Release gates and delivery plan

1. Require exact-candidate CI success; do not substitute older green commits.
2. Confirm builds available to Railway Hobby; do not force deployment while paused.
3. Review the Railway security incident and dependencies without displaying or
   changing credentials. Preserve founder-replaced S3 credentials. Any rotation
   or operation outside this candidate needs its own authorization.
4. Before requesting delivery approval, capture the current Sandbox API source,
   deployment/image, preview URL/API target, migration revision and recent
   restorable Sandbox backup. Do not touch Production backups here.
5. Prepare ONLY the Sandbox API candidate source and matching Vercel preview.
   The Commerce PR63 authorization is not authorization for this API release.
   Keep audio/streaming/purchases off and do not restart the API during preparation.
6. After explicit approval and platform checks, build the exact candidate and
   confirm actual runtime SHA, health/ready, unchanged migration head, logs and
   settings save/reload for Produits_Ero. Do not overwrite newer deployments.
7. Test CRM/Google with a separately approved synthetic event only. Backend
   success alone is not evidence of Google event creation/modification/deletion.
8. Roll back application source/image if critical regression; never restore an
   older backup over active data or silently re-enable a revoked credential.

## Real-phone acceptance, separate authorization required

Use the existing Sandbox number and Produits_Ero's own settings. Public callers
cannot read private analytics or obtain another company's information from a
routing PIN. Confirm configured catalog, service IDs, hours and caller role.

- French, English, Romanian: primary-language greeting; explicit switches only
  to selected secondary languages; unauthorized locale metadata must be ignored.
- Products and stock: names/prices from authorized evidence only. Historical
  Superstore data is not current stock; unknown inventory must remain unknown.
- Booking: ask for a slot with a negative or hesitant phrase. There must be no
  appointment or customer creation. Repeat with model flag true in simulation.
- The agent proposes full details. A clear yes may confirm only that latest exact
  proposal. Change the proposed time and verify an old slot cannot be confirmed.
- Verify the synthetic booking in CRM and Google directly, with correct timezone.
- Observe speed, tone/noise settings, audio latency, interruption and stop behavior.
  A synthetic test does not establish voice quality or certify live languages.
- Agree a test duration/cost estimate and stop controls before any paid call.
  Long-call capability does not itself authorize a60-minute paid test.

No live telephone, paid inference, tenant mutation or production operation is
performed by this validation. Verdict remains LIVE_COMPANY_INTELLIGENCE_PENDING.
