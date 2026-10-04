# Provider Production Audit

Evidence collected 2026-10-03 against the production Railway backend. No secrets,
tenant identities, prompts or business payloads are included in this report.

## Evidence Rules

IMPLEMENTED is not CONFIGURED, AUTHENTICATED, CONNECTED or PRODUCTION VERIFIED.
Configuration presence is reported only as CONFIGURED, MISSING or NOT REQUIRED.
SDK mocks establish implementation contracts, not external connectivity.
Model metadata establishes API access, not successful inference or billing access.
Database connection flags and historical syncs do not establish a fresh OAuth check.
READ_ONLY_SUCCESS is scoped to the named operation, not the complete integration.

## Vertex

- Adapter: IMPLEMENTED as `vertex`, separate from Gemini Developer API (`gemini`).
- Configuration: VERTEX_ENABLED, VERTEX_PROJECT, VERTEX_LOCATION, VERTEX_MODEL, VERTEX_SERVICE_ACCOUNT_EMAIL, AI_MODEL_CATALOG and AI_MODEL_RATE_CARD are CONFIGURED in Railway production.
- Authentication: GOOGLE_SERVICE_ACCOUNT_JSON is CONFIGURED as a Railway sealed variable. Its JSON was validated in memory as type service_account and matched the user-confirmed project and dedicated service-account email. Google credentials constructed successfully; key material was never emitted.
- Workload identity federation: Railway runtime has no OIDC identity token, issuer or audience. Classification C remains; this release uses the existing dedicated service-account key via sealed secret, not WIF or impersonation.
- IAM, billing and API: user-confirmed roles/aiplatform.user, billing-active and API-enabled configuration. No Google Cloud CLI identity exists here for independent IAM/billing-console inspection. Successful real online inference independently confirms authentication/API/model access.
- Region/model: configured model gemini-3.5-flash-lite and region passed a real inference. Google documents the model GA on global, us and eu endpoints.
- SDK: production google-genai 2.28.0 and google-auth 2.59.1 inspected; tests validated on the same Google versions.
- API: stable v1 client, bounded timeout, one SDK attempt for both Google transports; retries remain owned by the existing gateway.
- AI Central and Agent Registry: LIVE VERIFIED with a real Vertex response through CentralAIService; existing Retail agent was selected.
- Tenant isolation: foreign conversation rejected before provider execution in the new central regression test.
- Accounting: LIVE VERIFIED. The controlled Central request produced one Vertex provider-attempt ledger row with actual token usage and response ID, one settled reservation, one settlement, and exactly one credit charge.
- Pricing: explicit positive input/output rates, cached-input rate, zero separate reasoning rate and versioned source/date required. No invented Vertex tariff or free unknown price.
- Unknown usage: explicit failed `usage_unavailable` attempt; no success, retry or fallback on missing usage. Zero numeric storage fields are not evidence of zero vendor cost; operator reconciliation is required.
- Tools: returned function calls only; SDK automatic function execution disabled. Existing authorization, confirmation and idempotency executor remains authoritative.
- Real production Vertex request: LIVE VERIFIED. One direct minimal Vertex request returned the expected marker; usage reported 26 input / 5 output tokens and a response ID. No answer text or response ID was printed.
- Central AI: LIVE VERIFIED. One French controlled request selected Retail and returned the expected French marker; provider/model/tenant/user/conversation attribution and FR language continuity verified. One credit was charged (6212 to 6211).
- Fallback: LIVE VERIFIED separately in a second controlled Central request using a request-scoped Anthropic-primary / Vertex-fallback order; global AI_PRIMARY_PROVIDER was unchanged. Anthropic failed with quota_problem and zero credits; Vertex succeeded. Two attempts, one reservation, one settlement and one credit (6211 to 6210).
- Production verified: PASS for the bounded Vertex text-inference/Central/accounting scenario only. This is not a blanket claim about all Vertex features, regions, modalities or quotas.

## Runtime Inventory

- OpenAI text: IMPLEMENTED; CONFIGURED; model metadata READ_ONLY_SUCCESS. Recent production ledger contained 159 successful attempts with response IDs during the observed 24-hour window. Historical inference evidence, not a new audit prompt or a guarantee about every operation.
- Gemini direct: IMPLEMENTED; CONFIGURED; stable model metadata and prior production use observed. Dynamic alias pricing was replaced with a stable model profile and reasoning-inclusive output accounting. This task's real Vertex calls are separately attributed as `vertex`, not `gemini`.
- Anthropic: IMPLEMENTED; CONFIGURED; supported model metadata accessible. Text/tool/stream calls were fixed for SDK 1.11.0 (removed unsupported temperature parameter). Live fallback probe returned a quota_problem with zero Anthropic credits; no Anthropic success is claimed.
- OpenAI Voice STT / TTS / Realtime: IMPLEMENTED; CONFIGURED via OpenAI. Existing voice tests and prior production stream-ticket evidence retained. No new microphone-to-STT-to-reasoning-to-TTS audio quality test; no 44/44 production semantic/audio claim. Models and voice unchanged.
- Retell: IMPLEMENTED adapter; API key MISSING. Authentication, connection and live telephony NOT VERIFIED. No call initiated.
- Telnyx: IMPLEMENTED call-control/SMS/webhook adapter; key and webhook public key MISSING. NOT VERIFIED. No SMS or call action performed.
- Google Calendar: IMPLEMENTED; OAuth app settings CONFIGURED; one stored connected connection with one historical sync observed. Fresh API/OAuth connectivity NOT VERIFIED; no appointment action performed.
- Outlook Calendar: PARTIAL placeholder. Token exchange/refresh are unimplemented and read methods return empty values. NOT CONFIGURED, NOT CONNECTED, NOT PRODUCTION VERIFIED. Not a usable calendar integration.
- Stripe billing: IMPLEMENTED; key and webhook secret CONFIGURED; balance GET READ_ONLY_SUCCESS. Payment, Checkout, invoice mutation and webhook delivery NOT TESTED live.
- Shopify: IMPLEMENTED and registered; app settings CONFIGURED; one production connection was REAUTH_REQUIRED with stored credentials and no historical successful sync. NOT currently connected. Reauthorization must be performed by the authorized shop owner.
- WooCommerce: IMPLEMENTED and registered when callback/webhook configuration is complete; platform settings CONFIGURED. No tenant connection was observed; tenant credentials MISSING, authentication/connection NOT VERIFIED.
- Etsy: adapter source exists but is not registered by the production composition root; catalog is coming_soon and app configuration MISSING. PARTIAL, NOT CONNECTED, NOT VERIFIED. Default placeholder app identifiers are not credentials or a configured app.
- Resend HTTPS email: IMPLEMENTED; EMAIL_API_KEY CONFIGURED. No email sent; authentication and delivery NOT VERIFIED. Key presence does not prove selected transport or usable sending-domain permissions.
- SMTP email: IMPLEMENTED; host/username/password CONFIGURED. No login/send attempted; authentication and delivery NOT VERIFIED.
- Logging notifier: IMPLEMENTED local non-delivery fallback, external credentials NOT REQUIRED. Must never be represented as delivered email.
- S3-compatible backup storage: IMPLEMENTED; endpoint/bucket/access credentials CONFIGURED; bucket HEAD READ_ONLY_SUCCESS. No upload, restore, backup deletion or disaster-recovery exercise performed.
- Local dataset/artifact/backup storage: IMPLEMENTED; external authentication NOT REQUIRED. Migration and existing storage regression tests pass; durable production artifact content was not re-read or modified by this audit.
- PostgreSQL application database: IMPLEMENTED; CONFIGURED; read-only production aggregate queries succeeded and migration head observed as 0036_merge_sandbox_membership_ancestry.
- SQLite application database: IMPLEMENTED for local/tests; external authentication NOT REQUIRED. This is not the production database.

