"""Construit les candidats Deep Learning disponibles à partir du catalogue de modèles."""

from typing import Sequence

from shared.ai_engine.architectures.deep_learning.registry import build_deep_learning_registry
from shared.ai_engine.contracts import TrainingCandidate


def build_deep_learning_candidates() -> Sequence[TrainingCandidate]:
    return build_deep_learning_registry().build_all()
