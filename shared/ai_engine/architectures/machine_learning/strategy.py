"""Stratégie d'exécution Machine Learning : branche le catalogue ML sur l'algorithme générique."""

from shared.ai_engine.core.execution_domain import ExecutionDomain
from shared.ai_engine.core.generic_strategy import TrainEvaluateSelectStrategy
from shared.ai_engine.core.optimizer import HyperparameterOptimizer
from shared.ai_engine.architectures.machine_learning.evaluator import MachineLearningEvaluator
from shared.ai_engine.architectures.machine_learning.optimizer import (
    MachineLearningHyperparameterOptimizer,
)
from shared.ai_engine.architectures.machine_learning.registry import (
    build_machine_learning_registry,
)
from shared.ai_engine.architectures.machine_learning.trainer import MachineLearningTrainer
from shared.ai_engine.evaluation.service import EvaluationService
from shared.ai_engine.model_selection.service import ModelSelector


class MachineLearningStrategy(TrainEvaluateSelectStrategy):
    """Entraîne, évalue et sélectionne le meilleur candidat de Machine Learning classique."""

    def __init__(
        self,
        evaluator: EvaluationService,
        selector: ModelSelector | None = None,
        optimizer: HyperparameterOptimizer | None = None,
    ) -> None:
        super().__init__(
            domain=ExecutionDomain.MACHINE_LEARNING,
            candidate_registry=build_machine_learning_registry(),
            evaluator=MachineLearningEvaluator(evaluator),
            trainer=MachineLearningTrainer(),
            optimizer=optimizer or MachineLearningHyperparameterOptimizer(),
            selector=selector,
        )
