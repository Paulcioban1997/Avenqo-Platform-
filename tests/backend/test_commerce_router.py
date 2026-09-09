from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.connectors.shopify import ShopifyConnectorError
from backend.app.dependencies.auth import get_current_identity
from backend.app.dependencies.commerce import (
    get_commerce_connection_service,
    get_commerce_connector_registry,
    get_commerce_sync_runner,
    get_commerce_sync_service,
)
from backend.app.dependencies.subscription import require_active_subscription
from backend.app.routers.commerce import router
from shared.ai_engine.connectors.catalog import COMMERCE_CONNECTOR_CATALOG
from shared.ai_engine.connectors.commerce import ConnectorImplementationStatus
from shared.ai_engine.connectors.registry import CommerceConnectorRegistry
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.exceptions import ConnectorNotRegisteredError


EXPECTED_COMMERCE_PROVIDERS = {
    "shopify",
    "woocommerce",
    "bigcommerce",
    "adobe-commerce",
    "wix-ecommerce",
    "squarespace-commerce",
    "prestashop",
    "ecwid",
    "shopware",
    "salesforce-commerce-cloud",
    "commercetools",
    "vtex",
    "amazon-seller-central",
    "ebay",
    "etsy",
    "walmart-marketplace",
    "tiktok-shop",
    "meta-commerce",
    "mercado-libre",
    "mirakl",
    "shopee",
    "lazada",
    "square",
    "lightspeed-retail",
    "clover",
    "shopify-pos",
    "stripe-commerce",
    "paypal",
    "google-merchant-center",
    "shipstation",
}


class _Connections:
    def __init__(self, company_id):
        self.connection = SimpleNamespace(
            id=uuid4(),
            company_id=company_id,
            provider="shopify",
            external_account_id="alpha.myshopify.com",
            display_name="Alpha",
            status="READY",
            encrypted_credentials="encrypted",
            capabilities=["orders"],
            records_processed=12,
            current_entity=None,
            error_category=None,
            last_successful_sync=datetime.now(timezone.utc),
            sync_started_at=None,
            dataset_ids={},
        )

    def list_connections(self, tenant):
        return (self.connection,)

    def get_connection(self, tenant, connection_id):
        return self.connection


class _Sync:
    def __init__(self):
        self.reserved = []

    def reserve(self, tenant, connection_id):
        self.reserved.append((tenant.company_id, connection_id))


class _Runner:
    def __init__(self):
        self.runs = []
        self.woocommerce_initializations = []

    async def run_reserved(self, tenant, connection_id):
        self.runs.append((tenant.company_id, connection_id))

    async def initialize_woocommerce(self, tenant, connection_id):
        self.woocommerce_initializations.append((tenant.company_id, connection_id))


class _CallbackConnections:
    def __init__(self, company_id):
        self.connection = SimpleNamespace(id=uuid4(), company_id=company_id)
        self.failed = []
        self.completed = []

    async def complete_shopify_oauth(self, callback_parameters):
        return self.connection

    async def sync_context(self, tenant, connection_id):
        return SimpleNamespace()

    def mark_setup_failed(self, tenant, connection_id, *, error_category):
        self.failed.append((tenant.company_id, connection_id, error_category))

    def mark_setup_complete(self, tenant, connection_id):
        self.completed.append((tenant.company_id, connection_id))


class _WooConnections:
    def __init__(self, company_id):
        self.received_credentials = None
        self.connection = SimpleNamespace(
            id=uuid4(),
            company_id=company_id,
            provider="woocommerce",
            external_account_id="https://shop.example.com",
            display_name="shop.example.com",
            status="CONNECTING",
            encrypted_credentials="ciphertext-not-for-response",
            capabilities=["orders", "products"],
            records_processed=0,
            current_entity=None,
            error_category=None,
            last_successful_sync=None,
            sync_started_at=None,
            dataset_ids={},
        )

    async def complete_woocommerce_authorization(self, *, raw_state, callback_payload):
        assert raw_state == "valid-state"
        self.received_credentials = (
            callback_payload["consumer_key"],
            callback_payload["consumer_secret"],
        )
        return self.connection

    async def connect_woocommerce_manual(
        self,
        tenant,
        *,
        actor_user_id,
        store_url,
        consumer_key,
        consumer_secret,
    ):
        self.received_credentials = (consumer_key, consumer_secret)
        return self.connection

    async def sync_context(self, tenant, connection_id):
        return SimpleNamespace(connection_id=connection_id)

    def mark_setup_complete(self, tenant, connection_id):
        self.connection.status = "READY"
        return self.connection

    def mark_setup_degraded(self, tenant, connection_id, *, error_category):
        self.connection.status = "DEGRADED"
        self.connection.error_category = error_category
        return self.connection


