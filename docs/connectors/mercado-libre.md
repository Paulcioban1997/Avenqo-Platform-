# Mercado Libre

- Readiness: `COMING_SOON`; no adapter is registered.
- Developer account: Mercado Libre developer account and seller test user for a target site.
- Registration: create an application and configure OAuth redirect URI.
- Callback/webhook: reserved `${AVENQO_API_BASE}/api/v1/connectors/mercado-libre/callback` and `/mercado-libre/webhook`; not deployed.
- Scopes: read orders, items, inventory, claims/refunds, shipments, and seller identity.
- Environment: future `MERCADO_LIBRE_CLIENT_ID`, `MERCADO_LIBRE_CLIENT_SECRET`, `MERCADO_LIBRE_REDIRECT_URI`, `MERCADO_LIBRE_WEBHOOK_URI`.
- Sandbox/review: test users are available by site; production policy varies by market.
- Acceptance: validate site/market differences, OAuth refresh, notifications, pagination, quotas, and the common gate.
