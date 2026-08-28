"""Phase 19 — RetailSenseAI : capacités étendues sur le runtime générique existant.

Ces tests prouvent, via le pipeline de production réel (upload -> schema
detection -> `TaskResolutionService` -> `TrainingDispatcher` ->
`TrainingService` -> `ModelRegistry`), que :

- "demand" (regression) et "customer_segmentation" (clustering) sont
  désormais réellement câblées, en réutilisant tel quel
  `RegressionTrainingSpec`/`ClusteringTrainingSpec` (aucun nouveau moteur) ;
- "anomaly_detection" (IsolationForest) est intégrée dans le `TrainingService`
  ACTIF, avec les mêmes conventions que classification/regression/clustering
  (jamais `shared/ai_engine/families/anomaly/`, moteur orphelin non branché) ;
- Phase 20 : "weekly_forecast" (forecasting temporel, backtesting réel, jamais
  de `train_test_split` aléatoire) est désormais réellement câblée ;
  "recommendation"/"sentiment_analysis" restent détectables par
  `TaskResolutionService` mais ne créent toujours jamais de job (aucune
  configuration dans `MODULE_TRAINING_SPECS`) ;
- "synthetic_data_generation" reste une capacité future, jamais détectée ;
- plusieurs tâches sur un même dataset restent des jobs/modèles indépendants,
  jamais fusionnés, jamais désactivés entre eux ;
- l'isolation multi-tenant est respectée (aucun modèle partagé entre
  entreprises) ;
- aucune logique Olist n'est utilisée par ce chemin ;
- aucun second AI Engine (`shared.ai_engine.core`/`shared.ai_engine.families`)
  n'est importé par le chemin d'entraînement actif.

Aucune logique Olist : tous les datasets ci-dessous sont génériques
(clients/commandes/anomalies fictifs), jamais liés à un jeu de données réel.
"""

from __future__ import annotations

import inspect
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
from backend.app.services.data_import_policy import DataImportPolicy
from backend.main import create_application
from modules.entitlements import ModuleAccessService
from modules.retailsense.training_specs import CapabilityStatus, get_capability_status
from shared.ai_engine.contracts import TenantContext
from tests.subscription_helpers import add_active_subscription
from shared.ai_engine.exceptions import ModelNotFoundError
from shared.ai_engine.model_registry.serializer import JoblibArtifactSerializer
from shared.ai_engine.registry.registry import ModelRegistry as AIModelRegistry
from shared.ai_engine.task_resolution.service import TaskResolutionService

import backend.app.services.training_dispatcher as training_dispatcher_module
import modules.retailsense.training_specs as training_specs_module
import shared.ai_engine.task_resolution.service as task_resolution_module
import shared.ai_engine.training.service as training_service_module


# ---------------------------------------------------------------------------
# Générateurs de datasets génériques (aucune logique Olist)
# ---------------------------------------------------------------------------


