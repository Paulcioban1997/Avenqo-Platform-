"""Entraînement réel du forecasting temporel (weekly_forecast et futures tâches).

Stratégie strictement temporelle : AUCUN `train_test_split` aléatoire (voir
`shared/ai_engine/training/temporal_validation.py`). Plusieurs familles de
candidats (naïf, naïf saisonnier, ARIMA, SARIMA, gradient boosting avec lags)
sont comparées par backtesting (fenêtres d'expansion) ; le gagnant est
sélectionné via `rank_forecast_candidates` (jamais via le test final, qui
reste réservé et n'influence jamais la sélection). Le gagnant est ensuite
ré-entraîné sur tout l'historique disponible (hors test final), puis évalué
UNE SEULE FOIS sur le test final pour le reporting.

Même architecture que `train_anomaly.py`/`train_clusterer.py` : un seul
`TrainingService`, aucun second moteur, aucune dépendance vers
`shared.ai_engine.core`/`shared.ai_engine.families`.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping

import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, clone
from sklearn.model_selection import ParameterGrid, RandomizedSearchCV, TimeSeriesSplit

from shared.ai_engine.contracts import DatasetArtifact
from shared.ai_engine.evaluation.forecasting_metrics import (
    evaluate_forecast,
    rank_forecast_candidates,
    summarize_backtest,
)
from shared.ai_engine.preprocessing.temporal import (
    InsufficientObservationsError,
    prepare_time_series,
)
from shared.ai_engine.training.experiment_logger import ExperimentLogger
from shared.ai_engine.training.forecasting_features import (
    build_lag_feature_frame,
    build_next_step_features,
    lag_count_for,
)
from shared.ai_engine.training.forecasting_model import ForecastingModel
from shared.ai_engine.training.forecasting_order_search import (
    search_best_arima,
    search_best_sarima,
)
from shared.ai_engine.training.forecasting_result import ForecastingTrainingResult
from shared.ai_engine.training.run_context import TrainingRunContext
from shared.ai_engine.training.temporal_validation import build_backtest_plan

_DEFAULT_CANDIDATE_FAMILIES: tuple[str, ...] = (
    "naive",
    "seasonal_naive",
    "arima",
    "sarima",
    "gradient_boosting_lags",
)


def train_forecaster(
    data: pd.DataFrame,
    target_column: str,
    time_column: str,
    dataset: DatasetArtifact,
    version: str,
    run_context: TrainingRunContext,
    estimators: Mapping[str, BaseEstimator],
    parameter_spaces: Mapping[str, Mapping[str, Any]],
    destination: Path,
    experiment_logger: ExperimentLogger,
    candidate_families: tuple[str, ...] = _DEFAULT_CANDIDATE_FAMILIES,
    horizon: int = 1,
    frequency: str = "auto",
    aggregation: str = "sum",
    minimum_observations: int = 12,
    seasonal_period: int = 7,
) -> ForecastingTrainingResult:
    """Prépare la série, backteste chaque candidat, retient et journalise le gagnant."""

    run = experiment_logger.start(dataset, version, run_context)
    started = perf_counter()
    try:
        preparation = prepare_time_series(
            data,
            time_column,
            target_column,
            frequency=frequency,
            aggregation=aggregation,
            minimum_observations=minimum_observations,
        )
        series = preparation.frame["__target__"].reset_index(drop=True)
        timestamps = preparation.frame["__time__"].reset_index(drop=True)

        minimum_train_size = max(4, horizon * 2)
        plan = build_backtest_plan(
            len(series), horizon, minimum_train_size=minimum_train_size, max_windows=3
        )
        if not plan.windows:
            raise InsufficientObservationsError(
                "Série insuffisante pour au moins une fenêtre de backtesting "
                f"(observations={len(series)}, horizon={horizon})."
            )

        candidate_reports = _run_backtests(series, plan, horizon, seasonal_period, estimators, candidate_families)
        family_names = list(candidate_reports.keys())
        scores = rank_forecast_candidates([candidate_reports[name] for name in family_names])
        best_index = max(range(len(family_names)), key=lambda index: scores[index])
        best_family = family_names[best_index]

        history_series = series.iloc[: plan.final_test_start].reset_index(drop=True)
        history_timestamps = timestamps.iloc[: plan.final_test_start].reset_index(drop=True)

        fitted_model, best_parameters = _fit_final_model(
            best_family, history_series, seasonal_period, estimators, parameter_spaces
        )
        forecasting_model = ForecastingModel(
            family=best_family,
            frequency=preparation.frequency,
            last_timestamp=history_timestamps.iloc[-1],
            history=history_series.tolist(),
            seasonal_period=seasonal_period,
            fitted_model=fitted_model,
            lag_count=int(best_parameters.get("lag_count", 0)),
        )

        final_test_actuals = series.iloc[plan.final_test_start : plan.final_test_end].to_numpy()
        final_forecast = forecasting_model.forecast(len(final_test_actuals))
        final_predictions = np.array([point["prediction"] for point in final_forecast])
        final_metrics = evaluate_forecast(final_test_actuals, final_predictions)

        backtest_report = candidate_reports[best_family]
        metrics: dict[str, float] = {f"final_test_{name}": value for name, value in final_metrics.items()}
        metrics.update(
            {
                "backtest_mean_rmse": backtest_report["mean_rmse"],
                "backtest_std_rmse": backtest_report["std_rmse"],
                "backtest_windows_completed": backtest_report["windows_completed"],
                "backtest_windows_total": float(len(plan.windows)),
                "r2": final_metrics.get("r2", 0.0),
            }
        )

        destination.mkdir(parents=True, exist_ok=True)
        model_path = destination / "model.joblib"
        joblib.dump(forecasting_model, model_path)

        experiment_logger.complete(
            run,
            run_context,
            best_family,
            parameter_spaces.get(best_family, {}),
            best_parameters,
            metrics,
            model_path,
            None,
            perf_counter() - started,
            (),
            (),
        )

        return ForecastingTrainingResult(
            model_name=best_family,
            model=forecasting_model,
            best_parameters=best_parameters,
            metrics=metrics,
            model_path=model_path,
            preparation_metadata={
                "frequency": preparation.frequency,
                "observations": preparation.observations,
                "invalid_dates_dropped": preparation.invalid_dates_dropped,
                "duplicate_periods_aggregated": preparation.duplicate_periods_aggregated,
                "irregular_intervals": preparation.irregular_intervals,
                "backtest_windows": len(plan.windows),
            },
        )
    except Exception:
        experiment_logger.fail(run, perf_counter() - started)
        raise


def _run_backtests(
    series: pd.Series,
    plan,
    horizon: int,
    seasonal_period: int,
    estimators: Mapping[str, BaseEstimator],
    candidate_families: tuple[str, ...],
) -> dict[str, dict[str, float]]:
    """Backtest chaque famille candidate sur les mêmes fenêtres d'expansion.

    Utilise des hyperparamètres FIXES (pas de recherche imbriquée) pour rester
    rapide et robuste sur de petites fenêtres — la recherche d'hyperparamètres
    complète n'a lieu qu'une seule fois, sur le gagnant, dans `_fit_final_model`.
    """

    reports: dict[str, dict[str, float]] = {}
    for family in candidate_families:
        window_metrics = []
        for train_end, val_end in plan.windows:
            train_slice = series.iloc[:train_end]
            actual = series.iloc[train_end:val_end].to_numpy()
            predicted = _backtest_forecast(family, train_slice, len(actual), seasonal_period, estimators)
            if predicted is None:
                continue
            window_metrics.append(evaluate_forecast(actual, predicted))
        reports[family] = summarize_backtest(window_metrics)
    return reports


def _backtest_forecast(
    family: str,
    train_series: pd.Series,
    horizon: int,
    seasonal_period: int,
    estimators: Mapping[str, BaseEstimator],
) -> np.ndarray | None:
    try:
        if family == "naive":
            return np.full(horizon, float(train_series.iloc[-1]))
        if family == "seasonal_naive":
            if len(train_series) < seasonal_period:
                return None
            tail = train_series.iloc[-seasonal_period:].to_numpy()
            return np.resize(tail, horizon)
        if family == "arima":
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                fitted = search_best_arima(train_series.astype("float64"))
                return np.asarray(fitted.forecast(steps=horizon))
        if family == "sarima":
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                fitted = search_best_sarima(train_series.astype("float64"), seasonal_period=seasonal_period)
                return np.asarray(fitted.forecast(steps=horizon))
        if family == "gradient_boosting_lags":
            base_estimator = estimators.get("gradient_boosting_lags")
            if base_estimator is None:
                return None
            lag_count = lag_count_for(len(train_series))
            frame = build_lag_feature_frame(train_series, lag_count)
            if len(frame) < 2:
                return None
            estimator = clone(base_estimator)
            estimator.fit(frame.drop(columns=["target"]), frame["target"])
            history = train_series.tolist()
            predictions = []
            for _ in range(horizon):
                features = build_next_step_features(history, lag_count)
                value = float(estimator.predict(pd.DataFrame([features]))[0])
                predictions.append(value)
                history.append(value)
            return np.asarray(predictions)
    except Exception:
        return None
    return None


def _fit_final_model(
    family: str,
    history_series: pd.Series,
    seasonal_period: int,
    estimators: Mapping[str, BaseEstimator],
    parameter_spaces: Mapping[str, Mapping[str, Any]],
) -> tuple[Any, dict[str, Any]]:
    """Ré-entraîne le candidat gagnant sur tout l'historique (hors test final)."""

    if family == "naive":
        return None, {"family": "naive"}
    if family == "seasonal_naive":
        return None, {"family": "seasonal_naive", "seasonal_period": seasonal_period}
    if family == "arima":
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fitted = search_best_arima(history_series.astype("float64"))
        return fitted, {"family": "arima", "order": tuple(fitted.model.order)}
    if family == "sarima":
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fitted = search_best_sarima(history_series.astype("float64"), seasonal_period=seasonal_period)
        order = tuple(getattr(fitted.model, "order", ()))
        seasonal_order = tuple(getattr(fitted.model, "seasonal_order", ()))
        return fitted, {"family": "sarima", "order": order, "seasonal_order": seasonal_order}
    if family == "gradient_boosting_lags":
        lag_count = lag_count_for(len(history_series))
        frame = build_lag_feature_frame(history_series, lag_count)
        features, target = frame.drop(columns=["target"]), frame["target"]
        base_estimator = estimators["gradient_boosting_lags"]
        parameter_space = dict(parameter_spaces.get("gradient_boosting_lags", {}))
        splits = min(3, max(2, len(features) // 4))
        if parameter_space and len(features) > splits * 2:
            search = RandomizedSearchCV(
                clone(base_estimator),
                parameter_space,
                n_iter=min(8, _grid_size(parameter_space)),
                cv=TimeSeriesSplit(n_splits=splits),
                random_state=42,
                scoring="neg_root_mean_squared_error",
            )
            search.fit(features, target)
            best_estimator = search.best_estimator_
            best_params = dict(search.best_params_)
        else:
            best_estimator = clone(base_estimator)
            best_estimator.fit(features, target)
            best_params = {}
        return best_estimator, {"family": "gradient_boosting_lags", "lag_count": lag_count, **best_params}
    raise ValueError(f"Famille forecasting inconnue: {family}")


def _grid_size(parameter_space: Mapping[str, Any]) -> int:
    try:
        return max(1, len(ParameterGrid(dict(parameter_space))))
    except TypeError:
        return 8
