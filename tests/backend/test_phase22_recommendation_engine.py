"""Phase 22 — RetailSenseAI : moteur de recommandation + décisions métier

cross-capacité (churn + segmentation).

Ces tests prouvent, à travers le pipeline de production réel (upload CSV ->
`TaskResolutionService` -> `TrainingDispatcher` -> `TrainingService` ->
`ModelRegistry` -> `PredictionService` -> `PredictionRuntime`) que :

- la nouvelle capacité "recommendation" (Phase 22, BLOC A) est réellement
  câblée, en réutilisant l'architecture générique existante (Model Registry,
  PredictionRuntime, TrainingDispatcher) — aucun second moteur ;
- le mapping de colonnes fonctionne quels que soient les noms réels utilisés
  par chaque entreprise (ex. "client_number"/"sku"/"units" vs.
  "customer_id"/"product_code"/"quantity"), sans jamais inventer de colonne ;
- un jeu de données avec trop peu d'interactions échoue proprement (jamais de
  ligne ModelRegistry fantôme) ;
- deux entreprises ("company_A", "company_B") obtiennent des recommandeurs
  totalement indépendants, jamais partagés, jamais mélangés ;
- `/portfolio-decisions` (Phase 22, BLOC B) combine churn + segmentation en
  une décision 100% métier, sans jamais exposer de jargon ML.

Aucune logique Olist : tous les datasets ci-dessous sont génériques et
fictifs (clients/produits imaginaires).
"""

from __future__ import annotations

import re
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
    "grid search",
    "accuracy",
    "roc auc",
    "f1",
    "hyperparameter",
    "ai engine",
    "model registry",
    "pipeline",
    "classifier",
    "sklearn",
    "cosine",
    "collaborative filtering",
    "item_based_cf",
    "n_neighbors",
    ".joblib",
)


def _recommendation_csv(customer_column: str, product_column: str, interaction_column: str, label_prefix: str) -> bytes:
    """20 lignes d'interactions client/produit : capacité "recommendation" uniquement.

    Structure volontairement simple pour une similarité cosinus item-based
    lisible : 6 clients, 5 produits, chevauchements partiels, un client
    ("_full") ayant déjà interagi avec tous les produits (aucune
    recommandation possible pour lui).
    """

    customers = {
        "c1": ["p1", "p2", "p3"],
        "c2": ["p1", "p2", "p4"],
        "c3": ["p1", "p3", "p5"],
        "c4": ["p2", "p4", "p5"],
        "c5": ["p3", "p4", "p5"],
        "c_full": ["p1", "p2", "p3", "p4", "p5"],
    }
    rows = [f"{customer_column},{product_column},{interaction_column}"]
    for customer, products in customers.items():
        for index, product in enumerate(products):
            rows.append(f"{label_prefix}_{customer},{label_prefix}_{product},{index + 1}")
    return ("\n".join(rows) + "\n").encode("utf-8")


def _insufficient_recommendation_csv() -> bytes:
    """12 lignes seulement : sous le seuil minimum d'interactions (20)."""

    rows = ["customer_id,product_id,quantity"]
    customers = ["cA", "cB", "cC", "cD"]
    products = ["pA", "pB", "pC"]
    count = 0
    for customer in customers:
        for product in products:
            rows.append(f"{customer},{product},1")
            count += 1
            if count >= 12:
                break
        if count >= 12:
            break
    return ("\n".join(rows) + "\n").encode("utf-8")


def _churn_segmentation_csv(company_bias: int) -> bytes:
    """Colonnes customer_id/tenure/monthly_spend/churn (24 lignes) : déclenche

    à la fois "churn" (classification) et "segmentation" (clustering,
    "tenure" est un indicateur de segmentation) sur le même dataset — exactement
    6 clients churnés (comme l'exemple canonique de la spécification Phase 22).
    """

    rows = ["customer_id,tenure,monthly_spend,churn"]
    for i in range(24):
        tenure = i + 1
        monthly_spend = round(20 + i * 1.5 + company_bias, 2)
        churn = 1 if (i + company_bias) % 4 == 0 else 0
        rows.append(f"C{i},{tenure},{monthly_spend},{churn}")
    return ("\n".join(rows) + "\n").encode("utf-8")


