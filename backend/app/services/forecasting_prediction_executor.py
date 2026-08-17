"""Exécuteur de prédiction pour les modèles de prévision temporelle (forecasting).

Même convention que `SklearnPredictionExecutor` : charge l'artefact sérialisé
(``model.joblib``) et délègue toute la logique métier au modèle lui-même.
Ne renvoie jamais de nom de modèle interne, d'algorithme ni de métrique
technique — uniquement des points de prévision business-friendly
(horodatage + valeur, horizon convenu à l'entraînement).
"""

from __future__ import annotations

from typing import Any, Mapping

import joblib

from shared.ai_engine.contracts import ModelArtifact


class ForecastingPredictionExecutor:
    """Charge un `ForecastingModel` sérialisé et produit une prévision.

    Respecte le même contrat générique que les autres exécuteurs
    (``{"result": ..., "confidence": ...}``, voir `PredictionResponse`) :
    aucun nouvel endpoint n'est nécessaire, `/api/v1/predict` fonctionne à
    l'identique pour "weekly_forecast".
    """

    def predict(self, artifact: ModelArtifact, features: Mapping[str, Any]) -> dict[str, Any]:
        model = joblib.load(artifact.path / "model.joblib")
        horizon = int(features.get("horizon", 1))
        forecast = model.forecast(horizon)
        return {"result": {"forecast": forecast, "horizon": horizon}, "confidence": None}