## Catalog-Only Providers

These commerce entries have metadata but no registered runtime adapter. Their catalog
capabilities are planned declarations, not tested implementation. Configuration,
authentication, connection, fallback, accounting and tenant safety are NOT VERIFIED:

BigCommerce; Adobe Commerce/Magento; Wix eCommerce; Squarespace Commerce; PrestaShop;
Ecwid; Shopware; Salesforce Commerce Cloud; commercetools; VTEX; Amazon Seller Central;
eBay; Walmart Marketplace; TikTok Shop; Meta Commerce; Mercado Libre; Mirakl; Shopee;
Lazada; Square; Lightspeed Retail; Clover; Shopify POS; Stripe Commerce (separate from
implemented Stripe billing); PayPal; Google Merchant Center; ShipStation.

Source connector interfaces for REST API, MySQL, SQL Server, PostgreSQL and SQLite
derive from PlannedConnector and raise NotImplementedError. CSV/Excel interfaces in
that registry are also placeholders; separate backend CSV/Excel upload ingestion is
implemented and tested. A registered source kind is not a functioning adapter.

## Routing And Security

- Existing provider-neutral gateway, smart router, per-model breaker and fallback remain in use. Vertex is included only when enabled, project/location/model and a recognized ADC/sealed credential source exist; explicit invalid pricing fails closed.
- Auth/config failures are not retried or silently masked by fallback. Transient failure fallback and attempt-cost accounting are covered by gateway and credit tests.
- Gemini thoughts are included once in billable output. Vertex separate reasoning pricing must be zero to prevent duplicate charging.
- Configured model profiles contain pricing provenance. Historical ledger snapshots are not rewritten to retroactively change past charges.
- Central AI carries verified company/user/conversation context; tool authorization checks current membership, entitlements and mutation policy independently of provider choice.
- Canonical 44 locales retained. No provider-specific agent registry or competing locale list was created.
- LLM providers receive system instructions, bounded conversation/context and authorized tool results, not credentials. Voice receives audio/text required for STT/TTS/Realtime; calendars receive authorized scheduling data; commerce receives shop-scoped API requests; Stripe receives billing identifiers; email receives intended recipient/message; storage contains backups/artifacts. Provider retention, training and data-residency terms are not universal guarantees.
- Health without observations is now UNKNOWN, not fabricated HEALTHY. Recent vendor failures do not imply all configured providers are unavailable.
- A legacy production smoke script contained a database credential in tracked source. Removed from the current file, but ROTATION AND HISTORY REMEDIATION ARE STILL REQUIRED. The script also performs writes and was not executed in this audit. No claim of repository-wide secret-free history is made.

## Verification

- Full backend run before the final stable-profile follow-up: 1069 passed, 732 warnings, 3804.87 seconds. That run used google-genai 1.75.0.
- Final backend deployment slice on google-genai 2.28.0: 265 passed, 8 warnings, including Central AI, registry, execution security, accounting, gateway, Voice, locales and migrations.
- Latest compatibility follow-up on google-genai 2.28.0 and Anthropic 1.11.0: 273 passed, 7 warnings in 143.71 seconds; 102 focused provider/Central/accounting checks also passed.
- Web: 89 tests passed; TypeScript and production build passed.
- Web lint: FAILED with 90 source errors; global traversal reported 5455 errors and 10603 warnings. These are pre-existing frontend surfaces, not changed by this provider release. No lint rules were disabled.
- Flutter: analyze passed; 306 tests passed. Existing dependency/discontinued-package notices remain.
- CI gate expanded to continuously cover provider/accounting/Voice/migration regressions.
- Production health/readiness at audit start: healthy/ready; no deployment completion is inferred from those pre-release checks.

## Operator Provisioning

Production currently uses the existing dedicated service account's key through the
sealed Railway variable `GOOGLE_SERVICE_ACCOUNT_JSON`; the matching
`VERTEX_SERVICE_ACCOUNT_EMAIL` and sourced region-specific model prices are configured.
No key value is present in this repository, frontend, logs or audit output. The account
is scoped to `roles/aiplatform.user`. Key rotation/revocation remains an operator task.
WIF is preferred if Railway later exposes a documented, verifiable runtime OIDC token.

## Railway Identity Finding (2026-10-03 follow-up)

Classification: C for the inspected Railway runtime. The running container exposes
Railway deployment/replica metadata and `RAILWAY_API_TOKEN` (a Railway control-plane
credential), but no OIDC token, issuer or audience. Railway's documented provided
runtime variables include deployment, environment, service and replica identifiers,
not a signed workload identity assertion. The API token is not a Google principal and
must not be exchanged or treated as one. The local frontend's Vercel OIDC setting is
not an identity of the Railway backend. No Google Workload Identity Pool was created.

The dedicated Google service account and Vertex role/API/billing were user-confirmed.
The sealed production JSON was parsed in memory and credential construction succeeded;
credential type, project and email matched without printing any field values. There is
no gcloud CLI identity available for separate Cloud Console/IAM introspection. A real
inference proves endpoint authentication and configured-model availability at the
configured endpoint; quota status beyond these successful requests is not independently
enumerated.

The sealed service-account JSON is now configured in Railway production. The adapter
validates its `type`, project ID and client email in memory before loading credentials;
the secret is never logged or accepted from a request. The service account remains
limited to `roles/aiplatform.user`. This long-lived key is less secure than WIF; rotate
by creating a replacement in Google Cloud IAM, updating the sealed Railway variable,
deploying and verifying a centrally metered request, then disabling/deleting the old
key. Revoke immediately if exposed.

Current Vertex-only production check: `VERTEX_ENABLED`, `VERTEX_PROJECT`,
`VERTEX_ENABLED`, project, location, model, dedicated service-account email, model
catalog, regional rate card and sealed service-account JSON are CONFIGURED.
`GOOGLE_APPLICATION_CREDENTIALS` is NOT REQUIRED for the sealed JSON path. Credentials
were constructed and used for successful real inference. Vertex quota limits were not
queried directly; two small inference requests succeeded.

