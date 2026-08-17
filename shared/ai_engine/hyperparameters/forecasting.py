"""Estimateurs et grilles d'hyperparamètres pour la famille Forecasting.

Seule source de vérité pour le SEUL candidat compatible sklearn
(``gradient_boosting_lags``, via ``HistGradientBoostingRegressor`` sur des
variables retardées/lags — voir
`shared/ai_engine/training/forecasting_features.py`). Les autres candidats
(naïf, naïf saisonnier, ARIMA, SARIMA) ne sont PAS des estimateurs sklearn :
ils sont gérés directement par
`shared/ai_engine/training/train_forecaster.py` et
`forecasting_order_search.py`, jamais via ce fichier (même principe que
`hyperparameters/anomaly.py` : pas de préfixe ``model__`` ici non plus, car
appliqué directement via `estimator.set_params(**parameters)`).
"""

from __future__ import annotations

from typing import Any, Mapping

from sklearn.base import BaseEstimator
from sklearn.ensemble import HistGradientBoostingRegressor

# Familles candidates reconnues par le runtime de forecasting actif. Fixe et
# documentée ici (plutôt que découverte dynamiquement) pour que
# `ForecastingTrainingSpec.allowed_models` puisse restreindre explicitement
# n'importe laquelle d'entre elles, y compris les familles statistiques.
ALL_FORECASTING_FAMILIES: tuple[str, ...] = (
    "naive",
    "seasonal_naive",
    "arima",
    "sarima",
    "gradient_boosting_lags",
)


def build_estimators() -> dict[str, BaseEstimator]:
    """Construit l'unique estimateur sklearn disponible pour cette famille."""

    return {
        "gradient_boosting_lags": HistGradientBoostingRegressor(random_state=42),
    }


def build_parameter_spaces() -> dict[str, Mapping[str, Any]]:
    """Grille modeste pour `gradient_boosting_lags` (données temporelles courtes)."""

    return {
        "gradient_boosting_lags": {
            "max_depth": [2, 3, 4],
            "max_iter": [50, 100],
            "learning_rate": [0.05, 0.1],
        },
    }
