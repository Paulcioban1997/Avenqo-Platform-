# Squarespace Commerce

- Readiness: `COMING_SOON`; metadata only.
- Developer account: Squarespace developer account and a Commerce test site.
- Registration: create an OAuth application and configure a future redirect URI.
- Callback/webhook: reserved `${AVENQO_API_BASE}/api/v1/connectors/squarespace-commerce/callback`; no route is deployed.
- Scopes: read orders, products, variants, inventory, customers where authorized, and fulfillments.
- Environment: future `SQUARESPACE_CLIENT_ID`, `SQUARESPACE_CLIENT_SECRET`, `SQUARESPACE_REDIRECT_URI`.
- Sandbox/review: validate with a non-production site; public app approval depends on Squarespace policy.
- Acceptance: verify available API fields and privacy constraints, then complete the common OAuth and sync gate.
