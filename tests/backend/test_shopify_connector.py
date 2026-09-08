import base64
import hashlib
import hmac
import json
from dataclasses import replace
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import pytest

from backend.app.connectors.shopify import (
    ShopifyAuthenticationError,
    ShopifyConnector,
)
from shared.ai_engine.connectors.commerce import ConnectorSyncContext


def _connector(
    handler,
    *,
    sleep=None,
    max_retries: int = 3,
) -> tuple[ShopifyConnector, httpx.AsyncClient]:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    connector = ShopifyConnector(
        client_id="client-id",
        client_secret="client-secret",
        redirect_uri="https://api.avenqo.test/api/v1/connectors/shopify/callback",
        api_version="2026-07",
        scopes=("read_orders", "read_customers"),
        webhook_uri="https://api.avenqo.test/api/v1/connectors/shopify/webhook",
        http_client=client,
        sleep=sleep or _no_sleep,
        max_retries=max_retries,
    )
    return connector, client


async def _no_sleep(delay: float) -> None:
    return None


def test_shopify_authorization_url_is_tenant_state_bound() -> None:
    connector, _ = _connector(lambda request: httpx.Response(500))

    url = connector.authenticate(
        tenant_id=uuid4(),
        configuration={"shop_domain": "avenqo-demo", "state": "nonce"},
    )
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert parsed.netloc == "avenqo-demo.myshopify.com"
    assert query["client_id"] == ["client-id"]
    assert query["scope"] == ["read_orders,read_customers"]
    assert query["state"] == ["nonce"]


@pytest.mark.parametrize(
    "domain",
    ("https://evil.example", "safe.myshopify.com.evil.example", "two.parts.myshopify.com"),
)
def test_shopify_rejects_unsafe_shop_domains(domain: str) -> None:
    connector, _ = _connector(lambda request: httpx.Response(500))

    with pytest.raises(ShopifyAuthenticationError, match="Invalid Shopify shop domain"):
        connector.authenticate(
            tenant_id=uuid4(),
            configuration={"shop_domain": domain, "state": "nonce"},
        )


@pytest.mark.asyncio
async def test_shopify_oauth_callback_validates_hmac_and_exchanges_expiring_token() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/admin/oauth/access_token"
        assert b"expiring=1" in await request.aread()
        return httpx.Response(
            200,
            json={
                "access_token": "shpat_test",
                "refresh_token": "shprt_test",
                "scope": "read_orders,read_customers",
                "expires_in": 3600,
                "refresh_token_expires_in": 7776000,
            },
        )

    connector, client = _connector(handler)
    parameters = {
        "code": "authorization-code",
        "shop": "avenqo-demo.myshopify.com",
        "state": "nonce",
        "timestamp": "1788800000",
    }
    message = "&".join(f"{key}={value}" for key, value in sorted(parameters.items()))
    parameters["hmac"] = hmac.new(
        b"client-secret", message.encode(), hashlib.sha256
    ).hexdigest()

    credentials = await connector.handle_oauth_callback(
        tenant_id=uuid4(), callback_parameters=parameters
    )

    assert credentials["access_token"] == "shpat_test"
    assert credentials["refresh_token"] == "shprt_test"
    await client.aclose()


@pytest.mark.asyncio
async def test_shopify_graphql_paginates_and_retries_rate_limits() -> None:
    calls = 0
    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "2"})
        variables = json.loads(request.content)["variables"]
        cursor = variables["after"]
        return httpx.Response(
            200,
            json={
                "data": {
                    "orders": {
                        "nodes": [{"id": "gid://shopify/Order/1" if cursor is None else "gid://shopify/Order/2"}],
                        "pageInfo": {
                            "hasNextPage": cursor is None,
                            "endCursor": "next" if cursor is None else None,
                        },
                    }
                },
                "extensions": {
                    "cost": {
                        "throttleStatus": {
                            "currentlyAvailable": 500,
                            "restoreRate": 50,
                        }
                    }
                },
            },
        )

    connector, client = _connector(handler, sleep=sleep)
    context = ConnectorSyncContext(
        tenant_id=uuid4(),
        connection_id=uuid4(),
        access_token="backend-only",
        external_account_id="avenqo-demo.myshopify.com",
    )

    first = await connector.sync_orders(context)
    second = await connector.sync_orders(replace(context, cursor=first.next_cursor))

    assert first.next_cursor == "next"
    assert second.next_cursor is None
    assert delays == [2.0]
    assert calls == 3
    await client.aclose()


