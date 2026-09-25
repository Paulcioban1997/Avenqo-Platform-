from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.ai.tools.business.commerce_tools import (
    GetInventorySummaryTool,
    GetProductDetailTool,
    InventorySummaryArgs,
    ProductDetailArgs,
)
from backend.app.ai.tools.business.dataset_access import load_latest_prepared_dataset
from backend.app.ai.tools.contracts import ToolExecutionContext
from backend.app.ai.tools.exceptions import ToolUnavailableError
from backend.app.models import (
    Base,
    CommerceConnection,
    CommerceConnectionStatus,
    Company,
    Dataset,
    DatasetStatus,
    Mapping,
    NormalizedCommerceRecord,
    User,
    UserRole,
)
from backend.app.services.commerce_connection_service import (
    CommerceConnectionNotFound,
    CommerceConnectionService,
)
from backend.app.services.connector_secret_cipher import ConnectorSecretCipher
from backend.app.services.retail_source_service import RetailSourceService
from backend.app.services.tenant_analytics_service import TenantAnalyticsService
from backend.app.services.tenant_sales_service import TenantSalesService
from shared.ai_engine.connectors.registry import CommerceConnectorRegistry
from shared.ai_engine.contracts import TenantContext


class _PreparedIngestion:
    def __init__(self, prepared_by_id):
        self._prepared_by_id = prepared_by_id

    def get_prepared_dataset(self, tenant, dataset_id):
        prepared = self._prepared_by_id.get(dataset_id)
        if prepared is None or prepared.company_id != tenant.company_id:
            raise LookupError("Dataset not found")
        return prepared


class _MockShopifyConnector:
    definition = SimpleNamespace(provider="shopify", display_name="Shopify")

    def __init__(self):
        self.disconnected = False

    async def disconnect(self, context):
        self.disconnected = True


class _MockWooConnector:
    definition = SimpleNamespace(provider="woocommerce", display_name="WooCommerce")

    def __init__(self):
        self.disconnected = False

    async def disconnect(self, context):
        self.disconnected = True


def _company(session, name: str) -> tuple[Company, User]:
    company = Company(
        id=uuid4(),
        name=name,
        slug=f"{name.lower()}-{uuid4().hex[:6]}",
        email=f"{uuid4().hex}@example.com",
        country="Canada",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="professional",
        currency_code="CAD",
    )
    session.add(company)
    session.flush()
    user = User(
        id=uuid4(),
        company_id=company.id,
        first_name="Admin",
        last_name="User",
        email=f"{uuid4().hex}@example.com",
        password_hash="hash",
        role=UserRole.OWNER,
        email_verified_at=datetime.now(timezone.utc),
    )
    session.add(user)
    session.commit()
    return company, user


def _dataset(session, company, name: str) -> Dataset:
    dataset = Dataset(
        id=uuid4(),
        company_id=company.id,
        name=name,
        type="csv",
        source=str(Path(name)),
        rows_count=10,
        columns_count=7,
        status=DatasetStatus.READY,
        uploaded_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
    )
    dataset.mapping = Mapping(mapping_json={"accepted": {}}, confidence=1, approved=True)
    session.add(dataset)
    session.commit()
    return dataset


def _prepared(company, dataset, prefix: str, amount: float):
    return SimpleNamespace(
        company_id=company.id,
        dataset_id=dataset.id,
        version=1,
        canonical_columns={
            "date": "order_timestamp",
            "order": "order_id",
            "customer": "customer_id",
            "product": "product_id",
            "name": "product_name",
            "quantity": "quantity",
            "amount": "total_amount",
        },
        rows=(
            {
                "date": "2026-09-08",
                "order": f"{prefix}-ORDER-1",
                "customer": f"{prefix}-CUSTOMER-1",
                "product": f"{prefix}-PRODUCT-1",
                "name": f"{prefix} Special Product",
                "quantity": 1,
                "amount": amount,
            },
        ),
        profile=SimpleNamespace(),
        mapping=(),
        cleaning_report=SimpleNamespace(),
        quality=SimpleNamespace(),
        capability_readiness=(),
    )


def _seed_normalized_product(session, company_id, connection_id, provider, product_name, stock, price):
    record = NormalizedCommerceRecord(
        id=uuid4(),
        company_id=company_id,
        connection_id=connection_id,
        provider=provider,
        entity_type="product",
        source_record_id=str(uuid4()),
        normalized_data={
            "product_name": product_name,
            "product_id": f"id-{product_name.lower().replace(' ', '-')}",
            "sku": f"SKU-{product_name[:3].upper()}",
            "stock_quantity": stock,
            "unit_price": price,
            "in_stock": stock > 0,
        },
        deleted=False,
    )
    session.add(record)
    session.commit()
    return record


