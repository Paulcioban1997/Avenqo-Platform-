# Lazada

- Readiness: `COMING_SOON`; no adapter is registered.
- Developer account: Lazada Open Platform developer account and authorized seller test account.
- Registration: create an application and obtain app key/secret for target countries.
- Callback/webhook: reserved `${AVENQO_API_BASE}/api/v1/connectors/lazada/callback`; not deployed.
- Scopes: read orders, products/SKUs, inventory, returns/refunds, logistics, and seller authorization.
- Environment: future `LAZADA_APP_KEY`, `LAZADA_APP_SECRET`, `LAZADA_REDIRECT_URI`, `LAZADA_REGION`.
- Sandbox/review: sandbox and production approval depend on program and country.
- Acceptance: verify signed requests, country endpoints, token refresh, pagination, throttling, and the common gate.
