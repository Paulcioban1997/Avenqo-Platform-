from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker

from backend.app.database import get_db
from backend.app.dependencies.auth import get_tenant_context
from backend.app.dependencies.dashboard import get_tenant_dashboard_service
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
from backend.app.services.tenant_dashboard_service import TenantDashboardService
from backend.app.services.tenant_products_service import TenantProductsService
from backend.app.services.tenant_recommendations_service import TenantRecommendationsService
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


def _dashboard_service(session, prepared_by_id):
    analytics = TenantAnalyticsService(session, _PreparedIngestion(prepared_by_id))
    products = TenantProductsService(analytics)
    recommendations = TenantRecommendationsService(analytics, products, None)
    return TenantDashboardService(analytics, recommendations), recommendations


def _prepared(company_id, dataset_id, rows, canonical_columns=None):
    return SimpleNamespace(
        company_id=company_id,
        dataset_id=dataset_id,
        version=1,
        canonical_columns=canonical_columns or {
            "date": "order_timestamp",
            "sale": "order_id",
            "client": "customer_id",
            "amount": "total_amount",
        },
        rows=tuple(rows),
        profile=SimpleNamespace(),
        mapping=(),
        cleaning_report=SimpleNamespace(),
        quality=SimpleNamespace(),
        capability_readiness=(),
    )


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


def _dataset(
    session, company: Company, name: str, status: DatasetStatus = DatasetStatus.READY
) -> Dataset:
    dataset = Dataset(
        company_id=company.id,
        name=name,
        type="csv",
        source=str(Path("unused.csv")),
        rows_count=3,
        columns_count=4,
        status=status,
        uploaded_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
    )
    dataset.mapping = Mapping(mapping_json={"accepted": {}}, confidence=1, approved=True)
    session.add(dataset)
    session.commit()
    return dataset


def _model(
    session,
    company: Company,
    dataset: Dataset,
    task_code: str,
    *,
    active: bool,
) -> ModelRegistry:
    training_job = TrainingJob(
        company_id=company.id,
        dataset_id=dataset.id,
        ai_job_id=uuid4(),
        algorithm="validated",
        status=JobStatus.COMPLETED,
    )
    session.add(training_job)
    session.flush()
    model = ModelRegistry(
        company_id=company.id,
        training_job_id=training_job.id,
        module_code="retail",
        task_code=task_code,
        model_name=f"{task_code}-model",
        model_type="classification",
        framework="sklearn",
        version="1",
        storage_path="unused",
        metric={"accuracy": 0.9},
        dataset_rows_count=3,
        is_active=active,
    )
    session.add(model)
    session.commit()
    return model


