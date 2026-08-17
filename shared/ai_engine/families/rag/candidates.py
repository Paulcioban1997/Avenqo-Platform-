"""Construit les candidats RAG disponibles à partir du catalogue de modèles."""

from typing import Sequence

from shared.ai_engine.contracts import TrainingCandidate
from shared.ai_engine.families.rag.registry import build_rag_registry


def build_rag_candidates() -> Sequence[TrainingCandidate]:
    return build_rag_registry().build_all()
