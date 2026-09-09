# Google Merchant Center

- Readiness: `COMING_SOON`; no adapter is registered.
- Developer account: Google Cloud project, Merchant Center test/account access, and an authorized user or service identity.
- Registration: enable the current Merchant API, configure OAuth consent, and create credentials.
- Callback/webhook: reserved `${AVENQO_API_BASE}/api/v1/connectors/google-merchant-center/callback`; not deployed.
- Scopes: least-privilege Merchant Center product, inventory, and account read scopes.
- Environment: future `GOOGLE_MERCHANT_CLIENT_ID`, `GOOGLE_MERCHANT_CLIENT_SECRET`, `GOOGLE_MERCHANT_REDIRECT_URI`, `GOOGLE_MERCHANT_ACCOUNT_ID`.
- Sandbox/review: use test data/subaccounts where available; external OAuth apps may require Google verification.
- Acceptance: verify account/subaccount isolation, consent, quotas, pagination, product status mapping, and the common gate.