def test_dashboard_uses_processed_tenant_data_and_safe_period_comparison(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'dashboard.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        company_a = _company(session, "Company A", "CAD")
        company_b = _company(session, "Company B", "EUR")
        dataset_a = _dataset(session, company_a, "sales-a.csv")
        prepared = _prepared(
            company_a.id,
            dataset_a.id,
            [
                {"date": "2026-07-01", "sale": "old", "client": "C0", "amount": 0},
                {"date": "2026-08-20", "sale": "S1", "client": "C1", "amount": 100},
                {"date": "2026-08-28", "sale": "S2", "client": "C2", "amount": 50},
            ],
        )
        service, recommendations = _dashboard_service(session, {dataset_a.id: prepared})

        dashboard_a = service.build(TenantContext(company_a.id))
        full_recommendations = recommendations.build(TenantContext(company_a.id))
        dashboard_b = service.build(TenantContext(company_b.id))

    kpis = {item["key"]: item for item in dashboard_a["kpis"]}
    assert dashboard_a["status"] == "ready"
    assert dashboard_a["company"]["currency"] == "CAD"
    assert dashboard_a["company"]["plan_code"] == "professional"
    assert kpis["revenue"]["value"] == 150
    assert kpis["orders"]["value"] == 2
    assert kpis["customers"]["value"] == 2
    assert kpis["average_order_value"]["value"] == 75
    assert all(item["state"] == "AVAILABLE" for item in kpis.values())
    assert kpis["revenue"]["previous_value"] == 0
    assert kpis["revenue"]["change_percent"] is None
    assert dashboard_a["priorities"] == [
        {
            "id": item["id"],
            "type": item["type"],
            "title": item["title"],
            "explanation": item["explanation"],
            "severity": item["priority"],
            "source_capability": item["source_capability"],
            "evidence": item["evidence"],
            "suggested_action": item["suggested_action"],
            "action_route": item["action_route"],
        }
        for item in full_recommendations["recommendations"][:3]
    ]
    assert dashboard_b["status"] == "no_data"
    assert all(not item["available"] for item in dashboard_b["kpis"])
    assert all(item["state"] == "UNAVAILABLE" for item in dashboard_b["kpis"])


def test_dashboard_endpoint_is_tenant_derived_and_subscription_gated(tmp_path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'dashboard-api.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        company = _company(session, "Inactive", "RON", subscription="inactive")
        tenant = TenantContext(company.id)

    app = create_application()

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_tenant_context] = lambda: tenant
    app.dependency_overrides[get_tenant_dashboard_service] = lambda: SimpleNamespace(
        build=lambda resolved: {
            "status": "no_data",
            "generated_at": datetime.now(timezone.utc),
            "company": {"currency": "RON", "plan_code": "professional"},
            "period": {
                "start": None,
                "end": None,
                "comparison_start": None,
                "comparison_end": None,
            },
            "capabilities": [],
            "kpis": [],
            "priorities": [],
            "connections": {
                "total": 0,
                "ready": 0,
                "analyzing": 0,
                "preparing_data": 0,
                "training_ai": 0,
                "attention_required": 0,
                "failed": 0,
            },
            "recent_activity": [],
        }
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/dashboard?company_id=someone-else")

    assert response.status_code == 402


def test_dashboard_reflects_partial_data_active_models_and_dataset_deletion(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'dashboard-refresh.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        company = _company(session, "Refresh", "EUR")
        ready = _dataset(session, company, "orders.csv")
        processing = _dataset(session, company, "processing.csv", DatasetStatus.PROCESSING)
        prepared = _prepared(
            company.id,
            ready.id,
            [{"sale": "S1"}, {"sale": "S2"}],
            canonical_columns={"sale": "order_id"},
        )
        _model(session, company, ready, "active_opportunity", active=True)
        _model(session, company, ready, "inactive_opportunity", active=False)
        service, _ = _dashboard_service(session, {ready.id: prepared})

        dashboard = service.build(TenantContext(company.id))

        assert dashboard["status"] == "partial_ready"
        assert dashboard["connections"]["ready"] == 1
        assert dashboard["connections"]["analyzing"] == 1
        assert "active_opportunity" in dashboard["capabilities"]
        assert "inactive_opportunity" not in dashboard["capabilities"]
        assert len([item for item in dashboard["recent_activity"] if item["kind"] == "model_activated"]) == 1
        kpis = {item["key"]: item for item in dashboard["kpis"]}
        assert kpis["orders"]["value"] == 2
        assert kpis["revenue"]["available"] is False

        session.execute(
            delete(Dataset).where(Dataset.id.in_((ready.id, processing.id)))
        )
        session.commit()
        refreshed = service.build(TenantContext(company.id))

    assert refreshed["status"] == "no_data"
    assert refreshed["connections"]["total"] == 0
    assert all(not item["available"] for item in refreshed["kpis"])


def test_dashboard_handles_failed_and_unreadable_ready_datasets(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'dashboard-failures.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        company = _company(session, "Failures", "USD")
        failed = _dataset(session, company, "failed.csv", DatasetStatus.FAILED)
        service, _ = _dashboard_service(session, {})

        dashboard = service.build(TenantContext(company.id))
        assert dashboard["status"] == "error"
        assert dashboard["connections"]["failed"] == 1

        failed.status = DatasetStatus.READY
        session.commit()
        unreadable = service.build(TenantContext(company.id))

    assert unreadable["status"] == "processing"
    assert all(not item["available"] for item in unreadable["kpis"])
    assert all(item["state"] == "PROCESSING" for item in unreadable["kpis"])


def test_dashboard_endpoint_ignores_tenant_query_override(tmp_path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'dashboard-tenant-query.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        company = _company(session, "Authenticated", "CAD")
        tenant = TenantContext(company.id)

    captured = []

    def build(resolved):
        captured.append(resolved)
        return {
            "status": "no_data",
            "generated_at": datetime.now(timezone.utc),
            "company": {"currency": "CAD", "plan_code": "professional"},
            "period": {
                "start": None,
                "end": None,
                "comparison_start": None,
                "comparison_end": None,
            },
            "capabilities": [],
            "kpis": [],
            "priorities": [],
            "connections": {
                "total": 0,
                "ready": 0,
                "analyzing": 0,
                "preparing_data": 0,
                "training_ai": 0,
                "attention_required": 0,
                "failed": 0,
            },
            "recent_activity": [],
        }

    app = create_application()

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_tenant_context] = lambda: tenant
    app.dependency_overrides[get_tenant_dashboard_service] = lambda: SimpleNamespace(build=build)
    with TestClient(app) as client:
        response = client.get(f"/api/v1/dashboard?company_id={uuid4()}")

    assert response.status_code == 200
    assert captured == [tenant]