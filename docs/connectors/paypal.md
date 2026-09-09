# PayPal

- Readiness: `COMING_SOON`; no adapter is registered.
- Developer account: PayPal Developer account with sandbox business and buyer accounts.
- Registration: create a REST application and issue sandbox client credentials.
- Callback/webhook: no callback is planned for client credentials; reserved `${AVENQO_API_BASE}/api/v1/connectors/paypal/webhook` is not deployed.
- Scopes: read transactions/orders, customers only where permitted, captures, and refunds.
- Environment: future `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_WEBHOOK_ID`, `PAYPAL_ENVIRONMENT`.
- Sandbox/review: PayPal Sandbox is available; production activation and product eligibility may require review.
- Acceptance: validate token caching, webhook certificates/signatures, pagination, currency/refund mapping, and the common gate.
