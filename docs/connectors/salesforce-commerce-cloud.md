# Salesforce Commerce Cloud

- Readiness: `COMING_SOON`; no adapter is registered.
- Developer account: Salesforce Commerce Cloud tenant and Account Manager/API access.
- Registration: create an API client and assign least-privilege OCAPI/SCAPI roles.
- Callback/webhook: none deployed; client credentials are planned.
- Scopes: read orders, customers where contractually allowed, products, inventory, refunds, and shipments.
- Environment: future `SFCC_TENANT_ID`, `SFCC_CLIENT_ID`, `SFCC_CLIENT_SECRET`, `SFCC_INSTANCE_URL`.
- Sandbox/review: use a sandbox realm; customer-data access and production roles require tenant approval.
- Acceptance: validate realm/site boundaries, role restrictions, quotas, pagination, and the common isolation gate.