Use `scripts/audit_provider_runtime.py` from the repository root for presence-only output;
`--read-only-production --connectivity` enables safe aggregate and non-billable probes.
It deliberately has no send, pay, sync, appointment-write, deletion or inference command.

Official sources consulted: https://googleapis.github.io/python-genai/;
https://docs.cloud.google.com/vertex-ai/generative-ai/docs/start/gcp-auth;
https://platform.claude.com/docs/en/about-claude/models/overview;
https://platform.claude.com/docs/en/about-claude/pricing;
https://ai.google.dev/gemini-api/docs/models;
https://ai.google.dev/gemini-api/docs/pricing.

## Release Evidence

The first implementation release eca1b0559d5b9a7bbc7f707246888de87196a6d0 passed
CI run 37163052591 (backend, web and Flutter) and all three Vercel statuses.
Railway production deployment ea0775a8-fc68-410c-abdb-21eb0b42d333 and sandbox
deployment 3c00c853-371d-4ffa-b1d7-4f3cfbc3c8c1 succeeded at that SHA. Public production
health/readiness and internal sandbox readiness matched the SHA; migrations and
artifact storage were OK. The deployed read-only audit confirmed successful metadata
access to both replacement model configurations, and Stripe/S3 read probes remained
successful. No credentials or Vertex settings were changed.

A final follow-up disables direct Gemini SDK retries as well as Vertex SDK retries;
95 focused gateway, usage, Central AI and credit tests passed on Google SDK 2.28.0.
This follow-up's exact final CI/deployment and minimal centralized inference results
must be checked independently; the first release evidence does not establish them.

Centralized probes on the intermediate retry release recorded two failed classification
attempts and two failed deterministic Retail attempts, with zero credits charged in the
audit-prefix ledger. No successful inference was claimed from these failures. Sanitized
cause types identified the Anthropic SDK argument defect and a Google ClientError; no
credential, response text or tenant identity was printed. The compatibility follow-up
uses a current documented Google model profile, removes the unsupported Anthropic argument,
and classifies vendor errors by structured status codes. It requires fresh release/inference
verification rather than reusing metadata evidence as a production success claim.

## Vertex Live Verification (2026-10-03)

Final active code SHA during the checks: `632d13b54fd14c02e5586ba2519b7ac3aa3fa700`.
No credential value, private key, token, project-specific secret, prompt, response text,
tenant ID or user ID is recorded here.

- Sealed secret: `GOOGLE_SERVICE_ACCOUNT_JSON` CONFIGURED. JSON validation in process: PASS for service-account type, configured project match, dedicated email match and google-auth credential construction. No credential field was printed.
- Authentication: PASS. Direct Google GenAI Vertex client authenticated using the existing dedicated service account. No service-account impersonation was used; key-based service-account credentials were used because Railway runtime has no verifiable OIDC identity.
- Model availability and endpoint: PASS for the configured `gemini-3.5-flash-lite` at the configured supported endpoint, evidenced by a real Google 200 response. Configured model/location values are intentionally not repeated here.
- Direct inference: PASS. One minimal text-only Vertex request returned the expected marker; normalized usage reported 26 input and 5 output tokens and a provider response ID. Response content and ID were not printed. This direct smoke call is not tenant-metered by Avenqo.
- AI Central route: PASS. One controlled request used an existing empty French conversation in the Produits_Ero tenant, selected the Retail agent, exposed no tools, returned the expected French marker and passed FR language detection. The conversation was not created; the normal user/assistant audit messages were stored.
- Provider/model/tenant attribution: PASS. Exactly one successful `vertex` attempt recorded the configured model, authenticated tenant/user/conversation scope, provider response ID and nonzero normalized token usage.
- AIUsageService accounting: PASS. Credit balance moved from 6,212 to 6,211; one provider attempt, one reservation, one settlement and one credit charged. No duplicate charge.
- Fallback: PASS, separately. A second request used a request-scoped fixed provider order only; global `AI_PRIMARY_PROVIDER` was unchanged. Anthropic returned `quota_problem` with zero credits charged, then Vertex returned successfully. The same request had two attempts, one reservation, one settlement and exactly one credit charged; balance moved from 6,211 to 6,210. Both attempts were tenant-attributed and FR language continuity passed.
- Production deployment: PASS for the bounded text-inference and Central AI scenario. Production health was `healthy`; readiness was `ready`, migrations and artifacts were `ok`, all on the SHA above. The same SHA was also active and ready in sandbox. CI run 37170023197 passed backend, web and Flutter.
- Logs: the exact deployment logs were inspected with raw output withheld. No provider/gateway/central event text was present in the queried deployment log records; the inline test harness intentionally disabled its own logger to avoid emitting prompts, tenant IDs or response content. Thus live response and ledger are the evidence of these calls; no request-specific Railway application-log event is claimed. The queried startup log slice contained 11 Alembic-pattern records and 8 other error-level records; raw messages were not displayed and those records are not attributed to the Vertex requests.
- Fallback scope: the fallback request forced only the per-instance order through the existing gateway; no production variable or global provider order was changed. One ordinary provider quota rejection preceded the Vertex success.
- Data scope: two ordinary AI conversation turns and the explicitly requested AI usage/credit ledger records were written. No Retail, CRM, Voice, subscription payment, calendar, shop, email, SMS or other business-object mutation was performed.

Current status: IMPLEMENTED PASS; CONFIGURED PASS; AUTHENTICATED PASS; MODEL AVAILABLE PASS;
LIVE INFERENCE VERIFIED PASS; AI CENTRAL ROUTING VERIFIED PASS; ACCOUNTING VERIFIED PASS;
FALLBACK VERIFIED PASS; TENANT ATTRIBUTION VERIFIED PASS; PRODUCTION VERIFIED PASS
for this bounded production text-inference path only. This is not a claim of universal
Vertex availability, quota headroom, all-region support or multimodal capability.

## Connector Cron Incident (2026-10-04)

- Railway sandbox service: `avenqo-connector-ai-cron` (service ID
	`00d0f7c9-fb7e-4de1-a5e9-515bc1bb60f8`). Its latest deployment status was SUCCESS;
	`stopped=true` is expected for a one-shot scheduled service. It is a thin HTTP trigger,
	not the evaluation worker process.
- Railway itself does not currently show a failed cron deployment/execution: the latest
	recorded cron cycles completed normally, and both explicit sandbox invocations below
	exited 0. The UI failure corresponds to the persisted evaluation row, not process exit.
- Trigger configuration: scheduler URL/token CONFIGURED. The URL host was compared in
	memory against the sandbox API domain and matched. No URL or token value was printed.
- Latest automated cycles: logs contained 67 completed trigger cycles; latest and six
	preceding cycles all reported `claimed=0`; five earlier cycles reported positive
	claims. Logs had no traceback/error-level entries. Thus the Railway cron execution
	itself was not the failed component.