def _demand_and_price_csv() -> bytes:
    """Colonnes "price" et "quantity" : les deux tâches "price"/"demand"
    (même capacité "regression") doivent se déclencher indépendamment."""

    rows = ["customer_id,order_date,product_id,quantity,price"]
    for i in range(20):
        order_date = (datetime(2024, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d")
        product_id = f"P{i % 4}"
        quantity = i + 1
        price = round(12.5 + i * 0.85, 2)
        rows.append(f"C{i},{order_date},{product_id},{quantity},{price}")
    return ("\n".join(rows) + "\n").encode("utf-8")


def _segmentation_csv() -> bytes:
    """Colonnes RFM classiques (recency/frequency/monetary_value) : signal de
    segmentation uniquement, aucune autre capacité détectable."""

    rows = ["customer_id,recency,frequency,monetary_value"]
    for i in range(40):
        rows.append(f"C{i},{i},{i + 1},{round(50 + i * 2.5, 2)}")
    return ("\n".join(rows) + "\n").encode("utf-8")


def _anomaly_csv() -> bytes:
    """Signal numérique + colonne temporelle exacte ("timestamp") : capacité
    "anomaly_detection" uniquement (avec "forecasting", non câblé)."""

    outliers_response = {10: 520.0, 25: 610.0, 40: 495.0}
    outliers_latency = {10: 940.0, 25: 880.0, 40: 915.0}
    rows = ["timestamp,response_time,latency"]
    for i in range(60):
        response_time = outliers_response.get(i, round(100 + i * 0.5, 3))
        latency = outliers_latency.get(i, round(50 + i * 0.31, 3))
        rows.append(f"2024-01-{(i % 28) + 1:02d},{response_time},{latency}")
    return ("\n".join(rows) + "\n").encode("utf-8")


def _multi_capability_csv() -> bytes:
    """Schéma multi-capacité (mandaté explicitement) : customer_id, product_id,
    order_date, quantity, price, rating, review_text.

    Rend détectables : classification (fallback "rating"), regression
    ("price"/"quantity"), forecasting ("order_date" + numériques),
    recommendation (customer+product+rating), sentiment_analysis
    ("review_text"). Aucune donnée Olist.
    """

    rows = ["customer_id,product_id,order_date,quantity,price,rating,review_text"]
    for i in range(40):
        order_date = (datetime(2024, 1, 1) + timedelta(days=i % 28)).strftime("%Y-%m-%d")
        product_id = f"P{i % 6}"
        quantity = i + 1
        price = round(9.99 + i * 0.42, 2)
        rating = (i % 5) + 1
        review_text = (
            f"This product was great order number {i}"
            if i % 2 == 0
            else f"Not satisfied at all with this order {i}"
        )
        rows.append(f"C{i},{product_id},{order_date},{quantity},{price},{rating},{review_text}")
    return ("\n".join(rows) + "\n").encode("utf-8")


def _five_executable_tasks_csv() -> bytes:
    """Dataset générique qui satisfait les cinq capacités exécutables.

    Les signaux sont indépendants des noms d'un dataset scolaire : cible
    binaire, deux cibles continues, indicateurs RFM et mesures temporelles
    avec quelques valeurs atypiques.
    """

    rows = [
        "customer_id,product_id,timestamp,quantity,price,is_bad_review,"
        "recency,frequency,monetary_value,response_time,latency"
    ]
    outliers = {8: (520.0, 940.0), 24: (610.0, 880.0), 37: (495.0, 915.0)}
    for i in range(40):
        response_time, latency = outliers.get(
            i,
            (round(100 + i * 0.41, 3), round(50 + i * 0.29, 3)),
        )
        rows.append(
            f"C{i},P{i % 7},2024-01-{(i % 28) + 1:02d}T12:00:00,"
            f"{i + 1},{round(10 + i * 0.37, 2)},{1 if i % 4 == 0 else 0},"
            f"{i},{i + 1},{round(50 + i * 2.3, 2)},{response_time},{latency}"
        )
    return ("\n".join(rows) + "\n").encode("utf-8")


def _insufficient_csv() -> bytes:
    rows = ["id,name"]
    for i, name in enumerate(["Alice", "Bob", "Carol", "Diane", "Eve"]):
        rows.append(f"{i},{name}")
    return ("\n".join(rows) + "\n").encode("utf-8")


# ---------------------------------------------------------------------------
# Fixture d'environnement (même pattern que test_task_resolution_workflow.py)
# ---------------------------------------------------------------------------


@pytest.fixture
def phase19_environment(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'phase19.db'}",
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
            add_active_subscription(session, company)
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

    default_tenant = _create_company("Acme")
    app.dependency_overrides[get_tenant_context] = lambda: default_tenant

    with TestClient(app) as client:
        yield client, session_factory, default_tenant, model_root, app, _create_company


def _set_tenant(app, tenant: TenantContext) -> None:
    app.dependency_overrides[get_tenant_context] = lambda: tenant


def _registry_rows(session_factory, company_id) -> list[ModelRegistry]:
    with session_factory() as session:
        return list(
            session.scalars(
                select(ModelRegistry).where(ModelRegistry.company_id == company_id)
            ).all()
        )


def _ai_jobs(session_factory, company_id) -> list[AIJob]:
    with session_factory() as session:
        return list(
            session.scalars(select(AIJob).where(AIJob.company_id == company_id)).all()
        )


# ---------------------------------------------------------------------------
# 1 & 2 — bad_review / price continuent de fonctionner
# ---------------------------------------------------------------------------


def test_bad_review_and_price_still_work(phase19_environment) -> None:
    client, session_factory, tenant, _model_root, _app, _create_company = phase19_environment

    rows = ["customer_id,order_date,product_id,price,is_bad_review"]
    for i in range(20):
        order_date = (datetime(2024, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d")
        rows.append(f"C{i},{order_date},P{i % 3},{round(9.99 + i * 0.2, 2)},{1 if i % 4 == 0 else 0}")
    csv_bytes = ("\n".join(rows) + "\n").encode("utf-8")

    response = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("orders.csv", csv_bytes, "text/csv")},
    )
    assert response.status_code == 201

    registry_rows = _registry_rows(session_factory, tenant.company_id)
    by_task = {row.task_code: row for row in registry_rows}
    assert "price" in by_task and by_task["price"].model_type == "regression"
    assert "bad_review" in by_task and by_task["bad_review"].model_type == "classification"
    assert by_task["price"].is_active is True
    assert by_task["bad_review"].is_active is True


# ---------------------------------------------------------------------------
# 3 — demand déclenche regression, indépendamment de "price"
# ---------------------------------------------------------------------------


def test_demand_triggers_regression_independently_from_price(phase19_environment) -> None:
    client, session_factory, tenant, _model_root, _app, _create_company = phase19_environment

    response = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("orders.csv", _demand_and_price_csv(), "text/csv")},
    )
    assert response.status_code == 201

    ai_jobs = _ai_jobs(session_factory, tenant.company_id)
    assert {job.status for job in ai_jobs} == {JobStatus.COMPLETED}

    registry_rows = _registry_rows(session_factory, tenant.company_id)
    by_task = {row.task_code: row for row in registry_rows}
    # Phase 20 : "order_date" + "quantity" rendent aussi "weekly_forecast"
    # (forecasting) exécutable désormais, en plus de "price"/"demand". Phase 22 :
    # "customer_id"/"product_id"/"quantity" rendent aussi "recommendation"
    # exécutable (20 lignes >= seuil minimum d'interactions).
    assert set(by_task) == {"price", "demand", "weekly_forecast", "recommendation"}
    assert by_task["demand"].model_type == "regression"
    assert by_task["demand"].is_active is True
    assert by_task["price"].is_active is True
    assert by_task["weekly_forecast"].model_type == "forecasting"
    assert by_task["weekly_forecast"].is_active is True
    # Trois tâches indépendantes : trois versions distinctes, aucune fusion.
    assert by_task["demand"].version != by_task["price"].version


