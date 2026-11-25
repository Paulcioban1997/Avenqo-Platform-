# Stripe Facturation & Paiements

- Readiness: `AVAILABLE`; customer status `AVAILABLE` (billing).
- Auth method: `api_key`.
- Capabilities: `customers, incremental_sync, payments, refunds, webhooks`.
- Environment: `STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET`.
- Acceptance: configure tenant-scoped credentials, verify connection health check, execute incremental sync, and confirm strict `company_id` isolation across analytics and Central AI.