@pytest.fixture
def isolation_env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'isolation.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        company_a, user_a = _company(session, "TenantA")
        company_b, user_b = _company(session, "TenantB")

        # 1. Superstore Dataset (CSV)
        superstore = _dataset(session, company_a, "Superstore.csv")

        # 2. Shopify Connection + Dataset + Normalized Product
        from cryptography.fernet import Fernet
        cipher = ConnectorSecretCipher([Fernet.generate_key().decode("utf-8")])
        registry = CommerceConnectorRegistry()
        mock_shopify = _MockShopifyConnector()
        mock_woo = _MockWooConnector()
        registry.register(mock_shopify)
        registry.register(mock_woo)

        # 2. Shopify Connection + Dataset + Normalized Product
        shopify_dataset = _dataset(session, company_a, "shopify-retail.csv")
        shopify_conn = CommerceConnection(
            id=uuid4(),
            company_id=company_a.id,
            provider="shopify",
            external_account_id="store-shopify.myshopify.com",
            display_name="Shopify Store",
            status=CommerceConnectionStatus.READY.value,
            encrypted_credentials=cipher.encrypt({"access_token": "shpat_test", "refresh_token": "shprt_test"}),
            dataset_ids={"retail": str(shopify_dataset.id)},
            last_successful_sync=datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc),
        )
        session.add(shopify_conn)
        session.commit()
        _seed_normalized_product(
            session, company_a.id, shopify_conn.id, "shopify", "Shopify Silk Scarf", 15, 45.0
        )

        # 3. WooCommerce Connection + Dataset + Normalized Product
        woo_dataset = _dataset(session, company_a, "woocommerce-retail.csv")
        woo_conn = CommerceConnection(
            id=uuid4(),
            company_id=company_a.id,
            provider="woocommerce",
            external_account_id="https://woo-store.example",
            display_name="WooCommerce Store",
            status=CommerceConnectionStatus.READY.value,
            encrypted_credentials=cipher.encrypt({"consumer_key": "ck_test", "consumer_secret": "cs_test"}),
            dataset_ids={"retail": str(woo_dataset.id)},
            last_successful_sync=datetime(2026, 9, 8, 14, 0, tzinfo=timezone.utc),
        )
        session.add(woo_conn)
        session.commit()
        _seed_normalized_product(
            session, company_a.id, woo_conn.id, "woocommerce", "Wireless Headphones", 19, 99.0
        )

        prepared = {
            superstore.id: _prepared(company_a, superstore, "SUPERSTORE", 2297200.86),
            shopify_dataset.id: _prepared(company_a, shopify_dataset, "SHOPIFY", 12500.0),
            woo_dataset.id: _prepared(company_a, woo_dataset, "WOOCOMMERCE", 3400.0),
        }

        yield SimpleNamespace(
            session=session,
            company_a=company_a,
            user_a=user_a,
            company_b=company_b,
            user_b=user_b,
            superstore=superstore,
            shopify_dataset=shopify_dataset,
            shopify_conn=shopify_conn,
            woo_dataset=woo_dataset,
            woo_conn=woo_conn,
            prepared=prepared,
            registry=registry,
            cipher=cipher,
            mock_shopify=mock_shopify,
            mock_woo=mock_woo,
        )


def test_a_superstore_selected_serves_superstore_kpi_and_ai(isolation_env):
    """Test A: Superstore selected -> KPI Superstore -> AI Superstore."""
    env = isolation_env
    tenant = TenantContext(env.company_a.id)
    source_service = RetailSourceService(env.session)

    # Select Superstore
    selected = source_service.select_source(tenant, source_type="dataset", source_id=env.superstore.id)
    assert selected.active is True
    assert selected.dataset_id == env.superstore.id

    # Verify KPI Sales
    analytics = TenantAnalyticsService(env.session, _PreparedIngestion(env.prepared))
    sales = TenantSalesService(env.session, analytics, None).build(
        tenant, period_key="all"
    )
    assert sales["summary"]["revenue"] == 2297200.86

    # Verify AI Dataset Access
    ai_dataset = load_latest_prepared_dataset(
        env.session, _PreparedIngestion(env.prepared), tenant, frozenset({"total_amount"})
    )
    assert ai_dataset.dataset_id == env.superstore.id

    # Verify Commerce Tools do NOT leak live products when dataset is active
    tool = GetProductDetailTool(env.session)
    tool_ctx = ToolExecutionContext(
        tenant=tenant,
        user_id=env.user_a.id,
        permissions=frozenset({"ai:use"}),
        request_id="test-req",
    )
    import asyncio
    result = asyncio.run(tool.run(tool_ctx, ProductDetailArgs(product_name="Headphones")))
    # Should not find WooCommerce product because active source is dataset
    assert result.data.get("found") is False