class _WooRegistry:
    def get(self, provider):
        assert provider == "woocommerce"
        return self

    async def register_webhooks(self, context):
        return None


class _FailingWebhookRegistry:
    def get(self, provider):
        assert provider == "shopify"
        return self

    async def register_webhooks(self, context):
        raise ShopifyConnectorError("registration unavailable")


class _SuccessfulWebhookRegistry:
    def get(self, provider):
        assert provider == "shopify"
        return self

    async def register_webhooks(self, context):
        return None


def test_connector_catalog_contract_is_exact_and_truthful() -> None:
    definitions = {item.provider: item for item in COMMERCE_CONNECTOR_CATALOG}

    assert set(definitions) == EXPECTED_COMMERCE_PROVIDERS
    assert len(definitions) == 30
    assert {
        provider
        for provider, definition in definitions.items()
        if definition.implementation_status == ConnectorImplementationStatus.AVAILABLE
    } == {"shopify"}
    assert {
        provider
        for provider, definition in definitions.items()
        if definition.implementation_status
        == ConnectorImplementationStatus.CONFIGURATION_REQUIRED
    } == {"amazon-seller-central", "ebay", "etsy", "tiktok-shop", "square"}
    assert all(item.documentation_url for item in definitions.values())
    assert all(item.auth_method for item in definitions.values())
    assert all(item.capabilities for item in definitions.values())
    assert all(item.priority in {"P0", "P1", "P2"} for item in definitions.values())
    for definition in definitions.values():
        documentation = Path(definition.documentation_url.lstrip("/"))
        contents = documentation.read_text(encoding="utf-8")
        assert definition.display_name in contents
        assert "Readiness:" in contents
        assert "Environment:" in contents
        assert "Acceptance:" in contents


def test_catalog_metadata_does_not_register_unimplemented_adapters() -> None:
    registry = CommerceConnectorRegistry()

    assert registry.definition("woocommerce").display_name == "WooCommerce"
    with pytest.raises(ConnectorNotRegisteredError, match="is not available"):
        registry.get("woocommerce")


def test_connector_catalog_and_manual_sync_routes() -> None:
    company_id = uuid4()
    user = SimpleNamespace(
        id=uuid4(),
        company_id=company_id,
        role=SimpleNamespace(),
    )
    identity = SimpleNamespace(user=user)
    registry = CommerceConnectorRegistry()
    connections = _Connections(company_id)
    sync = _Sync()
    runner = _Runner()
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_current_identity] = lambda: identity
    app.dependency_overrides[require_active_subscription] = lambda: TenantContext(
        company_id=company_id
    )
    app.dependency_overrides[get_commerce_connector_registry] = lambda: registry
    app.dependency_overrides[get_commerce_connection_service] = lambda: connections
    app.dependency_overrides[get_commerce_sync_service] = lambda: sync
    app.dependency_overrides[get_commerce_sync_runner] = lambda: runner

    from backend.app.routers import commerce as commerce_router

    app.dependency_overrides[commerce_router.require_connector_read] = lambda: identity
    app.dependency_overrides[commerce_router.manage_connectors] = lambda: identity
    with TestClient(app) as client:
        catalog = client.get("/api/v1/connectors")
        listed = client.get("/api/v1/connectors/connections")
        started = client.post(
            f"/api/v1/connectors/connections/{connections.connection.id}/sync"
        )

    assert catalog.status_code == 200
    assert len(catalog.json()) == 30
    assert all("implementation_status" not in item for item in catalog.json())
    customer_statuses = {
        item["provider"]: item["customer_status"] for item in catalog.json()
    }
    assert customer_statuses["shopify"] == "AVAILABLE"
    assert customer_statuses["woocommerce"] == "COMING_SOON"
    assert set(customer_statuses.values()) == {"AVAILABLE", "COMING_SOON"}
    assert listed.json()[0]["external_account_id"] == "alpha.myshopify.com"
    assert listed.json()[0]["connection_status"] == "CONNECTED"
    assert listed.json()[0]["sync_status"] == "READY"
    assert started.status_code == 202
    assert started.json()["status"] == "SYNCING"
    assert sync.reserved == [(company_id, connections.connection.id)]
    assert runner.runs == [(company_id, connections.connection.id)]


