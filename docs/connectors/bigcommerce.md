# BigCommerce

- Readiness: `COMING_SOON`; catalog metadata is not an adapter.
- Developer account: BigCommerce Developer Portal account and sandbox store.
- Registration: create an app with OAuth client ID/secret and least-privilege store scopes.
- Callback/webhook: reserved `${AVENQO_API_BASE}/api/v1/connectors/bigcommerce/callback` and `/bigcommerce/webhook`; neither is deployed.
- Scopes: read orders, customers, products, inventory, refunds, and fulfillments.
- Environment: future `BIGCOMMERCE_CLIENT_ID`, `BIGCOMMERCE_CLIENT_SECRET`, `BIGCOMMERCE_REDIRECT_URI`, `BIGCOMMERCE_WEBHOOK_URI`.
- Sandbox/review: sandbox stores are available; marketplace distribution requires BigCommerce review.
- Acceptance: complete the common OAuth, webhook, pagination, rate-limit, isolation, and sandbox-sync gate before changing readiness.
