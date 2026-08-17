"""Construit les candidats Machine Learning disponibles à partir du catalogue de modèles."""

from typing import Sequence

from shared.ai_engine.architectures.machine_learning.registry import (
    build_machine_learning_registry,
)
from shared.ai_engine.contracts import TrainingCandidate


def build_machine_learning_candidates() -> Sequence[TrainingCandidate]:
    return build_machine_learning_registry().build_all()
