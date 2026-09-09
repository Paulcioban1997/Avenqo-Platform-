# PrestaShop

- Readiness: `COMING_SOON`; no adapter is registered.
- Developer account: administrator access to a staging PrestaShop store.
- Registration: enable webservice access and create a read-only API key restricted by resource.
- Callback/webhook: none deployed; planned authentication is store URL plus API key.
- Scopes: read orders, customers, products, combinations, stock, refunds, and carriers.
- Environment: future `PRESTASHOP_STORE_URL`, `PRESTASHOP_API_KEY`.
- Sandbox/review: use a staging store; no central approval is required for a private webservice key.
- Acceptance: validate version compatibility, ACLs, pagination, revoked-key behavior, and the common sync gate.
