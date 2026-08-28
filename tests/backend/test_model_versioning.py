"""Phase 9 â€” Model Versioning Enterprise : bout en bout via les endpoints internes.

Aucun bouton "Version"/"Rollback" n'existe cÃ´tÃ© utilisateur (Flutter/Avenqo) :
ces tests appellent directement les endpoints internes `/internal/versioning/*`,
rÃ©servÃ©s Ã  l'outillage d'exploitation/admin. RÃ©utilise le mÃªme environnement de
test que `tests/backend/test_auto_retraining.py`.
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
from backend.app.database.session import get_session_factory
from backend.app.dependencies.ai_engine import get_model_registry_root
from backend.app.dependencies.auth import get_tenant_context
from backend.app.dependencies.datasets import get_dataset_import_service
from backend.app.models import (
    Base,
    Company,
    CompanyModule,
    CompanyModuleStatus,
    ModelRegistry,
    Module,
)
from backend.app.repositories import SQLAlchemyModuleEntitlements
from backend.app.services.artifact_service import ArtifactService
from backend.app.services.dataset_import_service import DatasetImportService
from backend.app.services.data_import_policy import DataImportPolicy
from backend.main import create_application
from modules.entitlements import ModuleAccessService
from shared.ai_engine.contracts import TenantContext
from tests.subscription_helpers import add_active_subscription


def _build_csv(seed: int = 0) -> bytes:
    rows = ["id,age,segment,is_bad_review"]
    for i in range(30):
        age = 20 + ((i + seed) % 40)
        segment = "A" if i % 2 == 0 else "B"
        label = 1 if i % 3 == 0 else 0
        rows.append(f"{i},{age},{segment},{label}")
    return ("\n".join(rows) + "\n").encode("utf-8")


CSV_CONTENT = _build_csv()


@pytest.fixture
def training_environment(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'training.db'}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with session_factory() as session:
        company = Company(
            name="Acme",
            slug="acme",
            email="acme@example.ca",
            country="Canada",
            timezone="America/Toronto",
            industry="Retail",
            subscription_plan="professional",
        )
        module = Module(name="RetailSenseAI", code="retail", is_active=True)
        session.add_all([company, module])
        session.flush()
        session.add(
            CompanyModule(
                company_id=company.id,
                module_id=module.id,
                activated_at=datetime.now(timezone.utc) - timedelta(minutes=1),
                status=CompanyModuleStatus.ACTIVE,
            )
        )
        add_active_subscription(session, company)
        session.commit()
        tenant = TenantContext(company.id)

    artifact_root = tmp_path / "artifacts"
    model_root = tmp_path / "models"
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
    app.dependency_overrides[get_tenant_context] = lambda: tenant
    app.dependency_overrides[get_dataset_import_service] = override_dataset_service
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    app.dependency_overrides[get_model_registry_root] = lambda: model_root

    with TestClient(app) as client:
        yield client, session_factory, tenant, model_root


def test_upload_creates_a_first_version_automatically(training_environment) -> None:
    """Aucun bouton : l'upload seul crÃ©e dÃ©jÃ  automatiquement la premiÃ¨re version."""

    client, _session_factory, _tenant, _model_root = training_environment

    upload_response = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("reviews_v1.csv", CSV_CONTENT, "text/csv")},
    )
    assert upload_response.status_code == 201

    list_response = client.get(
        "/internal/versioning/versions",
        params={"module_code": "retail", "task_code": "bad_review"},
    )
    assert list_response.status_code == 200
    versions = list_response.json()["versions"]
    assert len(versions) == 1
    assert versions[0]["version_number"] == 1
    assert versions[0]["is_active"] is True
    assert versions[0]["parent_version"] is None
    assert versions[0]["retraining_reason"] is None


def test_retraining_creates_a_second_version_with_lineage(training_environment) -> None:
    """Un rÃ©-entraÃ®nement autonome crÃ©e une deuxiÃ¨me version rattachÃ©e Ã  la premiÃ¨re."""

    client, _session_factory, _tenant, _model_root = training_environment

    client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("reviews_v1.csv", CSV_CONTENT, "text/csv")},
    )
    first_version = client.get(
        "/internal/versioning/versions",
        params={"module_code": "retail", "task_code": "bad_review"},
    ).json()["versions"][0]["version"]

    check_response = client.post(
        "/internal/retraining/check",
        json={"module_code": "retail", "task_code": "bad_review"},
    )
    assert check_response.status_code == 200
    assert check_response.json()["queued"] is True

    list_response = client.get(
        "/internal/versioning/versions",
        params={"module_code": "retail", "task_code": "bad_review"},
    )
    versions = list_response.json()["versions"]
    assert len(versions) == 2
    assert versions[0]["version_number"] == 1
    assert versions[1]["version_number"] == 2
    assert versions[1]["parent_version"] == first_version
    assert versions[1]["retraining_reason"] == "auto_retraining"
    # Comportement Phase 8 prÃ©servÃ© : le candidat (donnÃ©es identiques) est activÃ©.
    assert versions[1]["is_active"] is True
    assert versions[0]["is_active"] is False


