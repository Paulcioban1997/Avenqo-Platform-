"""Métriques de forecasting — orientation "plus bas = meilleur" garantie.

Les métriques (MAE/RMSE/SMAPE) restent des erreurs classiques, jamais
inversées : c'est `rank_forecast_candidates` qui transforme ces erreurs en un
score "plus haut = meilleur" AVANT d'appeler `max()`, exactement comme
`rank_clustering_candidates`/`rank_anomaly_candidates`
(`shared/ai_engine/evaluation/clustering_metrics.py` /
`anomaly_metrics.py`) transforment déjà leurs métriques non supervisées de la
même façon. Aucun modèle n'est jamais sélectionné en appliquant `max()`
directement sur une métrique d'erreur brute.
"""

from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np
from sklearn.metrics import r2_score


def evaluate_forecast(actual: Sequence[float], predicted: Sequence[float]) -> dict[str, float]:
    """MAE/RMSE/SMAPE (toujours), MAPE (si mathématiquement valide), r2 (reporting)."""

    actual_arr = np.asarray(actual, dtype=float)
    predicted_arr = np.asarray(predicted, dtype=float)

    mae = float(np.mean(np.abs(actual_arr - predicted_arr)))
    rmse = float(np.sqrt(np.mean((actual_arr - predicted_arr) ** 2)))
    denominator = np.abs(actual_arr) + np.abs(predicted_arr)
    smape = float(
        np.mean(np.where(denominator == 0, 0.0, 2 * np.abs(predicted_arr - actual_arr) / denominator))
        * 100
    )

    metrics: dict[str, float] = {"mae": mae, "rmse": rmse, "smape": smape}

    if np.all(actual_arr != 0):
        metrics["mape"] = float(np.mean(np.abs((actual_arr - predicted_arr) / actual_arr)) * 100)

    if len(actual_arr) >= 2 and np.var(actual_arr) > 0:
        metrics["r2"] = float(r2_score(actual_arr, predicted_arr))
    else:
        # Trop peu de points ou série constante : un r2 classique n'a pas de
        # sens statistique ici — repli neutre, jamais utilisé pour la
        # sélection (uniquement pour le reporting/comparaison, voir
        # `shared/ai_engine/retraining/registry.py::_PRIMARY_METRIC_BY_FAMILY`).
        metrics["r2"] = 0.0

    return metrics


def summarize_backtest(window_metrics: Sequence[Mapping[str, float]]) -> dict[str, float]:
    """Agrège les métriques RMSE de chaque fenêtre de backtesting complétée."""

    completed_rmse = [metrics["rmse"] for metrics in window_metrics]
    if not completed_rmse:
        return {"mean_rmse": float("inf"), "std_rmse": float("inf"), "windows_completed": 0.0}
    return {
        "mean_rmse": float(np.mean(completed_rmse)),
        "std_rmse": float(np.std(completed_rmse)),
        "windows_completed": float(len(completed_rmse)),
    }


def rank_forecast_candidates(backtests: Sequence[Mapping[str, float]]) -> list[float]:
    """Transforme chaque rapport de backtesting en score "plus haut = meilleur".

    Un candidat sans aucune fenêtre complétée reçoit ``-inf`` (jamais
    sélectionnable). Sinon : ``score = -mean_rmse - 0.25 * std_rmse`` — pénalise
    à la fois l'erreur moyenne et son instabilité entre fenêtres, avant un
    simple `max()` (voir docstring de ce module).
    """

    scores: list[float] = []
    for report in backtests:
        if report.get("windows_completed", 0) <= 0:
            scores.append(float("-inf"))
            continue
        scores.append(-report["mean_rmse"] - 0.25 * report["std_rmse"])
    return scores
