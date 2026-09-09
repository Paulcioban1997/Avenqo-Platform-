"""WooCommerce REST API connector."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import ipaddress
import json
import socket
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit
from uuid import UUID

import httpx

from shared.ai_engine.connectors.catalog import COMMERCE_CONNECTOR_CATALOG
from shared.ai_engine.connectors.commerce import (
    CommerceConnector,
    ConnectorPage,
    ConnectorSyncContext,
)


class WooCommerceConnectorError(RuntimeError):
    pass


class WooCommerceAuthenticationError(WooCommerceConnectorError):
    pass


class WooCommerceTemporaryError(WooCommerceConnectorError):
    pass


class WooCommercePermissionError(WooCommerceConnectorError):
    pass


class WooCommerceRateLimitError(WooCommerceTemporaryError):
    pass


class WooCommerceConnector(CommerceConnector):
    definition = next(
        item for item in COMMERCE_CONNECTOR_CATALOG if item.provider == "woocommerce"
    )

    def __init__(
        self,
        *,
        callback_uri: str,
        return_uri: str,
        webhook_uri: str,
        app_name: str = "Avenqo",
        allow_insecure_localhost: bool = False,
        http_client: httpx.AsyncClient | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        resolve_host: Callable[[str], Awaitable[Sequence[str]]] | None = None,
        max_retries: int = 3,
        page_size: int = 100,
    ) -> None:
        self._callback_uri = callback_uri
        self._return_uri = return_uri
        self._webhook_uri = webhook_uri
        self._app_name = app_name
        self._allow_insecure_localhost = allow_insecure_localhost
        self._http_client = http_client
        self._sleep = sleep
        self._resolve_host = resolve_host or self._default_resolve_host
        self._max_retries = max_retries
        self._page_size = page_size

    def normalize_store_url(self, value: str) -> str:
        candidate = value.strip()
        parsed = urlsplit(candidate)
        hostname = (parsed.hostname or "").lower()
        local_host = hostname in {"localhost", "127.0.0.1", "::1"}
        if (
            not hostname
            or parsed.scheme.lower() not in {"http", "https"}
            or (parsed.scheme.lower() != "https" and not (
                self._allow_insecure_localhost and local_host
            ))
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise WooCommerceAuthenticationError("Invalid WooCommerce store URL")
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            address = None
        if address is not None and not (self._allow_insecure_localhost and address.is_loopback):
            raise WooCommerceAuthenticationError("Invalid WooCommerce store URL")
        try:
            port = parsed.port
        except ValueError as exc:
            raise WooCommerceAuthenticationError("Invalid WooCommerce store URL") from exc
        netloc = hostname
        if ":" in hostname:
            netloc = f"[{hostname}]"
        if port is not None:
            netloc = f"{netloc}:{port}"
        path = parsed.path.rstrip("/")
        return urlunsplit((parsed.scheme.lower(), netloc, path, "", ""))

    def authenticate(self, *, tenant_id: UUID, configuration: Mapping[str, str]) -> str:
        store_url = self.normalize_store_url(configuration.get("store_url", ""))
        state = configuration.get("state", "").strip()
        if not state:
            raise WooCommerceAuthenticationError("Authorization state is required")
        callback_separator = "&" if "?" in self._callback_uri else "?"
        callback_url = f"{self._callback_uri}{callback_separator}{urlencode({'state': state})}"
        query = urlencode(
            {
                "app_name": self._app_name,
                "scope": "read_write",
                "user_id": state,
                "return_url": self._return_uri,
                "callback_url": callback_url,
            }
        )
        return f"{store_url}/wc-auth/v1/authorize?{query}"

    async def handle_oauth_callback(
        self,
        *,
        tenant_id: UUID,
        callback_parameters: Mapping[str, str],
    ) -> Mapping[str, Any]:
        consumer_key = str(callback_parameters.get("consumer_key") or "").strip()
        consumer_secret = str(callback_parameters.get("consumer_secret") or "").strip()
        permissions = str(callback_parameters.get("key_permissions") or "").strip()
        if (
            not consumer_key.startswith("ck_")
            or not consumer_secret.startswith("cs_")
            or permissions not in {"read", "read_write"}
        ):
            raise WooCommerceAuthenticationError("WooCommerce authorization was rejected")
        return {
            "consumer_key": consumer_key,
            "consumer_secret": consumer_secret,
            "key_permissions": permissions,
        }

    async def test_connection(self, context: ConnectorSyncContext) -> bool:
        for resource in ("products", "orders", "customers"):
            await self._request_api(
                context,
                "GET",
                resource,
                params={"per_page": 1, "page": 1},
            )
        return True

    async def sync_orders(self, context: ConnectorSyncContext) -> ConnectorPage:
        return await self._sync_collection(context, "orders", extra={"status": "any"})

    async def sync_customers(self, context: ConnectorSyncContext) -> ConnectorPage:
        return await self._sync_collection(context, "customers")

    async def sync_products(self, context: ConnectorSyncContext) -> ConnectorPage:
        page = await self._sync_collection(context, "products")
        products: list[Mapping[str, Any]] = []
        for raw_product in page.records:
            product = dict(raw_product)
            product_id = product.get("id")
            variation_ids = product.get("variations") or ()
            if product_id and variation_ids:
                product["avenqo_variations"] = await self._collect_endpoint(
                    context,
                    f"products/{product_id}/variations",
                )
            else:
                product["avenqo_variations"] = []
            products.append(product)
        return ConnectorPage(tuple(products), page.next_cursor)

    async def sync_inventory(self, context: ConnectorSyncContext) -> ConnectorPage:
        products = await self.sync_products(context)
        inventory: list[Mapping[str, Any]] = []
        for product in products.records:
            variations = product.get("avenqo_variations") or ()
            if variations:
                for variation in variations:
                    if not isinstance(variation, Mapping):
                        continue
                    inventory.append(
                        {
                            "id": f"variation:{variation.get('id')}",
                            "inventory_item_id": str(variation.get("id") or ""),
                            "product_id": str(product.get("id") or ""),
                            "sku": variation.get("sku") or "",
                            "stock_quantity": variation.get("stock_quantity"),
                            "updated_at": variation.get("date_modified_gmt")
                            or variation.get("date_modified"),
                        }
                    )
                continue
            inventory.append(
                {
                    "id": f"product:{product.get('id')}",
                    "inventory_item_id": str(product.get("id") or ""),
                    "product_id": str(product.get("id") or ""),
                    "sku": product.get("sku") or "",
                    "stock_quantity": product.get("stock_quantity"),
                    "updated_at": product.get("date_modified_gmt")
                    or product.get("date_modified"),
                }
            )
        return ConnectorPage(tuple(inventory), products.next_cursor)

    async def sync_refunds(self, context: ConnectorSyncContext) -> ConnectorPage:
        orders = await self._sync_collection(context, "orders", extra={"status": "any"})
        refunds: list[Mapping[str, Any]] = []
        for order in orders.records:
            order_id = order.get("id")
            if not order_id:
                continue
            for raw_refund in await self._collect_endpoint(
                context,
                f"orders/{order_id}/refunds",
            ):
                refunds.append(
                    {
                        **dict(raw_refund),
                        "id": f"{order_id}:{raw_refund.get('id')}",
                        "avenqo_order_id": str(order_id),
                    }
                )
        return ConnectorPage(tuple(refunds), orders.next_cursor)

    async def initial_sync(
        self, context: ConnectorSyncContext
    ) -> Mapping[str, tuple[Mapping[str, Any], ...]]:
        return await self._collect_all(context)

    async def incremental_sync(
        self, context: ConnectorSyncContext
    ) -> Mapping[str, tuple[Mapping[str, Any], ...]]:
        if not context.updated_since:
            raise WooCommerceConnectorError(
                "Incremental synchronization requires an update timestamp"
            )
        return await self._collect_all(context)

    async def register_webhooks(self, context: ConnectorSyncContext) -> None:
        webhook_secret = self._credential(context, "webhook_secret")
        delivery_url = f"{self._public_https_url(self._webhook_uri)}/{context.connection_id}"
        existing = await self._collect_endpoint(context, "webhooks")
        existing_topics = {
            str(item.get("topic") or "")
            for item in existing
            if item.get("delivery_url") == delivery_url and item.get("status") == "active"
        }
        for topic in (
            "order.created",
            "order.updated",
            "order.deleted",
            "product.created",
            "product.updated",
            "product.deleted",
            "customer.created",
            "customer.updated",
        ):
            if topic in existing_topics:
                continue
            await self._request_api(
                context,
                "POST",
                "webhooks",
                json={
                    "name": f"Avenqo {topic}",
                    "topic": topic,
                    "delivery_url": delivery_url,
                    "secret": webhook_secret,
                    "status": "active",
                },
            )

    async def handle_webhook(
        self,
        *,
        tenant_id: UUID,
        headers: Mapping[str, str],
        body: bytes,
        credentials: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        supplied = headers.get("x-wc-webhook-signature", "")
        webhook_secret = str((credentials or {}).get("webhook_secret") or "")
        expected = base64.b64encode(
            hmac.new(webhook_secret.encode("utf-8"), body, hashlib.sha256).digest()
        ).decode("ascii")
        if not webhook_secret or not supplied or not hmac.compare_digest(expected, supplied):
            raise WooCommerceAuthenticationError(
                "Invalid WooCommerce webhook signature"
            )
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise WooCommerceConnectorError(
                "Invalid WooCommerce webhook payload"
            ) from exc
        if not isinstance(payload, dict):
            raise WooCommerceConnectorError("Invalid WooCommerce webhook payload")
        return payload

    async def get_sync_status(self, context: ConnectorSyncContext) -> str:
        try:
            return "CONNECTED" if await self.test_connection(context) else "FAILED"
        except WooCommerceConnectorError:
            return "FAILED"

    async def disconnect(self, context: ConnectorSyncContext) -> None:
        delivery_url = f"{self._public_https_url(self._webhook_uri)}/{context.connection_id}"
        for webhook in await self._collect_endpoint(context, "webhooks"):
            if webhook.get("delivery_url") != delivery_url or not webhook.get("id"):
                continue
            await self._request_api(
                context,
                "DELETE",
                f"webhooks/{webhook['id']}",
                params={"force": "true"},
            )

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

    async def _sync_collection(
        self,
        context: ConnectorSyncContext,
        endpoint: str,
        *,
        extra: Mapping[str, str] | None = None,
    ) -> ConnectorPage:
        page_number = self._page_number(context.cursor)
        params: dict[str, Any] = {
            "per_page": self._page_size,
            "page": page_number,
            "orderby": "modified",
            "order": "asc",
            **dict(extra or {}),
        }
        if context.updated_since:
            params["modified_after"] = context.updated_since
        response = await self._request_api(
            context,
            "GET",
            endpoint,
            params=params,
        )
        records = self._json_list(response)
        total_pages = self._positive_integer(response.headers.get("X-WP-TotalPages"))
        has_next = page_number < total_pages if total_pages else len(records) == self._page_size
        return ConnectorPage(tuple(records), str(page_number + 1) if has_next else None)

    async def _collect_endpoint(
        self,
        context: ConnectorSyncContext,
        endpoint: str,
    ) -> list[Mapping[str, Any]]:
        records: list[Mapping[str, Any]] = []
        page = 1
        while True:
            response = await self._request_api(
                context,
                "GET",
                endpoint,
                params={"per_page": self._page_size, "page": page},
            )
            current = self._json_list(response)
            records.extend(current)
            total_pages = self._positive_integer(response.headers.get("X-WP-TotalPages"))
            if (total_pages and page >= total_pages) or (
                not total_pages and len(current) < self._page_size
            ):
                return records
            page += 1

    async def _request_api(
        self,
        context: ConnectorSyncContext,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> httpx.Response:
        store_url = self.normalize_store_url(context.external_account_id)
        await self._validate_remote_host(store_url)
        consumer_key = self._credential(context, "consumer_key")
        consumer_secret = self._credential(context, "consumer_secret")
        url = f"{store_url}/wp-json/wc/v3/{endpoint.lstrip('/')}"
        for attempt in range(self._max_retries + 1):
            try:
                if self._http_client is not None:
                    response = await self._http_client.request(
                        method,
                        url,
                        auth=httpx.BasicAuth(consumer_key, consumer_secret),
                        timeout=30.0,
                        **kwargs,
                    )
                else:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        response = await client.request(
                            method,
                            url,
                            auth=httpx.BasicAuth(consumer_key, consumer_secret),
                            **kwargs,
                        )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt >= self._max_retries:
                    raise WooCommerceTemporaryError(
                        "WooCommerce store is unreachable"
                    ) from exc
                await self._sleep(self._delay(attempt))
                continue
            if response.status_code == 429:
                if attempt >= self._max_retries:
                    raise WooCommerceRateLimitError("WooCommerce rate limit reached")
                retry_after = response.headers.get("Retry-After", "")
                delay = float(retry_after) if retry_after.isdigit() else self._delay(attempt)
                await self._sleep(min(delay, 30.0))
                continue
            if response.status_code >= 500:
                if attempt >= self._max_retries:
                    raise WooCommerceTemporaryError(
                        "WooCommerce REST API is temporarily unavailable"
                    )
                await self._sleep(self._delay(attempt))
                continue
            if response.status_code == 401:
                raise WooCommerceAuthenticationError(
                    "WooCommerce credentials were rejected"
                )
            if response.status_code == 403:
                raise WooCommercePermissionError(
                    "WooCommerce permissions are insufficient"
                )
            if response.status_code == 404:
                raise WooCommerceConnectorError(
                    "WooCommerce REST API is unavailable"
                )
            if response.status_code >= 400:
                raise WooCommerceConnectorError("WooCommerce REST API request failed")
            return response
        raise WooCommerceTemporaryError("WooCommerce REST API is temporarily unavailable")

    async def _validate_remote_host(self, store_url: str) -> None:
        hostname = urlsplit(store_url).hostname or ""
        if self._allow_insecure_localhost and hostname in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            return
        try:
            addresses = await self._resolve_host(hostname)
        except OSError as exc:
            raise WooCommerceTemporaryError("WooCommerce store is unreachable") from exc
        if not addresses:
            raise WooCommerceTemporaryError("WooCommerce store is unreachable")
        for value in addresses:
            try:
                address = ipaddress.ip_address(value)
            except ValueError as exc:
                raise WooCommerceAuthenticationError(
                    "Invalid WooCommerce store URL"
                ) from exc
            if not address.is_global:
                raise WooCommerceAuthenticationError(
                    "WooCommerce store URL resolves to a private address"
                )

    @staticmethod
    async def _default_resolve_host(hostname: str) -> Sequence[str]:
        loop = asyncio.get_running_loop()
        results = await loop.getaddrinfo(
            hostname,
            None,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
        return tuple({str(result[4][0]) for result in results})

    @staticmethod
    def _credential(context: ConnectorSyncContext, key: str) -> str:
        value = str(context.credentials.get(key) or "")
        if not value:
            raise WooCommerceAuthenticationError(
                "WooCommerce credentials are missing"
            )
        return value

    @staticmethod
    def _json_list(response: httpx.Response) -> list[Mapping[str, Any]]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise WooCommerceConnectorError(
                "WooCommerce returned an invalid response"
            ) from exc
        if not isinstance(payload, list) or any(
            not isinstance(item, Mapping) for item in payload
        ):
            raise WooCommerceConnectorError("WooCommerce returned an invalid response")
        return list(payload)

    @staticmethod
    def _page_number(cursor: str | None) -> int:
        if cursor is None:
            return 1
        try:
            value = int(cursor)
        except (TypeError, ValueError) as exc:
            raise WooCommerceConnectorError(
                "WooCommerce pagination cursor is invalid"
            ) from exc
        if value < 1:
            raise WooCommerceConnectorError("WooCommerce pagination cursor is invalid")
        return value

    @staticmethod
    def _positive_integer(value: Any) -> int:
        try:
            parsed = int(value or 0)
        except (TypeError, ValueError):
            return 0
        return parsed if parsed > 0 else 0

    @staticmethod
    def _public_https_url(value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise WooCommerceConnectorError(
                "WooCommerce webhook URI must be a public HTTPS URL"
            )
        return value.rstrip("/")

    @staticmethod
    def _delay(attempt: int) -> float:
        return min(float(2**attempt), 30.0)