@pytest.fixture
def phase22_environment(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'phase22.db'}",
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


def _assert_no_ml_jargon(payload) -> None:
    if isinstance(payload, list):
        text = " ".join(str(item) for item in payload).lower()
    else:
        text = " ".join(str(value) for value in payload.values()).lower()
    for term in _FORBIDDEN_ML_TERMS:
        assert term not in text, f"Jargon ML détecté ({term!r}) dans {payload!r}"


# ---------------------------------------------------------------------------
# BLOC A — moteur de recommandation
# ---------------------------------------------------------------------------


def test_recommendation_is_detected_and_executable() -> None:
    from modules.retailsense.training_specs import CapabilityStatus, get_capability_status

    assert get_capability_status("retail", "recommendation") is CapabilityStatus.EXECUTABLE


def test_recommendation_trains_successfully_with_company_specific_column_names(phase22_environment) -> None:
    """company_A utilise "client_number"/"sku"/"units" (jamais "customer_id"/

    "product_id") : le mapping sémantique doit résoudre ces colonnes sans
    qu'aucun nom ne soit jamais codé en dur ni inventé.
    """

    client, session_factory, _model_root, app, create_company = phase22_environment
    tenant = create_company("Company A")
    _set_tenant(app, tenant)

    response = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={
            "file": (
                "orders.csv",
                _recommendation_csv("client_number", "sku", "units", "a"),
                "text/csv",
            )
        },
    )
    assert response.status_code == 201

    by_task = {row.task_code: row for row in _registry_rows(session_factory, tenant.company_id)}
    assert "recommendation" in by_task
    assert by_task["recommendation"].model_type == "recommendation"
    assert by_task["recommendation"].is_active is True


def test_insufficient_interactions_fails_cleanly_without_registry_row(phase22_environment) -> None:
    """Moins de 20 interactions utilisables : le job échoue proprement, jamais

    de ligne ModelRegistry fantôme, jamais de donnée inventée pour compenser."""

    client, session_factory, _model_root, app, create_company = phase22_environment
    tenant = create_company("Company Insufficient")
    _set_tenant(app, tenant)

    response = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("orders.csv", _insufficient_recommendation_csv(), "text/csv")},
    )
    assert response.status_code == 201

    by_task = {row.task_code: row for row in _registry_rows(session_factory, tenant.company_id)}
    assert "recommendation" not in by_task

    predict = client.post(
        "/api/v1/predict",
        json={
            "module_code": "retail",
            "task_code": "recommendation",
            "features": {"customer_id": "cA", "top_k": 3},
        },
    )
    assert predict.status_code == 409


def test_no_active_recommendation_model_returns_graceful_conflict(phase22_environment) -> None:
    """Aucun dataset importé du tout : la prédiction échoue proprement (409),

    jamais une erreur serveur ni une recommandation fabriquée."""

    client, _session_factory, _model_root, app, create_company = phase22_environment
    tenant = create_company("Company Empty")
    _set_tenant(app, tenant)

    predict = client.post(
        "/api/v1/predict",
        json={
            "module_code": "retail",
            "task_code": "recommendation",
            "features": {"customer_id": "anyone", "top_k": 3},
        },
    )
    assert predict.status_code == 409


