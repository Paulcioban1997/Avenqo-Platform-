"""Construit les candidats LLM disponibles à partir du catalogue de modèles."""

from typing import Sequence

from shared.ai_engine.contracts import TrainingCandidate
from shared.ai_engine.families.llm.registry import build_llm_registry


def build_llm_candidates() -> Sequence[TrainingCandidate]:
    return build_llm_registry().build_all()
