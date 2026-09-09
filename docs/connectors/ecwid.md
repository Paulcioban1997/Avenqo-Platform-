# Ecwid

- Readiness: `COMING_SOON`; no adapter is registered.
- Developer account: Ecwid developer account and a test store.
- Registration: create an OAuth application and configure a future redirect URI.
- Callback/webhook: reserved `${AVENQO_API_BASE}/api/v1/connectors/ecwid/callback`; not deployed.
- Scopes: read orders, customers, products, combinations, inventory, refunds, and fulfillments.
- Environment: future `ECWID_CLIENT_ID`, `ECWID_CLIENT_SECRET`, `ECWID_REDIRECT_URI`.
- Sandbox/review: use a test store; publication may require Ecwid review.
- Acceptance: validate OAuth, token refresh, pagination, rate limits, and the common tenant-isolated sync gate.
