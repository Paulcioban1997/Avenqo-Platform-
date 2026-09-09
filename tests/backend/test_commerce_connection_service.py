from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.connectors.shopify import ShopifyConnector
from backend.app.connectors.woocommerce import WooCommerceConnector
from backend.app.models import Base, Company, CommerceConnectionStatus, User, UserRole
from backend.app.services.commerce_connection_service import (
    CommerceAuthorizationError,
    CommerceConnectionNotFound,
    CommerceConnectionService,
)
from backend.app.services.connector_secret_cipher import ConnectorSecretCipher
from shared.ai_engine.connectors.registry import CommerceConnectorRegistry
from shared.ai_engine.contracts import TenantContext


class _TestShopifyConnector(ShopifyConnector):
    def __init__(self) -> None:
        super().__init__(
            client_id="client-id",
            client_secret="client-secret",
            redirect_uri="https://api.test/callback",
            api_version="2026-07",
            scopes=("read_orders",),
            webhook_uri="https://api.test/webhooks",
            http_client=httpx.AsyncClient(
                transport=httpx.MockTransport(lambda request: httpx.Response(500))
            ),
        )
        self.disconnected = False

    async def handle_oauth_callback(self, *, tenant_id, callback_parameters):
        return {
            "access_token": "shpat_secret",
            "refresh_token": "shprt_secret",
            "scope": "read_orders",
            "expires_in": 3600,
            "refresh_token_expires_in": 7776000,
        }

    async def test_connection(self, context):
        return True

    async def disconnect(self, context):
        self.disconnected = True


class _TestWooCommerceConnector(WooCommerceConnector):
    def __init__(self) -> None:
        super().__init__(
            callback_uri="https://api.test/api/v1/connectors/woocommerce/callback",
            return_uri="https://app.test/connections",
            webhook_uri="https://api.test/api/v1/connectors/woocommerce/webhook",
        )
        self.contexts = []
        self.disconnected = False

    async def test_connection(self, context):
        self.contexts.append(context)
        return True

    async def disconnect(self, context):
        self.disconnected = True


def _company(session, name: str) -> tuple[Company, User]:
    company = Company(
        name=name,
        slug=f"{name.lower()}-{uuid4().hex[:6]}",
        email=f"{uuid4().hex}@example.com",
        country="Canada",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="professional",
    )
    session.add(company)
    session.flush()
    user = User(
        company_id=company.id,
        first_name="Test",
        last_name="Owner",
        email=f"{uuid4().hex}@example.com",
        password_hash="not-used",
        role=UserRole.OWNER,
        email_verified_at=datetime.now(timezone.utc),
    )
    session.add(user)
    session.commit()
    return company, user


