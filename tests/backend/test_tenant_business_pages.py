from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker

from backend.app.database import get_db
from backend.app.ai.tools.business.analytics import compute_business_overview
from backend.app.dependencies.auth import get_tenant_context
from backend.app.dependencies.tenant_business import (
    get_tenant_customers_service,
    get_tenant_products_service,
    get_tenant_recommendations_service,
    get_tenant_sales_service,
)
from backend.app.models import (
    Base,
    BillingAccount,
    Company,
    Dataset,
    DatasetRelationship,
    DatasetStatus,
    JobStatus,
    Mapping,
    ModelRegistry,
    TrainingJob,
)
from backend.app.services.tenant_analytics_service import TenantAnalyticsService
from backend.app.services.tenant_customers_service import CustomerNotFound, TenantCustomersService
from backend.app.services.tenant_dashboard_service import TenantDashboardService
from backend.app.services.tenant_products_service import ProductNotFound, TenantProductsService
from backend.app.services.tenant_recommendations_service import TenantRecommendationsService
from backend.app.services.tenant_sales_service import InvalidSalesPeriod, TenantSalesService
from backend.main import create_application
from shared.ai_engine.contracts import TenantContext
from backend.app.ai.tools.business.sales_tools import BusinessOverviewArgs, GetBusinessOverviewTool
from backend.app.ai.tools.contracts import ToolExecutionContext


class _PreparedIngestion:
    def __init__(self, prepared_by_id):
        self._prepared_by_id = prepared_by_id

    def get_prepared_dataset(self, tenant, dataset_id):
        prepared = self._prepared_by_id[dataset_id]
        if prepared.company_id != tenant.company_id:
            raise LookupError("Dataset not found")
        return prepared


class _PredictionService:
    def __init__(self):
        self.calls = []

    def predict(self, tenant, module_code, task_code, features, executor):
        self.calls.append((tenant, module_code, task_code, features))
        if task_code == "weekly_forecast":
            return {"result": {"forecast": [80.0, 90.0]}}
        if task_code == "recommendation":
            return {
                "result": ["P2"] if features.get("customer_id") == "C1" else [],
                "confidence": 0.7,
            }
        customer_id = features.get("client")
        if task_code == "segmentation":
            return {"result": "loyal" if customer_id == "C1" else "new"}
        if task_code == "churn":
            return {"result": 1 if customer_id == "C2" else 0}
        raise AssertionError(task_code)


def _company(session, name: str, currency: str, subscription: str = "active") -> Company:
    company = Company(
        name=name,
        slug=f"{name.lower()}-{uuid4().hex[:6]}",
        email=f"{uuid4().hex}@example.com",
        country="Canada",
        currency_code=currency,
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="professional",
    )
    session.add(company)
    session.flush()
    session.add(BillingAccount(company_id=company.id, plan_code="professional", status=subscription))
    session.commit()
    return company


def _dataset(session, company, name="sales.csv", status=DatasetStatus.READY):
    dataset = Dataset(
        company_id=company.id,
        name=name,
        type="csv",
        source=str(Path("unused.csv")),
        rows_count=4,
        columns_count=6,
        status=status,
        uploaded_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
    )
    dataset.mapping = Mapping(mapping_json={"accepted": {}}, confidence=1, approved=True)
    session.add(dataset)
    session.commit()
    return dataset


def _prepared(company, dataset, rows, columns=None):
    return SimpleNamespace(
        company_id=company.id,
        dataset_id=dataset.id,
        version=1,
        canonical_columns=columns or {
            "date": "order_timestamp",
            "sale": "order_id",
            "client": "customer_id",
            "amount": "total_amount",
            "churned": "churn_flag",
        },
        rows=tuple(rows),
        profile=SimpleNamespace(),
        mapping=(),
        cleaning_report=SimpleNamespace(),
        quality=SimpleNamespace(),
        capability_readiness=(),
    )


