"""Tests for the EtsyConnector v3 implementation."""
import asyncio
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import pytest

from backend.app.connectors.etsy import (
    EtsyAuthenticationError,
    EtsyConnector,
)


def _make_connector(**kwargs) -> EtsyConnector:
    return EtsyConnector(
        client_id="test_client_id",
        callback_uri="https://app.test/api/v1/commerce/oauth/etsy/callback",
        **kwargs,
    )


# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------

def test_pkce_pair_has_correct_lengths():
    verifier, challenge = EtsyConnector.generate_pkce_pair()
    # verifier is base64url(64 random bytes) — 86 chars unpadded
    assert len(verifier) > 40
    # challenge is base64url(sha256) = 43 chars unpadded
    assert len(challenge) == 43


def test_pkce_pairs_are_unique():
    pairs = {EtsyConnector.generate_pkce_pair() for _ in range(10)}
    assert len(pairs) == 10


# ---------------------------------------------------------------------------
# authenticate()
# ---------------------------------------------------------------------------

def test_authenticate_returns_correct_oauth_url():
    connector = _make_connector()
    url_str = connector.authenticate(
        tenant_id=uuid4(),
        configuration={
            "state": "abc123",
            "code_challenge": "the_challenge",
        },
    )
    parsed = urlparse(url_str)
    qs = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "www.etsy.com"
    assert parsed.path == "/oauth/connect"
    assert qs["response_type"] == ["code"]
    assert qs["client_id"] == ["test_client_id"]
    assert qs["state"] == ["abc123"]
    assert qs["code_challenge"] == ["the_challenge"]
    assert qs["code_challenge_method"] == ["S256"]
    scope_str = qs["scope"][0]
    for expected_scope in ("listings_r", "transactions_r", "shops_r", "profile_r"):
        assert expected_scope in scope_str


def test_authenticate_raises_without_state():
    connector = _make_connector()
    with pytest.raises(EtsyAuthenticationError, match="state"):
        connector.authenticate(
            tenant_id=uuid4(),
            configuration={"code_challenge": "challenge_only"},
        )


def test_authenticate_uses_override_redirect_uri():
    connector = _make_connector()
    url_str = connector.authenticate(
        tenant_id=uuid4(),
        configuration={
            "state": "mystate",
            "code_challenge": "chal",
            "redirect_uri": "https://custom.example/callback",
        },
    )
    qs = parse_qs(urlparse(url_str).query)
    assert qs["redirect_uri"] == ["https://custom.example/callback"]


# ---------------------------------------------------------------------------
# handle_oauth_callback()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_callback_raises_without_code():
    connector = _make_connector()
    with pytest.raises(EtsyAuthenticationError, match="code"):
        await connector.handle_oauth_callback(
            tenant_id=uuid4(),
            callback_parameters={"code_verifier": "verifier_only"},
        )


@pytest.mark.asyncio
async def test_callback_exchanges_code_successfully():
    token_response_payload = {
        "access_token": "etsy_access_token",
        "refresh_token": "etsy_refresh_token",
        "expires_in": 3600,
        "user_id": 12345,
    }

    def mock_transport(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=token_response_payload)

    connector = EtsyConnector(
        client_id="test_client_id",
        callback_uri="https://app.test/callback",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(mock_transport)),
    )
    result = await connector.handle_oauth_callback(
        tenant_id=uuid4(),
        callback_parameters={
            "code": "auth_code_123",
            "code_verifier": "verifier_abc",
        },
    )
    assert result["access_token"] == "etsy_access_token"
    assert result["refresh_token"] == "etsy_refresh_token"
    assert result["expires_in"] == 3600
    assert result["account_id"] == "12345"


@pytest.mark.asyncio
async def test_callback_raises_on_http_error():
    def mock_transport(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="Unauthorized")

    connector = EtsyConnector(
        client_id="test_client_id",
        callback_uri="https://app.test/callback",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(mock_transport)),
    )
    with pytest.raises(EtsyAuthenticationError):
        await connector.handle_oauth_callback(
            tenant_id=uuid4(),
            callback_parameters={"code": "bad_code"},
        )


