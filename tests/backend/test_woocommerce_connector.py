import base64
import hashlib
import hmac
import json
from dataclasses import replace
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import pytest

from backend.app.connectors.woocommerce import (
    WooCommerceAuthenticationError,
    WooCommerceConnector,
    WooCommercePermissionError,
    WooCommerceRateLimitError,
)
from shared.ai_engine.connectors.commerce import ConnectorSyncContext


async def _no_sleep(delay: float) -> None:
    return None


async def _public_host(hostname: str) -> tuple[str, ...]:
    return ("8.8.8.8",)


def _connector(handler, *, page_size: int = 2, max_retries: int = 3):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    connector = WooCommerceConnector(
        callback_uri="https://api.avenqo.test/api/v1/connectors/woocommerce/callback",
        return_uri="https://app.avenqo.test/connections?connector=woocommerce",
        webhook_uri="https://api.avenqo.test/api/v1/connectors/woocommerce/webhook",
        http_client=client,
        sleep=_no_sleep,
        resolve_host=_public_host,
        page_size=page_size,
        max_retries=max_retries,
    )
    return connector, client


def _context(**changes) -> ConnectorSyncContext:
    values = {
        "tenant_id": uuid4(),
        "connection_id": uuid4(),
        "access_token": "",
        "external_account_id": "https://merchant.example/shop",
        "credentials": {
            "consumer_key": "ck_test",
            "consumer_secret": "cs_test",
            "webhook_secret": "webhook-test-secret",
        },
    }
    values.update(changes)
    return ConnectorSyncContext(**values)


def test_woocommerce_authorization_url_is_state_bound_and_normalized() -> None:
    connector, _ = _connector(lambda request: httpx.Response(500))

    authorization_url = connector.authenticate(
        tenant_id=uuid4(),
        configuration={
            "store_url": " https://Merchant.Example/shop/ ",
            "state": "nonce",
        },
    )
    parsed = urlparse(authorization_url)
    query = parse_qs(parsed.query)

    assert parsed.netloc == "merchant.example"
    assert parsed.path == "/shop/wc-auth/v1/authorize"
    assert query["scope"] == ["read_write"]
    assert query["user_id"] == ["nonce"]
    assert query["callback_url"] == [
        "https://api.avenqo.test/api/v1/connectors/woocommerce/callback?state=nonce"
    ]


@pytest.mark.parametrize(
    "store_url",
    (
        "http://merchant.example",
        "https://user:password@merchant.example",
        "https://merchant.example?consumer_secret=secret",
        "https://127.0.0.1",
        "not-a-url",
    ),
)
def test_woocommerce_rejects_unsafe_store_urls(store_url: str) -> None:
    connector, _ = _connector(lambda request: httpx.Response(500))

    with pytest.raises(
        WooCommerceAuthenticationError,
        match="Invalid WooCommerce store URL",
    ):
        connector.normalize_store_url(store_url)


def test_woocommerce_allows_explicit_local_development_http() -> None:
    connector = WooCommerceConnector(
        callback_uri="https://api.avenqo.test/callback",
        return_uri="http://localhost:8080/connections",
        webhook_uri="https://api.avenqo.test/webhook",
        allow_insecure_localhost=True,
    )

    assert connector.normalize_store_url("http://localhost:8081/shop/") == (
        "http://localhost:8081/shop"
    )


@pytest.mark.asyncio
async def test_woocommerce_callback_requires_returned_credentials_and_permissions() -> None:
    connector, client = _connector(lambda request: httpx.Response(500))

    credentials = await connector.handle_oauth_callback(
        tenant_id=uuid4(),
        callback_parameters={
            "consumer_key": "ck_returned",
            "consumer_secret": "cs_returned",
            "key_permissions": "read_write",
        },
    )

    assert credentials == {
        "consumer_key": "ck_returned",
        "consumer_secret": "cs_returned",
        "key_permissions": "read_write",
    }
    with pytest.raises(WooCommerceAuthenticationError, match="was rejected"):
        await connector.handle_oauth_callback(
            tenant_id=uuid4(),
            callback_parameters={
                "consumer_key": "ck_returned",
                "consumer_secret": "invalid",
                "key_permissions": "read",
            },
        )
    await client.aclose()


@pytest.mark.asyncio
async def test_woocommerce_connection_test_checks_required_resources_without_url_secrets() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        assert request.headers["Authorization"].startswith("Basic ")
        assert "ck_test" not in str(request.url)
        assert "cs_test" not in str(request.url)
        return httpx.Response(200, json=[])

    connector, client = _connector(handler)

    assert await connector.test_connection(_context()) is True
    assert paths == [
        "/shop/wp-json/wc/v3/products",
        "/shop/wp-json/wc/v3/orders",
        "/shop/wp-json/wc/v3/customers",
    ]
    await client.aclose()


@pytest.mark.asyncio
async def test_woocommerce_rejects_invalid_credentials_and_permissions() -> None:
    for status_code, error in (
        (401, WooCommerceAuthenticationError),
        (403, WooCommercePermissionError),
    ):
        connector, client = _connector(
            lambda request, status_code=status_code: httpx.Response(status_code)
        )
        with pytest.raises(error):
            await connector.test_connection(_context())
        await client.aclose()