def _model(session, company, dataset, task_code, model_type, *, active=True):
    job = TrainingJob(
        company_id=company.id,
        dataset_id=dataset.id,
        ai_job_id=uuid4(),
        algorithm="validated",
        status=JobStatus.COMPLETED,
    )
    session.add(job)
    session.flush()
    model = ModelRegistry(
        company_id=company.id,
        training_job_id=job.id,
        module_code="retail",
        task_code=task_code,
        model_name=task_code,
        model_type=model_type,
        framework="sklearn",
        version="1",
        storage_path="unused",
        metric={"quality": 1},
        dataset_rows_count=4,
        is_active=active,
    )
    session.add(model)
    session.commit()
    return model


@pytest.fixture
def business_environment(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'business.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        company_a = _company(session, "Alpha", "CAD")
        company_b = _company(session, "Beta", "EUR")
        dataset_a = _dataset(session, company_a)
        dataset_b = _dataset(session, company_b)
        rows_a = [
            {"date": "2026-07-20", "sale": "O0", "client": "C0", "amount": 50, "churned": 0},
            {"date": "2026-08-20", "sale": "O1", "client": "C1", "amount": 100, "churned": 0},
            {"date": "2026-08-25", "sale": "O2", "client": "C1", "amount": 25, "churned": 0},
            {"date": "2026-08-28", "sale": "O3", "client": "C2", "amount": 50, "churned": 1},
        ]
        rows_b = [
            {"date": "2026-08-28", "sale": "B1", "client": "B-C1", "amount": 999, "churned": 0},
        ]
        prepared = {
            dataset_a.id: _prepared(company_a, dataset_a, rows_a),
            dataset_b.id: _prepared(company_b, dataset_b, rows_b),
        }
        yield session, company_a, company_b, dataset_a, prepared


def _services(session, prepared):
    predictions = _PredictionService()
    analytics = TenantAnalyticsService(session, _PreparedIngestion(prepared))
    return (
        TenantSalesService(session, analytics, predictions),
        TenantCustomersService(analytics, predictions),
        predictions,
    )


def _phase4d_services(session, prepared):
    predictions = _PredictionService()
    analytics = TenantAnalyticsService(session, _PreparedIngestion(prepared))
    products = TenantProductsService(analytics)
    recommendations = TenantRecommendationsService(analytics, products, predictions)
    return products, recommendations, predictions


@pytest.mark.asyncio
async def test_related_ready_datasets_feed_retail_and_central_ai_without_tenant_leakage(
    business_environment,
):
    session, company, company_b, _dataset_a, prepared = business_environment
    prepared.clear()
    customers_data = _dataset(session, company, "party-records.csv")
    orders = _dataset(session, company, "commerce-events.csv")
    items = _dataset(session, company, "line-facts.csv")
    products_data = _dataset(session, company, "catalog-data.csv")
    payments = _dataset(session, company, "settlements.csv")
    foreign = _dataset(session, company_b, "foreign-settlements.csv")

    prepared.update(
        {
            customers_data.id: _prepared(
                company,
                customers_data,
                [{"buyer": "C1"}, {"buyer": "C2"}],
                {"buyer": "customer_id"},
            ),
            orders.id: _prepared(
                company,
                orders,
                [
                    {"order": "O1", "buyer": "C1", "when": "2026-07-01"},
                    {"order": "O2", "buyer": "C1", "when": "2026-08-01"},
                    {"order": "O3", "buyer": "C2", "when": "2026-08-15"},
                ],
                {"order": "order_id", "buyer": "customer_id", "when": "order_timestamp"},
            ),
            items.id: _prepared(
                company,
                items,
                [
                    {"order_ref": "O1", "sku": "P1", "units": 1, "each": 30.0},
                    {"order_ref": "O1", "sku": "P2", "units": 1, "each": 70.0},
                    {"order_ref": "O2", "sku": "P1", "units": 2, "each": 100.0},
                    {"order_ref": "O3", "sku": "P2", "units": 1, "each": 20.0},
                ],
                {
                    "order_ref": "order_id",
                    "sku": "product_id",
                    "units": "quantity",
                    "each": "unit_price",
                },
            ),
            products_data.id: _prepared(
                company,
                products_data,
                [
                    {"sku": "P1", "label": "Coffee", "group": "Drinks"},
                    {"sku": "P2", "label": "Tea", "group": "Drinks"},
                ],
                {"sku": "product_id", "label": "product_name", "group": "product_category"},
            ),
            payments.id: _prepared(
                company,
                payments,
                [
                    {"sale": "O1", "paid": 100.0},
                    {"sale": "O2", "paid": 200.0},
                    {"sale": "O3", "paid": 20.0},
                ],
                {"sale": "order_id", "paid": "total_amount"},
            ),
            foreign.id: _prepared(
                company_b,
                foreign,
                [{"sale": "O1", "paid": 9999.0}],
                {"sale": "order_id", "paid": "total_amount"},
            ),
        }
    )

    for left, right, field in (
        (orders, customers_data, "customer_id"),
        (items, orders, "order_id"),
        (items, products_data, "product_id"),
        (orders, payments, "order_id"),
    ):
        session.add(
            DatasetRelationship(
                company_id=company.id,
                left_dataset_id=left.id,
                right_dataset_id=right.id,
                left_column=field,
                right_column=field,
                canonical_field=field,
                overlap_ratio=1.0,
                confidence=1.0,
            )
        )
    session.commit()

    ingestion = _PreparedIngestion(prepared)
    analytics = TenantAnalyticsService(session, ingestion)
    predictions = _PredictionService()
    sales = TenantSalesService(session, analytics, predictions)
    customers = TenantCustomersService(analytics, predictions)
    products = TenantProductsService(analytics)
    recommendations = TenantRecommendationsService(analytics, products, None)
    dashboard = TenantDashboardService(analytics, recommendations)
    tenant = TenantContext(company.id)

    sales_result = sales.build(tenant, period_key="last_90_days")
    customer_result = customers.build(tenant)
    product_result = products.build(tenant)
    dashboard_result = dashboard.build(tenant)
    recommendation_result = recommendations.build(tenant)
    tool = GetBusinessOverviewTool(session, ingestion)
    tool_result = await tool.run(
        ToolExecutionContext(
            tenant=tenant,
            user_id=uuid4(),
            permissions=frozenset({"ai:use"}),
            request_id="multi-ready",
        ),
        BusinessOverviewArgs(),
    )

    assert sales_result["summary"]["revenue"] == 320.0
    assert customer_result["summary"]["total_customers"] == 2
    assert customer_result["summary"]["repeat_customers"] == 1
    assert product_result["summary"]["total_products"] == 2
    assert product_result["summary"]["units"] == 5.0
    assert sum(item["revenue"] for item in product_result["items"]) == 320.0
    assert {item["average_price"] for item in product_result["items"]} == {76.67, 45.0}
    growth = next(
        item
        for item in recommendation_result["recommendations"]
        if item["type"] == "revenue_growth"
    )
    assert growth["evidence"]["current"] == 220.0
    kpis = {item["key"]: item for item in dashboard_result["kpis"]}
    assert kpis["revenue"]["value"] == 220.0
    assert kpis["average_order_value"]["value"] == 110.0
    assert "average_order_value" in dashboard_result["capabilities"]
    assert tool_result.data["revenue"] == 320.0
    assert tool_result.data["customers"] == 2
    assert all(item.get("revenue") != 9999.0 for item in product_result["items"])


def test_line_quantity_and_unit_price_derive_real_zero_revenue(
    business_environment,
):
    session, company, _company_b, _dataset_a, prepared = business_environment
    prepared.clear()
    lines = _dataset(session, company, "line-values.csv")
    prepared[lines.id] = _prepared(
        company,
        lines,
        [
            {"sale": "O1", "units": 2, "price_each": 0.0},
            {"sale": "O2", "units": 3, "price_each": 10.0},
        ],
        {
            "sale": "order_id",
            "units": "quantity",
            "price_each": "unit_price",
        },
    )
    analytics = TenantAnalyticsService(session, _PreparedIngestion(prepared))

    source = analytics.load(TenantContext(company.id)).source_for(
        frozenset({"total_amount", "order_id"})
    )

    assert source is not None
    overview = compute_business_overview(source)
    assert overview["revenue"] == 30.0
    assert overview["orders"] == 2
    zero_source = replace(source, rows=(source.rows[0],))
    assert compute_business_overview(zero_source)["revenue"] == 0.0


def _product_prepared(company, dataset):
    rows = [
        {"date": "2026-07-20", "sale": "O0", "client": "C0", "product": "P1", "name": "Coffee", "category": "Drinks", "quantity": 2, "amount": 200, "stock": 8},
        {"date": "2026-08-20", "sale": "O1", "client": "C1", "product": "P1", "name": "Coffee", "category": "Drinks", "quantity": 1, "amount": 50, "stock": 7},
        {"date": "2026-08-25", "sale": "O2", "client": "C1", "product": "P2", "name": "Tea", "category": "Drinks", "quantity": 3, "amount": 90, "stock": 0},
        {"date": "2026-08-28", "sale": "O3", "client": "C2", "product": "P2", "name": "Tea", "category": "Drinks", "quantity": 2, "amount": 60, "stock": 0},
    ]
    return _prepared(
        company,
        dataset,
        rows,
        columns={
            "date": "order_timestamp",
            "sale": "order_id",
            "client": "customer_id",
            "product": "product_id",
            "name": "product_name",
            "category": "product_category",
            "quantity": "quantity",
            "amount": "total_amount",
            "stock": "inventory_level",
        },
    )


def test_sales_real_period_trend_currency_and_tenant_isolation(business_environment):
    session, company_a, company_b, _dataset_a, prepared = business_environment
    sales, _customers, _predictions = _services(session, prepared)

    result_a = sales.build(TenantContext(company_a.id), period_key="last_30_days")
    result_b = sales.build(TenantContext(company_b.id), period_key="last_30_days")

    assert result_a["status"] == "ready"
    assert result_a["currency"] == "CAD"
    assert result_a["summary"]["revenue"] == 175
    assert result_a["summary"]["orders"] == 3
    assert result_a["summary"]["average_order_value"] == 58.33
    assert result_a["summary"]["previous_revenue"] == 50
    assert result_a["summary"]["revenue_change_percent"] == 250
    assert result_a["summary"]["orders_change_percent"] == 200
    assert result_a["trend"]["granularity"] == "day"
    assert len(result_a["trend"]["points"]) == 3
    assert result_a["strongest_period"]["revenue"] == 100
    assert result_b["currency"] == "EUR"
    assert result_b["summary"]["revenue"] == 999
    assert "C1" not in str(result_b)


def test_sales_never_invents_change_and_only_uses_active_validated_forecast(business_environment):
    session, company, _company_b, dataset, prepared = business_environment
    _model(session, company, dataset, "weekly_forecast", "forecasting", active=False)
    sales, _customers, predictions = _services(session, prepared)
    assert sales.build(TenantContext(company.id))["forecast"] is None
    assert predictions.calls == []

    _model(session, company, dataset, "weekly_forecast", "forecasting", active=True)
    result = sales.build(TenantContext(company.id), period_key="current_month")
    assert result["forecast"]["forecasted_total"] == 170
    assert len(result["forecast"]["points"]) == 2
    assert result["summary"]["revenue_change_percent"] is not None


def test_sales_and_customers_capability_and_processing_states(business_environment):
    session, company, _company_b, dataset, prepared = business_environment
    prepared[dataset.id] = _prepared(
        company,
        dataset,
        [{"product": "P1"}],
        columns={"product": "product_id"},
    )
    sales, customers, _ = _services(session, prepared)
    assert sales.build(TenantContext(company.id))["available"] is False
    assert customers.build(TenantContext(company.id))["available"] is False

    dataset.status = DatasetStatus.PROCESSING
    session.commit()
    assert sales.build(TenantContext(company.id))["status"] == "processing"
    assert customers.build(TenantContext(company.id))["status"] == "processing"


def test_sales_validates_period_even_without_sales_capability(business_environment):
    session, company, _company_b, dataset, prepared = business_environment
    prepared[dataset.id] = _prepared(
        company,
        dataset,
        [{"product": "P1"}],
        columns={"product": "product_id"},
    )
    sales, _customers, _ = _services(session, prepared)

    with pytest.raises(InvalidSalesPeriod):
        sales.build(TenantContext(company.id), period_key="unsupported")
    with pytest.raises(InvalidSalesPeriod):
        sales.build(TenantContext(company.id), period_key="custom")


def test_customers_real_summary_pagination_search_and_tenant_lookup(business_environment):
    session, company_a, company_b, _dataset, prepared = business_environment
    _sales, customers, _ = _services(session, prepared)

    first = customers.build(TenantContext(company_a.id), page=1, page_size=2)
    assert first["currency"] == "CAD"
    assert first["summary"] == {
        "total_customers": 3,
        "active_customers": 3,
        "new_customers": 2,
        "repeat_customers": 1,
        "purchase_frequency": 1.33,
        "average_customer_value": 75.0,
    }
    assert first["pagination"] == {"page": 1, "page_size": 2, "total": 3, "pages": 2}
    searched = customers.build(TenantContext(company_a.id), search="c1")
    assert [item["customer_id"] for item in searched["items"]] == ["C1"]
    with pytest.raises(CustomerNotFound):
        customers.get_customer(TenantContext(company_b.id), "C1")


def test_customer_lookup_is_exact_beyond_partial_search_page(business_environment):
    session, company, _company_b, dataset, prepared = business_environment
    rows = [
        {"client": f"C1-{index}", "amount": 1000 + index}
        for index in range(120)
    ]
    rows.append({"client": "C1", "amount": 1})
    prepared[dataset.id] = _prepared(
        company,
        dataset,
        rows,
        columns={"client": "customer_id", "amount": "total_amount"},
    )
    _sales, customers, _ = _services(session, prepared)

    assert customers.get_customer(TenantContext(company.id), "C1")["customer_id"] == "C1"


def test_customers_only_surface_real_active_segment_and_churn_outputs(business_environment):
    session, company, _company_b, dataset, prepared = business_environment
    _model(session, company, dataset, "segmentation", "clustering")
    _model(session, company, dataset, "churn", "classification")
    _sales, customers, predictions = _services(session, prepared)

    result = customers.build(TenantContext(company.id))

    assert result["segments"] == [
        {"label": "new", "count": 2},
        {"label": "loyal", "count": 1},
    ]
    assert {item["customer_id"]: item["risk"] for item in result["items"]}["C2"] == "churn_prediction"
    assert all(call[0].company_id == company.id for call in predictions.calls)
    assert all("churned" not in call[3] for call in predictions.calls if call[2] == "churn")


def test_dataset_deletion_removes_sales_customers_and_model_outputs(business_environment):
    session, company, _company_b, dataset, prepared = business_environment
    _model(session, company, dataset, "weekly_forecast", "forecasting")
    sales, customers, predictions = _services(session, prepared)
    assert sales.build(TenantContext(company.id))["available"] is True

    session.execute(delete(Dataset).where(Dataset.id == dataset.id))
    session.commit()

    assert sales.build(TenantContext(company.id))["status"] == "no_data"
    assert customers.build(TenantContext(company.id))["status"] == "no_data"
    assert predictions.calls


def test_sales_and_customers_endpoints_are_tenant_derived_and_subscription_gated(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'business-api.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        active = _company(session, "Active", "CAD")
        inactive = _company(session, "Inactive", "USD", subscription="inactive")

    captured = []
    response_payload = {
        "status": "no_data",
        "available": False,
        "currency": "CAD",
        "capabilities": [],
        "period": {
            "key": "last_30_days",
            "start": None,
            "end": None,
            "comparison_start": None,
            "comparison_end": None,
            "date_filter_available": False,
            "granularity": "month",
        },
        "summary": None,
        "trend": {"granularity": "month", "points": []},
        "strongest_period": None,
        "weakest_period": None,
        "forecast": None,
    }
    app = create_application()

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_tenant_context] = lambda: TenantContext(active.id)
    app.dependency_overrides[get_tenant_sales_service] = lambda: SimpleNamespace(
        build=lambda tenant, **_kwargs: captured.append(tenant) or response_payload
    )
    with TestClient(app) as client:
        response = client.get(f"/api/v1/sales/summary?company_id={inactive.id}")
    assert response.status_code == 200
    assert captured == [TenantContext(active.id)]

    app.dependency_overrides[get_tenant_context] = lambda: TenantContext(inactive.id)
    with TestClient(app) as client:
        blocked = client.get("/api/v1/customers/summary")
    assert blocked.status_code == 402


def test_products_and_recommendations_endpoints_are_tenant_derived_and_subscription_gated(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'phase4d-api.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        active = _company(session, "Phase4D Active", "CAD")
        inactive = _company(session, "Phase4D Inactive", "USD", subscription="inactive")

    captured = []
    products_payload = {
        "status": "no_data",
        "available": False,
        "currency": "CAD",
        "capabilities": [],
        "summary": None,
        "categories": [],
        "trend": {"granularity": "month", "points": []},
        "items": [],
        "pagination": {"page": 1, "page_size": 25, "total": 0, "pages": 0},
    }
    recommendations_payload = {
        "status": "no_data",
        "currency": "CAD",
        "generated_at": datetime.now(timezone.utc),
        "recommendations": [],
    }
    app = create_application()

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_tenant_context] = lambda: TenantContext(active.id)
    app.dependency_overrides[get_tenant_products_service] = lambda: SimpleNamespace(
        build=lambda tenant, **_kwargs: captured.append(("products", tenant)) or products_payload
    )
    app.dependency_overrides[get_tenant_recommendations_service] = lambda: SimpleNamespace(
        build=lambda tenant: captured.append(("recommendations", tenant))
        or recommendations_payload
    )
    with TestClient(app) as client:
        products_response = client.get(f"/api/v1/products/summary?company_id={inactive.id}")
        recommendations_response = client.get(
            f"/api/v1/recommendations?company_id={inactive.id}"
        )
    assert products_response.status_code == 200
    assert recommendations_response.status_code == 200
    assert captured == [
        ("products", TenantContext(active.id)),
        ("recommendations", TenantContext(active.id)),
    ]

    app.dependency_overrides[get_tenant_context] = lambda: TenantContext(inactive.id)
    with TestClient(app) as client:
        blocked_products = client.get("/api/v1/products/summary")
        blocked_recommendations = client.get("/api/v1/recommendations")
    assert blocked_products.status_code == 402
    assert blocked_recommendations.status_code == 402


def test_products_reconcile_with_sales_and_expose_supported_metrics(business_environment):
    session, company, _company_b, dataset, prepared = business_environment
    prepared[dataset.id] = _product_prepared(company, dataset)
    products, _recommendations, _ = _phase4d_services(session, prepared)
    sales, _customers, _ = _services(session, prepared)

    result = products.build(TenantContext(company.id), page_size=1)
    sales_result = sales.build(TenantContext(company.id), period_key="year_to_date")

    assert result["status"] == "ready"
    assert result["currency"] == "CAD"
    assert result["summary"] == {
        "total_products": 2,
        "active_products": 1,
        "products_with_activity": 2,
        "revenue": 400.0,
        "units": 8.0,
        "average_selling_price": 50.0,
        "top_product_revenue_share": 62.5,
        "out_of_stock_products": 1,
    }
    assert result["summary"]["revenue"] == sales_result["summary"]["revenue"]
    assert result["categories"] == [
        {
            "category": "Drinks",
            "product_count": 2,
            "revenue": 400.0,
            "units": 8.0,
            "revenue_share": 100.0,
        }
    ]
    assert result["pagination"]["pages"] == 2
    assert result["trend"]["points"]


def test_products_search_sort_filter_detail_and_tenant_isolation(business_environment):
    session, company_a, company_b, dataset_a, prepared = business_environment
    prepared[dataset_a.id] = _product_prepared(company_a, dataset_a)
    products, _recommendations, _ = _phase4d_services(session, prepared)

    searched = products.build(TenantContext(company_a.id), search="tea")
    assert [item["product_id"] for item in searched["items"]] == ["P2"]
    weak = products.build(TenantContext(company_a.id), performance="weak")
    assert [item["product_id"] for item in weak["items"]] == ["P1"]
    out = products.build(TenantContext(company_a.id), status="out_of_stock")
    assert [item["product_id"] for item in out["items"]] == ["P2"]
    detail = products.get_product(TenantContext(company_a.id), "P1")
    assert detail["currency"] == "CAD"
    assert detail["trend"]["points"]
    with pytest.raises(ProductNotFound):
        products.get_product(TenantContext(company_b.id), "P1")


def test_products_missing_capabilities_remain_unavailable_or_none(business_environment):
    session, company, _company_b, dataset, prepared = business_environment
    prepared[dataset.id] = _prepared(
        company,
        dataset,
        [{"article": "Coffee"}],
        columns={"article": "product_name"},
    )
    products, _recommendations, _ = _phase4d_services(session, prepared)
    result = products.build(TenantContext(company.id))
    assert result["available"] is True
    assert result["summary"]["revenue"] is None
    assert result["summary"]["units"] is None
    assert result["summary"]["out_of_stock_products"] is None
    assert result["categories"] == []

    prepared[dataset.id] = _prepared(
        company,
        dataset,
        [{"amount": 10}],
        columns={"amount": "total_amount"},
    )
    assert products.build(TenantContext(company.id))["available"] is False


def test_recommendations_are_evidence_backed_ranked_deduplicated_and_have_no_fake_impact(
    business_environment,
):
    session, company, _company_b, dataset, prepared = business_environment
    prepared[dataset.id] = _product_prepared(company, dataset)
    _products, recommendations, _ = _phase4d_services(session, prepared)

    result = recommendations.build(TenantContext(company.id))
    items = result["recommendations"]

    assert items
    assert len({item["id"] for item in items}) == len(items)
    assert all(item["evidence"] for item in items)
    assert all(item["estimated_impact"] is None for item in items)
    assert all(item["lifecycle"] == "active" for item in items)
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "informational": 4}
    assert [priority_order[item["priority"]] for item in items] == sorted(
        priority_order[item["priority"]] for item in items
    )
    assert "product_decline:P1" in {item["id"] for item in items}
    assert "product_concentration:P1" in {item["id"] for item in items}


