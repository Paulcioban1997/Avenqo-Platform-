from __future__ import annotations

from dataclasses import dataclass

from shared.ai_engine.contracts import BusinessStrategy


@dataclass(frozen=True, slots=True)
class PipelinePlan:
    """Plan logique unique, sans exécution ni sélection de modèle."""

    module_code: str
    task_code: str
    stages: tuple[str, ...]


class AIPipelinePlanner:
    """Transforme une stratégie métier en ordre logique d'exécution technique.

    Cette couche ne construit ni le modèle, ni les features, ni la logique de
    machine learning. Elle planifie uniquement le séquençage des étapes qui
    seront ensuite exécutées par les composants downstream.
    """

    def plan(self, strategy: BusinessStrategy) -> PipelinePlan:
        return PipelinePlan(
            module_code=strategy.module_code,
            task_code=strategy.task_code,
            stages=(
                "validate_schema",
                "validate_mapping",
                "validate_dataset_quality",
                "validate_temporal_consistency",
                "prepare_feature_engineering",
                "prepare_ai_engine",
                "prepare_model_registry",
            ),
        )
