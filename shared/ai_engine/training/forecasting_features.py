"""Construction de variables retardées (lags) pour le candidat `gradient_boosting_lags`.

Chaque ligne d'entraînement n'utilise que des valeurs strictement passées par
rapport à sa cible (``shift``), jamais de valeur future : aucune fuite
d'information, contrairement à un simple découpage aléatoire.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def lag_count_for(n_observations: int) -> int:
    """Nombre de lags utilisés, borné pour rester exploitable sur de petites séries."""

    return max(1, min(4, n_observations // 5))


def build_lag_feature_frame(series: pd.Series, lag_count: int) -> pd.DataFrame:
    """Retourne un DataFrame ``target`` + ``lag_1..lag_k`` + ``rolling_mean``.

    Les premières lignes (sans historique suffisant) sont supprimées : aucune
    valeur manquante n'est jamais imputée par une information future.
    """

    frame = pd.DataFrame({"target": pd.Series(series).reset_index(drop=True)})
    for lag in range(1, lag_count + 1):
        frame[f"lag_{lag}"] = frame["target"].shift(lag)
    frame["rolling_mean"] = frame["target"].shift(1).rolling(window=lag_count, min_periods=1).mean()
    return frame.dropna().reset_index(drop=True)


def build_next_step_features(history: list[float], lag_count: int) -> dict[str, float]:
    """Construit la ligne de variables pour prédire le pas suivant (inférence récursive).

    Utilisée à la fois à l'entraînement final (implicitement, via
    `build_lag_feature_frame`) et lors de la prévision multi-pas récursive
    (`ForecastingModel._recursive_lag_forecast`) : mêmes noms de colonnes,
    même logique, pour rester cohérent entre entraînement et inférence.
    """

    row: dict[str, float] = {}
    for lag in range(1, lag_count + 1):
        row[f"lag_{lag}"] = float(history[-lag]) if len(history) >= lag else float(history[0])
    tail = history[-lag_count:] if history else []
    row["rolling_mean"] = float(np.mean(tail)) if tail else 0.0
    return row