def test_recommendations_only_consume_active_validated_same_dataset_model(business_environment):
    session, company, _company_b, dataset, prepared = business_environment
    prepared[dataset.id] = _product_prepared(company, dataset)
    _model(session, company, dataset, "recommendation", "recommendation", active=False)
    _products, recommendations, predictions = _phase4d_services(session, prepared)
    result = recommendations.build(TenantContext(company.id))
    assert "cross_sell_opportunity" not in {item["type"] for item in result["recommendations"]}
    assert predictions.calls == []

    _model(session, company, dataset, "recommendation", "recommendation", active=True)
    result = recommendations.build(TenantContext(company.id))
    model_item = next(item for item in result["recommendations"] if item["type"] == "cross_sell_opportunity")
    assert model_item["source_model_version"] == "1"
    assert model_item["estimated_impact"] is None
    assert all(call[0].company_id == company.id for call in predictions.calls)


def test_product_and_recommendation_outputs_invalidate_after_dataset_deletion(business_environment):
    session, company, _company_b, dataset, prepared = business_environment
    prepared[dataset.id] = _product_prepared(company, dataset)
    products, recommendations, _ = _phase4d_services(session, prepared)
    assert products.build(TenantContext(company.id))["available"] is True
    assert recommendations.build(TenantContext(company.id))["recommendations"]

    session.execute(delete(Dataset).where(Dataset.id == dataset.id))
    session.commit()

    assert products.build(TenantContext(company.id))["available"] is False
    assert recommendations.build(TenantContext(company.id))["recommendations"] == []