# Shopify

- Readiness: `AVAILABLE`; real OAuth, webhook registration, and sync adapter are deployed.
- Developer account: Shopify Partner account and a development store.
- Registration: create a public/custom app and configure the application URL.
- Callback: `${AVENQO_API_BASE}/api/v1/connectors/shopify/callback` (deployed).
- Webhook: `${AVENQO_API_BASE}/api/v1/connectors/shopify/webhook` (deployed; HMAC verified).
- Scopes: `read_orders`, `read_customers`, `read_products`, `read_inventory`, `read_fulfillments`; request protected customer data approval where Shopify requires it.
- Environment: `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET`, `SHOPIFY_REDIRECT_URI`, `SHOPIFY_WEBHOOK_URI`, optional `SHOPIFY_API_VERSION`.
- Sandbox/review: development stores are supported; distribution and protected-data review depend on app type.
- Acceptance: complete OAuth on a development store, verify webhook registration, run full and incremental sync, compare entity counts, select the Shopify Retail source, and verify tenant-isolated analytics and AI.