@pytest.fixture
def connection_environment(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'connectors.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        company_a, user_a = _company(session, "Alpha")
        company_b, user_b = _company(session, "Beta")
        connector = _TestShopifyConnector()
        registry = CommerceConnectorRegistry()
        registry.register(connector)
        cipher = ConnectorSecretCipher([Fernet.generate_key().decode("ascii")])
        service = CommerceConnectionService(session, registry, cipher)
        yield session, service, connector, (company_a, user_a), (company_b, user_b)


@pytest.fixture
def woocommerce_environment(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'woocommerce-connectors.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        company_a, user_a = _company(session, "Woo Alpha")
        company_b, user_b = _company(session, "Woo Beta")
        connector = _TestWooCommerceConnector()
        registry = CommerceConnectorRegistry()
        registry.register(connector)
        cipher = ConnectorSecretCipher([Fernet.generate_key().decode("ascii")])
        service = CommerceConnectionService(session, registry, cipher)
        yield session, service, connector, cipher, (company_a, user_a), (company_b, user_b)


@pytest.mark.asyncio
async def test_oauth_state_creates_encrypted_tenant_connection(connection_environment) -> None:
    session, service, _, (company, user), _ = connection_environment
    tenant = TenantContext(company_id=company.id)
    start = service.begin_shopify_oauth(
        tenant, actor_user_id=user.id, shop_domain="alpha-store"
    )

    connection = await service.complete_shopify_oauth(
        {"state": start.state, "shop": "alpha-store.myshopify.com"}
    )

    assert connection.company_id == company.id
    assert connection.status == CommerceConnectionStatus.CONNECTING.value
    assert "shpat_secret" not in (connection.encrypted_credentials or "")
    assert len(service.list_connections(tenant)) == 1
    completed = service.mark_setup_complete(tenant, connection.id)
    assert completed.status == CommerceConnectionStatus.CONNECTED.value
    with pytest.raises(CommerceAuthorizationError, match="invalid or expired"):
        await service.complete_shopify_oauth(
            {"state": start.state, "shop": "alpha-store.myshopify.com"}
        )


@pytest.mark.asyncio
async def test_connection_is_tenant_isolated_and_shop_has_one_owner(connection_environment) -> None:
    _, service, _, (company_a, user_a), (company_b, user_b) = connection_environment
    tenant_a = TenantContext(company_id=company_a.id)
    tenant_b = TenantContext(company_id=company_b.id)
    first = service.begin_shopify_oauth(
        tenant_a, actor_user_id=user_a.id, shop_domain="shared-store"
    )
    connection = await service.complete_shopify_oauth(
        {"state": first.state, "shop": "shared-store.myshopify.com"}
    )

    with pytest.raises(CommerceConnectionNotFound):
        service.get_connection(tenant_b, connection.id)

    second = service.begin_shopify_oauth(
        tenant_b, actor_user_id=user_b.id, shop_domain="shared-store"
    )
    with pytest.raises(CommerceAuthorizationError, match="another tenant"):
        await service.complete_shopify_oauth(
            {"state": second.state, "shop": "shared-store.myshopify.com"}
        )


@pytest.mark.asyncio
async def test_tenant_can_connect_multiple_stores_and_disconnect_safely(connection_environment) -> None:
    _, service, connector, (company, user), _ = connection_environment
    tenant = TenantContext(company_id=company.id)
    connections = []
    for shop in ("first-store", "second-store"):
        start = service.begin_shopify_oauth(
            tenant, actor_user_id=user.id, shop_domain=shop
        )
        connections.append(
            await service.complete_shopify_oauth(
                {"state": start.state, "shop": f"{shop}.myshopify.com"}
            )
        )

    disconnected = await service.disconnect(
        tenant, connections[0].id, actor_user_id=user.id
    )

    assert len(service.list_connections(tenant)) == 2
    assert disconnected.status == CommerceConnectionStatus.DISCONNECTED.value
    assert disconnected.encrypted_credentials is None
    assert connector.disconnected is True


@pytest.mark.asyncio
async def test_woocommerce_callback_encrypts_credentials_and_consumes_state(
    woocommerce_environment,
) -> None:
    _, service, connector, cipher, (company, user), _ = woocommerce_environment
    tenant = TenantContext(company_id=company.id)
    started = service.begin_woocommerce_authorization(
        tenant,
        actor_user_id=user.id,
        store_url="https://Merchant.Example/shop/",
    )

    connection = await service.complete_woocommerce_authorization(
        raw_state=started.state,
        callback_payload={
            "user_id": started.state,
            "consumer_key": "ck_returned_secret",
            "consumer_secret": "cs_returned_secret",
            "key_permissions": "read_write",
        },
    )

    assert connection.company_id == company.id
    assert connection.external_account_id == "https://merchant.example/shop"
    assert connection.display_name == "merchant.example/shop"
    assert connection.status == CommerceConnectionStatus.CONNECTING.value
    assert "ck_returned_secret" not in (connection.encrypted_credentials or "")
    assert "cs_returned_secret" not in (connection.encrypted_credentials or "")
    decrypted = cipher.decrypt(connection.encrypted_credentials or "")
    assert decrypted["consumer_key"] == "ck_returned_secret"
    assert decrypted["consumer_secret"] == "cs_returned_secret"
    assert decrypted["webhook_secret"]
    assert connector.contexts == []
    with pytest.raises(CommerceAuthorizationError, match="invalid or expired"):
        await service.complete_woocommerce_authorization(
            raw_state=started.state,
            callback_payload={
                "user_id": started.state,
                "consumer_key": "ck_returned_secret",
                "consumer_secret": "cs_returned_secret",
                "key_permissions": "read_write",
            },
        )


@pytest.mark.asyncio
async def test_woocommerce_authorization_uses_thirty_minute_state_and_invalid_payload_does_not_consume_it(
    woocommerce_environment,
) -> None:
    _, service, _, _, (company, user), _ = woocommerce_environment
    started_at = datetime.now(timezone.utc)
    started = service.begin_woocommerce_authorization(
        TenantContext(company_id=company.id),
        actor_user_id=user.id,
        store_url="https://merchant.example",
    )

    assert timedelta(minutes=29, seconds=55) <= started.expires_at - started_at
    with pytest.raises(CommerceAuthorizationError):
        await service.complete_woocommerce_authorization(
            raw_state=started.state,
            callback_payload={
                "user_id": started.state,
                "consumer_key": "ck_returned_secret",
                "consumer_secret": "invalid_secret",
                "key_permissions": "read_write",
            },
        )

    connection = await service.complete_woocommerce_authorization(
        raw_state=started.state,
        callback_payload={
            "user_id": started.state,
            "consumer_key": "ck_returned_secret",
            "consumer_secret": "cs_returned_secret",
            "key_permissions": "read_write",
        },
    )
    assert connection.status == CommerceConnectionStatus.CONNECTING.value


@pytest.mark.asyncio
async def test_woocommerce_callback_rejects_expired_state(
    woocommerce_environment,
) -> None:
    _, service, _, _, (company, user), _ = woocommerce_environment
    started = service.begin_woocommerce_authorization(
        TenantContext(company_id=company.id),
        actor_user_id=user.id,
        store_url="https://expired.example",
    )
    service._now = lambda: started.expires_at + timedelta(seconds=1)

    with pytest.raises(CommerceAuthorizationError, match="invalid or expired"):
        await service.complete_woocommerce_authorization(
            raw_state=started.state,
            callback_payload={
                "user_id": started.state,
                "consumer_key": "ck_returned_secret",
                "consumer_secret": "cs_returned_secret",
                "key_permissions": "read_write",
            },
        )


@pytest.mark.asyncio
async def test_woocommerce_manual_credentials_are_tenant_scoped_and_disconnect_safely(
    woocommerce_environment,
) -> None:
    _, service, connector, _, (company_a, user_a), (company_b, user_b) = (
        woocommerce_environment
    )
    tenant_a = TenantContext(company_id=company_a.id)
    tenant_b = TenantContext(company_id=company_b.id)
    connection = await service.connect_woocommerce_manual(
        tenant_a,
        actor_user_id=user_a.id,
        store_url="https://shared.example",
        consumer_key="ck_manual_secret",
        consumer_secret="cs_manual_secret",
    )

    with pytest.raises(CommerceConnectionNotFound):
        service.get_connection(tenant_b, connection.id)
    with pytest.raises(CommerceAuthorizationError, match="another tenant"):
        await service.connect_woocommerce_manual(
            tenant_b,
            actor_user_id=user_b.id,
            store_url="https://shared.example",
            consumer_key="ck_other",
            consumer_secret="cs_other",
        )

    disconnected = await service.disconnect(
        tenant_a,
        connection.id,
        actor_user_id=user_a.id,
    )
    assert disconnected.status == CommerceConnectionStatus.DISCONNECTED.value
    assert disconnected.encrypted_credentials is None
    assert connector.disconnected is True