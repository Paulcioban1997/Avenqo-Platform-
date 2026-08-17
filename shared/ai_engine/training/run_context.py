"""Informations préparées par l'AI Engine avant un entraînement."""

from dataclasses import dataclass
from typing import Any, Mapping

from shared.ai_engine.experiments import (
    DataPreparationRecord,
    DatasetSnapshot,
    ReproducibilityRecord,
    SearchMethod,
)


@dataclass(frozen=True, slots=True)
class TrainingRunContext:
    """Réunit les informations nécessaires pour tracer et rejouer un Run."""

    dataset: DatasetSnapshot
    preparation: DataPreparationRecord
    reproducibility: ReproducibilityRecord
    search_method: SearchMethod
    parameter_spaces: Mapping[str, Mapping[str, Any]]
    preprocessor_path: str | None = None