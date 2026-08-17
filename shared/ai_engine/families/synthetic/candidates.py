"""Construit les candidats Synthetic Data disponibles à partir du catalogue de modèles."""

from typing import Sequence

from shared.ai_engine.contracts import TrainingCandidate
from shared.ai_engine.families.synthetic.registry import build_synthetic_registry


def build_synthetic_candidates() -> Sequence[TrainingCandidate]:
    return build_synthetic_registry().build_all()