# ---------------------------------------------------------------------------
# 4 — customer_segmentation déclenche clustering
# ---------------------------------------------------------------------------


def test_customer_segmentation_triggers_clustering(phase19_environment) -> None:
    client, session_factory, tenant, _model_root, _app, _create_company = phase19_environment

    response = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("customers.csv", _segmentation_csv(), "text/csv")},
    )
    assert response.status_code == 201

    registry_rows = _registry_rows(session_factory, tenant.company_id)
    assert len(registry_rows) == 1
    assert registry_rows[0].task_code == "segmentation"
    assert registry_rows[0].model_type == "clustering"
    assert registry_rows[0].is_active is True


# ---------------------------------------------------------------------------
# 5 — anomaly_detection déclenche IsolationForest (runtime actif, jamais
# shared/ai_engine/families/anomaly/)
# ---------------------------------------------------------------------------


def test_anomaly_detection_triggers_isolation_forest(phase19_environment) -> None:
    client, session_factory, tenant, _model_root, _app, _create_company = phase19_environment

    response = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("system_events.csv", _anomaly_csv(), "text/csv")},
    )
    assert response.status_code == 201

    registry_rows = _registry_rows(session_factory, tenant.company_id)
    by_task = {row.task_code: row for row in registry_rows}
    # "forecasting" est détecté (colonne temporelle) mais pas câblé : seul
    # "anomaly" doit produire un job réel.
    assert set(by_task) == {"anomaly"}
    assert by_task["anomaly"].model_type == "anomaly_detection"
    assert by_task["anomaly"].is_active is True
    assert by_task["anomaly"].model_name == "isolation_forest"
    # Non supervisé : aucune accuracy/F1 fabriquée, uniquement une séparation
    # interne des scores de décision.
    assert set(by_task["anomaly"].metric) == {"anomaly_ratio", "separation_score", "mean_score"}


