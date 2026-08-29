from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker

from backend.app.database import get_db
from backend.app.dependencies.auth import get_tenant_context
from backend.app.dependencies.tenant_business import (
    get_tenant_customers_service,
    get_tenant_sales_service,
)
from backend.app.models import (
    Base,
    BillingAccount,
    Company,
    Dataset,
    DatasetStatus,
    JobStatus,
    Mapping,
    ModelRegistry,
    TrainingJob,
)
from backend.app.services.tenant_analytics_service import TenantAnalyticsService
from backend.app.services.tenant_customers_service import CustomerNotFound, TenantCustomersService
from backend.app.services.tenant_sales_service import InvalidSalesPeriod, TenantSalesService
from backend.main import create_application
from shared.ai_engine.contracts import TenantContext


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