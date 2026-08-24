"""Phase 21 — RetailSenseAI : runtime multi-tenant de bout en bout.

Ces tests prouvent, à travers le pipeline de production réel (upload CSV ->
`TaskResolutionService` -> `TrainingDispatcher` -> `TrainingService` ->
`ModelRegistry` -> `PredictionService` -> `PredictionRuntime` ->
`BusinessDecisionService`), que :

- la nouvelle capacité "churn" (Phase 21) est réellement câblée, en
  réutilisant tel quel `ClassificationTrainingSpec` (même moteur que
  "bad_review", aucun nouveau moteur ML) ;
- deux entreprises fictives ("company_A", "company_B") obtiennent des modèles
  totalement indépendants sur le même `task_code`, jamais partagés, jamais
  mélangés (isolation multi-tenant de bout en bout) ;
- `/predict/decision` renvoie un résultat 100% métier (titre, impact,
  recommandation, priorité), sans jamais exposer de nom de modèle,
  d'algorithme ni de métrique technique.

Aucune logique Olist : tous les datasets ci-dessous sont génériques et
fictifs (clients/abonnements imaginaires).
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

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

_FORBIDDEN_ML_TERMS = (
    "random forest",
    "xgboost",
    "gridsearch",
    "accuracy",
    "roc auc",
    "f1",
    "hyperparameter",
    "ai engine",
    "model registry",
    "pipeline",
    "classifier",
    "sklearn",
    ".joblib",
)


def _churn_csv(company_bias: int) -> bytes:
    """Colonnes customer_id/tenure/monthly_spend/churn : capacité "churn"
    (classification, même moteur que "bad_review") uniquement."""

    rows = ["customer_id,tenure,monthly_spend,churn"]
    for i in range(24):
        tenure = i + 1
        monthly_spend = round(20 + i * 1.5 + company_bias, 2)
        churn = 1 if (i + company_bias) % 4 == 0 else 0
        rows.append(f"C{i},{tenure},{monthly_spend},{churn}")
    return ("\n".join(rows) + "\n").encode("utf-8")


@pytest.fixture
def phase21_environment(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'phase21.db'}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    def _create_company(name: str) -> TenantContext:
        with session_factory() as session:
            company = Company(
                name=name,
                slug=name.lower().replace(" ", "-") + f"-{uuid4().hex[:6]}",
                email=f"{name.lower().replace(' ', '')}@example.ca",
                country="Canada",
                timezone="America/Toronto",
                industry="Retail",
                subscription_plan="professional",
            )
            module = session.scalar(select(Module).where(Module.code == "retail"))
            if module is None:
                module = Module(name="RetailSenseAI", code="retail", is_active=True)
                session.add(module)
                session.flush()
            session.add(company)
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
            return TenantContext(company.id)

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
    app.dependency_overrides[get_dataset_import_service] = override_dataset_service
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    app.dependency_overrides[get_model_registry_root] = lambda: model_root

    default_tenant = _create_company("Default Co")
    app.dependency_overrides[get_tenant_context] = lambda: default_tenant

    with TestClient(app) as client:
        yield client, session_factory, model_root, app, _create_company


def _set_tenant(app, tenant: TenantContext) -> None:
    app.dependency_overrides[get_tenant_context] = lambda: tenant


def _registry_rows(session_factory, company_id) -> list[ModelRegistry]:
    with session_factory() as session:
        return list(
            session.scalars(
                select(ModelRegistry).where(ModelRegistry.company_id == company_id)
            ).all()
        )


def _assert_no_ml_jargon(payload: dict) -> None:
    text = " ".join(str(value) for value in payload.values()).lower()
    for term in _FORBIDDEN_ML_TERMS:
        assert term not in text, f"Jargon ML détecté ({term!r}) dans {payload!r}"


def test_churn_task_is_executable_end_to_end(phase21_environment) -> None:
    """Upload -> détection -> entraînement -> registre pour la nouvelle tâche "churn"."""

    client, session_factory, _model_root, app, create_company = phase21_environment
    tenant = create_company("Company A")
    _set_tenant(app, tenant)

    response = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("customers.csv", _churn_csv(company_bias=0), "text/csv")},
    )
    assert response.status_code == 201

    by_task = {row.task_code: row for row in _registry_rows(session_factory, tenant.company_id)}
    assert "churn" in by_task
    assert by_task["churn"].model_type == "classification"
    assert by_task["churn"].is_active is True


def test_two_companies_never_share_churn_models(phase21_environment) -> None:
    """company_A et company_B obtiennent des modèles "churn" totalement isolés."""

    client, session_factory, _model_root, app, create_company = phase21_environment

    company_a = create_company("Company A")
    company_b = create_company("Company B")

    _set_tenant(app, company_a)
    response_a = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("customers.csv", _churn_csv(company_bias=0), "text/csv")},
    )
    assert response_a.status_code == 201

    # company_B n'a encore rien entraîné : sa prédiction doit échouer proprement,
    # jamais réutiliser (même par accident) le modèle de company_A.
    _set_tenant(app, company_b)
    predict_before_training = client.post(
        "/api/v1/predict",
        json={
            "module_code": "retail",
            "task_code": "churn",
            "features": {"customer_id": "C0", "tenure": 5, "monthly_spend": 40.0},
        },
    )
    assert predict_before_training.status_code == 409

    _set_tenant(app, company_b)
    response_b = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("customers.csv", _churn_csv(company_bias=2), "text/csv")},
    )
    assert response_b.status_code == 201

    rows_a = {row.task_code: row for row in _registry_rows(session_factory, company_a.company_id)}
    rows_b = {row.task_code: row for row in _registry_rows(session_factory, company_b.company_id)}

    assert "churn" in rows_a and "churn" in rows_b
    # Chemins de stockage distincts : deux artefacts totalement séparés.
    assert rows_a["churn"].storage_path != rows_b["churn"].storage_path

    # Chaque tenant ne peut prédire qu'avec son propre modèle actif.
    _set_tenant(app, company_a)
    predict_a = client.post(
        "/api/v1/predict",
        json={
            "module_code": "retail",
            "task_code": "churn",
            "features": {"customer_id": "C0", "tenure": 5, "monthly_spend": 40.0},
        },
    )
    assert predict_a.status_code == 200

    _set_tenant(app, company_b)
    predict_b = client.post(
        "/api/v1/predict",
        json={
            "module_code": "retail",
            "task_code": "churn",
            "features": {"customer_id": "C0", "tenure": 5, "monthly_spend": 40.0},
        },
    )
    assert predict_b.status_code == 200


def test_predict_decision_returns_only_business_friendly_output(phase21_environment) -> None:
    """`/predict/decision` : jamais de jargon ML, uniquement titre/impact/priorité."""

    client, _session_factory, _model_root, app, create_company = phase21_environment
    tenant = create_company("Company A")
    _set_tenant(app, tenant)

    upload = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("customers.csv", _churn_csv(company_bias=0), "text/csv")},
    )
    assert upload.status_code == 201

    response = client.post(
        "/api/v1/predict/decision",
        json={
            "module_code": "retail",
            "task_code": "churn",
            "features": {"customer_id": "C0", "tenure": 5, "monthly_spend": 40.0},
        },
    )
    assert response.status_code == 200

    body = response.json()
    assert set(body.keys()) == {"title", "impact", "recommendation", "priority"}
    assert body["title"]
    assert body["impact"]
    assert body["recommendation"]
    assert body["priority"] in {"low", "medium", "high", "critical"}
    _assert_no_ml_jargon(body)


def test_predict_decision_is_isolated_between_companies(phase21_environment) -> None:
    """Deux entreprises entraînées indépendamment reçoivent des décisions
    métier indépendantes : jamais le modèle/la décision de l'une chez l'autre."""

    client, _session_factory, _model_root, app, create_company = phase21_environment

    company_a = create_company("Company A")
    company_b = create_company("Company B")

    _set_tenant(app, company_a)
    client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("customers.csv", _churn_csv(company_bias=0), "text/csv")},
    )

    # company_B n'a jamais entraîné "churn" : la décision métier doit échouer
    # proprement (409), jamais retourner silencieusement le résultat de A.
    _set_tenant(app, company_b)
    decision_before_training = client.post(
        "/api/v1/predict/decision",
        json={
            "module_code": "retail",
            "task_code": "churn",
            "features": {"customer_id": "C0", "tenure": 5, "monthly_spend": 40.0},
        },
    )
    assert decision_before_training.status_code == 409
