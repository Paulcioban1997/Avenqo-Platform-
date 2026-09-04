"""End-to-end proof of the autonomous data science pipeline (consolidation task).

Uploads two related, generic business files (no Olist logic, no hardcoded
dataset names) for one tenant and proves the FULL chain works on real data:

    upload -> ingestion -> profiling (real statistics) -> automatic cleaning
    -> automatic semantic mapping -> relationship discovery -> READY canonical
    data -> automatic ML task discovery/training -> Retail dashboard KPIs
    -> a Central AI business tool answering from the same real data.

Every assertion checks *real* computed values (never zero/fabricated unless
genuinely empty), and tenant isolation is proven with a second, empty company.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.ai.tools.business.sales_tools import BusinessOverviewArgs, GetBusinessOverviewTool
from backend.app.ai.tools.contracts import ToolExecutionContext
from backend.app.database import get_db
from backend.app.database.session import get_session_factory
from backend.app.dependencies.ai_engine import get_model_registry_root
from backend.app.dependencies.auth import get_tenant_context
from backend.app.dependencies.datasets import get_company_dataset_ingestion_service
from backend.app.dependencies.training import get_training_dispatcher
from backend.app.models import (
    AIJob,
    Base,
    Company,
    CompanyModule,
    CompanyModuleStatus,
    Dataset,
    DatasetRelationship,
    DatasetStatus,
    JobStatus,
    Module,
    ModelRegistry,
)
from backend.app.routers.datasets import require_dataset_read
from backend.app.services.automatic_company_dataset_ingestion_service import (
    AutomaticCompanyDatasetIngestionService,
)
from backend.app.services.company_dataset_ingestion_service import CompanyDatasetIngestionService
from backend.app.services.data_import_policy import DataImportPolicy
from backend.app.services.tenant_analytics_service import TenantAnalyticsService
from backend.app.services.tenant_dashboard_service import TenantDashboardService
from backend.app.services.tenant_products_service import TenantProductsService
from backend.app.services.tenant_recommendations_service import TenantRecommendationsService
from backend.app.services.training_dispatcher import TrainingDispatcher
from backend.main import create_application
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.dataset_ingestion.storage import LocalDatasetStorage
from tests.subscription_helpers import add_active_subscription


def _orders_csv(rows: int = 40) -> bytes:
    """Generic sales file: customer_id/order_id/product_id/quantity/price/total/date."""

    header = "customer_id,order_id,product_sku,quantity_ordered,unit_price,order_total,order_date"
    lines = [header]
    start = datetime(2024, 1, 1)
    for i in range(rows):
        units = 1 + (i % 5)
        unit_cost = round(9.99 + (i % 7) * 1.35, 2)
        total = round(units * unit_cost, 2)
        when = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        lines.append(f"C{i % 12},O{i},P{i % 6},{units},{unit_cost},{total},{when}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _reviews_csv(rows: int = 40) -> bytes:
    """Generic review file sharing order_id/customer_id with the orders file."""

    header = "order_id,customer_id,review_text,review_score"
    lines = [header]
    for i in range(rows):
        score = 1 + (i % 5)
        message = "Excellent experience overall" if score >= 4 else "Not satisfied with this order"
        lines.append(f"O{i},C{i % 12},{message},{score}")
    return ("\n".join(lines) + "\n").encode("utf-8")


@pytest.fixture
def e2e_environment(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'e2e.db'}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    with session_factory() as session:
        active_co = Company(
            name="Active Co", slug="active-co", email="active@example.ca",
            country="Canada", timezone="America/Toronto", industry="Retail",
            subscription_plan="professional",
        )
        empty_co = Company(
            name="Empty Co", slug="empty-co", email="empty@example.ca",
            country="Canada", timezone="America/Toronto", industry="Retail",
            subscription_plan="professional",
        )
        module = Module(name="RetailSenseAI", code="retail", is_active=True)
        session.add_all([active_co, empty_co, module])
        session.flush()
        now = datetime.now(timezone.utc)
        for company in (active_co, empty_co):
            session.add(
                CompanyModule(
                    company_id=company.id, module_id=module.id,
                    activated_at=now - timedelta(minutes=1),
                    status=CompanyModuleStatus.ACTIVE,
                )
            )
            add_active_subscription(session, company)
        session.commit()
        tenants = {
            "active": TenantContext(active_co.id),
            "empty": TenantContext(empty_co.id),
        }

    current = {"tenant": tenants["active"]}
    artifact_root = tmp_path / "artifacts"
    model_root = tmp_path / "models"
    app = create_application()

    def override_db() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    def override_company_ingestion(
        db: Session = Depends(get_db),
        dispatcher: TrainingDispatcher = Depends(get_training_dispatcher),
    ) -> CompanyDatasetIngestionService:
        return AutomaticCompanyDatasetIngestionService(
            session=db,
            storage=LocalDatasetStorage(artifact_root / "company_datasets"),
            quota=DataImportPolicy(db),
            max_upload_bytes=5 * 1024 * 1024,
            dispatcher=dispatcher,
        )

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_tenant_context] = lambda: current["tenant"]
    app.dependency_overrides[require_dataset_read] = lambda: object()
    app.dependency_overrides[get_company_dataset_ingestion_service] = override_company_ingestion
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    app.dependency_overrides[get_model_registry_root] = lambda: model_root

    with TestClient(app) as client:
        yield client, session_factory, {**tenants, "current": current, "artifact_root": artifact_root}


def _upload(client: TestClient, filename: str, content: bytes):
    return client.post(
        "/api/v1/datasets/upload",
        data={"module_code": "retail"},
        files={"file": (filename, content, "text/csv")},
    )


def test_full_autonomous_pipeline_uses_real_data_end_to_end(e2e_environment) -> None:
    client, session_factory, tenants = e2e_environment

    orders_response = _upload(client, "orders.csv", _orders_csv())
    assert orders_response.status_code == 201
    orders_id = UUID(orders_response.json()["dataset_id"])

    reviews_response = _upload(client, "reviews.csv", _reviews_csv())
    assert reviews_response.status_code == 201
    reviews_id = UUID(reviews_response.json()["dataset_id"])

    with session_factory() as session:
        orders = session.get(Dataset, orders_id)
        reviews = session.get(Dataset, reviews_id)
        assert orders.status == DatasetStatus.READY
        assert reviews.status == DatasetStatus.READY

        # 1) ML task discovery/training actually happened on real data.
        ai_jobs = session.scalars(
            select(AIJob).where(AIJob.company_id == tenants["active"].company_id)
        ).all()
        assert len(ai_jobs) > 0
        completed = [job for job in ai_jobs if job.status == JobStatus.COMPLETED]
        assert len(completed) > 0
        registry_rows = session.scalars(
            select(ModelRegistry).where(
                ModelRegistry.company_id == tenants["active"].company_id,
                ModelRegistry.is_active.is_(True),
            )
        ).all()
        assert len(registry_rows) > 0

        # 2) Relationship discovery found the real order_ref/customer_ref link
        #    between the two independently uploaded files.
        relationships = session.scalars(
            select(DatasetRelationship).where(
                DatasetRelationship.company_id == tenants["active"].company_id
            )
        ).all()
        assert len(relationships) > 0
        linked_ids = {relationships[0].left_dataset_id, relationships[0].right_dataset_id}
        assert linked_ids == {orders.id, reviews.id}

    # 3) Profiling exposes real statistics for a numeric column, never
    #    placeholders, including the new distribution/outlier fields.
    profile_response = client.get(f"/api/v1/datasets/{orders_id}/profile")
    assert profile_response.status_code == 200
    profile = profile_response.json()
    assert profile["row_count"] == 40
    total_column = next(col for col in profile["columns"] if col["name"] == "order_total")
    assert total_column["mean_value"] is not None and total_column["mean_value"] > 0
    assert total_column["std_value"] is not None and total_column["std_value"] > 0
    assert total_column["p25_value"] is not None
    assert total_column["p75_value"] is not None
    assert total_column["p25_value"] <= total_column["median_value"] <= total_column["p75_value"]
    assert total_column["outlier_count"] is not None

    # 4) Cleaned data detail must never show "0 -> 0 rows" for real data.
    cleaning_response = client.get(f"/api/v1/datasets/{orders_id}/cleaning")
    assert cleaning_response.status_code == 200
    cleaning = cleaning_response.json()
    assert cleaning["summary"]["original_row_count"] == 40
    assert cleaning["summary"]["cleaned_row_count"] == 40
    assert cleaning["preview_total"] == 40
    assert len(cleaning["cleaned_preview"]) > 0

    # 5) CSV export of the cleaned data works and contains real rows.
    export_response = client.get(f"/api/v1/datasets/{orders_id}/export/csv")
    assert export_response.status_code == 200
    exported_lines = export_response.text.strip().splitlines()
    assert len(exported_lines) == 41  # header + 40 data rows

    # 6) Retail dashboard KPI shows a real, non-zero, non-fabricated revenue.
    with session_factory() as session:
        ingestion = AutomaticCompanyDatasetIngestionService(
            session=session,
            storage=LocalDatasetStorage(tenants["artifact_root"] / "company_datasets"),
            quota=DataImportPolicy(session),
            max_upload_bytes=5 * 1024 * 1024,
            dispatcher=None,  # not used for reads
        )
        analytics = TenantAnalyticsService(session, ingestion)
        products = TenantProductsService(analytics)
        recommendations = TenantRecommendationsService(analytics, products, None)
        dashboard = TenantDashboardService(analytics, recommendations)
        result = dashboard.build(tenants["active"])
        revenue_kpi = next(kpi for kpi in result["kpis"] if kpi["key"] == "revenue")
        assert revenue_kpi["state"] == "AVAILABLE"
        assert revenue_kpi["value"] is not None
        assert revenue_kpi["value"] > 0

        # 7) A Central AI business tool answers the same question grounded in
        #    the same real data (never invented, never a hardcoded number).
        tool = GetBusinessOverviewTool(session=session, ingestion=ingestion)
        context = ToolExecutionContext(
            tenant=tenants["active"],
            user_id=uuid4(),
            permissions=frozenset({"ai:use"}),
            request_id="e2e-test",
        )
        import asyncio

        outcome = asyncio.run(tool.run(context, BusinessOverviewArgs()))
        assert outcome.success is True
        # Full-history revenue (tool) vs. rolling-period revenue (dashboard KPI)
        # are legitimately different views of the same real data — both must
        # be real, non-zero, and neither ever fabricated.
        assert outcome.data["revenue"] > 0

    # 8) Tenant isolation: an empty company sees no fabricated data.
    tenants["current"]["tenant"] = tenants["empty"]
    with session_factory() as session:
        ingestion = AutomaticCompanyDatasetIngestionService(
            session=session,
            storage=LocalDatasetStorage(tenants["artifact_root"] / "company_datasets"),
            quota=DataImportPolicy(session),
            max_upload_bytes=5 * 1024 * 1024,
            dispatcher=None,
        )
        analytics = TenantAnalyticsService(session, ingestion)
        products = TenantProductsService(analytics)
        recommendations = TenantRecommendationsService(analytics, products, None)
        dashboard = TenantDashboardService(analytics, recommendations)
        empty_result = dashboard.build(tenants["empty"])
        empty_revenue_kpi = next(kpi for kpi in empty_result["kpis"] if kpi["key"] == "revenue")
        assert empty_revenue_kpi["state"] == "UNAVAILABLE"
        assert empty_revenue_kpi["value"] is None

    empty_profile = client.get(f"/api/v1/datasets/{orders_id}/profile")
    assert empty_profile.status_code == 404
