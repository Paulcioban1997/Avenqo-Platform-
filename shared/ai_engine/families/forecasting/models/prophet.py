"""Candidat Prophet, entraîné avec prophet.Prophet.

Recherche d'hyperparamètres : grille sur `changepoint_prior_scale` x
`seasonality_prior_scale` x `seasonality_mode`, sélection par erreur quadratique sur une
fenêtre de validation temporelle (holdout = les 20% dernières lignes). Alternative
pragmatique à `prophet.diagnostics.cross_validation` (l'outil officiel de validation
croisée de Prophet), qui ré-entraîne un modèle complet par fenêtre glissante et devient
disproportionné en temps de calcul pour une recherche de grille sur petit dataset.

Nécessite le backend Stan/cmdstanpy compilé (`python -m cmdstanpy.install_cmdstan`), qui
suppose une chaîne de compilation C++ (ex : RTools sous Windows). Si ce backend n'est pas
disponible dans l'environnement d'exécution, l'erreur est propagée avec un message clair
plutôt que d'être masquée par un stub silencieux.
"""

from __future__ import annotations

import itertools
from typing import Any

import pandas as pd

from shared.ai_engine.contracts import DatasetArtifact
from shared.ai_engine.core.model_stub import UntrainedModel
from shared.ai_engine.core.tabular_dataset import (
    detect_datetime_column,
    detect_target_column,
    load_dataframe,
)

_CHANGEPOINT_PRIOR_SCALES = (0.001, 0.01, 0.1, 0.5)
_SEASONALITY_PRIOR_SCALES = (0.01, 1.0, 10.0)
_SEASONALITY_MODES = ("additive", "multiplicative")
_DEFAULT_PARAMETERS = {
    "changepoint_prior_scale": 0.05,
    "seasonality_prior_scale": 10.0,
    "seasonality_mode": "additive",
}


class ProphetModel(UntrainedModel):
    """Ajuste un Prophet univarié sur la colonne cible détectée, après recherche de grille."""

    candidate_id = "prophet"
    validation_fraction = 0.2

    def train(self, dataset: DatasetArtifact) -> Any:
        from prophet import Prophet

        frame = load_dataframe(dataset)
        datetime_column = detect_datetime_column(frame)
        if datetime_column is None:
            raise ValueError(
                "Prophet nécessite une colonne date/heure détectable dans le dataset."
            )
        target_column = detect_target_column(frame, exclude=(datetime_column,))
        prophet_frame = (
            pd.DataFrame(
                {
                    "ds": pd.to_datetime(frame[datetime_column]),
                    "y": frame[target_column].astype("float64"),
                }
            )
            .sort_values("ds")
            .reset_index(drop=True)
        )

        best_parameters = self._search_best_parameters(Prophet, prophet_frame)

        model = Prophet(**best_parameters)
        try:
            model.fit(prophet_frame)
        except Exception as exc:  # pragma: no cover - dépend du backend Stan de l'environnement
            raise RuntimeError(
                "L'entraînement Prophet nécessite le backend Stan compilé (exécuter "
                "`python -m cmdstanpy.install_cmdstan`, ce qui suppose une chaîne de "
                "compilation C++ telle que RTools sous Windows)."
            ) from exc
        return model

    def _search_best_parameters(self, prophet_class: Any, prophet_frame: pd.DataFrame) -> dict[str, Any]:
        split_index = max(2, int(len(prophet_frame) * (1 - self.validation_fraction)))
        train_frame = prophet_frame.iloc[:split_index]
        validation_frame = prophet_frame.iloc[split_index:]
        if len(validation_frame) < 2:
            return dict(_DEFAULT_PARAMETERS)

        best_parameters: dict[str, Any] | None = None
        best_error = float("inf")
        candidates = itertools.product(
            _CHANGEPOINT_PRIOR_SCALES, _SEASONALITY_PRIOR_SCALES, _SEASONALITY_MODES
        )
        for changepoint_prior_scale, seasonality_prior_scale, seasonality_mode in candidates:
            parameters = {
                "changepoint_prior_scale": changepoint_prior_scale,
                "seasonality_prior_scale": seasonality_prior_scale,
                "seasonality_mode": seasonality_mode,
            }
            try:
                candidate_model = prophet_class(**parameters)
                candidate_model.fit(train_frame)
                forecast = candidate_model.predict(validation_frame[["ds"]])
                error = float(
                    ((forecast["yhat"].to_numpy() - validation_frame["y"].to_numpy()) ** 2).mean()
                )
            except Exception:  # combinaison instable (backend Stan ou données) : on l'écarte
                continue
            if error < best_error:
                best_error = error
                best_parameters = parameters

        return best_parameters if best_parameters is not None else dict(_DEFAULT_PARAMETERS)
