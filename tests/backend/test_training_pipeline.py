"""Vérifie le pipeline complet : upload -> entraînement automatique -> prédiction.

Aucun bouton "Train Model" n'est appelé ici : l'entraînement démarre tout
seul après l'upload, exactement comme en production. Le test vérifie aussi
qu'aucun terme technique (métriques, algorithmes) ne fuite dans les réponses
HTTP exposées au frontend.
"""

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
    AIJob,
    Base,
    Company,
    CompanyModule,
    CompanyModuleStatus,
    JobStatus,
    Module,
    ModelRegistry,
    TrainingJob,
)
from backend.app.repositories import SQLAlchemyModuleEntitlements
from backend.app.services.artifact_service import ArtifactService
from backend.app.services.dataset_import_service import DatasetImportService
from backend.main import create_application
from modules.entitlements import ModuleAccessService
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.drift.serializer import load_baseline, load_drift_report
from shared.ai_engine.drift.types import DriftSeverity
from shared.ai_engine.explainability.serializer import load_explanation
from shared.ai_engine.explainability.types import ExplanationArtifact
from shared.ai_engine.model_registry.serializer import JoblibArtifactSerializer
from shared.ai_engine.registry.registry import ModelRegistry as AIModelRegistry


def _build_csv() -> bytes:
    rows = ["id,age,segment,is_bad_review"]
    for i in range(30):
        age = 20 + (i % 40)
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
                access=ModuleAccessService(SQLAlchemyModuleEntitlements(session)),
                max_upload_bytes=1024 * 1024,
            )

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_tenant_context] = lambda: tenant
    app.dependency_overrides[get_dataset_import_service] = override_dataset_service
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    app.dependency_overrides[get_model_registry_root] = lambda: model_root

    with TestClient(app) as client:
        yield client, session_factory, tenant, model_root


def test_upload_triggers_automatic_training_and_prediction(training_environment) -> None:
    client, session_factory, tenant, model_root = training_environment

    response = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("reviews.csv", CSV_CONTENT, "text/csv")},
    )
    assert response.status_code == 201

    with session_factory() as session:
        ai_job = session.scalar(select(AIJob).where(AIJob.company_id == tenant.company_id))
        training_job = session.scalar(
            select(TrainingJob).where(TrainingJob.company_id == tenant.company_id)
        )
        model_registry_row = session.scalar(
            select(ModelRegistry).where(
                ModelRegistry.company_id == tenant.company_id,
                # Le dataset (colonne numérique "age") déclenche aussi la
                # tâche indépendante "segmentation" depuis la Phase 19 : on ne
                # regarde ici que la tâche testée ("bad_review").
                ModelRegistry.task_code == "bad_review",
            )
        )

    assert ai_job is not None
    assert ai_job.status == JobStatus.COMPLETED
    assert training_job is not None
    assert training_job.status == JobStatus.COMPLETED
    assert model_registry_row is not None
    assert model_registry_row.is_active is True

    # L'explication (Phase 6 — XAI) est enregistrée dans le ModelRegistry existant,
    # à côté du modèle versionné — jamais exposée par une réponse HTTP.
    ai_registry = AIModelRegistry(root=model_root, serializer=JoblibArtifactSerializer())
    explanation = load_explanation(
        ai_registry, tenant, "retail", "bad_review", model_registry_row.version
    )
    assert isinstance(explanation, ExplanationArtifact)
    assert explanation.global_importance

    status_response = client.get(f"/api/v1/training-jobs/{ai_job.id}")
    assert status_response.status_code == 200
    body = status_response.json()
    assert body["ready"] is True
    assert body["message"] == "Your AI workspace is ready."
    forbidden_terms = (
        "accuracy",
        "precision",
        "recall",
        "f1",
        "gridsearchcv",
        "randomforest",
        "algorithm",
        "hyperparameter",
        "shap",
        "feature importance",
        "permutation importance",
        "explanation",
        "drift",
        "psi",
        "kolmogorov",
        "wasserstein",
        "jensen-shannon",
        "chi-square",
        "divergence",
        "baseline",
    )
    # `ready`/`message` sont les seuls champs destinés au frontend — `ai_job_id`
    # est un UUID aléatoire qui peut accidentellement contenir un des termes
    # interdits (ex. "f1" en sous-chaîne hexadécimale) sans rapport avec une
    # fuite technique réelle : on ne vérifie donc que le message métier ici.
    rendered = body["message"].lower()
    for forbidden in forbidden_terms:
        assert forbidden not in rendered

    prediction_response = client.post(
        "/api/v1/predict",
        json={
            "module_code": "retail",
            "task_code": "bad_review",
            "features": {"id": 999, "age": 33, "segment": "A"},
        },
    )
    assert prediction_response.status_code == 200
    prediction_body = prediction_response.json()
    assert "result" in prediction_body
    rendered_prediction = str(prediction_body).lower()
    for forbidden in forbidden_terms:
        assert forbidden not in rendered_prediction