- The UI's “Last run failed” corresponded to one persisted connector evaluation row:
	status FAILED, decision `blocked`, reason `source_artifact_missing`, generation 2,
	provider WooCommerce, attempt_count 2,581. Dataset/connection tenant references
	matched. The WooCommerce connection was READY with historical successful sync.
- Root cause was verified by sandbox runtime filesystem checks: `Dataset.source` and the
	current `DatasetVersion.artifact_path` do not exist under the configured artifact root;
	prepared/canonical copies were also absent. There is no recoverable source artifact in
	the sandbox volume. The historical failure's raw exception stack/OS exit code was not
	retained; the evaluation was caught and recorded as a terminal blocked state.
- Fix already present and deployed at SHA `18b22ae44f4640984a43afa3919883b9f6ccc7a2`:
	FileNotFoundError is recorded once as FAILED/blocked/source_artifact_missing, and
	blocked failures are excluded from claims. Other transient evaluation failures remain
	retryable. Regression tests cover both paths.
- Backend CI run `37188506867` passed. Targeted connector/scheduler tests passed, and
	313 broader backend tests passed. Auth/session, tenant context/isolation, central AI,
	Agent Registry/tool security, credits/accounting, Voice, locales, Google Calendar,
	CRM, Retail, WooCommerce and migrations were included in targeted suites. Flutter
	connection/source tests passed (all tests in the two selected files).
- Manual sandbox trigger was run twice using sandbox Railway variables. Both invocations
	returned exit code 0 / `claimed=0`. Read-only before/after checks found one blocked
	source-artifact row, attempt_count unchanged at 2,581, no claimable work, and no
	additional evaluation or business records. This proves safe no-op/idempotency, NOT
	successful completion of the failed business evaluation. No sync/reseed/recreation
	was performed because the original WooCommerce source file is unavailable.
- The prior evaluation did not retain an OS exit code or traceback: the service catches
	FileNotFoundError and records a structured terminal decision. The exact verified
	error category is `source_artifact_missing`; raw paths/IDs were not published.
- Production was not targeted by either manual invocation and remained healthy/ready on
	the deployed release; migrations were OK.

### Current Provider Matrix (2026-10-04)

- Vertex AI — LIVE VERIFIED (bounded production text inference and Central AI accounting
	documented above; no universal/model-family availability claim).
- Gemini direct — LIVE VERIFIED (107 successful production ledger attempts with response
	IDs in the observed last-24-hours window; separate from the Vertex provider identity).
- OpenAI — LIVE VERIFIED (153 successful production ledger attempts with response IDs
	in the observed last-24-hours window; Voice-specific audio quality is not newly tested).
- Anthropic — QUOTA/BILLING BLOCKED (latest production inference fallback attempt received
	quota_problem; zero provider credits charged; fallback to Vertex succeeded).
- Shopify — AUTH REQUIRED in production (`REAUTH_REQUIRED`, no successful production
	sync); LIVE VERIFIED in sandbox by a successful sync at 2026-10-04 08:31 UTC.
- WooCommerce — CONFIGURED NOT LIVE VERIFIED in production (no production connection
	observed); LIVE VERIFIED in sandbox by successful sync at 2026-10-04 08:31 UTC.
- Google Calendar — LIVE VERIFIED for authenticated production Calendar list/event reads,
	OAuth refresh and FreeBusy in the later Calendar-only verification below. This does not
	certify CRM import or Google-aware Copilot availability. Sandbox connectivity was not
	upgraded by these production checks.
- Retell — NOT CONFIGURED (production API key missing; no call made).
- Telnyx — NOT CONFIGURED (production API/webhook keys missing; no call/SMS made).
- Outlook/Microsoft — BROKEN (current adapter is a placeholder: token exchange/refresh
	unimplemented and reads return empty results).

### Google Credential Rotation Check

The configured sealed service-account JSON authenticated the direct and Central Vertex
requests and matched the dedicated account in memory. A read-only IAM service-account
key-list request returned NOT_AUTHORIZED; therefore the active Google key inventory and
whether this exact key is a separately flagged rotation target are UNKNOWN. No key was
rotated, created, revoked or printed. Safe zero-downtime sequence: create replacement
key for the same least-privilege account; update the sealed Railway variable; deploy;
verify real Vertex direct + AI Central + accounting; only then revoke the previous key.

### Regression Evidence

- Connector root fix and surrounding targeted suites: 313 passed; connector evaluation
	and protected scheduler tests separately passed 9 tests.
- Follow-up AI Central/Agent Registry/security/accounting/tool tests: 114 passed.
- Auth/session, tenant isolation, locales, Voice/accounting, Calendar, Retail source ON/OFF,
	CRM, Commerce/WooCommerce and usage suites: 198 passed; Flutter connection/source flow
	and connector hub tests passed.
- No OAuth credential, external provider setting, business record or production dataset
	was changed by the connector incident check. Local worktree remained clean at report time.

## Final Hardening Follow-up (2026-10-04)

### Google Vertex Credential: Manual Rotation Required

Status: DOCUMENTED / MANUAL ACTION REQUIRED. The existing production credential
continues to authenticate Vertex, but a previously used service-account credential may
have been exposed outside its intended secret store. Treat it as requiring rotation.
No private key was revealed, inspected for identity, rotated, created, revoked or deleted
during this follow-up. This report does not claim that rotation occurred.

Perform this zero-downtime sequence using the existing dedicated account
`avenqo-vertex-runtime@avenqo-509823.iam.gserviceaccount.com`:

1. Create a replacement key for that service account without disabling the old key.
2. Replace `GOOGLE_SERVICE_ACCOUNT_JSON` directly in the Railway sealed production
	secret. Do not place it in a local file, command argument, Git, frontend setting,
	terminal transcript or application log.
3. Deploy the production backend with the replacement secret.
4. Verify production `/health` and `/ready` return healthy/ready and migrations are OK.
5. Perform one minimal real Vertex inference and confirm a successful authenticated
	response without logging its prompt, response or credential material.
6. Verify that AI Central routes a controlled request through Vertex as expected.
7. Verify `AIUsageService` records exactly one logical charge for that request, with
	one corresponding successful provider attempt/reservation/settlement and no duplicate.
8. Only after all checks pass, revoke/delete the old Google key. If verification fails,
	retain the old key while correcting the replacement deployment; do not report rotation
	complete until the old key is revoked.
9. Confirm the replacement secret never entered Git history, frontend configuration or
	logs. If it did, stop and perform the applicable repository-history and secret cleanup.


### Separate Vercel OIDC Material Concern

A separate concern was raised regarding Vercel OIDC credential material. No value is
included here, and this follow-up neither inspects nor changes Vercel credentials. Review
the Vercel project/runtime secret configuration through its authorized control plane and
rotate any material confirmed to be exposed. The tracked-file filename-only scan found no
tracked frontend `.env` files under `frontend/` or `web`, and no credential-like
assignments in such files; no matching lines or values were emitted. No tracked frontend
file referenced Vercel OIDC token material. This scoped result is not a repository-wide
secret scan and does not establish that external Vercel configuration is clear.

