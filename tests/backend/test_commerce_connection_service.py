from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.connectors.shopify import ShopifyConnector
from backend.app.connectors.woocommerce import WooCommerceConnector
from backend.app.models import Base, Company, CompanyMembership, CommerceConnectionStatus, CommerceOAuthState, User, UserRole
from backend.app.services.commerce_connection_service import (
    CommerceAuthorizationError,
    CommerceConnectionNotFound,
    CommerceConnectionService,
)
from backend.app.services.connector_secret_cipher import ConnectorSecretCipher
from shared.ai_engine.connectors.registry import CommerceConnectorRegistry
from shared.ai_engine.contracts import TenantContext
from tests.subscription_helpers import add_active_subscription


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
        self.invalid_signature = False
        self.refresh_rejected = False
        self.refresh_calls = 0

    def verify_callback_signature(self, parameters):
        if self.invalid_signature:
            from backend.app.connectors.shopify import ShopifyAuthenticationError
            raise ShopifyAuthenticationError("Invalid signature")

    async def refresh_credentials(self, **kwargs):
        self.refresh_calls += 1
        if self.refresh_rejected:
            from backend.app.connectors.shopify import ShopifyAuthenticationError
            raise ShopifyAuthenticationError("Revoked")
        return {"access_token": "new-test-access", "refresh_token": "new-test-refresh", "expires_in": 3600, "refresh_token_expires_in": 86400}

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

    async def get_shop_metadata(self, context):
        return {"id": "gid://shopify/Shop/123", "name": "Verified test shop", "domain": context.external_account_id}

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
    session.flush()
    session.add(CompanyMembership(company_id=company.id, user_id=user.id, role=UserRole.OWNER, is_active=True))
    add_active_subscription(session, company)
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
    assert connection.display_name == "Verified test shop"
    assert connection.sync_cursor["shop"]["domain"] == "alpha-store.myshopify.com"
    assert "shpat_secret" not in (connection.encrypted_credentials or "")
    assert len(service.list_connections(tenant)) == 1
    completed = service.mark_setup_complete(tenant, connection.id)
    assert completed.status == CommerceConnectionStatus.CONNECTED.value
    with pytest.raises(CommerceAuthorizationError, match="invalid or expired"):
        await service.complete_shopify_oauth(
            {"state": start.state, "shop": "alpha-store.myshopify.com"}
        )


@pytest.mark.asyncio
async def test_invalid_callback_does_not_consume_shopify_state(connection_environment):
    session, service, connector, (company, user), _ = connection_environment
    started = service.begin_shopify_oauth(TenantContext(company.id), actor_user_id=user.id, shop_domain="signature-test")
    connector.invalid_signature = True
    with pytest.raises(CommerceAuthorizationError, match="signature"):
        await service.complete_shopify_oauth({"state": started.state, "shop": "signature-test.myshopify.com"})
    assert session.query(CommerceOAuthState).one().consumed_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["inactive", "viewer"])
async def test_shopify_callback_rechecks_current_membership(connection_environment, change):
    session, service, _, (company, user), _ = connection_environment
    started = service.begin_shopify_oauth(TenantContext(company.id), actor_user_id=user.id, shop_domain="membership-test")
    membership = session.query(CompanyMembership).filter_by(user_id=user.id, company_id=company.id).one()
    if change == "inactive":
        membership.is_active = False
    else:
        membership.role = UserRole.VIEWER
    session.commit()
    with pytest.raises(CommerceAuthorizationError, match="no longer authorized"):
        await service.complete_shopify_oauth({"state": started.state, "shop": "membership-test.myshopify.com"})
    assert session.query(CommerceOAuthState).one().consumed_at is None


@pytest.mark.asyncio
async def test_shopify_callback_cannot_start_sync_with_revoked_subscription(connection_environment):
    from backend.app.models import BillingAccount
    session, service, _, (company, user), _ = connection_environment
    started = service.begin_shopify_oauth(TenantContext(company.id), actor_user_id=user.id, shop_domain="subscription-test")
    session.query(BillingAccount).filter_by(company_id=company.id).one().status = "inactive"
    session.commit()
    with pytest.raises(CommerceAuthorizationError, match="subscription"):
        await service.complete_shopify_oauth({"state": started.state, "shop": "subscription-test.myshopify.com"})


