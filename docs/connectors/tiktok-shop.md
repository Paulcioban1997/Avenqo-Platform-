# TikTok Shop

- Readiness: `CONFIGURATION_REQUIRED`; no adapter or Connect action is live.
- Developer account: TikTok Shop Partner Center account and eligible seller test account.
- Registration: create a partner app, select markets/scopes, and submit it for platform review.
- Callback/webhook: reserved `${AVENQO_API_BASE}/api/v1/connectors/tiktok-shop/callback` and `/tiktok-shop/webhook`; neither is deployed.
- Scopes: read orders, products, inventory, returns/refunds, fulfillment, and shop authorization data.
- Environment: future `TIKTOK_SHOP_APP_KEY`, `TIKTOK_SHOP_APP_SECRET`, `TIKTOK_SHOP_REDIRECT_URI`, `TIKTOK_SHOP_WEBHOOK_URI`.
- Sandbox/review: sandbox availability is region/program dependent; partner and production approval are required.
- Acceptance: obtain partner approval, validate signed requests/events, shop authorization, regional quotas, and the common gate.