### Final Regression Results

- Backend targeted regression: 498 passed, 24 existing warnings. Coverage included
  authentication/session/CSRF, tenant context/isolation, Retail active-source persistence,
  CRM, Copilot/Central AI and execution security, usage/fallback/credits/reservation/
  settlement, Voice, Calendar integration, Shopify/WooCommerce connection and sync state,
  dataset/source state, billing/Stripe, locale and RTL contracts, and migrations.
- Dedicated Assistant Registry, tool registry, and module entitlement suite: 49 passed,
	6 existing warnings. Combined backend total across these focused groups: 547 passed,
	30 existing warnings.
- Read-only production membership check confirmed one active Produits_Ero member; the
	query emitted an aggregate only and did not perform a login or tenant mutation.
- Connector-specific tests are included in the 498 total: 9 passed. Missing-artifact
  failures remain terminal and unreclaimable; transient failures remain retryable; source
  generations coalesce to one evaluation. Sandbox read-only verification found exactly
  one historical `FAILED/blocked/source_artifact_missing` evaluation, attempt count 2,581,
  and zero due claimable rows. No artifact was manufactured/restored and no cron was
  repeated because two prior manual no-op runs already established idempotency: both
  returned `claimed=0`, with no duplicate evaluation/action or attempt-count change.
- Web: 89 tests passed across 5 files, including session and all 44 locale catalogs.
- Flutter: analysis reported no issues; 306 tests passed, including connector, source,
	agent registry, routing, Retail, localization, and RTL/mobile-locale coverage.
- GitHub Actions workflow-dispatch run `37208141393` on the deployed code SHA:
	Frontend Web (catalog generation/check, typecheck, tests and production build) PASS;
	Flutter analyze/tests PASS; Backend Core PASS. Overall CI PASS (all 3 jobs succeeded).
- Production and sandbox `/health` both report `healthy`; `/ready` reports `ready` with
	migrations `ok`, on deployed SHA `acf473d5211c6bf3d2f9b39e8c97f7606428a946`.
- No destructive production mutation, provider call, credential operation, commerce sync,
  payment, calendar write, or source-data mutation was performed. Vertex architecture and
  provider routing were not altered.

## Google Calendar Production Read Verification (2026-10-04)

Final provider status: LIVE VERIFIED, scoped to genuine authenticated Google Calendar
reads using the existing Produits_Ero OAuth connection. No new OAuth architecture,
consent, calendar/event mutation, CRM import, notification or customer creation occurred.
This does not certify the complete CRM/Copilot scheduling workflow.

### Connection And Authentication

- Exactly one tenant-owned Google connection was found, stored as connected; its linked
	user had active Produits_Ero membership. Credentials decrypted successfully through the
	existing server-side Fernet/MultiFernet cipher. No credential or encrypted blob was output.
- Access and refresh tokens were present. Stored account identity matched the connection;
	authenticated Google userinfo returned HTTP 200 and matched that same account in memory.
	No account email was printed. No independent expected account address was supplied, so
	identity verification is against the existing linked record, not a newly asserted account.
- OAuth client ID, client secret and callback configuration were present. All configured
	scopes were recorded: calendar.events, calendar.readonly and userinfo.email. These cover
	the existing read/write product behavior, but calendar.events grants write capability
	beyond this read-only audit; no scopes or consent were changed.
- The stored access token received Calendar HTTP 401. The existing provider refresh method
	returned token-endpoint HTTP 200; the refreshed token then received Calendar HTTP 200.
	Refresh WORKS. Refreshed credentials remained in memory only; no production secret or
	connection row was replaced. Absolute expiry is not stored, although relative expiry
	metadata exists; exact token expiry cannot be established from that metadata alone.
- Calendar list HTTP 200 returned four calendars. The selected calendar resolved and its
	timezone metadata was present. This is genuine API evidence, not a configuration flag
	or mock. Calendar list, selected identity and raw event payloads were not published.

### Read-only Reconciliation And Idempotency

- Two real events.list calls over the same fixed seven-day range both returned HTTP 200,
	with two events and two unique provider IDs. Event identities were stable between calls.
- Neither event had an existing tenant CRM appointment mapping. No unmatched/personal
	event was imported. No claim of successful import or non-empty future mapping is made.
- Read-only PostgreSQL transactions enforced zero writes. Two authorized Copilot appointment
	reads for tomorrow both succeeded with zero appointments and stable results. In-memory
	fingerprints of tenant appointments, customers, communications/notifications and Calendar
	connection records were unchanged around the tool reads; no duplicate record was added.
- Existing tenant data had zero duplicate external-event mapping groups and zero appointment
	references to another tenant's clients. Existing provider-event IDs were compared in memory,
	not printed. CRM stores the provider event ID on appointments and selected calendar ID on
	the connection; it does not store a separate per-appointment external calendar ID, so
	calendar-selection changes are not certified safe by this check.
- No future Physiotherapy appointment exists in tenant CRM. One older Google-mapped
	Physiotherapy appointment was checked in its own narrow interval: events.list HTTP 200
	found its original event ID, not cancelled, with matching start/end instants and aware
	timezone parsing. It was not recreated or represented as an upcoming appointment.
- A genuine one-day Google FreeBusy request returned HTTP 200, zero calendar errors and
	zero busy intervals. This is verified empty busy data for that calendar/range, not an
	assumption of free time after a failed request or a guarantee for other intervals.

### Copilot Availability Limitations

- Existing `search_appointments` executed successfully through ToolExecutor and its
	database-backed authorization policy. A foreign-tenant context was denied at execution.
- `check_availability` executed, but checks CRM appointments only. Its result must not be
	presented as verified Google availability. The slot-list tool constructs the availability
	service without a credential cipher, bypassing the external Google busy-slot read.
- Google FreeBusy failures currently fall back to an empty list, and the availability
	service can silently fall back to CRM-only data. Working-hour generation also uses UTC
	defaults rather than verified tenant-local hours. Therefore Google-aware Copilot
	availability and the assertion that unavailable times are never offered are NOT VERIFIED.
	These existing limitations were documented, not patched or deployed in this audit.
- No LLM inference or full Copilot conversation was run; evidence concerns the existing
	read-tool execution boundary, not an end-to-end conversational scheduling claim.

### Security And Regression

- OAuth credentials remain server-side; the Calendar connection response exposes metadata,
	not tokens. The scoped scan of 628 tracked frontend files found no embedded Google
	credential assignment matches. A 300-record production log slice had zero credential-value
	pattern matches. Raw logs/values were withheld. These bounded checks do not establish a
	repository/history-wide or all-log absence of secrets. Audit logging was disabled to
	prevent provider error bodies and event/account data from being emitted by the probes.
- Targeted Calendar OAuth, CRM/timezone/deduplication, Copilot tools, tenant context,
	execution-time authorization, credential cipher and assistant registry tests: 73 passed.
	Mocks in regression tests establish code behavior only; real HTTP evidence above establishes
	Google access. Tests do not remove the documented availability limitations.
