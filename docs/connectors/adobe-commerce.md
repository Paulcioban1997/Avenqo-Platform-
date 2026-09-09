# Adobe Commerce / Magento

- Readiness: `COMING_SOON`; no adapter is registered.
- Developer account: Adobe Commerce administrator access to a non-production instance.
- Registration: create an integration, grant read-only resources, and activate its access token.
- Callback/webhook: none deployed; store URL plus token is the planned authentication method.
- Scopes: read sales, customers, catalog, inventory, refunds, shipments, and store metadata.
- Environment: future `ADOBE_COMMERCE_STORE_URL`, `ADOBE_COMMERCE_ACCESS_TOKEN`.
- Sandbox/review: use a staging instance; no Adobe marketplace approval is needed for a private integration.
- Acceptance: verify ACL restrictions, pagination, multi-store behavior, token revocation, and the common connector gate before enabling.
