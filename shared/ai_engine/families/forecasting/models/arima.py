"""Candidat ARIMA, entraîné avec statsmodels.tsa.arima.model.ARIMA.

Recherche d'hyperparamètres : voir `_order_search.py` (grille de `(p, d, q)` candidats,
sélection par AIC — GridSearchCV ne s'applique pas à un estimateur statsmodels, qui n'a
pas l'API scikit-learn ; l'équivalent standard pour ARIMA est une recherche par critère
d'information, comme le fait `pmdarima.auto_arima`).
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
from shared.ai_engine.families.forecasting.models._order_search import search_best_arima


class ARIMAModel(UntrainedModel):
    """Recherche le meilleur ARIMA(p, d, q) univarié sur la colonne cible détectée."""

    candidate_id = "arima"

    def train(self, dataset: DatasetArtifact) -> Any:
        frame = load_dataframe(dataset)
        datetime_column = detect_datetime_column(frame)
        if datetime_column is not None:
            frame = frame.sort_values(datetime_column)
        exclude = (datetime_column,) if datetime_column else ()
        target_column = detect_target_column(frame, exclude=exclude)
        series = frame[target_column].astype("float64").reset_index(drop=True)

        return search_best_arima(series)
