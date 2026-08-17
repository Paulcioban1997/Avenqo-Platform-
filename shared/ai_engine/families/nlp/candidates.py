"""Construit les candidats NLP disponibles à partir du catalogue de modèles."""

from typing import Sequence

from shared.ai_engine.contracts import TrainingCandidate
from shared.ai_engine.families.nlp.registry import build_nlp_registry


def build_nlp_candidates() -> Sequence[TrainingCandidate]:
    return build_nlp_registry().build_all()
