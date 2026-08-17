"""Construit les candidats Vision disponibles à partir du catalogue de modèles."""

from typing import Sequence

from shared.ai_engine.contracts import TrainingCandidate
from shared.ai_engine.families.vision.registry import build_vision_registry


def build_vision_candidates() -> Sequence[TrainingCandidate]:
    return build_vision_registry().build_all()
