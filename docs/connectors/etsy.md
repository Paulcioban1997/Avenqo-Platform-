# Etsy

- Readiness: `CONFIGURATION_REQUIRED`; no adapter or Connect action is live.
- Developer account: Etsy developer account and test shop access.
- Registration: create an API key application and configure OAuth 2.0 PKCE redirect URIs.
- Callback/webhook: reserved `${AVENQO_API_BASE}/api/v1/connectors/etsy/callback` and `/etsy/webhook`; neither is deployed.
- Scopes: `transactions_r`, `listings_r`, `shops_r`, and only additional read scopes required by accepted features.
- Environment: future `ETSY_CLIENT_ID`, `ETSY_REDIRECT_URI`, `ETSY_WEBHOOK_URI`.
- Sandbox/review: Etsy has no general full sandbox; use controlled test listings/orders. Commercial access may require Etsy approval.
- Acceptance: obtain API access, validate PKCE/state, pagination, rate limits, webhook signatures if approved, and the common gate.
