"""AI Engine — orchestrateur unique de toutes les familles d'intelligence artificielle.

Ce module absorbe l'ancien `AutoMLService` : celui-ci ne résolvait que la famille
Machine Learning. `AIEngine` résout désormais la famille adaptée à la tâche (étape 6
du pipeline) parmi les 12 familles enregistrées, puis délègue l'entraînement,
l'évaluation et la sélection à la stratégie de cette famille. Il n'existe qu'un seul
moteur IA dans la plateforme.
"""

from typing import Sequence

from shared.ai_engine.contracts import DatasetArtifact, TrainingCandidate
from shared.ai_engine.core.execution_domain import ExecutionDomain
from shared.ai_engine.core.family_resolver import FamilyResolver, StaticFamilyResolver
from shared.ai_engine.core.registry import (
    ExecutionStrategyRegistry,
    build_default_execution_strategy_registry,
)
from shared.ai_engine.core.result import AutoMLResult
from shared.ai_engine.evaluation.service import EvaluationService
from shared.ai_engine.model_selection.service import ModelSelector

__all__ = ["AutoMLResult", "AIEngine"]


class AIEngine:
    """Point d'entrée unique de l'AI Engine.

    FastAPI et les modules métiers ne connaissent jamais Random Forest, XGBoost, CNN,
    LSTM, Transformer, GAN, GNN ou tout autre modèle concret : ils appellent uniquement
    `run(dataset, candidates)` et reçoivent le meilleur candidat déjà entraîné et évalué.
    """

    def __init__(
        self,
        evaluator: EvaluationService,
        selector: ModelSelector | None = None,
        registry: ExecutionStrategyRegistry | None = None,
        family_resolver: FamilyResolver | None = None,
    ) -> None:
        self._registry = registry or build_default_execution_strategy_registry(
            evaluator, selector
        )
        self._family_resolver = family_resolver or StaticFamilyResolver(
            ExecutionDomain.MACHINE_LEARNING
        )

    def run(
        self,
        dataset: DatasetArtifact,
        candidates: Sequence[TrainingCandidate] | None = None,
        domain: ExecutionDomain | None = None,
    ) -> AutoMLResult:
        resolved_domain = domain or self._family_resolver.resolve(dataset)
        strategy = self._registry.resolve(resolved_domain)
        return strategy.execute(dataset, candidates)
