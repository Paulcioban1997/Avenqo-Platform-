"""Stratégie d'exécution Vision : branche le catalogue Vision sur l'algorithme générique."""

from shared.ai_engine.core.execution_domain import ExecutionDomain
from shared.ai_engine.core.generic_strategy import TrainEvaluateSelectStrategy
from shared.ai_engine.core.optimizer import HyperparameterOptimizer
from shared.ai_engine.evaluation.service import EvaluationService
from shared.ai_engine.families.vision.evaluator import VisionEvaluator
from shared.ai_engine.families.vision.optimizer import VisionHyperparameterOptimizer
from shared.ai_engine.families.vision.registry import build_vision_registry
from shared.ai_engine.families.vision.trainer import VisionTrainer
from shared.ai_engine.model_selection.service import ModelSelector


class VisionStrategy(TrainEvaluateSelectStrategy):
    """Entraîne, évalue et sélectionne le meilleur candidat Vision."""

    def __init__(
        self,
        evaluator: EvaluationService,
        selector: ModelSelector | None = None,
        optimizer: HyperparameterOptimizer | None = None,
    ) -> None:
        super().__init__(
            domain=ExecutionDomain.VISION,
            candidate_registry=build_vision_registry(),
            evaluator=VisionEvaluator(evaluator),
            trainer=VisionTrainer(),
            optimizer=optimizer or VisionHyperparameterOptimizer(),
            selector=selector,
        )
