# Amazon Seller Central / SP-API

- Readiness: `CONFIGURATION_REQUIRED`; no adapter or Connect action is live.
- Developer account: Seller Central developer profile, selling partner account, Login with Amazon application, and AWS IAM role.
- Registration: register an SP-API application, request required roles, and complete Amazon review where applicable.
- Callback/webhook: reserved `${AVENQO_API_BASE}/api/v1/connectors/amazon-seller-central/callback`; not deployed. Event delivery requires an approved SQS/SNS design before setup.
- Scopes/roles: Orders, Listings/Products, Inventory, Finances/refunds, and Shipping; restricted data tokens are required for protected data.
- Environment: future `AMAZON_LWA_CLIENT_ID`, `AMAZON_LWA_CLIENT_SECRET`, `AMAZON_AWS_ROLE_ARN`, `AMAZON_SPAPI_REGION`, `AMAZON_REDIRECT_URI`.
- Sandbox/review: dynamic sandbox is available for supported operations; production authorization and restricted roles require Amazon approval.
- Acceptance: obtain external approval, validate LWA/AWS role assumption, restricted-data handling, report polling, quotas, and the common gate before implementation readiness changes.