def test_compare_versions_delegates_to_existing_comparison_engine(training_environment) -> None:
    """La comparaison ne recalcule rien : elle rÃ©utilise les mÃ©triques dÃ©jÃ  capturÃ©es."""

    client, _session_factory, _tenant, _model_root = training_environment

    client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("reviews_v1.csv", CSV_CONTENT, "text/csv")},
    )
    client.post(
        "/internal/retraining/check",
        json={"module_code": "retail", "task_code": "bad_review"},
    )
    versions = client.get(
        "/internal/versioning/versions",
        params={"module_code": "retail", "task_code": "bad_review"},
    ).json()["versions"]
    version_a, version_b = versions[0]["version"], versions[1]["version"]

    compare_response = client.post(
        "/internal/versioning/compare",
        json={
            "module_code": "retail",
            "task_code": "bad_review",
            "version_a": version_a,
            "version_b": version_b,
        },
    )
    assert compare_response.status_code == 200
    body = compare_response.json()
    assert body["version_a"] == version_a
    assert body["version_b"] == version_b
    assert isinstance(body["b_is_better"], bool)


def test_compare_missing_version_returns_404(training_environment) -> None:
    client, _session_factory, _tenant, _model_root = training_environment

    client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("reviews_v1.csv", CSV_CONTENT, "text/csv")},
    )
    version = client.get(
        "/internal/versioning/versions",
        params={"module_code": "retail", "task_code": "bad_review"},
    ).json()["versions"][0]["version"]

    response = client.post(
        "/internal/versioning/compare",
        json={
            "module_code": "retail",
            "task_code": "bad_review",
            "version_a": version,
            "version_b": "does-not-exist",
        },
    )
    assert response.status_code == 404


def test_rollback_restores_previous_version_without_retraining(training_environment) -> None:
    """Le rollback ne fait que changer la version active â€” aucun rÃ©entraÃ®nement,
    aucune version supprimÃ©e, et la base de donnÃ©es reste synchronisÃ©e."""

    client, session_factory, tenant, _model_root = training_environment

    client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("reviews_v1.csv", CSV_CONTENT, "text/csv")},
    )
    client.post(
        "/internal/retraining/check",
        json={"module_code": "retail", "task_code": "bad_review"},
    )
    versions = client.get(
        "/internal/versioning/versions",
        params={"module_code": "retail", "task_code": "bad_review"},
    ).json()["versions"]
    first_version, second_version = versions[0]["version"], versions[1]["version"]
    assert versions[1]["is_active"] is True

    rollback_response = client.post(
        "/internal/versioning/rollback",
        json={
            "module_code": "retail",
            "task_code": "bad_review",
            "target_version": first_version,
        },
    )
    assert rollback_response.status_code == 200
    body = rollback_response.json()
    assert body["previous_active_version"] == second_version
    assert body["target_version"] == first_version
    assert body["activated"] is True

    versions_after = client.get(
        "/internal/versioning/versions",
        params={"module_code": "retail", "task_code": "bad_review"},
    ).json()["versions"]
    # Aucune version supprimÃ©e â€” toujours 2 versions prÃ©sentes.
    assert len(versions_after) == 2
    by_version = {v["version"]: v for v in versions_after}
    assert by_version[first_version]["is_active"] is True
    assert by_version[second_version]["is_active"] is False

    with session_factory() as session:
        rows = session.scalars(
            select(ModelRegistry).where(
                ModelRegistry.company_id == tenant.company_id,
                # Le dataset (colonne numÃ©rique "age") dÃ©clenche aussi la
                # tÃ¢che indÃ©pendante "segmentation" depuis la Phase 19 : on
                # ne compte ici que les lignes de la tÃ¢che testÃ©e ("bad_review").
                ModelRegistry.task_code == "bad_review",
            )
        ).all()
    active_rows = [row for row in rows if row.is_active]
    assert len(active_rows) == 1
    assert active_rows[0].version == first_version


def test_rollback_missing_version_returns_404(training_environment) -> None:
    client, _session_factory, _tenant, _model_root = training_environment

    client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("reviews_v1.csv", CSV_CONTENT, "text/csv")},
    )

    response = client.post(
        "/internal/versioning/rollback",
        json={
            "module_code": "retail",
            "task_code": "bad_review",
            "target_version": "does-not-exist",
        },
    )
    assert response.status_code == 404

