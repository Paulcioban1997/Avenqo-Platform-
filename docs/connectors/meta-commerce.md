# Meta Commerce / Facebook & Instagram Shops

- Readiness: `COMING_SOON`; no adapter is registered.
- Developer account: Meta for Developers account, Business Manager, catalog, and test business assets.
- Registration: create a Meta app, add required products, and configure business verification/app review.
- Callback/webhook: reserved `${AVENQO_API_BASE}/api/v1/connectors/meta-commerce/callback`; not deployed.
- Scopes: least-privilege catalog/product and business asset read permissions; customer/order data is not assumed available.
- Environment: future `META_APP_ID`, `META_APP_SECRET`, `META_REDIRECT_URI`.
- Sandbox/review: test users/assets are available; advanced access requires business verification and App Review.
- Acceptance: verify catalog-only capability boundaries, token lifecycle, business isolation, reviewed permissions, and the common gate.