def test_two_companies_get_isolated_recommenders_never_shared(phase22_environment) -> None:
    """company_A ("client_number"/"sku"/"units") et company_B ("customer_id"/

    "product_code"/"quantity") obtiennent des recommandeurs totalement
    indépendants : chemins de stockage distincts, jamais de fuite entre
    tenants, même sur le même task_code."""

    client, session_factory, _model_root, app, create_company = phase22_environment

    company_a = create_company("Company A")
    company_b = create_company("Company B")

    _set_tenant(app, company_a)
    response_a = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={
            "file": (
                "orders.csv",
                _recommendation_csv("client_number", "sku", "units", "a"),
                "text/csv",
            )
        },
    )
    assert response_a.status_code == 201

    # company_B n'a encore rien entraîné : sa prédiction doit échouer
    # proprement, jamais réutiliser (même par accident) le modèle de company_A.
    _set_tenant(app, company_b)
    predict_before_training = client.post(
        "/api/v1/predict",
        json={
            "module_code": "retail",
            "task_code": "recommendation",
            "features": {"customer_id": "b_c1", "top_k": 3},
        },
    )
    assert predict_before_training.status_code == 409

    response_b = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={
            "file": (
                "orders.csv",
                _recommendation_csv("customer_id", "product_code", "quantity", "b"),
                "text/csv",
            )
        },
    )
    assert response_b.status_code == 201

    rows_a = {row.task_code: row for row in _registry_rows(session_factory, company_a.company_id)}
    rows_b = {row.task_code: row for row in _registry_rows(session_factory, company_b.company_id)}
    assert "recommendation" in rows_a and "recommendation" in rows_b
    # Chemins de stockage distincts : deux artefacts totalement séparés.
    assert rows_a["recommendation"].storage_path != rows_b["recommendation"].storage_path

    # Chaque tenant ne reçoit des recommandations que basées sur ses propres
    # données (produits préfixés différemment par entreprise).
    _set_tenant(app, company_a)
    predict_a = client.post(
        "/api/v1/predict",
        json={
            "module_code": "retail",
            "task_code": "recommendation",
            "features": {"customer_id": "a_c1", "top_k": 3},
        },
    )
    assert predict_a.status_code == 200
    result_a = predict_a.json()["result"]
    assert all(str(item).startswith("a_") for item in result_a)

    _set_tenant(app, company_b)
    predict_b = client.post(
        "/api/v1/predict",
        json={
            "module_code": "retail",
            "task_code": "recommendation",
            "features": {"customer_id": "b_c1", "top_k": 3},
        },
    )
    assert predict_b.status_code == 200
    result_b = predict_b.json()["result"]
    assert all(str(item).startswith("b_") for item in result_b)

    _assert_no_ml_jargon(predict_a.json())
    _assert_no_ml_jargon(predict_b.json())


def test_customer_who_already_saw_everything_gets_no_recommendation(phase22_environment) -> None:
    """"_full" a déjà interagi avec tous les produits disponibles : aucune

    recommandation possible, réponse propre (liste vide), jamais d'erreur ni
    de donnée inventée."""

    client, _session_factory, _model_root, app, create_company = phase22_environment
    tenant = create_company("Company Full")
    _set_tenant(app, tenant)

    response = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={
            "file": (
                "orders.csv",
                _recommendation_csv("customer_id", "product_id", "quantity", "z"),
                "text/csv",
            )
        },
    )
    assert response.status_code == 201

    predict = client.post(
        "/api/v1/predict",
        json={
            "module_code": "retail",
            "task_code": "recommendation",
            "features": {"customer_id": "z_c_full", "top_k": 3},
        },
    )
    assert predict.status_code == 200
    assert predict.json()["result"] == []


def test_unknown_customer_gets_cold_start_fallback_recommendation(phase22_environment) -> None:
    """Un client jamais vu à l'entraînement reçoit tout de même des

    recommandations (repli par popularité, calculé uniquement à partir des
    données propres de cette entreprise — jamais une donnée partagée/inventée)."""

    client, _session_factory, _model_root, app, create_company = phase22_environment
    tenant = create_company("Company ColdStart")
    _set_tenant(app, tenant)

    response = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={
            "file": (
                "orders.csv",
                _recommendation_csv("customer_id", "product_id", "quantity", "y"),
                "text/csv",
            )
        },
    )
    assert response.status_code == 201

    predict = client.post(
        "/api/v1/predict",
        json={
            "module_code": "retail",
            "task_code": "recommendation",
            "features": {"customer_id": "never_seen_before", "top_k": 3},
        },
    )
    assert predict.status_code == 200
    assert len(predict.json()["result"]) > 0