def test_b_shopify_selected_serves_shopify_only_no_superstore_leak(isolation_env):
    """Test B: Shopify selected -> KPI Shopify -> AI Shopify (no Superstore data)."""
    env = isolation_env
    tenant = TenantContext(env.company_a.id)
    source_service = RetailSourceService(env.session)

    # Select Shopify
    selected = source_service.select_source(tenant, source_type="connector", source_id=env.shopify_conn.id)
    assert selected.active is True
    assert selected.dataset_id == env.shopify_dataset.id

    # Verify KPI Sales: ONLY Shopify revenue, NOT Superstore
    analytics = TenantAnalyticsService(env.session, _PreparedIngestion(env.prepared))
    sales = TenantSalesService(env.session, analytics, None).build(
        tenant, period_key="all"
    )
    assert sales["summary"]["revenue"] == 12500.0
    assert sales["summary"]["revenue"] != 2297200.86

    # Verify AI Dataset Access
    ai_dataset = load_latest_prepared_dataset(
        env.session, _PreparedIngestion(env.prepared), tenant, frozenset({"total_amount"})
    )
    assert ai_dataset.dataset_id == env.shopify_dataset.id

    # Verify AI Commerce Tools: finds Shopify product, NOT WooCommerce product
    tool = GetProductDetailTool(env.session)
    tool_ctx = ToolExecutionContext(
        tenant=tenant,
        user_id=env.user_a.id,
        permissions=frozenset({"ai:use"}),
        request_id="test-req",
    )
    import asyncio
    res_shopify = asyncio.run(tool.run(tool_ctx, ProductDetailArgs(product_name="Silk Scarf")))
    assert res_shopify.data.get("found") is True
    assert res_shopify.data["product"]["product_name"] == "Shopify Silk Scarf"

    res_woo = asyncio.run(tool.run(tool_ctx, ProductDetailArgs(product_name="Headphones")))
    assert res_woo.data.get("found") is False


def test_c_woocommerce_selected_serves_woocommerce_only_no_shopify_or_superstore(isolation_env):
    """Test C: WooCommerce selected -> KPI WooCommerce -> AI WooCommerce."""
    env = isolation_env
    tenant = TenantContext(env.company_a.id)
    source_service = RetailSourceService(env.session)

    # Select WooCommerce
    selected = source_service.select_source(tenant, source_type="connector", source_id=env.woo_conn.id)
    assert selected.active is True
    assert selected.dataset_id == env.woo_dataset.id

    # Verify KPI Sales
    analytics = TenantAnalyticsService(env.session, _PreparedIngestion(env.prepared))
    sales = TenantSalesService(env.session, analytics, None).build(
        tenant, period_key="all"
    )
    assert sales["summary"]["revenue"] == 3400.0

    # Verify AI Commerce Tools: finds Wireless Headphones, NOT Silk Scarf
    tool = GetProductDetailTool(env.session)
    tool_ctx = ToolExecutionContext(
        tenant=tenant,
        user_id=env.user_a.id,
        permissions=frozenset({"ai:use"}),
        request_id="test-req",
    )
    import asyncio
    res_woo = asyncio.run(tool.run(tool_ctx, ProductDetailArgs(product_name="Headphones")))
    assert res_woo.data.get("found") is True
    assert res_woo.data["product"]["product_name"] == "Wireless Headphones"
    assert res_woo.data["product"]["stock_quantity"] == 19

    res_shopify = asyncio.run(tool.run(tool_ctx, ProductDetailArgs(product_name="Silk Scarf")))
    assert res_shopify.data.get("found") is False


def test_d_switching_sources_leaves_zero_cross_contamination(isolation_env):
    """Test D: Switching A -> B -> C leaves zero cross-contamination."""
    env = isolation_env
    tenant = TenantContext(env.company_a.id)
    source_service = RetailSourceService(env.session)
    analytics = TenantAnalyticsService(env.session, _PreparedIngestion(env.prepared))
    sales_service = TenantSalesService(env.session, analytics, None)

    # 1. Select Superstore (A)
    source_service.select_source(tenant, source_type="dataset", source_id=env.superstore.id)
    res_a = sales_service.build(tenant, period_key="all")
    assert res_a["summary"]["revenue"] == 2297200.86

    # 2. Select Shopify (B)
    source_service.select_source(tenant, source_type="connector", source_id=env.shopify_conn.id)
    res_b = sales_service.build(tenant, period_key="all")
    assert res_b["summary"]["revenue"] == 12500.0

    # 3. Select WooCommerce (C)
    source_service.select_source(tenant, source_type="connector", source_id=env.woo_conn.id)
    res_c = sales_service.build(tenant, period_key="all")
    assert res_c["summary"]["revenue"] == 3400.0

    # 4. Back to Superstore (A)
    source_service.select_source(tenant, source_type="dataset", source_id=env.superstore.id)
    res_a2 = sales_service.build(tenant, period_key="all")
    assert res_a2["summary"]["revenue"] == 2297200.86


