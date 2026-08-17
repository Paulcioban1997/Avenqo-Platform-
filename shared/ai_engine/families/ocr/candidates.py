"""Construit les candidats OCR disponibles à partir du catalogue de modèles."""

from typing import Sequence

from shared.ai_engine.contracts import TrainingCandidate
from shared.ai_engine.families.ocr.registry import build_ocr_registry


def build_ocr_candidates() -> Sequence[TrainingCandidate]:
    return build_ocr_registry().build_all()