# ---------------------------------------------------------------------------
# 6, 7, 8 — weekly_forecast / recommendation / sentiment_analysis détectés
# mais jamais exécutés
# ---------------------------------------------------------------------------


def test_weekly_forecast_executes_while_recommendation_and_sentiment_stay_blocked(
    phase19_environment,
) -> None:
    """Phase 20 : "weekly_forecast" est désormais réellement câblé (forecasting

    temporel, backtesting). Phase 22 : "recommendation" est également câblée.
    Phase 23 : "sentiment_analysis" est désormais EXECUTABLE elle aussi (modèle
    de base par lexique, sans entraînement propre à l'entreprise), mais ne
    produit jamais de ligne ModelRegistry (Tier 1 sans état, voir
    `_STATELESS_EXECUTABLE_TASKS` dans `training_specs.py`).
    """

    client, session_factory, tenant, _model_root, _app, _create_company = phase19_environment

    rows = list(TaskResolutionService().resolve_dataset_capabilities(
        _rows_from_csv(_multi_capability_csv())
    ))
    assert "forecasting" in rows
    assert "recommendation" in rows
    assert "sentiment_analysis" in rows

    response = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("orders.csv", _multi_capability_csv(), "text/csv")},
    )
    assert response.status_code == 201

    registry_rows = _registry_rows(session_factory, tenant.company_id)
    registry_task_codes = {row.task_code for row in registry_rows}
    # "weekly_forecast" produit désormais un modèle réel (colonnes
    # "order_date" + "quantity" résolues) ; Phase 22 : "recommendation" est
    # elle aussi désormais câblée et produit un modèle réel. "sentiment"
    # est EXECUTABLE depuis Phase 23 (Tier 1 sans état) mais ne produit
    # jamais de ligne ModelRegistry (aucun entraînement par entreprise).
    assert "weekly_forecast" in registry_task_codes
    assert "recommendation" in registry_task_codes
    assert "sentiment" not in registry_task_codes

    by_task = {row.task_code: row for row in registry_rows}
    assert by_task["weekly_forecast"].model_type == "forecasting"
    assert by_task["weekly_forecast"].is_active is True
    assert by_task["recommendation"].model_type == "recommendation"
    assert by_task["recommendation"].is_active is True

    # Statuts explicites : "weekly_forecast"/"recommendation" sont maintenant
    # EXECUTABLE. Depuis Phase 23, "sentiment" est également EXECUTABLE
    # (modèle de base par lexique, Tier 1), sans que cela n'implique de ligne
    # ModelRegistry (voir plus haut).
    assert get_capability_status("retail", "weekly_forecast") is CapabilityStatus.EXECUTABLE
    assert get_capability_status("retail", "recommendation") is CapabilityStatus.EXECUTABLE
    assert get_capability_status("retail", "sentiment") is CapabilityStatus.EXECUTABLE


def _rows_from_csv(csv_bytes: bytes) -> list[dict]:
    import csv as csv_module
    from io import StringIO

    return list(csv_module.DictReader(StringIO(csv_bytes.decode("utf-8"))))


# ---------------------------------------------------------------------------
# 9 — synthetic_data_generation reste une capacité future
# ---------------------------------------------------------------------------


def test_synthetic_data_generation_is_future_capability_only() -> None:
    assert get_capability_status("retail", "synthetic_data") is CapabilityStatus.FUTURE_CAPABILITY

    # Jamais détectée par TaskResolutionService, quelles que soient les
    # données : `_normalize_module_task("synthetic_data")` ne correspond à
    # aucune des capacités détectables.
    capabilities = TaskResolutionService().resolve_dataset_capabilities(
        _rows_from_csv(_multi_capability_csv())
    )
    assert "synthetic_data" not in capabilities


# ---------------------------------------------------------------------------
# 10, 11, 12, 13 — plusieurs capacités -> plusieurs jobs indépendants,
# plusieurs modèles actifs simultanés, aucune désactivation croisée
# ---------------------------------------------------------------------------


