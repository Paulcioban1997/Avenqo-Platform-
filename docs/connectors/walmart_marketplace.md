# Walmart Marketplace

- Readiness: `CONFIGURATION_REQUIRED`; customer status `COMING_SOON` (marketplace).
- Auth method: `client_credentials`.
- Capabilities: `fulfillments, incremental_sync, inventory, orders, products, refunds, variants`.
- Environment: `WALMART_CLIENT_ID, WALMART_CLIENT_SECRET`.
- Acceptance: configure tenant-scoped credentials, verify connection health check, execute incremental sync, and confirm strict `company_id` isolation across analytics and Central AI.
