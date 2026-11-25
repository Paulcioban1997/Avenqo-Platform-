# Square POS

- Readiness: `CONFIGURATION_REQUIRED`; customer status `COMING_SOON` (pos).
- Auth method: `oauth2`.
- Capabilities: `customers, incremental_sync, inventory, locations, orders, payments, products, refunds, variants, webhooks`.
- Environment: `SQUARE_APPLICATION_ID, SQUARE_APPLICATION_SECRET`.
- Acceptance: configure tenant-scoped credentials, verify connection health check, execute incremental sync, and confirm strict `company_id` isolation across analytics and Central AI.
