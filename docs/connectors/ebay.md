# eBay

- Readiness: `CONFIGURATION_REQUIRED`; no adapter or Connect action is live.
- Developer account: eBay Developers Program account with sandbox and production keysets.
- Registration: create an OAuth application and configure a RuName/redirect URL.
- Callback/webhook: reserved `${AVENQO_API_BASE}/api/v1/connectors/ebay/callback` and `/ebay/webhook`; neither is deployed.
- Scopes: read inventory, fulfillment/orders, account, marketing where required, and identity basics.
- Environment: future `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`, `EBAY_REDIRECT_URI`, `EBAY_WEBHOOK_URI`, `EBAY_ENVIRONMENT`.
- Sandbox/review: eBay Sandbox is available; production access and event subscriptions may require review/verification.
- Acceptance: obtain production keyset, validate consent, notifications, pagination, quotas, refresh/revocation, and the common gate.
