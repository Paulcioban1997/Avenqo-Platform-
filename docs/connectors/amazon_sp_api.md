# Amazon Seller Central (SP-API)

- Readiness: `CONFIGURATION_REQUIRED`; customer status `COMING_SOON` (marketplace).
- Auth method: `partner_authorization`.
- Capabilities: `fulfillments, incremental_sync, inventory, orders, products, refunds, variants`.
- Environment: `AMAZON_LWA_CLIENT_ID, AMAZON_LWA_CLIENT_SECRET, AMAZON_SP_AWS_ROLE_ARN`.
- Acceptance: configure tenant-scoped credentials, verify connection health check, execute incremental sync, and confirm strict `company_id` isolation across analytics and Central AI.