def test_multi_capability_dataset_creates_independent_jobs_and_active_models(
    phase19_environment,
) -> None:
    client, session_factory, tenant, _model_root, _app, _create_company = phase19_environment

    response = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("orders.csv", _multi_capability_csv(), "text/csv")},
    )
    assert response.status_code == 201

    ai_jobs = _ai_jobs(session_factory, tenant.company_id)
    # bad_review et churn (classification, cible non résolvable ici -> échouent
    # chacun seul, sans jamais bloquer les autres), price et demand
    # (regression), weekly_forecast (forecasting, Phase 20 :
    # "order_date"/"quantity" résolus), et recommendation (Phase 22 :
    # "customer_id"/"product_id"/"quantity" résolus) : six jobs indépendants
    # créés à partir d'un seul dataset.
    assert len(ai_jobs) == 6

    registry_rows = _registry_rows(session_factory, tenant.company_id)
    by_task = {row.task_code: row for row in registry_rows}
    assert {"price", "demand", "weekly_forecast", "recommendation"}.issubset(by_task)
    # Plusieurs modèles actifs SIMULTANÉMENT pour la même entreprise, un par
    # tâche — aucun n'a désactivé l'autre.
    assert by_task["price"].is_active is True
    assert by_task["demand"].is_active is True
    assert by_task["weekly_forecast"].is_active is True
    assert by_task["weekly_forecast"].model_type == "forecasting"
    assert by_task["recommendation"].is_active is True
    assert by_task["recommendation"].model_type == "recommendation"
    assert by_task["price"].task_code != by_task["demand"].task_code
    assert by_task["price"].version != by_task["demand"].version


