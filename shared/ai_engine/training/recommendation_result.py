"""Résultat public d'un entraînement de recommandation (filtrage collaboratif)."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from shared.ai_engine.training.recommender import ItemBasedRecommender


@dataclass(frozen=True, slots=True)
class RecommendationTrainingResult:
    """Expose le recommender entraîné, ses métriques et son fichier."""

    model_name: str
    recommender: ItemBasedRecommender
    best_parameters: Mapping[str, Any]
    metrics: Mapping[str, float]
    model_path: Path
