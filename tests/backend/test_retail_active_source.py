from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.ai.tools.business.dataset_access import load_latest_prepared_dataset
from backend.app.ai.tools.exceptions import ToolUnavailableError
from backend.app.models import (
    Base,
    CommerceConnection,
    CommerceConnectionStatus,
    Company,
    Dataset,
    DatasetStatus,
    Mapping,
)
from backend.app.services.retail_source_service import (
    RetailSourceNotFound,
    RetailSourceService,
)
from backend.app.services.tenant_analytics_service import TenantAnalyticsService
from backend.app.services.tenant_customers_service import TenantCustomersService
from backend.app.services.tenant_products_service import TenantProductsService
from backend.app.services.tenant_recommendations_service import TenantRecommendationsService
from backend.app.services.tenant_sales_service import TenantSalesService
from shared.ai_engine.contracts import TenantContext


class _PreparedIngestion:
    def __init__(self, prepared_by_id):
        self._prepared_by_id = prepared_by_id

    def get_prepared_dataset(self, tenant, dataset_id):
        prepared = self._prepared_by_id[dataset_id]
        if prepared.company_id != tenant.company_id:
            raise LookupError("Dataset not found")
        return prepared


class _UnusedPredictions:
    def predict(self, *args, **kwargs):
        raise AssertionError("No active model should request predictions")