@pytest.mark.asyncio
async def test_woocommerce_order_pagination_incremental_filter_and_rate_limit_retry() -> None:
    calls = 0
    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "2"})
        page = int(request.url.params["page"])
        assert request.url.params["modified_after"] == "2026-09-01T00:00:00Z"
        return httpx.Response(
            200,
            headers={"X-WP-TotalPages": "2"},
            json=[{"id": page, "line_items": []}],
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    connector = WooCommerceConnector(
        callback_uri="https://api.avenqo.test/callback",
        return_uri="https://app.avenqo.test/connections",
        webhook_uri="https://api.avenqo.test/webhook",
        http_client=client,
        sleep=sleep,
        resolve_host=_public_host,
        page_size=2,
    )
    context = _context(updated_since="2026-09-01T00:00:00Z")

    first = await connector.sync_orders(context)
    second = await connector.sync_orders(replace(context, cursor=first.next_cursor))

    assert first.next_cursor == "2"
    assert second.next_cursor is None
    assert delays == [2.0]
    await client.aclose()


@pytest.mark.asyncio
async def test_woocommerce_customers_use_supported_id_ordering() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/customers")
        assert request.url.params["orderby"] == "id"
        assert request.url.params["order"] == "asc"
        return httpx.Response(
            200,
            headers={"X-WP-TotalPages": "1"},
            json=[{"id": 12, "first_name": "Luc", "last_name": "Martin"}],
        )

    connector, client = _connector(handler)

    page = await connector.sync_customers(_context())

    assert [record["id"] for record in page.records] == [12]
    assert page.next_cursor is None
    await client.aclose()


@pytest.mark.asyncio
async def test_woocommerce_raises_after_repeated_rate_limits() -> None:
    connector, client = _connector(
        lambda request: httpx.Response(429),
        max_retries=1,
    )

    with pytest.raises(WooCommerceRateLimitError, match="rate limit"):
        await connector.sync_orders(_context())
    await client.aclose()


@pytest.mark.asyncio
async def test_woocommerce_products_variations_inventory_and_refunds() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/products"):
            return httpx.Response(
                200,
                headers={"X-WP-TotalPages": "1"},
                json=[
                    {
                        "id": 10,
                        "name": "Variable product",
                        "variations": [11],
                        "date_modified_gmt": "2026-09-01T10:00:00",
                    }
                ],
            )
        if path.endswith("/products/10/variations"):
            return httpx.Response(
                200,
                headers={"X-WP-TotalPages": "1"},
                json=[
                    {
                        "id": 11,
                        "sku": "SKU-11",
                        "price": "12.50",
                        "stock_quantity": 7,
                    }
                ],
            )
        if path.endswith("/orders"):
            return httpx.Response(
                200,
                headers={"X-WP-TotalPages": "1"},
                json=[{"id": 20, "line_items": []}],
            )
        if path.endswith("/orders/20/refunds"):
            return httpx.Response(
                200,
                headers={"X-WP-TotalPages": "1"},
                json=[{"id": 30, "amount": "5.00", "line_items": []}],
            )
        raise AssertionError(path)

    connector, client = _connector(handler)

    products = await connector.sync_products(_context())
    inventory = await connector.sync_inventory(_context())
    refunds = await connector.sync_refunds(_context())

    assert products.records[0]["avenqo_variations"][0]["id"] == 11
    assert inventory.records[0]["id"] == "variation:11"
    assert inventory.records[0]["stock_quantity"] == 7
    assert refunds.records[0]["id"] == "20:30"
    assert refunds.records[0]["avenqo_order_id"] == "20"
    await client.aclose()


@pytest.mark.asyncio
async def test_woocommerce_empty_store_returns_empty_pages() -> None:
    connector, client = _connector(
        lambda request: httpx.Response(
            200,
            headers={"X-WP-TotalPages": "0"},
            json=[],
        )
    )

    assert (await connector.sync_orders(_context())).records == ()
    assert (await connector.sync_customers(_context())).records == ()
    assert (await connector.sync_products(_context())).records == ()
    await client.aclose()


@pytest.mark.asyncio
async def test_woocommerce_webhook_signature_is_verified() -> None:
    connector, client = _connector(lambda request: httpx.Response(500))
    body = json.dumps({"id": 42}).encode()
    signature = base64.b64encode(
        hmac.new(b"webhook-test-secret", body, hashlib.sha256).digest()
    ).decode()

    payload = await connector.handle_webhook(
        tenant_id=uuid4(),
        headers={"x-wc-webhook-signature": signature},
        body=body,
        credentials={"webhook_secret": "webhook-test-secret"},
    )

    assert payload == {"id": 42}
    with pytest.raises(WooCommerceAuthenticationError, match="signature"):
        await connector.handle_webhook(
            tenant_id=uuid4(),
            headers={"x-wc-webhook-signature": "invalid"},
            body=body,
            credentials={"webhook_secret": "webhook-test-secret"},
        )
    await client.aclose()


@pytest.mark.asyncio
async def test_woocommerce_registers_only_missing_webhooks_without_logging_secret() -> None:
    posts: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                headers={"X-WP-TotalPages": "1"},
                json=[
                    {
                        "id": 1,
                        "topic": "order.created",
                        "delivery_url": (
                            "https://api.avenqo.test/api/v1/connectors/"
                            f"woocommerce/webhook/{context.connection_id}"
                        ),
                        "status": "active",
                    }
                ],
            )
        payload = json.loads(request.content)
        posts.append(payload)
        assert payload["secret"] == "webhook-test-secret"
        return httpx.Response(201, json={"id": len(posts) + 1})

    connector, client = _connector(handler)
    context = _context()

    await connector.register_webhooks(context)

    assert len(posts) == 7
    assert {item["topic"] for item in posts} == {
        "order.updated",
        "order.deleted",
        "product.created",
        "product.updated",
        "product.deleted",
        "customer.created",
        "customer.updated",
    }
    await client.aclose()