# ---------------------------------------------------------------------------
# test_connection()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_connection_returns_true_on_200():
    from types import SimpleNamespace

    def mock_transport(request: httpx.Request) -> httpx.Response:
        assert "Bearer" in request.headers.get("Authorization", "")
        return httpx.Response(200, json={"application_id": 1})

    connector = _make_connector()
    ctx = SimpleNamespace(
        access_token="valid_token",
        credentials={"client_id": "test_client_id"},
        external_account_id="shop-12345",
        cursor=None,
        updated_since=None,
    )
    # Patch internal client
    connector._http_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_transport))
    result = await connector.test_connection(ctx)
    assert result is True


@pytest.mark.asyncio
async def test_connection_returns_false_without_token():
    from types import SimpleNamespace
    connector = _make_connector()
    ctx = SimpleNamespace(
        access_token=None,
        credentials={},
        external_account_id="shop-12345",
        cursor=None,
        updated_since=None,
    )
    result = await connector.test_connection(ctx)
    assert result is False


@pytest.mark.asyncio
async def test_connection_returns_false_on_4xx():
    from types import SimpleNamespace

    def mock_transport(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="Unauthorized")

    connector = _make_connector()
    connector._http_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_transport))
    ctx = SimpleNamespace(
        access_token="expired_token",
        credentials={"client_id": "test_client_id"},
        external_account_id="shop-12345",
        cursor=None,
        updated_since=None,
    )
    result = await connector.test_connection(ctx)
    assert result is False


# ---------------------------------------------------------------------------
# sync_orders()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_orders_returns_correct_records():
    from types import SimpleNamespace

    shop_receipts = {
        "count": 2,
        "results": [
            {"receipt_id": 1, "buyer_user_id": 101, "total_price": 50.0},
            {"receipt_id": 2, "buyer_user_id": 102, "total_price": 99.0},
        ],
    }

    def mock_transport(request: httpx.Request) -> httpx.Response:
        if "/receipts" in str(request.url):
            return httpx.Response(200, json=shop_receipts)
        return httpx.Response(404)

    connector = _make_connector()
    connector._http_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_transport))
    ctx = SimpleNamespace(
        access_token="tok",
        credentials={"client_id": "test_client_id"},
        external_account_id="shop-999",
        cursor="0",
        updated_since=None,
    )
    page = await connector.sync_orders(ctx)
    assert len(page.records) == 2
    assert page.records[0]["receipt_id"] == 1


@pytest.mark.asyncio
async def test_sync_orders_returns_empty_on_error():
    from types import SimpleNamespace

    def mock_transport(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    connector = _make_connector()
    connector._http_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_transport))
    ctx = SimpleNamespace(
        access_token="tok",
        credentials={},
        external_account_id="shop-999",
        cursor="0",
        updated_since=None,
    )
    page = await connector.sync_orders(ctx)
    assert page.records == ()
    assert page.next_cursor is None


# ---------------------------------------------------------------------------
# sync_products()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_products_returns_active_listings():
    from types import SimpleNamespace

    listings_response = {
        "count": 3,
        "results": [
            {"listing_id": 10, "title": "Handmade Scarf", "price": {"amount": 45, "divisor": 1}, "quantity": 5},
            {"listing_id": 11, "title": "Wooden Bowl", "price": {"amount": 78, "divisor": 1}, "quantity": 2},
            {"listing_id": 12, "title": "Ceramic Mug", "price": {"amount": 22, "divisor": 1}, "quantity": 10},
        ],
    }

    def mock_transport(request: httpx.Request) -> httpx.Response:
        if "/listings/active" in str(request.url):
            return httpx.Response(200, json=listings_response)
        return httpx.Response(404)

    connector = _make_connector()
    connector._http_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_transport))
    ctx = SimpleNamespace(
        access_token="tok",
        credentials={"client_id": "test_client_id"},
        external_account_id="shop-888",
        cursor="0",
        updated_since=None,
    )
    page = await connector.sync_products(ctx)
    assert len(page.records) == 3
    assert page.records[0]["listing_id"] == 10


