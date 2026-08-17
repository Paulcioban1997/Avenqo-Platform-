"""Construit les candidats Anomaly Detection disponibles à partir du catalogue de modèles."""

from typing import Sequence

from shared.ai_engine.contracts import TrainingCandidate
from shared.ai_engine.families.anomaly.registry import build_anomaly_registry


def build_anomaly_candidates() -> Sequence[TrainingCandidate]:
    return build_anomaly_registry().build_all()
