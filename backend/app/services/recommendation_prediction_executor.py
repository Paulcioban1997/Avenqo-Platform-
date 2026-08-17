"""Exécuteur de prédiction pour le Recommendation Engine (Phase 22).

Même contrat que `SklearnPredictionExecutor`/`ForecastingPredictionExecutor` :
charge l'artefact actif (`model.joblib`) et renvoie un résultat business-
friendly. Un client inconnu ("cold start") reçoit un secours par popularité
propre à SON entreprise — jamais une recommandation empruntée à une autre.
"""

from __future__ import annotations

from typing import Any, Mapping

import joblib

from shared.ai_engine.contracts import ModelArtifact
from shared.ai_engine.training.recommender import ItemBasedRecommender


class RecommendationPredictionExecutor:
    """Charge le recommender actif et produit une liste d'articles recommandés."""

    def predict(self, artifact: ModelArtifact, features: Mapping[str, Any]) -> dict[str, Any]:
        recommender: ItemBasedRecommender = joblib.load(artifact.path / "model.joblib")
        customer_id = str(features.get("customer_id") or features.get("entity") or "")
        top_k = int(features.get("top_k") or 5)

        recommended = recommender.recommend(customer_id, top_k)
        is_known_customer = customer_id in recommender.user_history
        confidence = 0.7 if is_known_customer and recommended else (0.4 if recommended else 0.0)
        return {"result": recommended, "confidence": confidence}
