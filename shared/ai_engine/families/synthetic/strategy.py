"""Stratégie d'exécution Synthetic Data : branche le catalogue Synthetic sur l'algorithme générique."""

from shared.ai_engine.core.execution_domain import ExecutionDomain
from shared.ai_engine.core.generic_strategy import TrainEvaluateSelectStrategy
from shared.ai_engine.core.optimizer import HyperparameterOptimizer
from shared.ai_engine.evaluation.service import EvaluationService
from shared.ai_engine.families.synthetic.evaluator import SyntheticDataEvaluator
from shared.ai_engine.families.synthetic.optimizer import SyntheticDataHyperparameterOptimizer
from shared.ai_engine.families.synthetic.registry import build_synthetic_registry
from shared.ai_engine.families.synthetic.trainer import SyntheticDataTrainer
from shared.ai_engine.model_selection.service import ModelSelector


class SyntheticDataStrategy(TrainEvaluateSelectStrategy):
    """Entraîne, évalue et sélectionne le meilleur candidat Synthetic Data."""

    def __init__(
        self,
        evaluator: EvaluationService,
        selector: ModelSelector | None = None,
        optimizer: HyperparameterOptimizer | None = None,
    ) -> None:
        super().__init__(
            domain=ExecutionDomain.SYNTHETIC_DATA,
            candidate_registry=build_synthetic_registry(),
            evaluator=SyntheticDataEvaluator(evaluator),
            trainer=SyntheticDataTrainer(),
            optimizer=optimizer or SyntheticDataHyperparameterOptimizer(),
            selector=selector,
        )
