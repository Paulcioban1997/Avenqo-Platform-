# Wix eCommerce

- Readiness: `COMING_SOON`; no adapter or OAuth route exists.
- Developer account: Wix Developers account and a test site with Wix Stores.
- Registration: create an app, configure OAuth, and request only required permissions.
- Callback/webhook: reserved `${AVENQO_API_BASE}/api/v1/connectors/wix-ecommerce/callback` and `/wix-ecommerce/webhook`; not deployed.
- Scopes: read orders, contacts/customers, products, variants, inventory, refunds, and fulfillments.
- Environment: future `WIX_CLIENT_ID`, `WIX_CLIENT_SECRET`, `WIX_REDIRECT_URI`, `WIX_WEBHOOK_URI`.
- Sandbox/review: test sites are available; public distribution may require Wix review.
- Acceptance: exercise OAuth install/uninstall, webhook signatures, pagination, rate limits, and the common sandbox gate.
