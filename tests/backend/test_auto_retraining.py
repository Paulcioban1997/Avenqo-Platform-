"""Phase 8 — Auto Retraining Enterprise : bout en bout via l'endpoint interne.

Aucun bouton "Train"/"Retrain" n'existe côté utilisateur : ces tests
appellent directement l'endpoint interne `/internal/retraining/check`, exactement
comme le ferait un CronJob Kubernetes ou une action d'exploitation manuelle.
Ils réutilisent l'environnement de test de `tests/backend/test_training_pipeline.py`.
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
        label = 1 if age >= 35 else 0
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


def test_retraining_check_without_prior_model_is_a_noop(training_environment) -> None:
    """Sans modèle actif, l'endpoint interne ne fait rien (le premier
    entraînement n'est pas piloté par cette couche)."""

    client, _session_factory, _tenant, _model_root = training_environment

    response = client.post(
        "/internal/retraining/check",
        json={"module_code": "retail", "task_code": "bad_review"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["queued"] is False
    assert body["ai_job_id"] is None


def test_manual_trigger_forces_retraining_and_activates_better_model(
    training_environment,
) -> None:
    """Un déclenchement manuel via l'API interne force une décision de
    ré-entraînement ; si le nouveau modèle n'est pas pire, il est activé et un
    nouvel enregistrement `ModelRegistry` apparaît."""

    client, session_factory, tenant, _model_root = training_environment

    upload_response = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("reviews_v1.csv", CSV_CONTENT, "text/csv")},
    )
    assert upload_response.status_code == 201

    with session_factory() as session:
        rows_before = session.scalars(
            select(ModelRegistry).where(
                ModelRegistry.company_id == tenant.company_id,
                # Le dataset (colonne numérique "age") déclenche aussi la
                # tâche indépendante "segmentation" depuis la Phase 19 : on
                # ne compte ici que les lignes de la tâche testée ("bad_review").
                ModelRegistry.task_code == "bad_review",
            )
        ).all()
    assert len(rows_before) == 1
    first_row = rows_before[0]
    assert first_row.is_active is True

    check_response = client.post(
        "/internal/retraining/check",
        json={"module_code": "retail", "task_code": "bad_review"},
    )
    assert check_response.status_code == 200
    check_body = check_response.json()
    assert check_body["queued"] is True
    assert check_body["ai_job_id"] is not None

    with session_factory() as session:
        rows_after = session.scalars(
            select(ModelRegistry)
            .where(
                ModelRegistry.company_id == tenant.company_id,
                ModelRegistry.task_code == "bad_review",
            )
            .order_by(ModelRegistry.created_at.asc())
        ).all()

    assert len(rows_after) == 2
    candidate_row = rows_after[1]
    # Le modèle candidat n'est ni meilleur ni pire que lui-même (mêmes
    # données) : la comparaison obligatoire l'active (delta == 0, tolérance
    # par défaut incluse) sans jamais activer un modèle strictement pire.
    assert candidate_row.is_active is True
    assert rows_after[0].is_active is False

    # Aucun terme technique/interne ne doit fuiter dans la réponse HTTP de
    # l'endpoint interne, au cas où il serait un jour exposé par erreur.
    forbidden_terms = ("retrain", "decision", "drift", "psi", "baseline", "accuracy", "r2")
    rendered = str(check_body).lower()
    for forbidden in forbidden_terms:
        assert forbidden not in rendered
