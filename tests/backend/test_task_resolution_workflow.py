"""Phase 18.2 — Preuve d'intégration : `TaskResolutionService` dans le workflow réel.

Ces tests ne valident pas `TaskResolutionService` en isolation (déjà couvert par
`tests/ai_engine/test_generic_task_resolution.py`) : ils prouvent que le
pipeline de production complet (upload -> `DatasetImportService` -> détection
de schéma -> `TrainingDispatcher.dispatch()` -> `TaskResolutionService` ->
intersection avec les tâches câblées du module -> `AIJob`/`TrainingJob`
indépendants -> `TrainingService` -> `ModelRegistry`) utilise réellement le
composant, sans double logique et sans jamais exposer de terme technique.

Aucune logique Olist : le dataset utilisé est un exemple générique
(`customer_id`, `order_date`, `product_id`, `quantity`, `price`), jamais lié à
un jeu de données spécifique.
"""

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
import logging
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
from backend.app.services.data_import_policy import DataImportPolicy
from backend.main import create_application
from modules.entitlements import ModuleAccessService
from shared.ai_engine.contracts import TenantContext
from tests.subscription_helpers import add_active_subscription

FORBIDDEN_TERMS = (
    "accuracy",
    "precision",
    "recall",
    "f1",
    "gridsearchcv",
    "randomforest",
    "algorithm",
    "hyperparameter",
    "regression",
    "classification",
    "shap",
    "drift",
)


def _single_task_csv() -> bytes:
    """Exemple générique (aucune logique Olist) : capacité "regression" uniquement.

    `customer_id` est une chaîne ("C0", "C1", ...), jamais un entier séquentiel :
    un identifiant numérique brut ferait à tort ressembler ce dataset à un
    signal de segmentation (voir `TaskResolutionService._has_segmentation_signal`),
    ce qui n'est pas le comportement testé ici.
    """

    rows = ["customer_id,order_date,product_id,quantity,price"]
    for i in range(15):
        order_date = (datetime(2024, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d")
        product_id = f"P{i % 5}"
        quantity = i + 1  # valeurs uniques : n'imite pas un indicateur de classification.
        price = round(9.99 + i * 1.5, 2)
        rows.append(f"C{i},{order_date},{product_id},{quantity},{price}")
    return ("\n".join(rows) + "\n").encode("utf-8")


def _multi_task_csv() -> bytes:
    """Même schéma générique, avec un indicateur binaire supplémentaire.

    Rend simultanément possibles plusieurs tâches câblées pour "retail" :
    "price"/"demand" (regression) et "bad_review" (classification) — sans
    dupliquer aucune logique métier, uniquement à partir des données réelles.
    Même précaution que `_single_task_csv` sur `customer_id` (chaîne, jamais
    un entier) pour ne pas déclencher accidentellement la segmentation ici :
    ce cas précis est couvert par un test dédié.
    """

    rows = ["customer_id,order_date,product_id,quantity,price,is_bad_review"]
    for i in range(30):
        order_date = (datetime(2024, 1, 1) + timedelta(days=i % 28)).strftime("%Y-%m-%d")
        product_id = f"P{i % 5}"
        quantity = i + 1
        price = round(9.99 + i * 0.37, 2)
        is_bad_review = 1 if i % 3 == 0 else 0
        rows.append(f"C{i},{order_date},{product_id},{quantity},{price},{is_bad_review}")
    return ("\n".join(rows) + "\n").encode("utf-8")


def _insufficient_csv() -> bytes:
    """Dataset sans signal exploitable : aucune tâche automatique ne doit se déclencher."""

    rows = ["id,name"]
    names = ["Alice", "Bob", "Carol", "Diane", "Eve"]
    for i, name in enumerate(names):
        rows.append(f"{i},{name}")
    return ("\n".join(rows) + "\n").encode("utf-8")


@pytest.fixture
def workflow_environment(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'workflow.db'}",
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
        yield client, session_factory, tenant


def test_upload_reaches_task_resolution_and_dispatches_matching_task(workflow_environment) -> None:
    """Preuve bout-en-bout : upload -> TaskResolutionService -> Training Dispatcher.

    Un seul type de capacité ("regression") est détectable dans ce dataset, mais
    DEUX tâches câblées du module "retail" la partagent ("price" et "demand",
    voir Phase 19) : chacune reste indépendante, avec son propre `AIJob`/
    `TrainingJob`/modèle actif, résolue vers sa propre colonne cible ("price"
    pour l'une, "quantity" pour l'autre). Phase 20 : "order_date" + "quantity"
    rendent aussi "weekly_forecast" (forecasting) exécutable sur ce même
    dataset — une troisième tâche indépendante, jamais fusionnée.
    """

    client, session_factory, tenant = workflow_environment

    response = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("orders.csv", _single_task_csv(), "text/csv")},
    )
    assert response.status_code == 201

    with session_factory() as session:
        ai_jobs = session.scalars(
            select(AIJob).where(AIJob.company_id == tenant.company_id)
        ).all()
        registry_rows = session.scalars(
            select(ModelRegistry).where(ModelRegistry.company_id == tenant.company_id)
        ).all()

    assert len(ai_jobs) == 4
    # Phase 22 : "recommendation" est détectée sur ce dataset (customer_id +
    # product_id + quantity) mais ce fixture ne contient que 15 lignes, sous
    # le seuil minimum d'interactions (20) : son job échoue seul, sans jamais
    # bloquer ni désactiver les trois tâches réellement exécutables, et ne
    # produit aucune ligne ModelRegistry.
    assert {job.status for job in ai_jobs} == {JobStatus.COMPLETED, JobStatus.FAILED}
    assert len([job for job in ai_jobs if job.status == JobStatus.COMPLETED]) == 3
    assert len(registry_rows) == 3
    by_task = {row.task_code: row for row in registry_rows}
    assert set(by_task) == {"price", "demand", "weekly_forecast"}
    assert by_task["price"].module_code == "retail"
    assert by_task["price"].model_type == "regression"
    assert by_task["price"].is_active is True
    assert by_task["demand"].module_code == "retail"
    assert by_task["demand"].model_type == "regression"
    assert by_task["demand"].is_active is True
    assert by_task["weekly_forecast"].module_code == "retail"
    assert by_task["weekly_forecast"].model_type == "forecasting"
    assert by_task["weekly_forecast"].is_active is True

    status_response = client.get(f"/api/v1/training-jobs/{ai_jobs[0].id}")
    assert status_response.status_code == 200
    # Seul le message métier ("message") doit rester exempt de terme technique :
    # `ai_job_id` est un UUID opaque qui peut contenir, par pur hasard, une
    # sous-chaîne hexadécimale identique à un terme interdit (ex. "f1") sans que
    # cela ne révèle jamais rien de technique à l'utilisateur final.
    rendered = str(status_response.json()["message"]).lower()
    for forbidden in FORBIDDEN_TERMS:
        assert forbidden not in rendered


