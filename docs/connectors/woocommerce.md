# WooCommerce

- Readiness: `COMING_SOON`; no adapter or Connect action exists.
- Developer account: administrator access to a WooCommerce store with REST API enabled.
- Registration: create read-only WooCommerce REST API keys for the integration user.
- Callback/webhook: none deployed; future webhooks require a signed delivery route before configuration.
- Scopes: read orders, customers, products, variations, inventory, refunds, and fulfillments.
- Environment: future `WOOCOMMERCE_STORE_URL`, `WOOCOMMERCE_CONSUMER_KEY`, `WOOCOMMERCE_CONSUMER_SECRET`.
- Sandbox/review: use a staging WordPress store; no central marketplace review for private keys.
- Acceptance: follow the common gate, validate HTTPS/authentication and pagination against staging, then enable readiness only after the adapter is registered.
