# Clover

- Readiness: `COMING_SOON`; no adapter is registered.
- Developer account: Clover developer account with sandbox merchant.
- Registration: create an app, configure OAuth, and select merchant permissions.
- Callback/webhook: reserved `${AVENQO_API_BASE}/api/v1/connectors/clover/callback`; not deployed.
- Scopes: read orders, customers, inventory/items, merchants, payments, refunds, and employees only if required.
- Environment: future `CLOVER_APP_ID`, `CLOVER_APP_SECRET`, `CLOVER_REDIRECT_URI`, `CLOVER_ENVIRONMENT`.
- Sandbox/review: sandbox merchants are available; App Market distribution requires Clover review.
- Acceptance: validate merchant authorization, regional endpoints, pagination, token revocation, and the common gate.
