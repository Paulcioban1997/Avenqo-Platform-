"""Stratégie d'exécution Deep Learning : branche le catalogue DL sur l'algorithme générique.

Utilise exactement le même `TrainEvaluateSelectStrategy` que Machine Learning : seuls
le domaine, le catalogue de modèles et les composants injectés changent.
"""

from shared.ai_engine.core.execution_domain import ExecutionDomain
from shared.ai_engine.core.generic_strategy import TrainEvaluateSelectStrategy
from shared.ai_engine.core.optimizer import HyperparameterOptimizer
from shared.ai_engine.architectures.deep_learning.evaluator import DeepLearningEvaluator
from shared.ai_engine.architectures.deep_learning.optimizer import (
    DeepLearningHyperparameterOptimizer,
)
from shared.ai_engine.architectures.deep_learning.registry import build_deep_learning_registry
from shared.ai_engine.architectures.deep_learning.trainer import DeepLearningTrainer
from shared.ai_engine.evaluation.service import EvaluationService
from shared.ai_engine.model_selection.service import ModelSelector


class DeepLearningStrategy(TrainEvaluateSelectStrategy):
    """Entraîne, évalue et sélectionne le meilleur candidat Deep Learning."""

    def __init__(
        self,
        evaluator: EvaluationService,
        selector: ModelSelector | None = None,
        optimizer: HyperparameterOptimizer | None = None,
    ) -> None:
        super().__init__(
            domain=ExecutionDomain.DEEP_LEARNING,
            candidate_registry=build_deep_learning_registry(),
            evaluator=DeepLearningEvaluator(evaluator),
            trainer=DeepLearningTrainer(),
            optimizer=optimizer or DeepLearningHyperparameterOptimizer(),
            selector=selector,
        )