- Production health was healthy; readiness ready; migrations ok, at deployed SHA
	`acf473d5211c6bf3d2f9b39e8c97f7606428a946`. No deployment was performed.
- Retail, Voice, Vertex, billing and datasets were untouched. Shopify/WooCommerce verification
	was not started. Earlier audit edits were preserved.

## Google-aware Availability Implementation (2026-10-04)

Historical candidate status: PARTIALLY VERIFIED (superseded by the deployed release below).
Candidate implementation and regression were complete;
real production-data reads succeeded in an isolated candidate process, but serving code
was not deployed and Produits_Ero lacks configured business opening hours. No hours,
appointments, Google events, customers or notifications were manufactured to remove this
blocker. The previous authenticated Calendar read status remains LIVE VERIFIED.

### Canonical Scheduling Contract

- Extended the existing CRMAvailabilityService rather than adding a second scheduling
	engine. CRM slot reads, Copilot point/slot tools, requested FR/EN/RO/ES read intents,
	and Voice availability delegate to it. Existing conversation/Voice provider architecture
	is retained; no LLM/provider routing changes were made.
- Availability intersects existing business hours (VoiceBusinessConfig), staff shifts when
	requested, CRM appointments/blocked status, selected tenant Google Calendar FreeBusy,
	duration and configured service buffers. Missing business hours return
	BUSINESS_HOURS_UNAVAILABLE instead of assumed 09:00-18:00 hours. No standalone blocked-
	period schema was invented; CRM blocked appointments and Google busy periods are honored.
- Google timeout, 403, malformed/calendar-error responses, decryption failure and failed
	refresh fail closed as EXTERNAL_AVAILABILITY_UNAVAILABLE. A 401 permits one existing
	OAuth refresh and retry. Credential refresh is in memory only; availability never commits
	token or connection updates. Existing event/list read implementations are preserved.
- Tenant-owned staff/services are validated. External reads select only that tenant's
	Google connections; disconnected connections are not active sources, while errored active
	connections prevent a free-slot claim. Caller authentication/membership/entitlement
	enforcement remains at the existing CRM and tool-execution boundaries.
- Tenant timezone is authoritative. Naive local inputs are normalized to UTC; ambiguous
	or nonexistent DST inputs fail explicitly, offset-bearing inputs retain their real
	instant, and slot generation traverses UTC instants while returning local offsets.
	Conflicting business/tenant timezone configuration is unavailable rather than guessed.
- Booking creation/rescheduling rechecks canonical business/staff hours, buffers and
	Google/CRM conflicts under the existing tenant PostgreSQL advisory transaction lock.
	Lock acquisition is off the API event loop; creation rechecks idempotency after acquiring
	the lock. This protects Avenqo workers sharing PostgreSQL, not unrelated third-party
	Google calendar writers; FreeBusy is not an atomic Google reservation.

### Bounded Production-data Verification

- Candidate provider and availability modules were loaded only into an isolated process
	on the production container; no file, server process, deployment or environment setting
	was changed. This is production-data candidate verification, NOT deployed API verification.
- Active Produits_Ero membership and the existing tenant-owned encrypted connection were
	used. A repeatable-read, read-only PostgreSQL transaction enforced zero database writes.
- Two repeated fixed one-hour checks used real Google FreeBusy: stored access-token HTTP
	401, existing OAuth refresh HTTP 200, then FreeBusy HTTP 200. CRM conflict reads succeeded;
	Google busy count was zero and the combined conflict result was false in both checks.
- Full bookable availability was false with BUSINESS_HOURS_UNAVAILABLE in both checks.
	CRM-free plus Google-free is therefore not presented as a bookable slot. The operator
	must configure genuine tenant opening hours before available slots can be offered.
- Responses were stable, and fingerprints of tenant appointments, customers,
	communications/notifications and Calendar connection records remained unchanged.
	Zero appointment/event mutations, notifications or duplicate records were introduced.
- No real busy interval was observed. Google/CRM conflict combinations are TEST VERIFIED,
	not production-observed conflict demonstrations. No synthetic production booking was made.

### Regression And Remaining Verification

- Final targeted/surrounding regression: 225 passed, one existing pytest warning. Coverage
	includes all four CRM/Google busy/free combinations, timeout, successful 401 refresh,
	failed refresh, 403, malformed responses, resource and Google-connection tenant isolation,
	business/staff constraints, existing/candidate buffers, timezone conversion, DST gap/fold
	rejection and slot generation, repeated reads, multilingual Copilot read intents,
	Voice reuse/fail-closed behavior, booking lock order and simultaneous local booking attempts.
	Central AI, provider fallback/accounting, execution security and multilingual Voice
	regression were also included. No claim of live concurrent PostgreSQL booking testing
	is made; the simultaneous-attempt test uses isolated local test data.
- Final production health was healthy; readiness ready; migrations ok, on serving SHA
	`acf473d5211c6bf3d2f9b39e8c97f7606428a946`. The final candidate-source read-only probe
	reproduced the same stable result and zero mutations. Deployment verification remains
	required after operator-approved release and genuine opening-hours configuration.
- No Shopify/WooCommerce work followed. Earlier audit edits and manual credential-rotation
	requirements are preserved. No OAuth credential was printed, rotated or persisted by
	the availability verification.

## Availability Release Candidate And CRM Runtime Repair (2026-10-04)

- Canonical hours now live on the existing tenant Company settings, independent of
	Retell/Telnyx provisioning. Validated CRM GET/PUT settings support timezone, closed days,
	split opening periods and tenant-owned staff shifts. Existing Voice hours remain a
	compatibility source; the canonical service gives tenant settings precedence.
- Temporary verification schedules are explicitly marked verification_only and apply
	to one bounded future date, not weekly company operating hours. Production verification
	must restore and verify the prior schedule; no genuine hours are invented.
- CRM runtime regression root: incomplete KPI responses were assigned unchecked and
	active_clients.toLocaleString threw on undefined. Appointment count/revenue and report
	attendance formatting had the same unsafe contract. Initial fake zero KPIs were removed.
- Numeric/date formatting now validates finite metrics and valid dates. Missing optional
	values use existing localized unavailable states, while genuine API zeroes remain zero.
	API/session failures clear stale data; tenant/source changes invalidate older requests.
- Browser checks with deliberately absent KPI fields passed in FR/Arabic, desktop/mobile,
	with no runtime or console errors. The shell main flex item gained min-width:0 to avoid
	mobile/RTL expansion. Hours UI labels cover all 44 canonical locales.
- Local release gates: 468 broad backend tests passed; 109 final focused scheduling,
	Calendar/security/Voice/migration tests passed with PostgreSQL enabled; 95 web tests
	passed, typecheck/build/catalog checks passed; Flutter analyze clean and 306 tests passed.
