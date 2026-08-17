"""Construit les candidats Forecasting disponibles à partir du catalogue de modèles."""

from typing import Sequence

from shared.ai_engine.contracts import TrainingCandidate
from shared.ai_engine.families.forecasting.registry import build_forecasting_registry


def build_forecasting_candidates() -> Sequence[TrainingCandidate]:
    return build_forecasting_registry().build_all()