def test_shopify_callback_marks_setup_failed_when_webhooks_cannot_register() -> None:
    company_id = uuid4()
    connections = _CallbackConnections(company_id)
    sync = _Sync()
    runner = _Runner()
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_commerce_connection_service] = lambda: connections
    app.dependency_overrides[get_commerce_sync_service] = lambda: sync
    app.dependency_overrides[get_commerce_sync_runner] = lambda: runner
    app.dependency_overrides[get_commerce_connector_registry] = (
        lambda: _FailingWebhookRegistry()
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/connectors/shopify/callback?state=valid",
            follow_redirects=False,
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Shopify webhook registration failed"
    assert connections.failed == [
        (
            company_id,
            connections.connection.id,
            "webhook_registration_failed",
        )
    ]
    assert connections.completed == []
    assert sync.reserved == []
    assert runner.runs == []


def test_shopify_callback_completes_setup_after_webhook_registration() -> None:
    company_id = uuid4()
    connections = _CallbackConnections(company_id)
    sync = _Sync()
    runner = _Runner()
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_commerce_connection_service] = lambda: connections
    app.dependency_overrides[get_commerce_sync_service] = lambda: sync
    app.dependency_overrides[get_commerce_sync_runner] = lambda: runner
    app.dependency_overrides[get_commerce_connector_registry] = (
        lambda: _SuccessfulWebhookRegistry()
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/connectors/shopify/callback?state=valid",
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert connections.completed == [(company_id, connections.connection.id)]
    assert connections.failed == []
    assert sync.reserved == [(company_id, connections.connection.id)]
    assert runner.runs == [(company_id, connections.connection.id)]


def test_woocommerce_manual_route_masks_secrets_and_reserves_sync() -> None:
    company_id = uuid4()
    user = SimpleNamespace(id=uuid4(), company_id=company_id, role=SimpleNamespace())
    identity = SimpleNamespace(user=user)
    connections = _WooConnections(company_id)
    sync = _Sync()
    runner = _Runner()
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_current_identity] = lambda: identity
    app.dependency_overrides[require_active_subscription] = lambda: TenantContext(
        company_id=company_id
    )
    app.dependency_overrides[get_commerce_connection_service] = lambda: connections
    app.dependency_overrides[get_commerce_sync_service] = lambda: sync
    app.dependency_overrides[get_commerce_sync_runner] = lambda: runner
    app.dependency_overrides[get_commerce_connector_registry] = lambda: _WooRegistry()

    from backend.app.routers import commerce as commerce_router

    app.dependency_overrides[commerce_router.manage_connectors] = lambda: identity
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/connectors/woocommerce/manual",
            json={
                "store_url": "https://shop.example.com",
                "consumer_key": "ck_route_secret",
                "consumer_secret": "cs_route_secret",
            },
        )

    assert response.status_code == 202
    assert connections.received_credentials == (
        "ck_route_secret",
        "cs_route_secret",
    )
    response_text = response.text
    assert "ck_route_secret" not in response_text
    assert "cs_route_secret" not in response_text
    assert "ciphertext-not-for-response" not in response_text
    assert response.json()["provider"] == "woocommerce"
    assert response.json()["status"] == "READY"
    assert sync.reserved == [(company_id, connections.connection.id)]
    assert runner.runs == [(company_id, connections.connection.id)]


def test_woocommerce_json_callback_returns_accepted_and_schedules_initialization() -> None:
    company_id = uuid4()
    connections = _WooConnections(company_id)
    runner = _Runner()
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_commerce_connection_service] = lambda: connections
    app.dependency_overrides[get_commerce_sync_runner] = lambda: runner

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/connectors/woocommerce/callback?state=valid-state",
            headers={"Content-Type": "application/json"},
            json={
                "key_id": 42,
                "user_id": "valid-state",
                "consumer_key": "ck_callback_secret",
                "consumer_secret": "cs_callback_secret",
                "key_permissions": "read_write",
            },
        )

    assert response.status_code == 202
    assert connections.received_credentials == (
        "ck_callback_secret",
        "cs_callback_secret",
    )
    assert "ck_callback_secret" not in response.text
    assert "cs_callback_secret" not in response.text
    assert runner.woocommerce_initializations == [
        (company_id, connections.connection.id)
    ]


def test_woocommerce_callback_rejects_malformed_json() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/connectors/woocommerce/callback?state=valid-state",
            headers={"Content-Type": "application/json"},
            content=b"{not-json",
        )

    assert response.status_code == 422