- True isolated PostgreSQL concurrent test: two authorized sessions attempted the same
	slot; exactly one success, one conflict and one appointment. No production booking
	was used. CI now provisions PostgreSQL and runs this test continuously.
- API Git triggers in Railway production/sandbox have checkSuites enabled. Web main
	automatic Git deployment is disabled so manual production promotion follows green CI.
	Commit/deployment/live verification receipts are recorded only after completion below.

## Deployed Availability Verification And Next Priority (2026-10-04)

- Release SHA `60637dce56bcefb37336fd361ce214f49f57d341`; CI `37225671750` succeeded:
	backend 295 tests including true PostgreSQL concurrency, web 95 tests/build/typecheck,
	Flutter succeeded. Local broad backend regression passed 468 tests and final focused
	scheduling/security/migration gate passed 109 tests with PostgreSQL enabled.
- Next.js project `web` was deployed after CI and aliased to avenqo.ca; Vercel deployment
	`EutWbGWmJTUG2YHNGN6vw3e3x7Ck`. Flutter's app.avenqo.ca project was not substituted
	for the web target. Local environment files were excluded from manual web uploads.
- Production and sandbox served the release, healthy/ready with migrations ok. Production
	startup showed migration 0037 and no traceback. One transient 502 was observed during
	the single-instance rollout; subsequent fresh checks were green, not stale cached values.
- Produits_Ero's existing active session and current tenant membership were reused in
	memory for normal authenticated CRM API requests. No token, account identity or session
	credential was emitted or persisted by the probe.
- GET/PUT business-hour settings returned 200. With no genuine schedule present, a schedule
	explicitly marked verification_only applied to one future date and a two-hour range.
	Two deployed canonical availability GETs returned 200, three available slots each,
	with identical results. Real FreeBusy returned 401, refresh 200, then FreeBusy 200.
- No Google busy interval was observed; exclusion/conflict behavior remains TEST VERIFIED.
	Fingerprints of appointments, customers, communications/notifications and Calendar
	connection records were unchanged. Zero appointment mutations, Google event mutations,
	notifications or duplicate records were introduced.
- The temporary schedule was restored through the normal PUT path. A fresh GET matched
	the original settings exactly, and record fingerprints remained unchanged after cleanup.
	The operating-hours UI remains functional for entering genuine hours later; removal of
	the verification schedule is not disabling the feature.
- A final small follow-up routes Voice's opening-window and naive-time prechecks through
	the canonical service too, so tenant hours override legacy Voice fields consistently.
	Follow-up SHA `4e4496ca4ed819178a90aa469c16666fcf53bf04` deployed successfully after CI
	`37226580021` passed all three jobs (295 backend tests, 95 web tests and Flutter gate).
	No telephony call is claimed.
- Availability TODOs have evidence for configuration, 44-locale UI/RTL, external fail-closed
	reads, timezone/DST, tenant isolation, idempotency and PostgreSQL same-slot exclusion.
	Earlier candidate-only limitations are historical, not open availability TODOs.

Final availability status: GOOGLE-AWARE AVAILABILITY VERIFIED. The final deployed backend
was reverified through normal authenticated tenant settings and availability APIs: two
identical responses with three slots each, genuine FreeBusy 401/refresh 200/FreeBusy 200,
zero busy periods observed, no record/event/notification mutations, and exact restoration
of the explicitly temporary date-only schedule. The production web KPI proxy returned
HTTP 200 with the expected real numeric contract; no metric values were published.

Final mobile check identified a separate header-width issue; responsive control spacing,
tenant-name truncation and CRM header wrapping repaired it. Browser assertions now check
the whole document, not just the editor: 390px document/viewport on mobile, 1440px on
desktop, FR/Arabic LTR/RTL, with zero runtime or console errors. This final web-only
follow-up is promoted after its own CI gate; backend scheduling logic is unchanged.

Final web receipt: SHA `b31cb00dca4f7fa143e59ec5b0ed8f683900b0c6`, CI `37227846756`
PASS for all three jobs, Vercel production deployment `6Ajzf1fpS7WCQxt8qywtdADzmyqt`,
aliased to avenqo.ca after CI. Post-fix browser measurements were 390/390 pixels for
FR/Arabic mobile and 1440/1440 for desktop, with zero runtime/console errors. No backend
or migration source changed between the fully verified backend SHA and this web receipt.

### Shopify Owner Authorization Required

Fresh tenant-scoped production audit: Shopify app/client/callback configuration present,
HTTPS callback matched the production API host, but Produits_Ero had zero Shopify and
zero WooCommerce connections. No shop authorization, sync or dataset write was attempted.
No CONNECTED/LIVE VERIFIED status is claimed for this tenant. Shopify OAuth and tenant-
security regression passed in the broad gate; no new code defect was established.

Manual next action: sign into Avenqo, select Produits_Ero, open Connections, choose Shopify,
enter the owner's actual myshopify.com shop, sign into Shopify as an authorized owner/admin,
and approve the configured app scopes. Return through the Avenqo callback; verify the
connection status before authorizing a legitimate sync. No credential should be sent in chat.

Downstream external blockers remain truthful: WooCommerce requires owner connection/sync,
its historical missing-artifact evaluation must remain blocked; Anthropic's last real quota/
billing failure is not bypassed; RETELL_API_KEY is missing; TELNYX_API_KEY,
TELNYX_PUBLIC_KEY and TELNYX_MESSAGING_PROFILE_ID are missing. Microsoft OAuth app
credentials are absent and the Outlook provider remains the previously documented partial
placeholder; no new implementation or authenticated Microsoft operation is claimed here.

## Shopify Production Hardening (2026-10-04)

External status: AUTH REQUIRED for Produits_Ero. Fresh read-only production audit found
zero Shopify connections for this tenant. Client/callback/webhook configuration is present;
both callback and webhook are HTTPS on the production API, frontend redirect host is
avenqo.ca, and the configured stable API version is 2026-07. No credential value was
printed, rotated or changed, and no OAuth state/connection/sync was created in production.

### Code-only Findings And Repairs

- Backend previously reported CONNECTED from encrypted-credential presence alone, and a
	token-only manual endpoint persisted CONNECTED before any Shopify validation. That
	endpoint now returns 410 and directs owners to existing OAuth; historical company data
	is not deleted. Web and Flutter now use explicit backend verification state, never a
	client is_active flag or default connected label.
- OAuth verifies the Shopify HMAC before consuming state, serializes state consumption,
	invalidates prior same-store attempts and rejects foreign-tenant shop claims before
	token exchange. Actor membership, data-management permission and active subscription
	are rechecked at callback/persistence time. Nonces remain hashed at rest.
- Authenticated Shopify metadata supplies shop id, name and myshopifyDomain. The returned
	domain must match the authorization request. The real name is persisted and displayed;
	verified setup provenance is required for CONNECTED, including legacy status rows.
