# Shopee

- Readiness: `COMING_SOON`; no adapter is registered.
- Developer account: Shopee Open Platform partner account and authorized test shop.
- Registration: create a partner application and obtain partner ID/key for supported markets.
- Callback/webhook: reserved `${AVENQO_API_BASE}/api/v1/connectors/shopee/callback`; not deployed.
- Scopes: read orders, products, inventory, returns/refunds, logistics, and shop authorization.
- Environment: future `SHOPEE_PARTNER_ID`, `SHOPEE_PARTNER_KEY`, `SHOPEE_REDIRECT_URI`, `SHOPEE_REGION`.
- Sandbox/review: test environment and approval depend on region/partner program.
- Acceptance: obtain partner approval, verify request signatures/time skew, market differences, quotas, and the common gate.
