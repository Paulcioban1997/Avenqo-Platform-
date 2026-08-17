"""Résultat d'un entraînement de forecasting — même rôle que `TrainingResult`.

Délibérément sans ``preprocessor_path``/``explanation``/``reference_baseline``
(confirmé inutilisés génériquement par `TrainingDispatcher._finalize_and_persist`/
`_complete`/`_record_version`, qui y accèdent uniquement via `getattr(..., None)`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from shared.ai_engine.training.forecasting_model import ForecastingModel


@dataclass(frozen=True, slots=True)
class ForecastingTrainingResult:
    model_name: str
    model: ForecastingModel
    best_parameters: Mapping[str, Any]
    metrics: Mapping[str, float]
    model_path: Path
    preparation_metadata: Mapping[str, Any] = field(default_factory=dict)