- Expiring access/refresh credentials remain server-side encrypted. Renewal is serialized;
	expired/revoked/malformed/reduced-scope refresh fails as REAUTH_REQUIRED, not success.
	The transaction lock is released before subsequent Shopify network calls. Admin 401/403
	requires authorization, while retryable vendor errors remain separate.
- Entity responses missing nodes or valid pagination are errors, not fabricated empty
	products/orders/customers/inventory. Existing entity/nested pagination, normalizers,
	stable tenant dataset ingestion, canonical Retail projection and worker generation
	deduplication are reused. Discounts/refunds are derived from authorized order data.
- Sync checkpoints retain shop metadata and connection settings, including OFF state.
	Disconnect keeps imported datasets/references; disconnected/reauthorization-required
	sync starts are refused. Webhook retries are bound to tenant, connection, topic and
	payload hash; disconnected deliveries cannot relaunch a sync.
- Web tenant/session changes clear store/source data and reject stale API responses.
	All new UI states reuse existing 44-locale catalogs; no new locale registry was added.

### Verification Gates

- Targeted Shopify/source/Retail/worker contract suite: 118 passed. Preservation backend
	regression: 399 passed, one local PostgreSQL test skipped, two existing warnings.
	Final transaction-boundary follow-up: 54 passed. CI continues the isolated PostgreSQL
	gate and now also requires the Shopify/source/worker suites.
- Web typecheck and generated 44-catalog check passed; 97 tests passed; production build
	passed. Flutter analysis clean; 306 tests passed, including 38 focused connector flows.
- These tests prove implementation, tenant isolation, normalized-record/dataset and
	webhook retry contracts. They do NOT prove Shopify production authentication or real
	store data. Products, orders, customers, inventory, real dataset ingestion and real
	Retail/Copilot consumption remain NOT RUN until authorized consent.
- The user authorized commit/push and deployment of these corrections only after green
	CI, expressly without running real Shopify OAuth or sync. Publication gates require
	CI before backend/UI promotion. Final CI/deployment receipts are recorded after success.

### Exact Owner Step

Open https://avenqo.ca/connections after signing in; select the Produits_Ero organization.
In the Shopify card, click the localized Connecter/Connect button. The Connecter Shopify
prompt requests only the actual permanent myshopify.com shop domain, never a secret.
Expect Shopify login (if needed), followed by its app-install/authorization or permission-
update screen for the configured Avenqo app and the correct store. Approve the requested
read_orders, read_customers, read_products, read_inventory and read_locations access.
Cancel if the displayed store/app is not the expected one. No access token, API key or
client secret should be pasted into chat. Return through the Avenqo callback afterward.

Stop here for human owner/admin authorization. Only after this genuine OAuth completion
may bounded production sync, real shop identity and downstream Retail/Copilot consumption
be verified. No Shopify LIVE VERIFIED or CONNECTED claim is made from code tests.

### Publication And Callback Log Safety

Candidate SHA `53ffed7a0b9a552f1e06244cb9b30c650c9ef935` passed CI `37234617850`
for backend, web and Flutter. Web deployment `6gd3Tv5zx847yMfpWAwpTDUG2yCc` was promoted
to avenqo.ca after CI; Flutter deployment `JBfuWYrCC9dXvGn9viEpQv7Ae2Ua` was promoted to
its existing app.avenqo.ca project without changing its backend target. Backend deployment
must be confirmed from fresh health/SHA before the owner proceeds.

A final callback-security review found that Uvicorn access logs would retain OAuth query
parameters. Callback queries are now removed from log records while method/path/status
remain observable; the existing request-id logging is preserved. A synthetic log test
and Shopify/Google OAuth code regressions passed (66 tests); no real callback was run.
The current subscription is also force-refreshed at each callback check instead of using
a stale ORM instance. This final security follow-up is released through its own green CI.

Final backend/security SHA `99af714603f4c7d8124355c53aa70f7dffb92425` passed CI
`37235589237`: 409 backend tests, 97 web tests/build/catalog/typecheck and Flutter gate
all succeeded. Production subsequently served this SHA with healthy/ready and migrations
ok. Authenticated read-only Produits_Ero GETs to the deployed catalog/connections API
both succeeded: Shopify AVAILABLE and CONFIGURED, zero tenant Shopify connections,
zero writes. OAuth, shop identity and real sync remain NOT RUN / NOT VERIFIED.
No OAuth callback, Shopify event, production dataset or provider inference was generated.
Human owner consent is the next required step, not an outstanding engineering test.

## Shopify Pre-authorization TODO Closure (2026-10-04)

All currently identified safe pre-authorization engineering/verification TODOs are
COMPLETE. External status remains AUTH REQUIRED, not CONNECTED or LIVE VERIFIED.

- Local hub verification COMPLETE: desktop 1440px/mobile 390px, French and Arabic RTL,
	no document overflow, no runtime/console errors, explicit unverified-state rejection
	and verified-fixture identity rendering. Exactly one synthetic Connect click reached
	an intercepted synthetic consent screen. All APIs and the Shopify destination were
	mocked; this is UI/handoff evidence only, not Shopify authentication evidence.
- Automated regression COMPLETE: the entire isolated tests/backend and tests/ai_engine
	directories passed 1,318 tests, one local PostgreSQL test skipped, 743 warnings
	(principally existing ML convergence/deprecation warnings). No test failed. Live root
	E2E scripts and destructive production workflows were intentionally excluded.
- Web/localization COMPLETE: 97 tests passed, TypeScript, 44 generated catalogs and
	production build passed. Flutter analysis clean; all 306 tests passed. The already
	published CI also runs isolated PostgreSQL and the required Shopify/source suites.
- Production routes/configuration COMPLETE: anonymous catalog/connections/authorization
	requests returned 401; an empty callback returned 400 without consuming valid state;
	authenticated retired token-only manual connection returned 410. No OAuth start or
	Shopify callback parameters were submitted.
- Authenticated Produits_Ero catalog and connection reads returned 200; the avenqo.ca
	proxy returned 200 with the same tenant connections. Shopify AVAILABLE/CONFIGURED,
	correct production callback/webhook hosts, requested read scopes confirmed, zero
	Shopify connections. No secret/token/account data was emitted. No sync or business
	mutation was performed, and no Vertex/Calendar live operation was repeated.
- Tenant isolation, encrypted storage, callback authorization, source ON/OFF preservation,
	disconnect retention, webhook/record/dataset/worker idempotency and Retail/Copilot data
	contracts remain TEST VERIFIED by the full regression, not real Shopify data claims.

The sole prerequisite for live verification is physical Shopify owner/admin login and
consent through https://avenqo.ca/connections, Produits_Ero, Shopify, Connecter. After
approval, the pending real callback/shop identity/tenant attribution, bounded sync,
products/orders/customers/inventory, dataset/source, Retail/KPI/Copilot and repeated-sync
duplicate checks must be completed using real evidence. They are AUTH BLOCKED, not
forgotten engineering TODOs. No other integration should be marked live or advanced
merely because these simulated/automated checks succeeded.