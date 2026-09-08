from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

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
from shared.ai_engine.connectors.registry import CommerceConnectorRegistry
from shared.ai_engine.contracts import TenantContext


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

    async def run_reserved(self, tenant, connection_id):
        self.runs.append((tenant.company_id, connection_id))


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
    assert sum(item["implementation_status"] == "AVAILABLE" for item in catalog.json()) == 1
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