def test_second_training_run_persists_drift_report_against_previous_model(
    training_environment,
) -> None:
    """Phase 7 — un ré-entraînement (nouvel upload) doit comparer les nouvelles
    données à la baseline du modèle précédemment actif, et persister le
    `DriftReport` obtenu — jamais exposé par une réponse HTTP."""

    client, session_factory, tenant, model_root = training_environment

    first_response = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("reviews_v1.csv", CSV_CONTENT, "text/csv")},
    )
    assert first_response.status_code == 201

    with session_factory() as session:
        first_registry_row = session.scalar(
            select(ModelRegistry).where(
                ModelRegistry.company_id == tenant.company_id,
                ModelRegistry.task_code == "bad_review",
            )
        )
    assert first_registry_row is not None
    first_version = first_registry_row.version

    second_response = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("reviews_v2.csv", CSV_CONTENT, "text/csv")},
    )
    assert second_response.status_code == 201

    with session_factory() as session:
        second_registry_row = session.scalar(
            select(ModelRegistry)
            .where(
                ModelRegistry.company_id == tenant.company_id,
                ModelRegistry.task_code == "bad_review",
            )
            .order_by(ModelRegistry.created_at.desc())
        )
    assert second_registry_row is not None
    second_version = second_registry_row.version
    assert second_version != first_version
    assert second_registry_row.is_active is True

    ai_registry = AIModelRegistry(root=model_root, serializer=JoblibArtifactSerializer())
    report = load_drift_report(ai_registry, tenant, "retail", "bad_review", second_version)
    assert report.model_name
    assert report.data_drift is not None
    assert report.overall_severity in (
        DriftSeverity.NONE,
        DriftSeverity.WARNING,
        DriftSeverity.CRITICAL,
    )

    # La baseline de la version qui vient d'être activée est disponible pour
    # comparer le PROCHAIN ré-entraînement.
    baseline = load_baseline(ai_registry, tenant, "retail", "bad_review", second_version)
    assert baseline.model_name

    # Aucun terme technique de drift ne doit fuiter dans une réponse HTTP.
    with session_factory() as session:
        second_training_job = session.get(TrainingJob, second_registry_row.training_job_id)
        ai_job_id = second_training_job.ai_job_id

    status_response = client.get(f"/api/v1/training-jobs/{ai_job_id}")
    forbidden_terms = ("drift", "psi", "kolmogorov", "wasserstein", "divergence", "baseline")
    rendered = status_response.json()["message"].lower()
    for forbidden in forbidden_terms:
        assert forbidden not in rendered


def test_upload_skips_dispatch_for_module_without_training_spec(training_environment) -> None:
    client, session_factory, tenant, model_root = training_environment

    with session_factory() as session:
        module = Module(name="AccountingAI", code="accounting", is_active=True)
        session.add(module)
        session.flush()
        session.add(
            CompanyModule(
                company_id=tenant.company_id,
                module_id=module.id,
                activated_at=datetime.now(timezone.utc) - timedelta(minutes=1),
                status=CompanyModuleStatus.ACTIVE,
            )
        )
        session.commit()

    response = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "accounting"},
        files={"file": ("ledger.csv", CSV_CONTENT, "text/csv")},
    )
    assert response.status_code == 201

    with session_factory() as session:
        ai_job = session.scalar(select(AIJob).where(AIJob.company_id == tenant.company_id))
    assert ai_job is None