def test_one_dataset_creates_six_independent_tasks_without_tenant_leakage(
    phase19_environment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Une entreprise + un dataset produisent six entraînements isolés.

    Phase 20 : "weekly_forecast" (forecasting) rejoint bad_review/price/demand/
    segmentation/anomaly comme sixième tâche exécutable simultanée. La méthode
    générique `TrainingService.train(..., automl=AIEngine)` appartient au
    chemin dormant `core/families`. Le runtime RetailSense actif doit passer
    exclusivement par les méthodes spécialisées du même `TrainingService`.
    """

    client, session_factory, tenant_a, model_root, _app, create_company = phase19_environment
    tenant_b = create_company("No Data Retailer")

    def reject_orphaned_engine(*_args, **_kwargs):
        raise AssertionError("Le runtime actif ne doit pas appeler l'ancien AIEngine")

    monkeypatch.setattr(
        training_service_module.TrainingService,
        "train",
        reject_orphaned_engine,
    )

    response = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("retail_signals.csv", _five_executable_tasks_csv(), "text/csv")},
    )
    assert response.status_code == 201

    expected_tasks = {
        "bad_review",
        "price",
        "demand",
        "segmentation",
        "anomaly",
        "weekly_forecast",
        "recommendation",
    }
    ai_jobs = _ai_jobs(session_factory, tenant_a.company_id)
    # Phase 21 : "churn" partage la capacité "classification" avec
    # "bad_review" et est donc lui aussi dispatché, mais ce dataset ne
    # contient aucun signal de churn : son job échoue seul, sans jamais
    # bloquer ni désactiver les sept tâches réellement exécutables. Phase 22 :
    # "recommendation" rejoint désormais les tâches réellement exécutables.
    assert len(ai_jobs) == 8
    assert {job.status for job in ai_jobs} == {JobStatus.COMPLETED, JobStatus.FAILED}
    completed_jobs = [job for job in ai_jobs if job.status == JobStatus.COMPLETED]
    assert len(completed_jobs) == 7

    with session_factory() as session:
        training_jobs = session.scalars(
            select(TrainingJob).where(TrainingJob.company_id == tenant_a.company_id)
        ).all()
    assert len(training_jobs) == 8
    assert len({job.dataset_id for job in training_jobs}) == 1

    registry_rows = _registry_rows(session_factory, tenant_a.company_id)
    by_task = {row.task_code: row for row in registry_rows}
    assert set(by_task) == expected_tasks
    assert by_task["weekly_forecast"].model_type == "forecasting"
    assert by_task["recommendation"].model_type == "recommendation"
    assert all(row.is_active for row in registry_rows)
    assert len({row.training_job_id for row in registry_rows}) == 7
    assert len({row.storage_path for row in registry_rows}) == 7
    assert all(Path(row.storage_path).is_file() for row in registry_rows)

    registry = AIModelRegistry(root=model_root, serializer=JoblibArtifactSerializer())
    active_artifacts = {
        task_code: registry.resolve_active(tenant_a, "retail", task_code)
        for task_code in expected_tasks
    }
    assert len({artifact.path.parent for artifact in active_artifacts.values()}) == 7
    assert all(str(tenant_a.company_id) in str(artifact.path) for artifact in active_artifacts.values())

    assert _ai_jobs(session_factory, tenant_b.company_id) == []
    assert _registry_rows(session_factory, tenant_b.company_id) == []
    for task_code in expected_tasks:
        with pytest.raises(ModelNotFoundError):
            registry.resolve_active(tenant_b, "retail", task_code)


# ---------------------------------------------------------------------------
# 14 — isolation multi-tenant : aucun modèle partagé entre entreprises
# ---------------------------------------------------------------------------


def test_company_isolation_never_shares_models_across_tenants(phase19_environment) -> None:
    client, session_factory, tenant_a, model_root, app, create_company = phase19_environment
    tenant_b = create_company("Widgets Inc")

    _set_tenant(app, tenant_a)
    response_a = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("orders_a.csv", _demand_and_price_csv(), "text/csv")},
    )
    assert response_a.status_code == 201

    _set_tenant(app, tenant_b)
    response_b = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("orders_b.csv", _demand_and_price_csv(), "text/csv")},
    )
    assert response_b.status_code == 201

    rows_a = _registry_rows(session_factory, tenant_a.company_id)
    rows_b = _registry_rows(session_factory, tenant_b.company_id)
    assert rows_a and rows_b
    assert {row.company_id for row in rows_a} == {tenant_a.company_id}
    assert {row.company_id for row in rows_b} == {tenant_b.company_id}

    ai_registry = AIModelRegistry(root=model_root, serializer=JoblibArtifactSerializer())
    active_a = ai_registry.resolve_active(tenant_a, "retail", "price")
    active_b = ai_registry.resolve_active(tenant_b, "retail", "price")
    assert str(tenant_a.company_id) in str(active_a.path)
    assert str(tenant_b.company_id) in str(active_b.path)
    assert str(tenant_a.company_id) not in str(active_b.path)
    assert str(tenant_b.company_id) not in str(active_a.path)


# ---------------------------------------------------------------------------
# 15 — aucune logique Olist n'est utilisée par le chemin actif
# ---------------------------------------------------------------------------


_ACTIVE_PATH_MODULES = (
    training_specs_module,
    training_dispatcher_module,
    task_resolution_module,
    training_service_module,
)


def test_no_olist_logic_in_active_retail_training_path() -> None:
    for module in _ACTIVE_PATH_MODULES:
        source = inspect.getsource(module)
        assert "olist" not in source.lower(), f"Olist reference found in {module.__name__}"


# ---------------------------------------------------------------------------
# 16 — aucun second AI Engine n'est appelé par le chemin actif
# ---------------------------------------------------------------------------


def test_no_second_ai_engine_is_used_by_active_training_path() -> None:
    forbidden_imports = ("shared.ai_engine.core", "shared.ai_engine.families")
    for module in _ACTIVE_PATH_MODULES:
        source = inspect.getsource(module)
        for forbidden in forbidden_imports:
            assert forbidden not in source, (
                f"{module.__name__} imports the orphaned engine ({forbidden})"
            )


# ---------------------------------------------------------------------------
# Négatif (héritage Phase 18.2) : dataset sans signal reste sans job
# ---------------------------------------------------------------------------


def test_dataset_without_signal_still_skips_all_new_tasks(phase19_environment) -> None:
    client, session_factory, tenant, _model_root, _app, _create_company = phase19_environment

    response = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("contacts.csv", _insufficient_csv(), "text/csv")},
    )
    assert response.status_code == 201
    assert _ai_jobs(session_factory, tenant.company_id) == []
    assert _registry_rows(session_factory, tenant.company_id) == []