@pytest.mark.asyncio
async def test_shopify_new_authorization_invalidates_old_same_store_state(connection_environment):
    _, service, _, (company, user), _ = connection_environment
    tenant = TenantContext(company.id)
    old = service.begin_shopify_oauth(tenant, actor_user_id=user.id, shop_domain="reconnect-test")
    current = service.begin_shopify_oauth(tenant, actor_user_id=user.id, shop_domain="reconnect-test")
    with pytest.raises(CommerceAuthorizationError, match="invalid or expired"):
        await service.complete_shopify_oauth({"state": old.state, "shop": "reconnect-test.myshopify.com"})
    connection = await service.complete_shopify_oauth({"state": current.state, "shop": "reconnect-test.myshopify.com"})
    service.mark_setup_complete(tenant, connection.id)
    assert connection.sync_cursor["shop"]["setup_verified"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("rejected", [True, False])
async def test_shopify_refresh_rotation_and_revocation(connection_environment, rejected):
    _, service, connector, (company, user), _ = connection_environment
    tenant = TenantContext(company.id)
    started = service.begin_shopify_oauth(tenant, actor_user_id=user.id, shop_domain="refresh-test")
    connection = await service.complete_shopify_oauth({"state": started.state, "shop": "refresh-test.myshopify.com"})
    service.mark_setup_complete(tenant, connection.id)
    connection.access_token_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    service._db.commit()
    connector.refresh_rejected = rejected
    if rejected:
        with pytest.raises(CommerceAuthorizationError):
            await service.sync_context(tenant, connection.id)
        assert connection.status == "REAUTH_REQUIRED"
    else:
        await service.sync_context(tenant, connection.id)
        assert connector.refresh_calls == 1
        await service.sync_context(tenant, connection.id)
        assert connector.refresh_calls == 1
        assert "new-test-access" not in connection.encrypted_credentials


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

    with pytest.raises(CommerceAuthorizationError, match="another tenant"):
        service.begin_shopify_oauth(tenant_b, actor_user_id=user_b.id, shop_domain="shared-store")


@pytest.mark.asyncio
async def test_tenant_can_connect_multiple_stores_and_disconnect_safely(connection_environment) -> None:
    session, service, connector, (company, user), _ = connection_environment
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

    from backend.app.models import Dataset, DatasetStatus
    dataset = Dataset(company_id=company.id, name="imported-test.csv", type="csv", source="test-only.csv",
        rows_count=1, columns_count=1, status=DatasetStatus.READY)
    session.add(dataset)
    session.flush()
    connections[0].dataset_ids = {"retail": str(dataset.id)}
    session.commit()
    disconnected = await service.disconnect(
        tenant, connections[0].id, actor_user_id=user.id
    )

    assert len(service.list_connections(tenant)) == 2
    assert session.get(Dataset, dataset.id) is not None
    assert disconnected.dataset_ids["retail"] == str(dataset.id)
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
async def test_new_woocommerce_authorization_supersedes_previous_state(
    woocommerce_environment,
) -> None:
    session, service, _, cipher, (company, user), _ = woocommerce_environment
    tenant = TenantContext(company_id=company.id)
    first = service.begin_woocommerce_authorization(
        tenant,
        actor_user_id=user.id,
        store_url="https://merchant.example",
    )
    second = service.begin_woocommerce_authorization(
        tenant,
        actor_user_id=user.id,
        store_url="https://merchant.example",
    )

    assert first.state != second.state
    with pytest.raises(CommerceAuthorizationError, match="invalid or expired"):
        await service.complete_woocommerce_authorization(
            raw_state=first.state,
            callback_payload={
                "user_id": first.state,
                "consumer_key": "ck_stale_secret",
                "consumer_secret": "cs_stale_secret",
                "key_permissions": "read_write",
            },
        )

    connection = await service.complete_woocommerce_authorization(
        raw_state=second.state,
        callback_payload={
            "user_id": second.state,
            "consumer_key": "ck_fresh_secret",
            "consumer_secret": "cs_fresh_secret",
            "key_permissions": "read_write",
        },
    )
    assert connection.status == CommerceConnectionStatus.CONNECTING.value

    previous_ciphertext = connection.encrypted_credentials
    connection.status = CommerceConnectionStatus.REAUTH_REQUIRED.value
    connection.error_category = "reauthorization_required"
    session.commit()
    reconnect = service.begin_woocommerce_reauthorization(
        tenant,
        actor_user_id=user.id,
        connection_id=connection.id,
    )
    reconnected = await service.complete_woocommerce_authorization(
        raw_state=reconnect.state,
        callback_payload={
            "user_id": reconnect.state,
            "consumer_key": "ck_reconnected_secret",
            "consumer_secret": "cs_reconnected_secret",
            "key_permissions": "read_write",
        },
    )
    credentials = cipher.decrypt(reconnected.encrypted_credentials or "")
    assert reconnected.id == connection.id
    assert len(service.list_connections(tenant)) == 1
    assert reconnected.encrypted_credentials != previous_ciphertext
    assert credentials["consumer_key"] == "ck_reconnected_secret"
    assert credentials["consumer_secret"] == "cs_reconnected_secret"

    reconnected.status = CommerceConnectionStatus.FAILED.value
    session.commit()
    service.begin_woocommerce_authorization(
        tenant,
        actor_user_id=user.id,
        store_url="https://merchant.example",
    )
    assert reconnected.status == CommerceConnectionStatus.AUTHORIZING.value
    assert reconnected.encrypted_credentials is None


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