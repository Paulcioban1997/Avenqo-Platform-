# Stripe

- Readiness: `COMING_SOON`; no commerce adapter is registered.
- Developer account: Stripe account with test mode and Connect platform configuration if multi-account OAuth is required.
- Registration: create a Connect OAuth application or restricted key design; never ingest raw card data.
- Callback/webhook: reserved `${AVENQO_API_BASE}/api/v1/connectors/stripe-commerce/callback` and `/stripe-commerce/webhook`; neither is deployed.
- Scopes: read customers, payment intents/charges, refunds, and only commerce objects required by the accepted mapping.
- Environment: future `STRIPE_CLIENT_ID`, `STRIPE_CLIENT_SECRET`, `STRIPE_REDIRECT_URI`, `STRIPE_WEBHOOK_SECRET`.
- Sandbox/review: test mode is available; Connect platform review/activation may be required.
- Acceptance: validate connected-account isolation, event signatures/idempotency, pagination, refunds, restricted-key policy, and the common gate.
