"""Exécuteur de prédiction générique pour les pipelines sklearn entraînés.

Ne renvoie jamais de nom de modèle, d'algorithme ni de métrique technique :
uniquement un résultat métier et un score de confiance optionnel.
"""

from __future__ import annotations

from typing import Any, Mapping

import joblib
import pandas as pd

from backend.app.services.prediction_compatibility import validate_input_compatibility
from shared.ai_engine.contracts import ModelArtifact


class SklearnPredictionExecutor:
    """Charge le pipeline sklearn actif et produit un résultat business-friendly."""

    def predict(self, artifact: ModelArtifact, features: Mapping[str, Any]) -> dict[str, Any]:
        pipeline = joblib.load(artifact.path / "model.joblib")
        validate_input_compatibility(pipeline, features)
        frame = pd.DataFrame([features])
        raw_prediction = pipeline.predict(frame)[0]
        confidence: float | None = None
        if hasattr(pipeline, "predict_proba"):
            confidence = float(max(pipeline.predict_proba(frame)[0]))
        result = raw_prediction.item() if hasattr(raw_prediction, "item") else raw_prediction
        return {"result": result, "confidence": confidence}
