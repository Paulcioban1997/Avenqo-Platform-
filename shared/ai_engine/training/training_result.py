"""Résultat public d'un entraînement tabulaire sklearn."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from sklearn.pipeline import Pipeline

from shared.ai_engine.drift.types import ReferenceBaseline
from shared.ai_engine.explainability.types import ExplanationArtifact


@dataclass(frozen=True, slots=True)
class SupervisedTrainingResult:
    model_name: str
    pipeline: Pipeline
    best_parameters: Mapping[str, Any]
    metrics: Mapping[str, float]
    feature_importance: Mapping[str, float]
    permutation_importance: Mapping[str, float]
    numerical_columns: tuple[str, ...]
    categorical_columns: tuple[str, ...]
    model_path: Path
    preprocessor_path: Path
    baseline_metrics: Mapping[str, float] | None = None
    quality_approved: bool = True
    quality_reason: str | None = None
    explanation: ExplanationArtifact | None = None
    reference_baseline: ReferenceBaseline | None = None