# ---------------------------------------------------------------------------
# sync_inventory()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_inventory_maps_quantity_to_stock_fields():
    from types import SimpleNamespace

    listings_response = {
        "count": 1,
        "results": [
            {"listing_id": 55, "title": "Eco Tote Bag", "quantity": 8, "sku": "ECO-TOTE-1"},
        ],
    }

    def mock_transport(request: httpx.Request) -> httpx.Response:
        if "/listings/active" in str(request.url):
            return httpx.Response(200, json=listings_response)
        return httpx.Response(404)

    connector = _make_connector()
    connector._http_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_transport))
    ctx = SimpleNamespace(
        access_token="tok",
        credentials={"client_id": "test_client_id"},
        external_account_id="shop-777",
        cursor="0",
        updated_since=None,
    )
    page = await connector.sync_inventory(ctx)
    assert len(page.records) == 1
    item = page.records[0]
    assert item["stock_quantity"] == 8
    assert item["inventory_level"] == 8
    assert item["product_id"] == "55"


# ---------------------------------------------------------------------------
# sync_customers()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_customers_deduplicates_buyers():
    from types import SimpleNamespace

    receipts = {
        "count": 3,
        "results": [
            {"receipt_id": 1, "buyer_user_id": 200, "buyer_email": "alice@example.com", "name": "Alice"},
            {"receipt_id": 2, "buyer_user_id": 201, "buyer_email": "bob@example.com", "name": "Bob"},
            {"receipt_id": 3, "buyer_user_id": 200, "buyer_email": "alice@example.com", "name": "Alice"},
        ],
    }

    def mock_transport(request: httpx.Request) -> httpx.Response:
        if "/receipts" in str(request.url):
            return httpx.Response(200, json=receipts)
        return httpx.Response(404)

    connector = _make_connector()
    connector._http_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_transport))
    ctx = SimpleNamespace(
        access_token="tok",
        credentials={"client_id": "test_client_id"},
        external_account_id="shop-666",
        cursor="0",
        updated_since=None,
    )
    page = await connector.sync_customers(ctx)
    customer_ids = [c["customer_id"] for c in page.records]
    assert len(customer_ids) == 2
    assert "200" in customer_ids
    assert "201" in customer_ids


# ---------------------------------------------------------------------------
# initial_sync() and incremental_sync()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_initial_sync_returns_all_entity_types():
    from types import SimpleNamespace

    def mock_transport(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/receipts" in url:
            return httpx.Response(200, json={"count": 1, "results": [{"receipt_id": 1, "buyer_user_id": 5}]})
        if "/listings/active" in url:
            return httpx.Response(200, json={"count": 1, "results": [{"listing_id": 10, "quantity": 3}]})
        return httpx.Response(200, json={"count": 0, "results": []})

    connector = _make_connector()
    connector._http_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_transport))
    ctx = SimpleNamespace(
        access_token="tok",
        credentials={"client_id": "test_client_id"},
        external_account_id="shop-555",
        cursor="0",
        updated_since=None,
    )
    result = await connector.initial_sync(ctx)
    assert "orders" in result
    assert "products" in result
    assert "inventory" in result
    assert "customers" in result
    assert "refunds" in result
    assert len(result["orders"]) == 1
    assert len(result["products"]) == 1


@pytest.mark.asyncio
async def test_disconnect_is_noop():
    from types import SimpleNamespace
    connector = _make_connector()
    ctx = SimpleNamespace(
        access_token="tok",
        credentials={},
        external_account_id="shop-444",
        cursor=None,
        updated_since=None,
    )
    # Should complete without raising
    await connector.disconnect(ctx)
