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
- Configuration: VERTEX_ENABLED, VERTEX_PROJECT, VERTEX_LOCATION, VERTEX_MODEL are MISSING.
- Authentication: server-side ADC via google-auth; credentials never accepted from chat or a tenant tool argument.
- ADC environment declaration: MISSING. Workload identity, IAM, billing, API enablement, quotas and regional model availability remain UNVERIFIED.
- Region: explicit operator choice, no default global-region substitution.
- SDK: production google-genai 2.28.0 and google-auth 2.59.1 inspected; tests validated on the same Google versions.
- API: stable v1 client, bounded timeout, one SDK attempt for both Google transports; retries remain owned by the existing gateway.
- AI Central and Agent Registry: IMPLEMENTATION VERIFIED with a mocked Vertex response through CentralAIService and the existing Retail agent.
- Tenant isolation: foreign conversation rejected before provider execution in the new central regression test.
- Accounting: one tenant ledger attempt and one credit charge verified in that test; real provider response IDs preserved.
- Pricing: explicit positive input/output rates, cached-input rate, zero separate reasoning rate and versioned source/date required. No invented Vertex tariff or free unknown price.
- Unknown usage: explicit failed `usage_unavailable` attempt; no success, retry or fallback on missing usage. Zero numeric storage fields are not evidence of zero vendor cost; operator reconciliation is required.
- Tools: returned function calls only; SDK automatic function execution disabled. Existing authorization, confirmation and idempotency executor remains authoritative.
- Real production Vertex request: NOT RUN, because configuration prerequisites are missing. No direct-SDK inference bypass of centralized accounting.
- Connected / production verified: NOT VERIFIED. This release deploys capability, not provisioned Google infrastructure.

## Runtime Inventory

- OpenAI text: IMPLEMENTED; CONFIGURED; model metadata READ_ONLY_SUCCESS. Recent production ledger contained 159 successful attempts with response IDs during the observed 24-hour window. Historical inference evidence, not a new audit prompt or a guarantee about every operation.
- Gemini direct: IMPLEMENTED; CONFIGURED; model metadata READ_ONLY_SUCCESS. Recent ledger contained 112 successful attempts with response IDs and four failures. Dynamic alias pricing was not trustworthy; stable model profiles and reasoning-inclusive output accounting were added.
- Anthropic: IMPLEMENTED; CONFIGURED; the previously configured model returned 404. Models-list authentication succeeded and a supported Sonnet replacement's limits were read from the API. Replacement inference/billing remains subject to a centralized live check after deployment.
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

- Existing provider-neutral gateway, smart router, per-model breaker and fallback remain in use. Missing Vertex is excluded from optional routing; explicit invalid pricing fails closed.
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
- Web: 89 tests passed; TypeScript and production build passed.
- Web lint: FAILED with 90 source errors; global traversal reported 5455 errors and 10603 warnings. These are pre-existing frontend surfaces, not changed by this provider release. No lint rules were disabled.
- Flutter: analyze passed; 306 tests passed. Existing dependency/discontinued-package notices remain.
- CI gate expanded to continuously cover provider/accounting/Voice/migration regressions.
- Production health/readiness at audit start: healthy/ready; no deployment completion is inferred from those pre-release checks.

## Operator Provisioning

Provision Vertex server-side ADC (prefer workload identity federation/attached service
account), an explicitly authorized project and region, enabled API/billing, appropriate
IAM and quota, and an accessible model. Supply matching capability limits and verified
Vertex pricing in AI_MODEL_CATALOG / AI_MODEL_RATE_CARD before enabling VERTEX_ENABLED.
Do not paste credentials into chat, commit service-account JSON or reuse a Gemini API key
as evidence of ADC authentication. A single minimal real Vertex request must then pass
through AI Central and AIUsageService, with provider/model, response ID and charge verified.

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