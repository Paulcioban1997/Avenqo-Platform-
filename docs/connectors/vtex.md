# VTEX

- Readiness: `COMING_SOON`; no adapter is registered.
- Developer account: VTEX account with administrator access to a test workspace.
- Registration: create an application key/token or OAuth client appropriate to the account contract.
- Callback/webhook: none deployed; client credentials are planned in catalog metadata.
- Scopes: read orders, customers, catalog, SKU inventory, refunds, and logistics.
- Environment: future `VTEX_ACCOUNT_NAME`, `VTEX_CLIENT_ID`, `VTEX_CLIENT_SECRET`, `VTEX_ENVIRONMENT`.
- Sandbox/review: use a development workspace; production API access depends on account policy.
- Acceptance: validate workspace/account boundaries, pagination, throttling, credential rotation, and the common gate.
