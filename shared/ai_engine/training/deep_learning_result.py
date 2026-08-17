"""Résultat public d'un entraînement TensorFlow/Keras."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from shared.ai_engine.drift.types import ReferenceBaseline
from shared.ai_engine.explainability.types import ExplanationArtifact


@dataclass(frozen=True, slots=True)
class DeepLearningTrainingResult:
    model: Any
    metrics: Mapping[str, float]
    history: Mapping[str, list[float]]
    numerical_columns: tuple[str, ...]
    categorical_columns: tuple[str, ...]
    model_path: Path
    preprocessor_path: Path
    explanation: ExplanationArtifact | None = None
    reference_baseline: ReferenceBaseline | None = None