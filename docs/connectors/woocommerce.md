# WooCommerce

Readiness: `BETA`. Shopify remains the only `AVAILABLE` commerce connector. Do not promote WooCommerce until the real-store acceptance steps below pass in the staging sandbox.

Environment: configure the encrypted callback and webhook settings documented below.

Acceptance: complete every real-store staging step before any readiness promotion.

## WOOCOMMERCE_REAL_TEST_REQUIREMENTS

- A staging WordPress site with WooCommerce and the REST API enabled.
- HTTPS with a publicly trusted certificate. Plain HTTP is accepted only for localhost in development when explicitly enabled.
- Representative products, variations, inventory, customers, orders, and refunds. An empty store must also be tested.
- An Avenqo staging tenant with an active subscription and permission to manage connectors.
- Public Avenqo backend callback and webhook endpoints reachable by the WooCommerce store.

## WOOCOMMERCE_REQUIRED_STORE_SETTINGS

- WordPress permalinks must not use the `Plain` format.
- WooCommerce REST API access must be enabled.
- The authorizing WordPress account must be an administrator allowed to create API keys and webhooks.
- Outbound HTTPS requests from WordPress to the Avenqo webhook endpoint must be allowed.
- The canonical store URL must include `https://` and any installation subpath, with no query string, fragment, or embedded credentials.

## WOOCOMMERCE_REQUIRED_PERMISSIONS

The standard WooCommerce authorization flow requests `read_write`. This is required to read products, variations, inventory, customers, orders, and refunds and to create or remove Avenqo webhooks. Manual credentials must also have `Read/Write` access.

Avenqo registers these topics: `order.created`, `order.updated`, `order.deleted`, `product.created`, `product.updated`, `product.deleted`, `customer.created`, and `customer.updated`.

## WOOCOMMERCE_CALLBACK_URL

Set `WOOCOMMERCE_CALLBACK_URI` to:

```text
https://<staging-api-host>/api/v1/connectors/woocommerce/callback
```

The connector appends a one-time `state` query parameter. WooCommerce sends the generated consumer key and secret to this server-to-server callback; they must never be sent to the frontend or written to logs.

## WOOCOMMERCE_WEBHOOK_URL

Set `WOOCOMMERCE_WEBHOOK_URI` to the route prefix:

```text
https://<staging-api-host>/api/v1/connectors/woocommerce/webhook
```

Avenqo appends the connection UUID when registering each webhook. Signatures are verified with the per-connection secret and deliveries are deduplicated by WooCommerce Delivery ID.

## WOOCOMMERCE_ENVIRONMENT_VARIABLES

```dotenv
CONNECTOR_ENCRYPTION_KEYS=<fernet-key>
WOOCOMMERCE_CALLBACK_URI=https://<staging-api-host>/api/v1/connectors/woocommerce/callback
WOOCOMMERCE_WEBHOOK_URI=https://<staging-api-host>/api/v1/connectors/woocommerce/webhook
WOOCOMMERCE_APP_NAME=Avenqo
WOOCOMMERCE_ALLOW_INSECURE_LOCALHOST=false
```

`FRONTEND_URL` must point to the staging frontend so WooCommerce can return the browser to `/connections`. Do not configure global consumer keys: standard authorization or the optional manual form stores credentials encrypted for one tenant and one connection.

## WOOCOMMERCE_REAL_ACCEPTANCE_STEPS

1. Deploy the backend to the staging sandbox with the environment variables above and confirm the catalog reports WooCommerce as `BETA` and `configured: true`.
2. From the staging frontend, enter the canonical store URL and complete the standard WooCommerce authorization as an administrator.
3. Confirm the connection is tenant-scoped, no key or secret appears in API responses or logs, and replaying the callback state is rejected.
4. Confirm the initial background sync imports products, variations, inventory, customers, orders, and refunds without fabricated rows.
5. Create and update an order, product, and customer; confirm signed webhook delivery schedules an incremental sync and replaying the same Delivery ID is ignored.
6. Delete an order or product and confirm its source record is removed only from that connection's materialized snapshot.
7. Exercise pagination and a `429` retry, then confirm an interrupted sync preserves the previous successful snapshot and checkpoint.
8. Switch the tenant's active Retail source between WooCommerce, Shopify, and a file dataset; confirm analytics never mix sources or tenants.
9. Disconnect WooCommerce and confirm Avenqo webhooks and encrypted credentials are removed while historical datasets remain governed by the existing retention policy.
10. Repeat with an empty store and with insufficient permissions. The empty store must complete without demo data; insufficient permissions must produce an actionable failure state.

Keep status `BETA` until all steps pass against a real staging store and the evidence is recorded. Real acceptance is not part of automated mock coverage.