def test_e_deleting_dataset_a_leaves_b_and_c_intact(isolation_env):
    """Test E: Deleting Dataset A leaves B & C intact."""
    env = isolation_env
    tenant = TenantContext(env.company_a.id)

    # Delete Superstore dataset
    dataset_to_delete = env.session.get(Dataset, env.superstore.id)
    env.session.delete(dataset_to_delete)
    env.session.commit()

    # Verify Superstore is gone
    assert env.session.get(Dataset, env.superstore.id) is None

    # Verify Shopify and WooCommerce datasets and connections are 100% intact
    assert env.session.get(Dataset, env.shopify_dataset.id) is not None
    assert env.session.get(CommerceConnection, env.shopify_conn.id) is not None
    assert env.session.get(Dataset, env.woo_dataset.id) is not None
    assert env.session.get(CommerceConnection, env.woo_conn.id) is not None

    # Verify sources list
    sources = RetailSourceService(env.session).list_sources(tenant)
    source_ids = {s.source_id for s in sources}
    assert env.shopify_conn.id in source_ids
    assert env.woo_conn.id in source_ids
    assert env.superstore.id not in source_ids


@pytest.mark.asyncio
async def test_f_disconnecting_shopify_removes_credentials_and_stops_sync(isolation_env):
    """Test F: Disconnecting Shopify removes credentials and stops sync."""
    env = isolation_env
    tenant = TenantContext(env.company_a.id)

    service = CommerceConnectionService(
        db=env.session,
        registry=env.registry,
        cipher=env.cipher,
    )

    disconnected = await service.disconnect(
        tenant,
        env.shopify_conn.id,
        actor_user_id=env.user_a.id,
    )

    assert disconnected.status == CommerceConnectionStatus.DISCONNECTED.value
    assert disconnected.encrypted_credentials is None
    assert disconnected.disconnected_at is not None
    assert env.mock_shopify.disconnected is True

    # Data is NOT deleted by disconnect alone
    assert env.session.get(Dataset, env.shopify_dataset.id) is not None
    records = list(
        env.session.scalars(
            select(NormalizedCommerceRecord).where(
                NormalizedCommerceRecord.connection_id == env.shopify_conn.id
            )
        ).all()
    )
    assert len(records) > 0


@pytest.mark.asyncio
async def test_g_deleting_shopify_data_purges_shopify_records_while_woocommerce_intact(isolation_env):
    """Test G: Deleting Shopify data purges Shopify records while WooCommerce remains intact."""
    env = isolation_env
    tenant = TenantContext(env.company_a.id)

    service = CommerceConnectionService(
        db=env.session,
        registry=env.registry,
        cipher=env.cipher,
    )

    # Delete Shopify data transactionally
    await service.delete_connection_data(
        tenant,
        env.shopify_conn.id,
        actor_user_id=env.user_a.id,
    )

    # Verify Shopify connection, dataset, and normalized records are purged
    assert env.session.get(CommerceConnection, env.shopify_conn.id) is None
    assert env.session.get(Dataset, env.shopify_dataset.id) is None
    shopify_records = list(
        env.session.scalars(
            select(NormalizedCommerceRecord).where(
                NormalizedCommerceRecord.connection_id == env.shopify_conn.id
            )
        ).all()
    )
    assert len(shopify_records) == 0

    # Verify WooCommerce connection, dataset, and normalized records are 100% intact
    assert env.session.get(CommerceConnection, env.woo_conn.id) is not None
    assert env.session.get(Dataset, env.woo_dataset.id) is not None
    woo_records = list(
        env.session.scalars(
            select(NormalizedCommerceRecord).where(
                NormalizedCommerceRecord.connection_id == env.woo_conn.id
            )
        ).all()
    )
    assert len(woo_records) == 1
    assert woo_records[0].normalized_data["product_name"] == "Wireless Headphones"


@pytest.mark.asyncio
async def test_h_cross_tenant_deletion_is_blocked(isolation_env):
    """Test H: Cross-tenant deletion is blocked (403/404)."""
    env = isolation_env
    tenant_b = TenantContext(env.company_b.id)

    service = CommerceConnectionService(
        db=env.session,
        registry=env.registry,
        cipher=env.cipher,
    )

    # Tenant B attempts to delete Tenant A's connection -> must raise CommerceConnectionNotFound
    with pytest.raises(CommerceConnectionNotFound):
        await service.delete_connection_data(
            tenant_b,
            env.shopify_conn.id,
            actor_user_id=env.user_b.id,
        )

    # Ensure Tenant A's connection and data were NOT touched
    assert env.session.get(CommerceConnection, env.shopify_conn.id) is not None
    assert env.session.get(Dataset, env.shopify_dataset.id) is not None
