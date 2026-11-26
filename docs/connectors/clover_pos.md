# Clover POS

- Readiness: `CONFIGURATION_REQUIRED`; customer status `COMING_SOON` (pos).
- Auth method: `oauth2`.
- Capabilities: `customers, incremental_sync, inventory, locations, orders, payments, products, refunds, variants`.
- Environment: `CLOVER_APP_ID, CLOVER_APP_SECRET`.
- Acceptance: configure tenant-scoped credentials, verify connection health check, execute incremental sync, and confirm strict `company_id` isolation across analytics and Central AI.