def _company(session, name):
    company = Company(
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
    session.commit()
    return company


def _dataset(session, company, name):
    dataset = Dataset(
        company_id=company.id,
        name=name,
        type="csv",
        source=str(Path(name)),
        rows_count=1,
        columns_count=7,
        status=DatasetStatus.READY,
        uploaded_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
    )
    dataset.mapping = Mapping(mapping_json={"accepted": {}}, confidence=1, approved=True)
    session.add(dataset)
    session.commit()
    return dataset


def _prepared(company, dataset, prefix, amount):
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
                "order": f"{prefix}-ORDER",
                "customer": f"{prefix}-CUSTOMER",
                "product": f"{prefix}-PRODUCT",
                "name": f"{prefix} Product",
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


@pytest.fixture
def source_environment(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'retail-sources.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        company = _company(session, "Alpha")
        other_company = _company(session, "Beta")
        uploaded = _dataset(session, company, "Superstore.csv")
        shopify_dataset = _dataset(session, company, "shopify-retail.csv")
        synced_at = datetime(2026, 9, 8, 17, 30, tzinfo=timezone.utc)
        connection = CommerceConnection(
            company_id=company.id,
            provider="shopify",
            external_account_id="avenqo-retail-test.myshopify.com",
            display_name="avenqo-retail-test.myshopify.com",
            status=CommerceConnectionStatus.READY.value,
            encrypted_credentials="encrypted",
            dataset_ids={"retail": str(shopify_dataset.id)},
            last_successful_sync=synced_at,
        )
        session.add(connection)
        session.commit()
        prepared = {
            uploaded.id: _prepared(company, uploaded, "SUPER", 999),
            shopify_dataset.id: _prepared(company, shopify_dataset, "SHOPIFY", 42),
        }
        yield session, company, other_company, uploaded, shopify_dataset, connection, prepared


def test_sources_are_tenant_isolated_and_include_sync_metadata(source_environment):
    session, company, other_company, _, shopify_dataset, connection, _ = source_environment
    sources = RetailSourceService(session).list_sources(TenantContext(company.id))

    assert {source.source_type for source in sources} == {"connector", "dataset"}
    shopify = next(source for source in sources if source.source_type == "connector")
    assert shopify.active is True
    assert shopify.source_id == connection.id
    assert shopify.dataset_id == shopify_dataset.id
    assert shopify.provider == "shopify"
    assert shopify.display_name == "avenqo-retail-test.myshopify.com"
    assert shopify.last_synchronized_at == connection.last_successful_sync
    assert RetailSourceService(session).list_sources(TenantContext(other_company.id)) == ()
    with pytest.raises(RetailSourceNotFound):
        RetailSourceService(session).select_source(
            TenantContext(other_company.id),
            source_type="connector",
            source_id=connection.id,
        )


def test_uploaded_source_selection_persists(source_environment):
    session, company, _, uploaded, _, _, _ = source_environment
    tenant = TenantContext(company.id)

    selected = RetailSourceService(session).select_source(
        tenant,
        source_type="dataset",
        source_id=uploaded.id,
    )
    reloaded = RetailSourceService(session).list_sources(tenant)

    assert selected.active is True
    assert selected.dataset_id == uploaded.id
    assert next(source for source in reloaded if source.active).source_id == uploaded.id


def test_shopify_active_source_filters_all_retail_services(source_environment):
    session, company, _, _, shopify_dataset, connection, prepared = source_environment
    tenant = TenantContext(company.id)
    RetailSourceService(session).select_source(
        tenant,
        source_type="connector",
        source_id=connection.id,
    )
    analytics = TenantAnalyticsService(session, _PreparedIngestion(prepared))
    predictions = _UnusedPredictions()
    sales = TenantSalesService(session, analytics, predictions)
    customers = TenantCustomersService(analytics, predictions)
    products = TenantProductsService(analytics)
    recommendations = TenantRecommendationsService(analytics, products, None)

    snapshot = analytics.load(tenant)
    sales_result = sales.build(tenant, period_key="last_30_days")
    customer_result = customers.build(tenant)
    product_result = products.build(tenant)
    recommendation_result = recommendations.build(tenant)

    assert snapshot.active_source_selected is True
    assert snapshot.active_source_dataset_id == shopify_dataset.id
    assert {item.dataset_id for item in snapshot.prepared} == {shopify_dataset.id}
    assert sales_result["summary"]["revenue"] == 42
    assert [item["customer_id"] for item in customer_result["items"]] == ["SHOPIFY-CUSTOMER"]
    assert [item["product_id"] for item in product_result["items"]] == ["SHOPIFY-PRODUCT"]
    assert "SUPER" not in str(recommendation_result)


def test_shopify_without_dataset_never_falls_back_to_uploaded_data(source_environment):
    session, company, _, _, _, connection, prepared = source_environment
    connection.dataset_ids = {}
    session.commit()
    tenant = TenantContext(company.id)
    RetailSourceService(session).select_source(
        tenant,
        source_type="connector",
        source_id=connection.id,
    )
    analytics = TenantAnalyticsService(session, _PreparedIngestion(prepared))
    predictions = _UnusedPredictions()

    snapshot = analytics.load(tenant)
    sales = TenantSalesService(session, analytics, predictions).build(tenant)
    customers = TenantCustomersService(analytics, predictions).build(tenant)
    products = TenantProductsService(analytics).build(tenant)
    recommendations = TenantRecommendationsService(
        analytics,
        TenantProductsService(analytics),
        None,
    ).build(tenant)

    assert snapshot.active_source_selected is True
    assert snapshot.datasets == ()
    assert sales["available"] is False and sales["summary"] is None
    assert customers["available"] is False and customers["items"] == []
    assert products["available"] is False and products["items"] == []
    assert recommendations["recommendations"] == []


def test_active_shopify_source_tracks_new_dataset_after_sync(source_environment):
    session, company, _, _, _, connection, _ = source_environment
    tenant = TenantContext(company.id)
    service = RetailSourceService(session)
    service.select_source(
        tenant,
        source_type="connector",
        source_id=connection.id,
    )
    refreshed_dataset = _dataset(session, company, "shopify-refreshed.csv")
    connection.dataset_ids = {"retail": str(refreshed_dataset.id)}
    connection.last_successful_sync = datetime(2026, 9, 8, 18, 45, tzinfo=timezone.utc)
    session.commit()

    active = next(source for source in service.list_sources(tenant) if source.active)
    selection = service.active_selection(tenant)

    assert active.dataset_id == refreshed_dataset.id
    assert active.last_synchronized_at == connection.last_successful_sync
    assert selection is not None and selection.dataset_id == refreshed_dataset.id


def test_ai_dataset_access_never_falls_back_when_shopify_is_active(source_environment):
    session, company, _, _, _, connection, prepared = source_environment
    connection.dataset_ids = {}
    session.commit()
    tenant = TenantContext(company.id)
    RetailSourceService(session).select_source(
        tenant,
        source_type="connector",
        source_id=connection.id,
    )

    with pytest.raises(ToolUnavailableError, match="No business data"):
        load_latest_prepared_dataset(
            session,
            _PreparedIngestion(prepared),
            tenant,
            frozenset({"total_amount"}),
        )
