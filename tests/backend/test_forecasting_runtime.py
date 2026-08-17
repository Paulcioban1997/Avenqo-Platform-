"""Phase 20 (BLOC A) — forecasting temporel réellement exécutable.

Deux familles de tests :

- Tests unitaires (aucune base de données/HTTP) sur les briques pures de
  préparation temporelle, backtesting et métriques
  (`shared/ai_engine/preprocessing/temporal.py`,
  `shared/ai_engine/training/temporal_validation.py`,
  `shared/ai_engine/training/forecasting_features.py`,
  `shared/ai_engine/evaluation/forecasting_metrics.py`) : prouvent qu'il n'y a
  jamais de mélange aléatoire, jamais de fuite d'information future, et
  qu'une métrique d'erreur (plus bas = meilleur) n'est jamais utilisée
  directement avec `max()`.
- Tests d'intégration bout-en-bout (upload -> TaskResolutionService ->
  TrainingDispatcher -> TrainingService -> ModelRegistry -> `/predict`)
  prouvant que "weekly_forecast" est désormais EXECUTABLE, produit un modèle
  persistant réutilisable, respecte l'isolation multi-tenant, et échoue
  proprement (jamais de crash) quand la cible/colonne temporelle est absente.

Aucune logique Olist : tous les datasets sont génériques et fictifs.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd
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
)
from backend.app.repositories import SQLAlchemyModuleEntitlements
from backend.app.services.artifact_service import ArtifactService
from backend.app.services.dataset_import_service import DatasetImportService
from backend.main import create_application
from modules.entitlements import ModuleAccessService
from modules.retailsense.training_specs import CapabilityStatus, get_capability_status
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.evaluation.forecasting_metrics import (
    evaluate_forecast,
    rank_forecast_candidates,
    summarize_backtest,
)
from shared.ai_engine.preprocessing.temporal import (
    InsufficientObservationsError,
    InvalidTimeColumnError,
    prepare_time_series,
)
from shared.ai_engine.training.forecasting_features import build_lag_feature_frame, lag_count_for
from shared.ai_engine.training.temporal_validation import build_backtest_plan


# ---------------------------------------------------------------------------
# 1 — préparation temporelle : tri chronologique, dates invalides, doublons,
#     trous irréguliers, série trop courte
# ---------------------------------------------------------------------------


def test_prepare_time_series_sorts_chronologically_regardless_of_input_order() -> None:
    shuffled = pd.DataFrame(
        {
            "order_date": [
                "2024-01-10", "2024-01-01", "2024-01-05", "2024-01-03", "2024-01-08",
                "2024-01-02", "2024-01-09", "2024-01-04", "2024-01-06", "2024-01-07",
                "2024-01-11", "2024-01-12",
            ],
            "quantity": [10, 1, 5, 3, 8, 2, 9, 4, 6, 7, 11, 12],
        }
    )
    result = prepare_time_series(shuffled, "order_date", "quantity", minimum_observations=8)

    # Jamais de mélange aléatoire : la série préparée est strictement
    # croissante en temps, quel que soit l'ordre des lignes en entrée.
    timestamps = result.frame["__time__"].tolist()
    assert timestamps == sorted(timestamps)
    assert result.observations == 12


def test_prepare_time_series_drops_invalid_dates_and_counts_them() -> None:
    valid_dates = [
        (datetime(2024, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(10)
    ]
    dates: list[str] = []
    for index, day in enumerate(valid_dates):
        dates.append(day)
        if index % 2 == 0:
            dates.append("not-a-date")  # une date invalide intercalée sur deux
    data = pd.DataFrame({"order_date": dates, "quantity": list(range(len(dates)))})

    result = prepare_time_series(data, "order_date", "quantity", minimum_observations=8)

    assert result.invalid_dates_dropped > 0
    assert result.observations == 10


def test_prepare_time_series_aggregates_duplicate_periods() -> None:
    dates = []
    for i in range(10):
        day = (datetime(2024, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d")
        dates.extend([day, day])  # deux lignes par jour -> doublons temporels
    data = pd.DataFrame({"order_date": dates, "quantity": list(range(len(dates)))})

    result = prepare_time_series(data, "order_date", "quantity", minimum_observations=8)

    assert result.duplicate_periods_aggregated > 0
    # Une observation par jour après agrégation, jamais deux.
    assert result.observations == 10


def test_prepare_time_series_interpolates_irregular_gaps_without_future_leakage() -> None:
    dates = [
        (datetime(2024, 1, 1) + timedelta(days=offset)).strftime("%Y-%m-%d")
        for offset in (0, 1, 2, 3, 5, 6, 7, 9, 10, 11, 12, 13)  # jours 4 et 8 manquants
    ]
    data = pd.DataFrame({"order_date": dates, "quantity": [float(i + 1) for i in range(len(dates))]})

    result = prepare_time_series(data, "order_date", "quantity", minimum_observations=8)

    assert result.irregular_intervals is True
    # La régularisation comble les jours manquants (12 fournis + 2 comblés).
    assert result.observations == 14
    assert not result.frame["__target__"].isna().any()


def test_prepare_time_series_raises_when_series_too_short() -> None:
    data = pd.DataFrame(
        {
            "order_date": [f"2024-01-0{i}" for i in range(1, 6)],
            "quantity": [1, 2, 3, 4, 5],
        }
    )
    with pytest.raises(InsufficientObservationsError):
        prepare_time_series(data, "order_date", "quantity", minimum_observations=12)


def test_prepare_time_series_raises_when_time_column_entirely_invalid() -> None:
    data = pd.DataFrame({"order_date": ["not-a-date"] * 10, "quantity": list(range(10))})
    with pytest.raises(InvalidTimeColumnError):
        prepare_time_series(data, "order_date", "quantity", minimum_observations=8)


def test_prepare_time_series_raises_when_target_column_missing() -> None:
    data = pd.DataFrame({"order_date": [f"2024-01-0{i}" for i in range(1, 6)]})
    with pytest.raises(ValueError):
        prepare_time_series(data, "order_date", "missing_target", minimum_observations=3)


# ---------------------------------------------------------------------------
# 2 — backtesting temporel : jamais de découpage aléatoire, jamais de fuite
# ---------------------------------------------------------------------------


def test_build_backtest_plan_never_lets_windows_touch_the_final_test() -> None:
    plan = build_backtest_plan(n_observations=30, horizon=2, minimum_train_size=10, max_windows=3)

    assert plan.final_test_start == 28
    assert plan.final_test_end == 30
    for train_end, val_end in plan.windows:
        # Aucune fenêtre de backtesting ne dépasse jamais le début du test final.
        assert val_end <= plan.final_test_start


def test_build_backtest_plan_windows_expand_and_never_overlap() -> None:
    plan = build_backtest_plan(n_observations=40, horizon=2, minimum_train_size=10, max_windows=3)

    assert len(plan.windows) >= 1
    previous_val_end = -1
    for train_end, val_end in plan.windows:
        assert train_end >= 10  # jamais en dessous du minimum_train_size
        assert val_end > train_end
        # Fenêtres d'expansion : jamais de retour en arrière ni de chevauchement.
        assert train_end >= previous_val_end
        previous_val_end = val_end


def test_build_backtest_plan_returns_no_windows_when_history_too_short() -> None:
    plan = build_backtest_plan(n_observations=11, horizon=2, minimum_train_size=10, max_windows=3)

    assert plan.windows == ()
    assert plan.final_test_start == 9


def test_build_lag_feature_frame_never_uses_future_values() -> None:
    series = pd.Series([float(i) for i in range(10)])
    lag_count = 3
    frame = build_lag_feature_frame(series, lag_count=lag_count)

    # `build_lag_feature_frame` supprime les premières lignes sans historique
    # suffisant puis réindexe à partir de 0 : la ligne de sortie `i`
    # correspond donc toujours à la position d'origine `i + lag_count`.
    # lag_1 à la ligne `i` doit toujours correspondre à la valeur strictement
    # précédente dans la série d'origine (jamais une valeur future).
    for output_index, row in frame.iterrows():
        original_position = output_index + lag_count
        assert row["lag_1"] == series.iloc[original_position - 1]
    assert lag_count_for(40) == 4
    assert lag_count_for(5) == 1


# ---------------------------------------------------------------------------
# 3 — métriques : orientation "plus bas = meilleur" jamais inversée directement
# ---------------------------------------------------------------------------


def test_rank_forecast_candidates_prefers_lower_rmse() -> None:
    good_candidate = summarize_backtest([{"rmse": 1.0}, {"rmse": 1.2}])
    bad_candidate = summarize_backtest([{"rmse": 20.0}, {"rmse": 22.0}])

    scores = rank_forecast_candidates([bad_candidate, good_candidate])

    # Le meilleur candidat (RMSE la plus basse) doit obtenir le score le plus
    # haut une fois transformé — jamais l'inverse.
    assert scores[1] > scores[0]
    assert good_candidate == max([good_candidate, bad_candidate], key=lambda report: -report["mean_rmse"])


def test_rank_forecast_candidates_never_selects_candidate_with_zero_windows() -> None:
    never_validated = summarize_backtest([])
    validated = summarize_backtest([{"rmse": 5.0}])

    scores = rank_forecast_candidates([never_validated, validated])

    assert scores[0] == float("-inf")
    assert scores[1] > scores[0]


def test_evaluate_forecast_reports_lower_is_better_error_metrics() -> None:
    actual = [10.0, 12.0, 14.0, 16.0]
    close_prediction = [10.5, 11.5, 14.5, 15.5]
    far_prediction = [50.0, 2.0, 80.0, 1.0]

    close_metrics = evaluate_forecast(actual, close_prediction)
    far_metrics = evaluate_forecast(actual, far_prediction)

    assert close_metrics["rmse"] < far_metrics["rmse"]
    assert close_metrics["mae"] < far_metrics["mae"]


# ---------------------------------------------------------------------------
# 4 — bout-en-bout : detection/exécution réelle, persistance, prédiction,
#     isolation multi-tenant, échec propre sans colonnes exploitables
# ---------------------------------------------------------------------------


def _weekly_demand_csv(rows: int = 20) -> bytes:
    lines = ["order_date,quantity"]
    for i in range(rows):
        order_date = (datetime(2024, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d")
        # Valeurs strictement croissantes (jamais de doublon) : évite toute
        # ambiguïté avec l'heuristique de détection "classification" (qui se
        # déclenche sur des colonnes numériques avec valeurs répétées).
        quantity = 20 + i
        lines.append(f"{order_date},{quantity}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _no_demand_signal_csv() -> bytes:
    """Aucune colonne temporelle/cible exploitable pour le forecasting."""

    rows = ["id,name"]
    for i, name in enumerate(["Alice", "Bob", "Carol", "Diane", "Eve", "Frank"]):
        rows.append(f"{i},{name}")
    return ("\n".join(rows) + "\n").encode("utf-8")


@pytest.fixture
def forecasting_environment(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'forecasting.db'}",
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
                access=ModuleAccessService(SQLAlchemyModuleEntitlements(session)),
                max_upload_bytes=1024 * 1024,
            )

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_dataset_import_service] = override_dataset_service
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    app.dependency_overrides[get_model_registry_root] = lambda: model_root

    default_tenant = _create_company("Acme Forecast")
    app.dependency_overrides[get_tenant_context] = lambda: default_tenant

    with TestClient(app) as client:
        yield client, session_factory, default_tenant, model_root, app, _create_company


def _registry_rows(session_factory, company_id):
    with session_factory() as session:
        return list(
            session.scalars(select(ModelRegistry).where(ModelRegistry.company_id == company_id)).all()
        )


def _ai_jobs(session_factory, company_id):
    with session_factory() as session:
        return list(session.scalars(select(AIJob).where(AIJob.company_id == company_id)).all())


def test_weekly_forecast_is_executable_and_persists_a_real_model(forecasting_environment) -> None:
    client, session_factory, tenant, _model_root, _app, _create_company = forecasting_environment

    assert get_capability_status("retail", "weekly_forecast") is CapabilityStatus.EXECUTABLE

    response = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("orders.csv", _weekly_demand_csv(), "text/csv")},
    )
    assert response.status_code == 201

    ai_jobs = _ai_jobs(session_factory, tenant.company_id)
    assert {job.status for job in ai_jobs} == {JobStatus.COMPLETED}

    registry_rows = _registry_rows(session_factory, tenant.company_id)
    by_task = {row.task_code: row for row in registry_rows}
    assert "weekly_forecast" in by_task
    assert by_task["weekly_forecast"].model_type == "forecasting"
    assert by_task["weekly_forecast"].is_active is True
    assert Path(by_task["weekly_forecast"].storage_path).is_file()


def test_weekly_forecast_prediction_is_retrievable_via_generic_predict_endpoint(
    forecasting_environment,
) -> None:
    client, session_factory, tenant, _model_root, _app, _create_company = forecasting_environment

    response = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("orders.csv", _weekly_demand_csv(), "text/csv")},
    )
    assert response.status_code == 201

    prediction_response = client.post(
        "/api/v1/predict",
        json={"module_code": "retail", "task_code": "weekly_forecast", "features": {"horizon": 2}},
    )
    assert prediction_response.status_code == 200
    body = prediction_response.json()
    # Contrat générique inchangé : "result"/"confidence", jamais de nouveau
    # champ d'API dédié au forecasting.
    assert "result" in body
    forecast_points = body["result"]["forecast"]
    assert len(forecast_points) == 2
    for point in forecast_points:
        assert "timestamp" in point
        assert "prediction" in point


def test_weekly_forecast_never_shares_models_across_tenants(forecasting_environment) -> None:
    client, session_factory, tenant_a, model_root, app, create_company = forecasting_environment
    tenant_b = create_company("No Forecast Retailer")

    response = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("orders.csv", _weekly_demand_csv(), "text/csv")},
    )
    assert response.status_code == 201

    assert _registry_rows(session_factory, tenant_a.company_id) != []
    assert _registry_rows(session_factory, tenant_b.company_id) == []

    app.dependency_overrides[get_tenant_context] = lambda: tenant_b
    prediction_response = client.post(
        "/api/v1/predict",
        json={"module_code": "retail", "task_code": "weekly_forecast", "features": {"horizon": 1}},
    )
    # Aucun modèle actif pour tenant_b : conflit explicite, jamais le modèle
    # de tenant_a.
    assert prediction_response.status_code == 409


def test_weekly_forecast_fails_gracefully_without_exploitable_columns(
    forecasting_environment,
) -> None:
    client, session_factory, tenant, _model_root, _app, _create_company = forecasting_environment

    response = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("contacts.csv", _no_demand_signal_csv(), "text/csv")},
    )
    # L'upload réussit toujours (l'entraînement automatique reste annexe,
    # jamais bloquant) même si aucune capacité n'est détectée.
    assert response.status_code == 201

    ai_jobs = _ai_jobs(session_factory, tenant.company_id)
    assert ai_jobs == []
    assert _registry_rows(session_factory, tenant.company_id) == []
