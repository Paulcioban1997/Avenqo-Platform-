from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.database import get_db
from backend.app.dependencies.auth import get_tenant_context
from backend.app.dependencies.datasets import get_dataset_import_service
from backend.app.models import (
    Base,
    Company,
    CompanyModule,
    CompanyModuleStatus,
    Dataset,
    DatasetVersion,
    DatasetVersionStatus,
    ModelRegistry,
    Module,
    TrainingJob,
)
from backend.app.repositories import SQLAlchemyModuleEntitlements
from backend.app.services.artifact_service import ArtifactService
from backend.app.services.dataset_import_service import DatasetImportService
from backend.app.services.data_import_policy import DataImportPolicy
from backend.main import create_application
from modules.entitlements import ModuleAccessService
from shared.ai_engine.contracts import TenantContext

CSV_CONTENT = b"id,age,segment\n1,20,A\n2,,B\n2,,B\n"


@pytest.fixture
def dataset_environment(
    tmp_path: Path,
) -> Generator[tuple[TestClient, sessionmaker[Session], dict[str, TenantContext], Path], None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'datasets.db'}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with session_factory() as session:
        companies = [
            Company(
                name=name,
                slug=slug,
                email=email,
                country="Canada",
                timezone="America/Toronto",
                industry="Retail",
                subscription_plan="professional",
            )
            for name, slug, email in (
                ("Acme", "acme", "acme@example.ca"),
                ("Nova", "nova", "nova@example.ca"),
                ("No Access", "no-access", "no-access@example.ca"),
            )
        ]
        module = Module(name="RetailSenseAI", code="retail", is_active=True)
        session.add_all([*companies, module])
        session.flush()
        now = datetime.now(timezone.utc)
        session.add_all([
            CompanyModule(
                company_id=company.id,
                module_id=module.id,
                activated_at=now - timedelta(minutes=1),
                status=CompanyModuleStatus.ACTIVE,
            )
            for company in companies[:2]
        ])
        session.commit()
        tenants = {
            "acme": TenantContext(companies[0].id),
            "nova": TenantContext(companies[1].id),
            "no_access": TenantContext(companies[2].id),
        }

    current = {"tenant": tenants["acme"]}
    artifact_root = tmp_path / "artifacts"
    app = create_application()

    def override_db() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    def override_dataset_service() -> Generator[DatasetImportService, None, None]:
        with session_factory() as session:
            yield DatasetImportService(
                session=session,
                artifacts=ArtifactService(artifact_root),
                quota=DataImportPolicy(session),
                max_upload_bytes=1024 * 1024,
            )

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_tenant_context] = lambda: current["tenant"]
    app.dependency_overrides[get_dataset_import_service] = override_dataset_service
    with TestClient(app) as client:
        yield client, session_factory, {**tenants, "current": current}, artifact_root


def test_csv_import_creates_tenant_profile_and_artifact(dataset_environment) -> None:
    client, session_factory, tenants, artifact_root = dataset_environment

    response = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("customers.csv", CSV_CONTENT, "text/csv")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "validated"
    assert body["rows_count"] == 3
    assert body["columns_count"] == 3
    assert body["numerical_columns"] == 2
    assert body["categorical_columns"] == 1
    assert body["missing_values"] == 2
    assert body["duplicates"] == 1
    assert [column["inferred_type"] for column in body["columns"]] == [
        "integer",
        "integer",
        "string",
    ]
    with session_factory() as session:
        dataset = session.scalar(select(Dataset))
        assert dataset is not None
        source = Path(dataset.source)
        assert str(tenants["acme"].company_id) in source.parts
        assert source.is_file()
        assert artifact_root.resolve() in source.parents
        assert session.scalars(select(TrainingJob)).all() == []
        assert session.scalars(select(ModelRegistry)).all() == []
        assert list(artifact_root.rglob("*"))[-1] == source


def test_dataset_routes_hide_other_tenants(dataset_environment) -> None:
    client, _, tenants, _ = dataset_environment
    upload = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("customers.csv", CSV_CONTENT, "text/csv")},
    )
    dataset_id = upload.json()["id"]

    tenants["current"]["tenant"] = tenants["nova"]

    assert client.get("/api/v1/datasets").json() == []
    assert client.get(f"/api/v1/datasets/{dataset_id}").status_code == 404


def test_dataset_delete_is_tenant_scoped_and_removes_artifacts(dataset_environment) -> None:
    client, session_factory, tenants, _ = dataset_environment
    upload = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("customers.csv", CSV_CONTENT, "text/csv")},
    )
    assert upload.status_code == 201
    dataset_id = upload.json()["id"]

    with session_factory() as session:
        dataset = session.get(Dataset, UUID(dataset_id))
        assert dataset is not None
        source = Path(dataset.source)
        dataset_root = source.parent
        assert source.is_file()
        assert dataset_root.is_dir()

    # Une autre entreprise ne peut ni voir ni supprimer le fichier.
    tenants["current"]["tenant"] = tenants["nova"]
    assert client.delete(f"/api/v1/datasets/{dataset_id}").status_code == 404
    assert source.is_file()

    # Le propriétaire peut supprimer le dataset, ses métadonnées et son dossier.
    tenants["current"]["tenant"] = tenants["acme"]
    response = client.delete(f"/api/v1/datasets/{dataset_id}")
    assert response.status_code == 204
    assert client.get(f"/api/v1/datasets/{dataset_id}").status_code == 404
    assert client.get("/api/v1/datasets").json() == []
    assert not dataset_root.exists()


def test_csv_import_succeeds_without_active_module_core_capability(dataset_environment) -> None:
    """L'ingestion de données est une capacité CORE Avenqo : une entreprise
    sans module optionnel actif peut tout de même importer un CSV."""
    client, _, tenants, _ = dataset_environment
    tenants["current"]["tenant"] = tenants["no_access"]

    response = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("customers.csv", CSV_CONTENT, "text/csv")},
    )

    assert response.status_code == 201
