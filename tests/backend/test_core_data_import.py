"""Import de données CORE — indépendant de l'activation des modules optionnels.

Couvre le blocage historique (403 pour une entreprise Demo sans
`CompanyModule`), la mise en place des quotas par plan, la persistance des
modules optionnels choisis pendant l'onboarding, et le fait que l'exécution
d'une capacité métier reste, elle, subordonnée à l'activation du module.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.database import get_db
from backend.app.dependencies.auth import get_account_notifier, get_tenant_context
from backend.app.dependencies.datasets import (
    get_capability_execution_gate,
    get_company_dataset_ingestion_service,
)
from backend.app.models import (
    Base,
    Company,
    CompanyModule,
    CompanyModuleStatus,
    Dataset,
    Module,
)
from backend.app.repositories import SQLAlchemyModuleEntitlements
from backend.app.services.capability_execution_gate import CapabilityExecutionGate
from backend.app.services.company_dataset_ingestion_service import CompanyDatasetIngestionService
from backend.app.services.data_import_policy import DataImportPolicy
from backend.main import create_application
from modules.entitlements import ModuleAccessService
from payments.plans import data_import_limits_for
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.dataset_ingestion.storage import LocalDatasetStorage

from tests.backend.test_auth import RecordingNotifier, registration_payload, verify_and_login


def _csv(row_marker: str) -> bytes:
    return f"id,age,segment\n1,20,{row_marker}\n2,30,{row_marker}\n".encode()


# ---------------------------------------------------------------------------
# 1. Real end-to-end new-company flow: register -> verify -> login -> upload
# ---------------------------------------------------------------------------


@pytest.fixture
def core_import_environment(
    tmp_path: Path,
) -> Generator[tuple[TestClient, RecordingNotifier], None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'core_data_import.db'}",
        connect_args={"check_same_thread": False},
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    notifier = RecordingNotifier()
    app = create_application()

    def override_db() -> Generator[Session, None, None]:
        session = testing_session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_account_notifier] = lambda: notifier
    with TestClient(app) as client:
        yield client, notifier


def test_new_demo_company_can_import_data_with_zero_company_modules(
    core_import_environment,
) -> None:
    """Le bug historique : une entreprise Demo fraîchement inscrite (donc sans
    aucun `CompanyModule` actif) doit pouvoir importer des données — capacité
    CORE Avenqo, jamais subordonnée à un module optionnel."""
    client, notifier = core_import_environment
    email = "owner@core-import-demo.ca"
    response = client.post(
        "/api/v1/auth/register",
        json=registration_payload(email=email, company_name="Core Import Demo Co"),
    )
    assert response.status_code == 201
    session = verify_and_login(client, notifier, email)
    assert session["company"]["subscription_plan"] == "demo"
    token = session["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    upload = client.post(
        "/api/v1/datasets/upload",
        data={"module_code": "retail"},
        files={"file": ("first_import.csv", _csv("A"), "text/csv")},
        headers=headers,
    )
    assert upload.status_code == 201
    assert upload.json()["status"] == "ready"

    datasets = client.get("/api/v1/datasets", headers=headers)
    assert datasets.status_code == 200
    assert len(datasets.json()) == 1


def test_new_demo_company_dataset_is_tenant_isolated(core_import_environment) -> None:
    client, notifier = core_import_environment

    def _register_and_upload(email: str, company_name: str, filename: str) -> str:
        assert client.post(
            "/api/v1/auth/register",
            json=registration_payload(email=email, company_name=company_name),
        ).status_code == 201
        token = verify_and_login(client, notifier, email)["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        upload = client.post(
            "/api/v1/datasets/upload",
            data={"module_code": "retail"},
            files={"file": (filename, _csv("A"), "text/csv")},
            headers=headers,
        )
        assert upload.status_code == 201
        return token

    token_a = _register_and_upload("owner-a@core-import-iso.ca", "Core Import Co A", "a.csv")
    token_b = _register_and_upload("owner-b@core-import-iso.ca", "Core Import Co B", "b.csv")

    datasets_a = client.get("/api/v1/datasets", headers={"Authorization": f"Bearer {token_a}"}).json()
    datasets_b = client.get("/api/v1/datasets", headers={"Authorization": f"Bearer {token_b}"}).json()
    assert len(datasets_a) == 1
    assert len(datasets_b) == 1
    assert datasets_a[0]["id"] != datasets_b[0]["id"]

    cross = client.get(
        f"/api/v1/datasets/{datasets_b[0]['id']}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert cross.status_code == 404


# ---------------------------------------------------------------------------
# 2. Plan-scoped quotas (reuses the entitlement/plan architecture)
# ---------------------------------------------------------------------------


@pytest.fixture
def quota_environment(
    tmp_path: Path,
) -> Generator[tuple[TestClient, dict[str, TenantContext]], None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'quota.db'}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with session_factory() as session:
        companies = {
            "demo": Company(
                name="Demo Co", slug="quota-demo", email="demo@quota.ca",
                country="Canada", timezone="America/Toronto", industry="Retail",
                subscription_plan="demo",
            ),
            "professional": Company(
                name="Pro Co", slug="quota-pro", email="pro@quota.ca",
                country="Canada", timezone="America/Toronto", industry="Retail",
                subscription_plan="professional",
            ),
        }
        session.add_all(companies.values())
        session.commit()
        tenants = {code: TenantContext(company.id) for code, company in companies.items()}

    current = {"tenant": tenants["demo"]}
    artifact_root = tmp_path / "artifacts"
    app = create_application()

    def override_db() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    def override_ingestion_service() -> Generator[CompanyDatasetIngestionService, None, None]:
        with session_factory() as session:
            yield CompanyDatasetIngestionService(
                session=session,
                storage=LocalDatasetStorage(artifact_root / "company_datasets"),
                quota=DataImportPolicy(session),
                max_upload_bytes=5 * 1024 * 1024,
            )

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_tenant_context] = lambda: current["tenant"]
    app.dependency_overrides[get_company_dataset_ingestion_service] = override_ingestion_service
    with TestClient(app) as client:
        yield client, {**tenants, "current": current}


def _upload(client: TestClient, filename: str) -> "object":
    return client.post(
        "/api/v1/datasets/upload",
        data={"module_code": "retail"},
        files={"file": (filename, _csv("A"), "text/csv")},
    )


def test_demo_plan_has_a_lower_dataset_quota_than_professional() -> None:
    demo_limits = data_import_limits_for("demo")
    professional_limits = data_import_limits_for("professional")
    enterprise_limits = data_import_limits_for("enterprise")
    assert demo_limits.max_datasets < professional_limits.max_datasets < enterprise_limits.max_datasets
    assert demo_limits.max_file_mb < professional_limits.max_file_mb < enterprise_limits.max_file_mb


def test_demo_plan_upload_rejected_once_dataset_quota_reached(quota_environment) -> None:
    client, tenants = quota_environment
    tenants["current"]["tenant"] = tenants["demo"]
    limit = data_import_limits_for("demo").max_datasets

    for index in range(limit):
        response = _upload(client, f"demo-dataset-{index}.csv")
        assert response.status_code == 201, response.text

    over_quota = _upload(client, "demo-dataset-over-quota.csv")
    assert over_quota.status_code == 403


def test_professional_plan_tolerates_more_datasets_than_demo_limit(quota_environment) -> None:
    client, tenants = quota_environment
    tenants["current"]["tenant"] = tenants["professional"]
    demo_limit = data_import_limits_for("demo").max_datasets

    # Dépasse la limite Demo sans être bloqué, car l'offre Professional a un
    # plafond plus élevé (`data_import_limits_for`).
    for index in range(demo_limit + 1):
        response = _upload(client, f"pro-dataset-{index}.csv")
        assert response.status_code == 201, response.text


# ---------------------------------------------------------------------------
# 3. Capability execution still requires the optional module to be active
# ---------------------------------------------------------------------------


@pytest.fixture
def capability_gating_environment(
    tmp_path: Path,
) -> Generator[tuple[TestClient, dict], None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'capability_gating.db'}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with session_factory() as session:
        company = Company(
            name="No Module Co", slug="no-module-co", email="no-module@example.ca",
            country="Canada", timezone="America/Toronto", industry="Retail",
            subscription_plan="professional",
        )
        session.add(company)
        session.flush()
        tenant = TenantContext(company.id)
        session.commit()

    current = {"tenant": tenant}
    artifact_root = tmp_path / "artifacts"
    app = create_application()

    def override_db() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    def override_ingestion_service() -> Generator[CompanyDatasetIngestionService, None, None]:
        with session_factory() as session:
            yield CompanyDatasetIngestionService(
                session=session,
                storage=LocalDatasetStorage(artifact_root / "company_datasets"),
                quota=DataImportPolicy(session),
                max_upload_bytes=5 * 1024 * 1024,
            )

    def override_gate() -> Generator[CapabilityExecutionGate, None, None]:
        with session_factory() as session:
            service = CompanyDatasetIngestionService(
                session=session,
                storage=LocalDatasetStorage(artifact_root / "company_datasets"),
                quota=DataImportPolicy(session),
                max_upload_bytes=5 * 1024 * 1024,
            )
            yield CapabilityExecutionGate(
                service, access=ModuleAccessService(SQLAlchemyModuleEntitlements(session))
            )

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_tenant_context] = lambda: current["tenant"]
    app.dependency_overrides[get_company_dataset_ingestion_service] = override_ingestion_service
    app.dependency_overrides[get_capability_execution_gate] = override_gate
    with TestClient(app) as client:
        yield client, {"tenant": tenant, "current": current, "session_factory": session_factory}


def test_ingestion_succeeds_but_capability_execution_still_requires_module(
    capability_gating_environment,
) -> None:
    client, ctx = capability_gating_environment

    upload = client.post(
        "/api/v1/datasets/upload",
        data={"module_code": "retail"},
        files={"file": ("no_module.csv", _csv("A"), "text/csv")},
    )
    assert upload.status_code == 201
    dataset_id = upload.json()["dataset_id"]

    denied = client.post(f"/api/v1/datasets/{dataset_id}/capabilities/churn/prepare")
    assert denied.status_code == 403

    session_factory = ctx["session_factory"]
    with session_factory() as session:
        module = Module(name="RetailSenseAI", code="retail", is_active=True)
        session.add(module)
        session.flush()
        session.add(
            CompanyModule(
                company_id=ctx["tenant"].company_id,
                module_id=module.id,
                activated_at=datetime.now(timezone.utc) - timedelta(minutes=1),
                status=CompanyModuleStatus.ACTIVE,
            )
        )
        session.commit()

    allowed = client.post(f"/api/v1/datasets/{dataset_id}/capabilities/churn/prepare")
    assert allowed.status_code in (200, 422)  # 422 si le mapping ne couvre pas "churn"
