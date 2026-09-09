# Commerce connector runbook

This directory documents the canonical 30-provider Connector Hub catalog. Metadata registration is not adapter implementation.

## Readiness meanings

- `AVAILABLE`: a production adapter is registered and the Hub may offer Connect.
- `CONFIGURATION_REQUIRED`: Avenqo still needs external app registration, credentials, review, or partner approval. It is not live.
- `COMING_SOON`: catalog metadata exists, but no adapter is registered.
- `BETA`: implemented with an explicitly limited acceptance scope.
- `UNAVAILABLE`: deliberately disabled.

Only Shopify is currently `AVAILABLE`. Never change readiness until an adapter, tenant isolation, encrypted credential storage, pagination, retries, rate-limit handling, incremental sync, snapshot normalization, disconnect behavior, and provider acceptance tests are complete.

## URL conventions

`AVENQO_API_BASE` is the public backend origin. Shopify currently deploys:

- Callback: `${AVENQO_API_BASE}/api/v1/connectors/shopify/callback`
- Webhook: `${AVENQO_API_BASE}/api/v1/connectors/shopify/webhook`

Other provider files show reserved URL shapes. Reserved URLs are not deployed endpoints and must not be entered in a provider console until the adapter routes exist.

## Acceptance gate

For every new adapter: provision a sandbox account where available; register least-privilege scopes; verify OAuth state and signature validation; sync paginated fixtures; exercise 429 retry/backoff; verify incremental checkpoints and webhook idempotency; confirm cross-tenant denial; disconnect and revoke credentials; run connector, active-source, billing, and Retail AI isolation tests; then perform a reviewed sandbox sync before changing catalog readiness.

Secrets belong in the deployment secret manager. Do not commit populated environment files.
