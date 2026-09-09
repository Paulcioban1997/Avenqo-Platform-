# Shopify POS

- Readiness: `COMING_SOON`; no separate POS adapter or Connect action exists.
- Developer account: Shopify Partner account, development store, POS channel, and test locations.
- Registration: extend the reviewed Shopify application only after POS-specific data mapping is implemented.
- Callback/webhook: would reuse the deployed Shopify OAuth/webhook infrastructure only after explicit adapter support; do not configure a second route today.
- Scopes: read orders, customers, products, inventory, locations, fulfillments, and approved payment metadata; no raw card data.
- Environment: future adapter is expected to reuse `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET`, `SHOPIFY_REDIRECT_URI`, `SHOPIFY_WEBHOOK_URI`.
- Sandbox/review: development stores support testing; POS/protected-data access depends on Shopify approval.
- Acceptance: distinguish POS versus online orders, validate location/inventory mapping and duplicate prevention, then complete the common gate.
