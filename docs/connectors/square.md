# Square

- Readiness: `CONFIGURATION_REQUIRED`; no adapter or Connect action is live.
- Developer account: Square Developer account with Sandbox seller/location.
- Registration: create an application, configure OAuth, and request least-privilege permissions.
- Callback/webhook: reserved `${AVENQO_API_BASE}/api/v1/connectors/square/callback` and `/square/webhook`; neither is deployed.
- Scopes: read orders, customers, catalog, inventory, merchants/locations, payments, and refunds.
- Environment: future `SQUARE_APPLICATION_ID`, `SQUARE_APPLICATION_SECRET`, `SQUARE_REDIRECT_URI`, `SQUARE_WEBHOOK_URI`, `SQUARE_ENVIRONMENT`.
- Sandbox/review: full Sandbox support is available; production OAuth apps require Square configuration and applicable review.
- Acceptance: provision credentials, verify OAuth/state, webhook signatures, cursor pagination, idempotency, location isolation, and the common gate.
