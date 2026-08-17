"""Candidat SARIMA, entraîné avec statsmodels.tsa.statespace.sarimax.SARIMAX.

Recherche d'hyperparamètres : voir `_order_search.py` (grille de `(p, d, q)` x saisonnier
`(P, Q)` candidats, D fixé à 0 pour la stabilité numérique — voir sa docstring pour le
détail —, sélection par AIC).
"""

from __future__ import annotations

from typing import Any

from shared.ai_engine.contracts import DatasetArtifact
from shared.ai_engine.core.model_stub import UntrainedModel
from shared.ai_engine.core.tabular_dataset import (
    detect_datetime_column,
    detect_target_column,
    load_dataframe,
)
from shared.ai_engine.families.forecasting.models._order_search import search_best_sarima


class SARIMAModel(UntrainedModel):
    """Recherche le meilleur SARIMAX(p, d, q)(P, D, Q, s) sur la colonne cible détectée."""

    candidate_id = "sarima"
    seasonal_period = 12

    def train(self, dataset: DatasetArtifact) -> Any:
        frame = load_dataframe(dataset)
        datetime_column = detect_datetime_column(frame)
        if datetime_column is not None:
            frame = frame.sort_values(datetime_column)
        exclude = (datetime_column,) if datetime_column else ()
        target_column = detect_target_column(frame, exclude=exclude)
        series = frame[target_column].astype("float64").reset_index(drop=True)

        return search_best_sarima(series, seasonal_period=self.seasonal_period)
