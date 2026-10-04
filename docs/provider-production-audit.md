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