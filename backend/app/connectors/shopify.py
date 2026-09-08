"""Shopify OAuth and Admin GraphQL connector."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any
from urllib.parse import urlencode

import httpx

from shared.ai_engine.connectors.catalog import COMMERCE_CONNECTOR_CATALOG
from shared.ai_engine.connectors.commerce import (
    CommerceConnector,
    ConnectorPage,
    ConnectorSyncContext,
)

_SHOP_DOMAIN = re.compile(r"^[a-z0-9][a-z0-9-]*\.myshopify\.com$")


class ShopifyConnectorError(RuntimeError):
    pass


class ShopifyAuthenticationError(ShopifyConnectorError):
    pass


class ShopifyTemporaryError(ShopifyConnectorError):
    pass


class ShopifyConnector(CommerceConnector):
    definition = next(
        item for item in COMMERCE_CONNECTOR_CATALOG if item.provider == "shopify"
    )

    _ORDERS_QUERY = """
      query AvenqoOrders($first: Int!, $after: String, $query: String) {
        orders(first: $first, after: $after, sortKey: UPDATED_AT, query: $query) {
          nodes {
            id name createdAt updatedAt currencyCode email sourceName
            displayFulfillmentStatus
            customer { id email firstName lastName }
            shippingAddress { countryCodeV2 }
            currentSubtotalPriceSet { shopMoney { amount currencyCode } }
            currentTotalPriceSet { shopMoney { amount currencyCode } }
            currentTotalTaxSet { shopMoney { amount currencyCode } }
            totalDiscountsSet { shopMoney { amount currencyCode } }
            lineItems(first: 250) {
              nodes {
                id quantity
                originalUnitPriceSet { shopMoney { amount currencyCode } }
                discountedTotalSet { shopMoney { amount currencyCode } }
                product { id title productType }
                variant { id sku title inventoryQuantity }
                discountAllocations {
                  allocatedAmountSet { shopMoney { amount currencyCode } }
                }
              }
                            pageInfo { hasNextPage endCursor }
            }
                        refunds {
                            id createdAt processedAt updatedAt
              totalRefundedSet { shopMoney { amount currencyCode } }
                            refundLineItems(first: 250) {
                                nodes {
                                    quantity
                                    subtotalSet { shopMoney { amount currencyCode } }
                                    lineItem { id }
                                }
                                pageInfo { hasNextPage endCursor }
              }
            }
          }
          pageInfo { hasNextPage endCursor }
        }
      }
    """
    _ORDER_LINE_ITEMS_QUERY = """
            query AvenqoOrderLineItems($id: ID!, $first: Int!, $after: String) {
                node(id: $id) {
                    ... on Order {
                        lineItems(first: $first, after: $after) {
                            nodes {
                                id quantity
                                originalUnitPriceSet { shopMoney { amount currencyCode } }
                                discountedTotalSet { shopMoney { amount currencyCode } }
                                product { id title productType }
                                variant { id sku title inventoryQuantity }
                                discountAllocations {
                                    allocatedAmountSet { shopMoney { amount currencyCode } }
                                }
                            }
                            pageInfo { hasNextPage endCursor }
                        }
                    }
                }
            }
        """
    _CUSTOMERS_QUERY = """
      query AvenqoCustomers($first: Int!, $after: String, $query: String) {
        customers(first: $first, after: $after, sortKey: UPDATED_AT, query: $query) {
          nodes {
            id email firstName lastName createdAt updatedAt numberOfOrders
            amountSpent { amount currencyCode }
            defaultAddress { countryCodeV2 }
          }
          pageInfo { hasNextPage endCursor }
        }
      }
    """
    _REFUND_LINE_ITEMS_QUERY = """
            query AvenqoRefundLineItems($id: ID!, $first: Int!, $after: String) {
                node(id: $id) {
                    ... on Refund {
                        refundLineItems(first: $first, after: $after) {
                            nodes {
                                quantity
                                subtotalSet { shopMoney { amount currencyCode } }
                                lineItem { id }
                            }
                            pageInfo { hasNextPage endCursor }
                        }
                    }
                }
            }
        """
    _PRODUCTS_QUERY = """
      query AvenqoProducts($first: Int!, $after: String, $query: String) {
        products(first: $first, after: $after, sortKey: UPDATED_AT, query: $query) {
          nodes {
            id title productType vendor createdAt updatedAt
            variants(first: 250) {
              nodes { id sku title price inventoryQuantity updatedAt inventoryItem { id } }
                            pageInfo { hasNextPage endCursor }
            }
          }
          pageInfo { hasNextPage endCursor }
        }
      }
    """
    _PRODUCT_VARIANTS_QUERY = """
            query AvenqoProductVariants($id: ID!, $first: Int!, $after: String) {
                node(id: $id) {
                    ... on Product {
                        variants(first: $first, after: $after) {
                            nodes { id sku title price inventoryQuantity updatedAt inventoryItem { id } }
                            pageInfo { hasNextPage endCursor }
                        }
                    }
                }
            }
        """
    _INVENTORY_QUERY = """
      query AvenqoInventory($first: Int!, $after: String, $query: String) {
        inventoryItems(first: $first, after: $after, query: $query) {
          nodes {
            id sku updatedAt
                        inventoryLevels(first: 250) {
              nodes {
                id
                quantities(names: ["available"]) { name quantity }
                location { id name }
              }
                            pageInfo { hasNextPage endCursor }
            }
          }
          pageInfo { hasNextPage endCursor }
        }
      }
    """
    _INVENTORY_LEVELS_QUERY = """
            query AvenqoInventoryLevels($id: ID!, $first: Int!, $after: String) {
                node(id: $id) {
                    ... on InventoryItem {
                        inventoryLevels(first: $first, after: $after) {
                            nodes {
                                id
                                quantities(names: ["available"]) { name quantity }
                                location { id name }
                            }
                            pageInfo { hasNextPage endCursor }
                        }
                    }
                }
            }
        """
    _WEBHOOK_TOPICS = (
        "ORDERS_CREATE",
        "ORDERS_UPDATED",
        "ORDERS_DELETE",
        "REFUNDS_CREATE",
        "PRODUCTS_CREATE",
        "PRODUCTS_UPDATE",
        "PRODUCTS_DELETE",
        "INVENTORY_ITEMS_CREATE",
        "INVENTORY_ITEMS_UPDATE",
        "INVENTORY_ITEMS_DELETE",
        "INVENTORY_LEVELS_CONNECT",
        "INVENTORY_LEVELS_DISCONNECT",
        "INVENTORY_LEVELS_UPDATE",
        "CUSTOMERS_CREATE",
        "CUSTOMERS_UPDATE",
        "CUSTOMERS_DELETE",
        "APP_UNINSTALLED",
    )

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        api_version: str,
        scopes: Sequence[str],
        webhook_uri: str,
        http_client: httpx.AsyncClient | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        max_retries: int = 3,
        base_delay_seconds: float = 1.0,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._api_version = api_version
        self._scopes = tuple(scopes)
        self._webhook_uri = webhook_uri
        self._http_client = http_client
        self._sleep = sleep
        self._max_retries = max_retries
        self._base_delay_seconds = base_delay_seconds

    @staticmethod
    def normalize_shop_domain(value: str) -> str:
        normalized = value.strip().lower()
        if "." not in normalized:
            normalized = f"{normalized}.myshopify.com"
        if not _SHOP_DOMAIN.fullmatch(normalized):
            raise ShopifyAuthenticationError("Invalid Shopify shop domain")
        return normalized

    def authenticate(self, *, tenant_id, configuration: Mapping[str, str]) -> str:
        shop = self.normalize_shop_domain(configuration.get("shop_domain", ""))
        state = configuration.get("state", "")
        if not state:
            raise ShopifyAuthenticationError("OAuth state is required")
        query = urlencode(
            {
                "client_id": self._client_id,
                "scope": ",".join(self._scopes),
                "redirect_uri": self._redirect_uri,
                "state": state,
            }
        )
        return f"https://{shop}/admin/oauth/authorize?{query}"

    async def handle_oauth_callback(
        self,
        *,
        tenant_id,
        callback_parameters: Mapping[str, str],
    ) -> Mapping[str, Any]:
        self._verify_callback_hmac(callback_parameters)
        shop = self.normalize_shop_domain(callback_parameters.get("shop", ""))
        code = callback_parameters.get("code", "")
        if not code:
            raise ShopifyAuthenticationError("Authorization code is required")
        response = await self._request(
            "POST",
            f"https://{shop}/admin/oauth/access_token",
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "code": code,
                "expiring": "1",
            },
            headers={"Accept": "application/json"},
        )
        if response.status_code >= 400:
            raise ShopifyAuthenticationError("Shopify token exchange failed")
        payload = self._json_object(response)
        access_token = payload.get("access_token")
        refresh_token = payload.get("refresh_token")
        granted_scopes = {
            item.strip() for item in str(payload.get("scope", "")).split(",") if item.strip()
        }
        missing = [scope for scope in self._scopes if scope not in granted_scopes]
        if not access_token or not refresh_token or missing:
            raise ShopifyAuthenticationError("Shopify did not grant the required access")
        return {
            "access_token": str(access_token),
            "refresh_token": str(refresh_token),
            "scope": ",".join(sorted(granted_scopes)),
            "expires_in": int(payload.get("expires_in") or 0),
            "refresh_token_expires_in": int(payload.get("refresh_token_expires_in") or 0),
            "shop": shop,
        }

    async def refresh_credentials(
        self, *, shop: str, refresh_token: str
    ) -> Mapping[str, Any]:
        response = await self._request(
            "POST",
            f"https://{self.normalize_shop_domain(shop)}/admin/oauth/access_token",
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            headers={"Accept": "application/json"},
        )
        if response.status_code == 401:
            raise ShopifyAuthenticationError("Shopify reauthorization is required")
        if response.status_code >= 400:
            raise ShopifyConnectorError("Shopify token refresh failed")
        return self._json_object(response)

    async def test_connection(self, context: ConnectorSyncContext) -> bool:
        data = await self._graphql(context, "query AvenqoShop { shop { id } }")
        return bool((data.get("shop") or {}).get("id"))

    async def sync_orders(self, context: ConnectorSyncContext) -> ConnectorPage:
        page = await self._sync_connection(context, "orders", self._ORDERS_QUERY)
        records: list[Mapping[str, Any]] = []
        for raw_record in page.records:
            record = dict(raw_record)
            line_items = record.get("lineItems")
            if isinstance(line_items, Mapping):
                record["lineItems"] = await self._paginate_nested_connection(
                    context,
                    owner_id=record.get("id"),
                    initial=line_items,
                    field="lineItems",
                    query=self._ORDER_LINE_ITEMS_QUERY,
                    page_size=250,
                )
            refunds: list[Mapping[str, Any]] = []
            for raw_refund in record.get("refunds") or ():
                if not isinstance(raw_refund, Mapping):
                    continue
                refund = dict(raw_refund)
                refund_line_items = refund.get("refundLineItems")
                if isinstance(refund_line_items, Mapping):
                    refund["refundLineItems"] = await self._paginate_nested_connection(
                        context,
                        owner_id=refund.get("id"),
                        initial=refund_line_items,
                        field="refundLineItems",
                        query=self._REFUND_LINE_ITEMS_QUERY,
                        page_size=250,
                    )
                refunds.append(refund)
            record["refunds"] = refunds
            records.append(record)
        return ConnectorPage(tuple(records), page.next_cursor)

    async def sync_customers(self, context: ConnectorSyncContext) -> ConnectorPage:
        return await self._sync_connection(context, "customers", self._CUSTOMERS_QUERY)

    async def sync_products(self, context: ConnectorSyncContext) -> ConnectorPage:
        page = await self._sync_connection(context, "products", self._PRODUCTS_QUERY)
        records: list[Mapping[str, Any]] = []
        for raw_record in page.records:
            record = dict(raw_record)
            variants = record.get("variants")
            if isinstance(variants, Mapping):
                record["variants"] = await self._paginate_nested_connection(
                    context,
                    owner_id=record.get("id"),
                    initial=variants,
                    field="variants",
                    query=self._PRODUCT_VARIANTS_QUERY,
                    page_size=250,
                )
            records.append(record)
        return ConnectorPage(tuple(records), page.next_cursor)

    async def sync_inventory(self, context: ConnectorSyncContext) -> ConnectorPage:
        page = await self._sync_connection(context, "inventoryItems", self._INVENTORY_QUERY)
        records: list[Mapping[str, Any]] = []
        for raw_record in page.records:
            record = dict(raw_record)
            levels = record.get("inventoryLevels")
            if isinstance(levels, Mapping):
                record["inventoryLevels"] = await self._paginate_nested_connection(
                    context,
                    owner_id=record.get("id"),
                    initial=levels,
                    field="inventoryLevels",
                    query=self._INVENTORY_LEVELS_QUERY,
                    page_size=250,
                )
            records.append(record)
        return ConnectorPage(tuple(records), page.next_cursor)

    async def sync_refunds(self, context: ConnectorSyncContext) -> ConnectorPage:
        orders = await self.sync_orders(context)
        refunds: list[Mapping[str, Any]] = []
        for order in orders.records:
            for refund in order.get("refunds") or ():
                refunds.append({**refund, "orderId": order.get("id")})
        return ConnectorPage(tuple(refunds), orders.next_cursor)

    async def sync_discounts(self, context: ConnectorSyncContext) -> ConnectorPage:
        orders = await self.sync_orders(context)
        discounted = tuple(
            order
            for order in orders.records
            if self._money(order.get("totalDiscountsSet")) > 0
        )
        return ConnectorPage(discounted, orders.next_cursor)

    async def initial_sync(
        self, context: ConnectorSyncContext
    ) -> Mapping[str, tuple[Mapping[str, Any], ...]]:
        return await self._collect_all(context)

    async def incremental_sync(
        self, context: ConnectorSyncContext
    ) -> Mapping[str, tuple[Mapping[str, Any], ...]]:
        if not context.updated_since:
            raise ShopifyConnectorError("Incremental sync requires an updated timestamp")
        return await self._collect_all(context)

    async def register_webhooks(self, context: ConnectorSyncContext) -> None:
        listing_query = (
            "query AvenqoWebhooks($first: Int!, $after: String, "
            "$topics: [WebhookSubscriptionTopic!], $uri: String) { "
            "webhookSubscriptions(first: $first, after: $after, topics: $topics, "
            "uri: $uri) { nodes { topic uri } "
            "pageInfo { hasNextPage endCursor } } }"
        )
        mutation = """
          mutation AvenqoWebhook($topic: WebhookSubscriptionTopic!, $subscription: WebhookSubscriptionInput!) {
            webhookSubscriptionCreate(topic: $topic, webhookSubscription: $subscription) {
              webhookSubscription { id }
              userErrors { field message }
            }
          }
        """
        existing_topics: set[str] = set()
        cursor = None
        seen_cursors: set[str] = set()
        while True:
            data = await self._graphql(
                context,
                listing_query,
                {
                    "first": 250,
                    "after": cursor,
                    "topics": list(self._WEBHOOK_TOPICS),
                    "uri": self._webhook_uri,
                },
            )
            subscriptions = data.get("webhookSubscriptions") or {}
            for subscription in subscriptions.get("nodes") or ():
                if isinstance(subscription, Mapping) and subscription.get("uri") == self._webhook_uri:
                    existing_topics.add(str(subscription.get("topic") or ""))
            page_info = subscriptions.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                break
            next_cursor = str(page_info.get("endCursor") or "")
            if not next_cursor or next_cursor in seen_cursors:
                raise ShopifyConnectorError(
                    "Shopify returned invalid webhook pagination data"
                )
            seen_cursors.add(next_cursor)
            cursor = next_cursor

        for topic in self._WEBHOOK_TOPICS:
            if topic in existing_topics:
                continue
            data = await self._graphql(
                context,
                mutation,
                {
                    "topic": topic,
                    "subscription": {"uri": self._webhook_uri, "format": "JSON"},
                },
            )
            errors = (data.get("webhookSubscriptionCreate") or {}).get("userErrors") or []
            if errors:
                raise ShopifyConnectorError("Shopify webhook registration failed")

    async def handle_webhook(
        self,
        *,
        tenant_id,
        headers: Mapping[str, str],
        body: bytes,
    ) -> Mapping[str, Any]:
        supplied = headers.get("x-shopify-hmac-sha256", "")
        expected = base64.b64encode(
            hmac.new(self._client_secret.encode("utf-8"), body, hashlib.sha256).digest()
        ).decode("ascii")
        if not supplied or not hmac.compare_digest(expected, supplied):
            raise ShopifyAuthenticationError("Invalid Shopify webhook signature")
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ShopifyConnectorError("Invalid Shopify webhook payload") from exc
        if not isinstance(payload, dict):
            raise ShopifyConnectorError("Invalid Shopify webhook payload")
        return payload

    async def get_sync_status(self, context: ConnectorSyncContext) -> str:
        try:
            return "CONNECTED" if await self.test_connection(context) else "ERROR"
        except ShopifyConnectorError:
            return "ERROR"

    async def disconnect(self, context: ConnectorSyncContext) -> None:
        mutation = "mutation AvenqoDisconnect { appUninstall { userErrors { field message } } }"
        data = await self._graphql(context, mutation)
        errors = (data.get("appUninstall") or {}).get("userErrors") or []
        if errors:
            raise ShopifyConnectorError("Shopify app uninstall failed")

    async def _collect_all(
        self, context: ConnectorSyncContext
    ) -> Mapping[str, tuple[Mapping[str, Any], ...]]:
        methods = {
            "orders": self.sync_orders,
            "customers": self.sync_customers,
            "products": self.sync_products,
            "inventory": self.sync_inventory,
            "refunds": self.sync_refunds,
        }
        result: dict[str, tuple[Mapping[str, Any], ...]] = {}
        for entity, method in methods.items():
            records: list[Mapping[str, Any]] = []
            cursor = None
            while True:
                page = await method(replace(context, cursor=cursor))
                records.extend(page.records)
                cursor = page.next_cursor
                if cursor is None:
                    break
            result[entity] = tuple(records)
        return result

    async def _sync_connection(
        self,
        context: ConnectorSyncContext,
        field: str,
        query: str,
    ) -> ConnectorPage:
        updated_query = (
            f"updated_at:>='{context.updated_since}'" if context.updated_since else None
        )
        data = await self._graphql(
            context,
            query,
            {"first": 50, "after": context.cursor, "query": updated_query},
        )
        connection = data.get(field) or {}
        page_info = connection.get("pageInfo") or {}
        next_cursor = page_info.get("endCursor") if page_info.get("hasNextPage") else None
        return ConnectorPage(tuple(connection.get("nodes") or ()), next_cursor)

    async def _paginate_nested_connection(
        self,
        context: ConnectorSyncContext,
        *,
        owner_id: Any,
        initial: Mapping[str, Any],
        field: str,
        query: str,
        page_size: int,
    ) -> dict[str, Any]:
        nodes = list(initial.get("nodes") or ())
        page_info = initial.get("pageInfo") or {}
        seen_cursors: set[str] = set()
        while page_info.get("hasNextPage"):
            cursor = str(page_info.get("endCursor") or "")
            if not owner_id or not cursor or cursor in seen_cursors:
                raise ShopifyConnectorError(
                    f"Shopify returned invalid {field} pagination data"
                )
            seen_cursors.add(cursor)
            data = await self._graphql(
                context,
                query,
                {"id": owner_id, "first": page_size, "after": cursor},
            )
            owner = data.get("node")
            connection = owner.get(field) if isinstance(owner, Mapping) else None
            if not isinstance(connection, Mapping):
                raise ShopifyConnectorError(
                    f"Shopify returned invalid {field} pagination data"
                )
            nodes.extend(connection.get("nodes") or ())
            page_info = connection.get("pageInfo") or {}
        return {**initial, "nodes": nodes, "pageInfo": dict(page_info)}

    async def _graphql(
        self,
        context: ConnectorSyncContext,
        query: str,
        variables: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = (
            f"https://{self.normalize_shop_domain(context.external_account_id)}"
            f"/admin/api/{self._api_version}/graphql.json"
        )
        for attempt in range(self._max_retries + 1):
            response = await self._request(
                "POST",
                url,
                json={"query": query, "variables": dict(variables or {})},
                headers={
                    "Content-Type": "application/json",
                    "X-Shopify-Access-Token": context.access_token,
                },
            )
            if response.status_code == 401:
                raise ShopifyAuthenticationError("Shopify reauthorization is required")
            if response.status_code >= 400:
                raise ShopifyConnectorError("Shopify Admin API request failed")
            payload = self._json_object(response)
            errors = payload.get("errors") or []
            retryable = any(
                (error.get("extensions") or {}).get("code")
                in {"THROTTLED", "INTERNAL_SERVER_ERROR"}
                for error in errors
                if isinstance(error, dict)
            )
            if retryable and attempt < self._max_retries:
                await self._sleep(self._delay(attempt))
                continue
            if errors:
                raise ShopifyConnectorError("Shopify Admin API returned an error")
            data = payload.get("data")
            if not isinstance(data, dict):
                raise ShopifyConnectorError("Shopify Admin API returned invalid data")
            await self._respect_throttle(payload)
            return data
        raise ShopifyTemporaryError("Shopify Admin API is temporarily unavailable")

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        for attempt in range(self._max_retries + 1):
            try:
                if self._http_client is not None:
                    response = await self._http_client.request(method, url, timeout=30.0, **kwargs)
                else:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        response = await client.request(method, url, **kwargs)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt >= self._max_retries:
                    raise ShopifyTemporaryError("Shopify is temporarily unreachable") from exc
                await self._sleep(self._delay(attempt))
                continue
            if response.status_code == 429 or response.status_code >= 500:
                if attempt >= self._max_retries:
                    raise ShopifyTemporaryError("Shopify is temporarily unavailable")
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else self._delay(attempt)
                await self._sleep(min(delay, 30.0))
                continue
            return response
        raise ShopifyTemporaryError("Shopify is temporarily unavailable")

    async def _respect_throttle(self, payload: Mapping[str, Any]) -> None:
        throttle = (((payload.get("extensions") or {}).get("cost") or {}).get("throttleStatus") or {})
        available = float(throttle.get("currentlyAvailable") or 0)
        restore_rate = float(throttle.get("restoreRate") or 0)
        if restore_rate > 0 and available < 50:
            await self._sleep(min((50 - available) / restore_rate, 2.0))

    def _verify_callback_hmac(self, parameters: Mapping[str, str]) -> None:
        supplied = parameters.get("hmac", "")
        message = "&".join(
            f"{key}={value}"
            for key, value in sorted(parameters.items())
            if key != "hmac"
        )
        expected = hmac.new(
            self._client_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not supplied or not hmac.compare_digest(expected, supplied):
            raise ShopifyAuthenticationError("Invalid Shopify callback signature")

    def _delay(self, attempt: int) -> float:
        return min(self._base_delay_seconds * (2**attempt), 30.0)

    @staticmethod
    def _json_object(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise ShopifyConnectorError("Shopify returned an invalid response") from exc
        if not isinstance(payload, dict):
            raise ShopifyConnectorError("Shopify returned an invalid response")
        return payload

    @staticmethod
    def _money(value: Any) -> float:
        try:
            return float(((value or {}).get("shopMoney") or {}).get("amount") or 0)
        except (AttributeError, TypeError, ValueError):
            return 0.0