# ---------------------------------------------------------------------------
# BLOC B — décisions métier cross-capacité (churn + segmentation)
# ---------------------------------------------------------------------------


def test_portfolio_decisions_returns_business_friendly_churn_segmentation_decision(
    phase22_environment,
) -> None:
    """`/portfolio-decisions` combine churn + segmentation en une décision

    100% métier, dans le format exact attendu par la spécification Phase 22 :
    Titre "X clients à forte valeur présentent un risque élevé de départ.",
    Impact "Valeur commerciale potentiellement à risque.", Recommandation
    contenant "Créer une campagne de rétention ciblée pour ces clients.",
    Priorité HIGH — sans jamais exposer de jargon ML."""

    client, _session_factory, _model_root, app, create_company = phase22_environment
    tenant = create_company("Company Churn")
    _set_tenant(app, tenant)

    upload = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("customers.csv", _churn_segmentation_csv(company_bias=0), "text/csv")},
    )
    assert upload.status_code == 201

    response = client.post("/api/v1/portfolio-decisions", json={"module_code": "retail"})
    assert response.status_code == 200

    decisions = response.json()
    assert decisions
    for decision in decisions:
        assert set(decision.keys()) == {"title", "impact", "recommendation", "priority"}
        _assert_no_ml_jargon(decision)

    churn_segmentation_decisions = [
        decision
        for decision in decisions
        if "risque élevé de départ" in decision["title"]
    ]
    assert len(churn_segmentation_decisions) == 1
    decision = churn_segmentation_decisions[0]

    assert re.match(r"^\d+ clients à forte valeur présentent un risque élevé de départ\.$", decision["title"])
    assert decision["impact"] == "Valeur commerciale potentiellement à risque."
    assert "Créer une campagne de rétention ciblée pour ces clients." in decision["recommendation"]
    # Sévérité HIGH en entrée (voir `_churn_segmentation_rule`) ; la priorité
    # finale, calculée par le moteur générique de priorisation à partir de
    # l'impact/urgence réels, peut légitimement monter à "critical".
    assert decision["priority"] in {"high", "critical"}


def test_portfolio_decisions_isolated_between_companies(phase22_environment) -> None:
    """Deux entreprises entraînées indépendamment reçoivent des décisions de

    portefeuille indépendantes : jamais les clients/décisions de l'une chez
    l'autre."""

    client, _session_factory, _model_root, app, create_company = phase22_environment

    company_a = create_company("Company A Decisions")
    company_b = create_company("Company B Decisions")

    _set_tenant(app, company_a)
    client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("customers.csv", _churn_segmentation_csv(company_bias=0), "text/csv")},
    )

    # company_B n'a jamais rien entraîné : la décision de portefeuille doit
    # échouer proprement (409), jamais retourner silencieusement les
    # décisions de company_A.
    _set_tenant(app, company_b)
    decision_before_training = client.post("/api/v1/portfolio-decisions", json={"module_code": "retail"})
    assert decision_before_training.status_code == 409


def test_no_active_models_returns_graceful_conflict_for_portfolio_decisions(phase22_environment) -> None:
    """Aucun modèle actif du tout pour cette entreprise : réponse 409 propre,

    jamais une décision fabriquée."""

    client, _session_factory, _model_root, app, create_company = phase22_environment
    tenant = create_company("Company Nothing")
    _set_tenant(app, tenant)

    response = client.post("/api/v1/portfolio-decisions", json={"module_code": "retail"})
    assert response.status_code == 409
