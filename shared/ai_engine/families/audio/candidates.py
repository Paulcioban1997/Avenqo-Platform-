"""Construit les candidats Audio disponibles à partir du catalogue de modèles."""

from typing import Sequence

from shared.ai_engine.contracts import TrainingCandidate
from shared.ai_engine.families.audio.registry import build_audio_registry


def build_audio_candidates() -> Sequence[TrainingCandidate]:
    return build_audio_registry().build_all()