def test_dataset_with_multiple_capabilities_creates_independent_jobs_per_task(
    workflow_environment, caplog,
) -> None:
    """Un dataset rendant plusieurs tâches possibles génère plusieurs jobs indépendants.

    Aucune duplication : `tenant_id` + `dataset_id` + `module_code` +
    `task_code` restent uniques par job, et chaque tâche garde son propre
    modèle actif (correction Phase 18.2 de la limitation "un seul modèle actif
    par entreprise").
    """

    caplog.set_level(logging.INFO, logger="backend.app.services.training_dispatcher")
    client, session_factory, tenant = workflow_environment

    response = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("orders_multi.csv", _multi_task_csv(), "text/csv")},
    )
    assert response.status_code == 201

    with session_factory() as session:
        ai_jobs = session.scalars(
            select(AIJob).where(AIJob.company_id == tenant.company_id)
        ).all()
        training_jobs = session.scalars(
            select(TrainingJob).where(TrainingJob.company_id == tenant.company_id)
        ).all()
        registry_rows = session.scalars(
            select(ModelRegistry).where(ModelRegistry.company_id == tenant.company_id)
        ).all()

    # Quatre tâches câblées ("price"/regression, "demand"/regression,
    # "bad_review"/classification, "weekly_forecast"/forecasting depuis la
    # Phase 20) sont toutes détectées comme possibles par les données : quatre
    # jobs indépendants, jamais un seul job "fusionné". "churn" partage la
    # capacité "classification" avec "bad_review", mais sa cible n'existe pas
    # dans ce dataset : il est donc non applicable et aucun job en échec n'est
    # créé. Phase 22 : "recommendation" (30 lignes,
    # customer_id/product_id/quantity) est également détectée et s'entraîne
    # avec succès (au-dessus du seuil minimum d'interactions).
    assert len(ai_jobs) == 5
    assert len(training_jobs) == 5
    assert {job.status for job in ai_jobs} == {JobStatus.COMPLETED}
    assert "task=churn" in caplog.text
    assert "skipped as not applicable" in caplog.text

    assert len(registry_rows) == 5
    by_task = {row.task_code: row for row in registry_rows}
    assert set(by_task) == {"price", "demand", "bad_review", "weekly_forecast", "recommendation"}

    # Isolation : chaque tâche garde sa propre décision d'activation. Le
    # classifieur est activé lorsqu'il atteint au minimum la baseline naïve.
    assert by_task["price"].is_active is True
    assert by_task["price"].model_type == "regression"
    assert by_task["demand"].is_active is True
    assert by_task["demand"].model_type == "regression"
    assert by_task["bad_review"].is_active is True
    assert by_task["bad_review"].model_type == "classification"
    assert by_task["weekly_forecast"].is_active is True
    assert by_task["weekly_forecast"].model_type == "forecasting"
    assert by_task["price"].module_code == "retail"
    assert by_task["demand"].module_code == "retail"
    assert by_task["bad_review"].module_code == "retail"

    for ai_job in ai_jobs:
        status_response = client.get(f"/api/v1/training-jobs/{ai_job.id}")
        assert status_response.status_code == 200
        # Voir commentaire équivalent plus haut : seul le message métier est
        # vérifié (l'UUID opaque n'est jamais un terme technique, même s'il en
        # contient la sous-chaîne par coïncidence).
        rendered = str(status_response.json()["message"]).lower()
        for forbidden in FORBIDDEN_TERMS:
            assert forbidden not in rendered


def test_dataset_without_exploitable_signal_skips_automatic_training(
    workflow_environment,
) -> None:
    """Négatif : un dataset sans signal exploitable ne déclenche aucun entraînement artificiel.

    L'upload doit tout de même réussir (l'entraînement automatique reste une
    fonctionnalité annexe, jamais bloquante) mais aucun `AIJob` ne doit être
    créé : `TaskResolutionService` ne détecte aucune capacité, donc
    l'intersection DATASET CAPABILITIES ∩ MODULE CAPABILITIES est vide.
    """

    client, session_factory, tenant = workflow_environment

    response = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("contacts.csv", _insufficient_csv(), "text/csv")},
    )
    assert response.status_code == 201

    with session_factory() as session:
        ai_jobs = session.scalars(
            select(AIJob).where(AIJob.company_id == tenant.company_id)
        ).all()
        registry_rows = session.scalars(
            select(ModelRegistry).where(ModelRegistry.company_id == tenant.company_id)
        ).all()

    assert ai_jobs == []
    assert registry_rows == []
