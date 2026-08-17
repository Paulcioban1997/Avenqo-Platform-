"""Construit les candidats Recommendation disponibles à partir du catalogue de modèles."""

from typing import Sequence

from shared.ai_engine.contracts import TrainingCandidate
from shared.ai_engine.families.recommendation.registry import build_recommendation_registry


def build_recommendation_candidates() -> Sequence[TrainingCandidate]:
    return build_recommendation_registry().build_all()