@pytest.mark.asyncio
async def test_shopify_paginates_nested_order_line_items() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        variables = json.loads(request.content)["variables"]
        if calls == 1:
            assert variables == {"first": 50, "after": None, "query": None}
            data = {
                "orders": {
                    "nodes": [
                        {
                            "id": "gid://shopify/Order/1",
                            "lineItems": {
                                "nodes": [{"id": "gid://shopify/LineItem/1"}],
                                "pageInfo": {
                                    "hasNextPage": True,
                                    "endCursor": "line-page-2",
                                },
                            },
                            "refunds": [],
                        }
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        else:
            assert variables == {
                "id": "gid://shopify/Order/1",
                "first": 250,
                "after": "line-page-2",
            }
            data = {
                "node": {
                    "lineItems": {
                        "nodes": [{"id": "gid://shopify/LineItem/2"}],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            }
        return httpx.Response(200, json={"data": data})

    connector, client = _connector(handler)
    context = ConnectorSyncContext(
        tenant_id=uuid4(),
        connection_id=uuid4(),
        access_token="backend-only",
        external_account_id="avenqo-demo.myshopify.com",
    )

    page = await connector.sync_orders(context)

    assert calls == 2
    assert [item["id"] for item in page.records[0]["lineItems"]["nodes"]] == [
        "gid://shopify/LineItem/1",
        "gid://shopify/LineItem/2",
    ]
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "root_field", "nested_field", "owner_id", "item_prefix"),
    (
        (
            "sync_products",
            "products",
            "variants",
            "gid://shopify/Product/1",
            "ProductVariant",
        ),
        (
            "sync_inventory",
            "inventoryItems",
            "inventoryLevels",
            "gid://shopify/InventoryItem/1",
            "InventoryLevel",
        ),
    ),
)
async def test_shopify_paginates_nested_catalog_connections(
    method_name: str,
    root_field: str,
    nested_field: str,
    owner_id: str,
    item_prefix: str,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            data = {
                root_field: {
                    "nodes": [
                        {
                            "id": owner_id,
                            nested_field: {
                                "nodes": [{"id": f"gid://shopify/{item_prefix}/1"}],
                                "pageInfo": {
                                    "hasNextPage": True,
                                    "endCursor": "nested-page-2",
                                },
                            },
                        }
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        else:
            variables = json.loads(request.content)["variables"]
            assert variables == {
                "id": owner_id,
                "first": 250,
                "after": "nested-page-2",
            }
            data = {
                "node": {
                    nested_field: {
                        "nodes": [{"id": f"gid://shopify/{item_prefix}/2"}],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            }
        return httpx.Response(200, json={"data": data})

    connector, client = _connector(handler)
    context = ConnectorSyncContext(
        tenant_id=uuid4(),
        connection_id=uuid4(),
        access_token="backend-only",
        external_account_id="avenqo-demo.myshopify.com",
    )

    page = await getattr(connector, method_name)(context)

    assert calls == 2
    assert len(page.records[0][nested_field]["nodes"]) == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_shopify_paginates_nested_refund_line_items() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            data = {
                "orders": {
                    "nodes": [
                        {
                            "id": "gid://shopify/Order/1",
                            "lineItems": {"nodes": []},
                            "refunds": [
                                {
                                    "id": "gid://shopify/Refund/1",
                                    "refundLineItems": {
                                        "nodes": [{"quantity": 1}],
                                        "pageInfo": {
                                            "hasNextPage": True,
                                            "endCursor": "refund-page-2",
                                        },
                                    },
                                }
                            ],
                        }
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        else:
            variables = json.loads(request.content)["variables"]
            assert variables == {
                "id": "gid://shopify/Refund/1",
                "first": 250,
                "after": "refund-page-2",
            }
            data = {
                "node": {
                    "refundLineItems": {
                        "nodes": [{"quantity": 2}],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            }
        return httpx.Response(200, json={"data": data})

    connector, client = _connector(handler)
    context = ConnectorSyncContext(
        tenant_id=uuid4(),
        connection_id=uuid4(),
        access_token="backend-only",
        external_account_id="avenqo-demo.myshopify.com",
    )

    page = await connector.sync_refunds(context)

    assert calls == 2
    assert [item["quantity"] for item in page.records[0]["refundLineItems"]["nodes"]] == [
        1,
        2,
    ]
    await client.aclose()


@pytest.mark.asyncio
async def test_shopify_webhook_registration_creates_only_missing_topics() -> None:
    calls = 0
    missing_topic = ShopifyConnector._WEBHOOK_TOPICS[-1]
    webhook_uri = "https://api.avenqo.test/api/v1/connectors/shopify/webhook"

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        request_payload = json.loads(request.content)
        variables = request_payload["variables"]
        if calls == 1:
            assert "webhookSubscriptions" in request_payload["query"]
            assert variables == {
                "first": 250,
                "after": None,
                "topics": list(ShopifyConnector._WEBHOOK_TOPICS),
                "uri": webhook_uri,
            }
            data = {
                "webhookSubscriptions": {
                    "nodes": [
                        {"topic": topic, "uri": webhook_uri}
                        for topic in ShopifyConnector._WEBHOOK_TOPICS[:-1]
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        else:
            assert "webhookSubscriptionCreate" in request_payload["query"]
            assert variables == {
                "topic": missing_topic,
                "subscription": {"uri": webhook_uri, "format": "JSON"},
            }
            data = {
                "webhookSubscriptionCreate": {
                    "webhookSubscription": {
                        "id": "gid://shopify/WebhookSubscription/1"
                    },
                    "userErrors": [],
                }
            }
        return httpx.Response(200, json={"data": data})

    connector, client = _connector(handler)
    context = ConnectorSyncContext(
        tenant_id=uuid4(),
        connection_id=uuid4(),
        access_token="backend-only",
        external_account_id="avenqo-demo.myshopify.com",
    )

    await connector.register_webhooks(context)

    assert calls == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_shopify_webhook_requires_valid_raw_body_hmac() -> None:
    connector, client = _connector(lambda request: httpx.Response(500))
    body = b'{"id":123}'
    signature = base64.b64encode(
        hmac.new(b"client-secret", body, hashlib.sha256).digest()
    ).decode()

    payload = await connector.handle_webhook(
        tenant_id=uuid4(),
        headers={"x-shopify-hmac-sha256": signature},
        body=body,
    )
    assert payload == {"id": 123}

    with pytest.raises(ShopifyAuthenticationError):
        await connector.handle_webhook(
            tenant_id=uuid4(),
            headers={"x-shopify-hmac-sha256": "invalid"},
            body=body,
        )
    await client.aclose()